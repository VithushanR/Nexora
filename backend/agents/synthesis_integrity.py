"""
Agent 3 -- Synthesis & Integrity

Node signature matches the LangGraph pattern used across the pipeline:

    async def synthesis_integrity_node(state: ResearchState) -> dict:
        ...
        return {"evidence_table": ..., "contradictions": ...,
                "contradictions_status": ...}

State ownership: this node writes evidence_table, contradictions and
contradictions_status, and nothing else. It must not read or write `gaps`
-- Agent 4 runs as a genuinely independent branch off the same
selected_papers, and the two only meet again at report assembly.

Pipeline (per the Agent Build Reference):
  1. Full text -- seven-strategy cascade per paper (sources/fulltext.py),
     with a title-match guard so a mis-fetched PDF is discarded rather
     than summarised as if it were the right paper.
  2. Section split -- heading detection over the fetched text. No LLM call.
  3. Evidence row -- LLM summaries of methodology and results. Papers with
     no full text fall back to abstract-derived summaries and are TAGGED
     as such, so a thin row is never displayed as if it were a rich one.
  4. Integrity -- Crossref retraction lookup per DOI. A failed lookup is
     recorded as "unknown", never as clean (see sources/crossref.py).
  5. Contradiction shortlist -- pairwise embedding similarity over the
     results summaries. Free, deterministic, no LLM call.
  6. Contradiction confirmation -- one LLM call per shortlisted pair.
     Topical similarity alone is not a contradiction; a pair the model
     declines to confirm is discarded rather than forced through.

Empty vs. broken is a distinction this agent takes seriously.
`contradictions_status` always says which one happened: "no contradictions
were found among these papers" and "the analysis could not be run" are
both legitimate outcomes, and reporting the second as the first would be
the single most misleading thing this agent could do.
"""

import os
import re
import asyncio
import logging
from typing import Optional

import httpx

from backend.llm import client as llm_client
from backend.llm.client import llm_json_call
from backend.llm.embeddings import (
    embed, cosine_similarity_matrix, EmbeddingUnavailableError,
)
from backend.sources.crossref import check_retraction
from backend.sources.fulltext import get_full_text
from backend.graph.state import ResearchState, Candidate

logger = logging.getLogger("nexora.agent3")

# ------------------------------------------------------------------
# Consumer contract with report_assembly.py
# ------------------------------------------------------------------
# report_assembly.py (Agent 4's owner, already on main) reads specific key
# names off our rows, and reads NOTHING else -- render_evidence_table()
# takes row["method"] / row["finding"], render_contradictions() takes
# item["summary"], and chunk_report() indexes those same keys for the
# Copilot chat. A key it doesn't find renders as an em dash, silently:
# no crash, just a table of blanks and an empty search index.
#
# So we emit those names alongside our own more descriptive ones. The
# duplication is deliberate -- our names say what the field actually is
# (a methodology summary, not a "method"), and the frontend's
# EvidenceTable/ContradictionCard components can use the richer set,
# while report_assembly keeps working untouched.
#
# The tests at the bottom of test_synthesis_integrity.py assert against
# the real report_assembly functions, so if either side renames a key the
# suite fails instead of the report quietly going blank.
CONSUMER_ROW_KEYS = ("title", "method", "finding")
CONSUMER_CONTRADICTION_KEYS = ("summary",)

SECTION_WINDOW_CHARS = 6000
SUMMARY_INPUT_CHARS = 5000
PAPER_CONCURRENCY = int(os.getenv("SYNTHESIS_PAPER_CONCURRENCY", "4"))
CONTRADICTION_SIMILARITY_THRESHOLD = float(os.getenv("CONTRADICTION_SIMILARITY_THRESHOLD", "0.55"))
MAX_CONTRADICTION_PAIRS = int(os.getenv("MAX_CONTRADICTION_PAIRS", "20"))
PAIR_CONCURRENCY = int(os.getenv("CONTRADICTION_PAIR_CONCURRENCY", "4"))


# ------------------------------------------------------------------
# Prompts
# ------------------------------------------------------------------

EVIDENCE_SYSTEM_PROMPT = """You summarize research paper sections for an evidence table.
You will be given the paper's TITLE and a chunk of TEXT extracted automatically from its PDF or XML.

IMPORTANT: extraction is unreliable and sometimes grabs the WRONG content. Before summarizing,
check whether the TEXT is plausibly ABOUT THE SAME SUBJECT MATTER as the TITLE. If it describes
a clearly different method, dataset, or topic, it is almost certainly misextracted -- set
text_looked_valid to false. Fluent text is not evidence it's the right text.

Prefer concrete detail: architectures, datasets, sample sizes, metrics and their values.
Never invent detail that is not present in the TEXT.

Respond ONLY with valid JSON, no markdown fences:
{"summary": "your summary here", "text_looked_valid": true or false}"""

CONTRADICTION_PAIR_SYSTEM_PROMPT = """You are checking whether two research papers genuinely CONTRADICT each other.

A contradiction means the two papers make specific claims that cannot both be true: opposite
directions of effect, incompatible performance rankings between the same methods, or one
reporting a result the other explicitly rules out.

The following are NOT contradictions:
- covering different sub-topics, datasets, tasks or populations
- using different methods without comparing them
- one reporting a result the other simply does not discuss
- differing amounts of detail

The two papers below were shortlisted only because their results summaries are TOPICALLY
SIMILAR. Topical similarity is not disagreement. If they do not genuinely conflict, say so --
returning false is the expected answer most of the time and is not a failure.

Respond ONLY with valid JSON, no markdown fences:
{"is_contradiction": true or false,
 "description": "one sentence naming the specific conflict, or why there is none",
 "paper_a_claim": "the exact conflicting claim from paper A, or empty string",
 "paper_b_claim": "the exact conflicting claim from paper B, or empty string"}"""


# ------------------------------------------------------------------
# Step 2: section splitting (deterministic, no LLM)
# ------------------------------------------------------------------

# Deliberately wide. Real papers head their methodology section a dozen
# different ways -- "Attention Is All You Need" calls it "Model
# Architecture", clinical papers call it "Materials and Methods", and an
# empty methodology summary is a silent quality loss rather than a visible
# error, so the cost of a missing keyword is higher than the cost of an
# occasional over-match. _looks_like_heading() does the narrowing: a match
# only counts on a short standalone line, equal to or prefixed by the
# keyword, never as a substring of running prose.
SECTION_KEYWORDS = {
    "methodology": ["method", "methods", "methodology", "materials and methods",
                    "material and methods", "methods and materials", "approach",
                    "proposed approach", "proposed method", "proposed methodology",
                    "model", "models", "model architecture", "architecture",
                    "proposed model", "network architecture", "system design",
                    "framework", "proposed framework", "implementation",
                    "experimental setup", "experimental design", "study design",
                    "data and methods", "datasets and methods"],
    "results": ["results", "result", "experiment", "experiments", "evaluation",
                "experimental results", "results and discussion", "experiments and results",
                "findings", "empirical results", "performance", "evaluation results",
                "experiments and analysis"],
    "discussion": ["discussion", "conclusion", "conclusions", "future work",
                   "limitations", "limitation", "conclusion and future work",
                   "discussion and conclusion", "concluding remarks"],
}


def _looks_like_heading(line: str, keywords: list[str]) -> bool:
    """A heading is short, standalone, and (after stripping any leading
    numbering like "3." or "IV)") equals or starts with a section keyword.
    Requiring equality-or-prefix rather than substring matching keeps
    'we describe our method below' from being read as a heading."""
    stripped = line.strip().strip(":.").strip()
    if not (0 < len(stripped) < 70):
        return False
    cleaned = re.sub(r"^[\dIVXivx]+[\.\)\-\s]+", "", stripped).strip().lower()
    return any(cleaned == kw or cleaned.startswith(kw + " ") for kw in keywords)


def split_sections(full_text: Optional[str], window_chars: int = SECTION_WINDOW_CHARS) -> dict[str, str]:
    """Returns {section_name: text} for methodology/results/discussion.

    Takes a fixed window after each detected heading rather than slicing to
    the next heading: papers vary too much in structure for reliable
    end-boundary detection, and an over-long window costs a few wasted
    tokens whereas a wrong boundary costs the wrong content entirely.
    """
    if not full_text:
        return {}

    lines = full_text.split("\n")
    line_starts: list[tuple[int, str]] = []
    offset = 0
    for line in lines:
        line_starts.append((offset, line))
        offset += len(line) + 1

    sections: dict[str, str] = {}
    for section_name, keywords in SECTION_KEYWORDS.items():
        found_offset = None
        for off, line in line_starts:
            if _looks_like_heading(line, keywords):
                found_offset = off + len(line) + 1
                break
        sections[section_name] = (
            full_text[found_offset:found_offset + window_chars].strip()
            if found_offset is not None else ""
        )
    return sections


# ------------------------------------------------------------------
# Step 3: LLM summaries
# ------------------------------------------------------------------

def _system_note(text: str) -> str:
    """Wraps a processing note so downstream renderers can tell it apart
    from a real summary. The report renderer italicises and greys anything
    parenthesised, and is_system_note() below is what the contradiction
    stage uses to exclude non-content rows."""
    return f"({text})"


def is_system_note(text: Optional[str]) -> bool:
    s = (text or "").strip()
    return s.startswith("(") and s.endswith(")")


async def summarize_section(label: str, text: str, paper_title: str = "") -> str:
    """One LLM call. Returns either a summary or a parenthesised system
    note explaining why there isn't one -- never a silently empty string,
    and never a fabricated summary standing in for a failed call."""
    if not text or not text.strip():
        return _system_note(f"No {label} section available in source text.")

    result = await llm_json_call(
        EVIDENCE_SYSTEM_PROMPT,
        f"PAPER TITLE: {paper_title}\n\nSECTION TYPE: {label}\n\nTEXT:\n{text[:SUMMARY_INPUT_CHARS]}",
        debug_label=f"{paper_title[:40]} / {label}",
    )

    if result is None:
        return _system_note(f"Could not summarize {label} -- model output was unparseable.")
    if result.get("_budget_exhausted"):
        return _system_note(f"LLM budget/quota exhausted -- {label} not summarized this run.")
    if result.get("_blocked_or_empty"):
        return _system_note(f"Model returned an empty response for {label} -- likely a safety filter.")
    if result.get("text_looked_valid") is False:
        return _system_note(
            f"Extracted text for {label} did not look like it belonged to this paper -- "
            f"discarded rather than summarized."
        )

    summary = (result.get("summary") or "").strip()
    return summary or _system_note(f"No summary returned for {label}.")


# ------------------------------------------------------------------
# Steps 1-4: one evidence row per paper
# ------------------------------------------------------------------

async def integrity_check(client: httpx.AsyncClient, paper: Candidate) -> dict:
    """Retraction status for one paper.

    An arXiv paper with no registered DOI is short-circuited rather than
    guessed at: arXiv's 10.48550/arXiv.* DOIs are registered with DataCite,
    not Crossref, so synthesising one only produces a 404 and a misleading
    "lookup failed" note. Reporting the real reason is more useful than
    pretending we tried the right index.
    """
    doi = paper.get("doi")
    if doi:
        return await check_retraction(client, doi)

    if paper.get("arxiv_id"):
        return {
            "retracted": None, "status": "unknown",
            "note": ("arXiv preprint with no registered DOI -- Crossref does not index arXiv, "
                     "so retraction status could not be verified."),
        }

    return await check_retraction(client, None)


async def build_evidence_row(client: httpx.AsyncClient, paper: Candidate) -> dict:
    title = paper.get("title") or "(untitled)"
    abstract = paper.get("abstract") or ""

    full_text, strategy = await get_full_text(client, dict(paper))
    full_text_available = full_text is not None

    abstract_summary = await summarize_section("abstract", abstract, title)

    if full_text_available:
        sections = split_sections(full_text)
        methodology_summary = await summarize_section("methodology", sections.get("methodology", ""), title)
        results_summary = await summarize_section("results", sections.get("results", ""), title)
        summary_source = f"full_text ({strategy})"
    else:
        # Honest degradation: an abstract can usually support a rough
        # methodology sketch, but results detail genuinely is not in there,
        # and inventing one from an abstract is exactly the failure mode
        # this whole pipeline exists to avoid.
        methodology_summary = await summarize_section(
            "methodology (from abstract only)", abstract, title)
        results_summary = _system_note(
            "Full text unavailable -- results are not separately extractable from the abstract.")
        summary_source = "abstract_fallback"

    retraction = await integrity_check(client, paper)

    return {
        "title": title,
        "doi": paper.get("doi") or "(none)",
        "year": paper.get("year"),
        "source": paper.get("source"),
        "full_text_available": full_text_available,
        "full_text_strategy": strategy or "(none)",
        "summary_source": summary_source,
        "abstract_summary": abstract_summary,
        "methodology_summary": methodology_summary,
        "results_summary": results_summary,
        # Consumer contract -- see CONSUMER_ROW_KEYS below. Same values as
        # the two fields above, under the names report_assembly.py reads.
        "method": methodology_summary,
        "finding": results_summary,
        "retracted": retraction["retracted"],
        "retraction_status": retraction["status"],
        "retraction_note": retraction["note"],
    }


def _failed_row(paper: Candidate, error: Exception) -> dict:
    """A row that survives its own failure. The user explicitly selected
    this paper, so dropping it would silently shrink the evidence base they
    chose; the row stays, visibly marked as unprocessed."""
    return {
        "title": paper.get("title") or "(untitled)",
        "doi": paper.get("doi") or "(none)",
        "year": paper.get("year"),
        "source": paper.get("source"),
        "full_text_available": False,
        "full_text_strategy": "(none)",
        "summary_source": "error",
        "abstract_summary": _system_note(f"Processing failed: {type(error).__name__}."),
        "methodology_summary": _system_note("Processing failed for this paper."),
        "results_summary": _system_note("Processing failed for this paper."),
        "method": _system_note("Processing failed for this paper."),
        "finding": _system_note("Processing failed for this paper."),
        "retracted": None,
        "retraction_status": "unknown",
        "retraction_note": "Not checked -- processing failed before the integrity lookup.",
    }


async def build_evidence_table(selected_papers: list[Candidate],
                               concurrency: int = PAPER_CONCURRENCY) -> list[dict]:
    """Bounded concurrency, not full fan-out: each paper costs up to seven
    HTTP fetches plus three LLM calls, so 20 papers unleashed at once would
    breach both the source rate limits and the Gemini quota.

    Row order mirrors the user's selection order, which is what the report
    and the citation indices downstream assume.
    """
    if not selected_papers:
        return []

    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient() as client:
        async def _one(index: int, paper: Candidate) -> tuple[int, dict]:
            async with semaphore:
                try:
                    return index, await build_evidence_row(client, paper)
                except Exception as e:
                    logger.exception("Evidence row failed for %r", (paper.get("title") or "")[:60])
                    return index, _failed_row(paper, e)

        results = await asyncio.gather(*(_one(i, p) for i, p in enumerate(selected_papers)))

    return [row for _, row in sorted(results, key=lambda pair: pair[0])]


# ------------------------------------------------------------------
# Step 5: contradiction shortlist (deterministic, no LLM)
# ------------------------------------------------------------------

def comparable_row_indices(evidence_table: list[dict]) -> list[int]:
    """Rows whose results summary is real content, not a system note.
    Comparing two "(full text unavailable)" placeholders would produce
    spurious pairs with high similarity and zero meaning."""
    return [i for i, row in enumerate(evidence_table)
            if not is_system_note(row.get("results_summary"))]


async def shortlist_contradiction_pairs(
    evidence_table: list[dict],
    threshold: float = CONTRADICTION_SIMILARITY_THRESHOLD,
    max_pairs: int = MAX_CONTRADICTION_PAIRS,
) -> list[tuple[int, int, float]]:
    """Embeds each comparable results summary and returns (i, j, similarity)
    for pairs above `threshold`, strongest first, capped at `max_pairs`.

    This is the cost control for the whole stage: confirming every pair of
    20 papers would be 190 LLM calls, whereas embedding is free and
    discards the overwhelming majority of them before a single call.
    """
    indices = comparable_row_indices(evidence_table)
    if len(indices) < 2:
        return []

    summaries = [evidence_table[i]["results_summary"] for i in indices]
    vectors = await embed(summaries)
    similarity = cosine_similarity_matrix(vectors)

    pairs: list[tuple[int, int, float]] = []
    for a in range(len(indices)):
        for b in range(a + 1, len(indices)):
            score = float(similarity[a][b])
            if score >= threshold:
                pairs.append((indices[a], indices[b], score))

    pairs.sort(key=lambda p: p[2], reverse=True)
    return pairs[:max_pairs]


# ------------------------------------------------------------------
# Step 6: contradiction confirmation (one LLM call per shortlisted pair)
# ------------------------------------------------------------------

def _pair_prompt(row_a: dict, row_b: dict) -> str:
    return f"""PAPER A: {row_a['title']}
(summary source: {row_a['summary_source']})
Methodology: {row_a['methodology_summary']}
Results: {row_a['results_summary']}

PAPER B: {row_b['title']}
(summary source: {row_b['summary_source']})
Methodology: {row_b['methodology_summary']}
Results: {row_b['results_summary']}"""


def _contradiction_summary(description: str, row_a: dict, claim_a: str,
                           row_b: dict, claim_b: str) -> str:
    """One self-contained sentence describing the conflict.

    Must stand alone: report_assembly.py renders ONLY this field and feeds
    ONLY this field to the Copilot chat index, so anything left out of it
    is invisible downstream no matter how good the structured fields are.
    """
    parts = [description.strip()] if description.strip() else []
    if claim_a.strip():
        parts.append(f'"{row_a["title"]}" claims: {claim_a.strip()}')
    if claim_b.strip():
        parts.append(f'"{row_b["title"]}" claims: {claim_b.strip()}')
    if not parts:
        parts.append(f'"{row_a["title"]}" and "{row_b["title"]}" report conflicting results.')
    return " — ".join(parts)


async def confirm_contradiction(row_a: dict, row_b: dict, similarity: float) -> Optional[dict]:
    """Returns a contradiction record, or None if the pair does not
    genuinely conflict or could not be checked. None is the common,
    expected answer -- most topically similar papers simply agree."""
    result = await llm_json_call(
        CONTRADICTION_PAIR_SYSTEM_PROMPT,
        _pair_prompt(row_a, row_b),
        debug_label=f"contradiction: {row_a['title'][:30]} vs {row_b['title'][:30]}",
    )

    if result is None or result.get("_budget_exhausted") or result.get("_blocked_or_empty"):
        return None
    if result.get("is_contradiction") is not True:
        return None

    description = result.get("description", "")
    claim_a = result.get("paper_a_claim", "")
    claim_b = result.get("paper_b_claim", "")

    return {
        "description": description,
        "paper_a_title": row_a["title"],
        "paper_a_claim": claim_a,
        "paper_b_title": row_b["title"],
        "paper_b_claim": claim_b,
        "shortlist_similarity": round(similarity, 4),
        # Consumer contract -- see CONSUMER_CONTRADICTION_KEYS below.
        "summary": _contradiction_summary(description, row_a, claim_a, row_b, claim_b),
    }


def _status(code: str, message: str, is_error: bool = False, **extra) -> dict:
    return {"code": code, "is_error": is_error, "message": message, **extra}


async def detect_contradictions(evidence_table: list[dict]) -> tuple[list[dict], dict]:
    """Returns (contradictions, status). An empty list is only ever
    reported as a finding when the analysis actually ran to completion;
    every failure path sets is_error=True and says what broke."""
    if len(evidence_table) < 2:
        return [], _status(
            "too_few_papers",
            "Fewer than two papers were analysed, so no comparison was possible.",
        )

    comparable = comparable_row_indices(evidence_table)
    abstract_only = sum(1 for r in evidence_table if not r.get("full_text_available"))

    if len(comparable) < 2:
        return [], _status(
            "no_comparable_summaries",
            f"Only {len(comparable)} of {len(evidence_table)} papers produced usable results "
            f"summaries, so there was nothing to compare. Contradiction analysis needs at "
            f"least two papers with real results content.",
        )

    try:
        pairs = await shortlist_contradiction_pairs(evidence_table)
    except EmbeddingUnavailableError as e:
        logger.error("Contradiction shortlisting unavailable: %s", e)
        return [], _status(
            "embedding_unavailable",
            "Contradiction analysis could not be completed: the embedding model could not be "
            "loaded, so plausible pairs were never shortlisted. This is a processing failure, "
            "not a finding.",
            is_error=True,
        )

    if not pairs:
        return [], _status(
            "none_shortlisted",
            f"All {len(comparable)} comparable papers were compared and none discussed "
            f"sufficiently overlapping results to be candidates for disagreement -- they "
            f"address largely complementary methods and datasets.",
            shortlisted_pairs=0,
        )

    # If the LLM budget died during evidence building, every confirmation
    # call below would short-circuit and we would report a clean "nothing
    # confirmed" that is really "nothing was checked". Catch it up front.
    if llm_client.LLM_BUDGET_EXHAUSTED:
        return [], _status(
            "llm_budget_exhausted",
            f"{len(pairs)} plausible pair(s) were shortlisted but none could be checked: the "
            f"LLM quota was exhausted. This is a processing failure, not a finding.",
            is_error=True, shortlisted_pairs=len(pairs),
        )

    semaphore = asyncio.Semaphore(PAIR_CONCURRENCY)

    async def _confirm(pair: tuple[int, int, float]) -> Optional[dict]:
        i, j, score = pair
        async with semaphore:
            return await confirm_contradiction(evidence_table[i], evidence_table[j], score)

    confirmed = [c for c in await asyncio.gather(*(_confirm(p) for p in pairs)) if c is not None]

    if llm_client.LLM_BUDGET_EXHAUSTED and not confirmed:
        return [], _status(
            "llm_budget_exhausted",
            f"Contradiction analysis was cut short: the LLM quota was exhausted partway "
            f"through checking {len(pairs)} shortlisted pair(s). This is a processing "
            f"failure, not a finding.",
            is_error=True, shortlisted_pairs=len(pairs),
        )

    if confirmed:
        return confirmed, _status(
            "ok",
            f"{len(confirmed)} contradiction(s) confirmed from {len(pairs)} shortlisted pair(s).",
            shortlisted_pairs=len(pairs),
        )

    caveat = ""
    if abstract_only:
        caveat = (f" Note that {abstract_only} of {len(evidence_table)} papers were analysed "
                  f"from abstracts only, which limits how much detail was available to compare.")
    return [], _status(
        "none_confirmed",
        f"{len(pairs)} pair(s) were similar enough to check, but on inspection none made "
        f"genuinely conflicting claims -- they overlap in topic rather than disagree." + caveat,
        shortlisted_pairs=len(pairs),
    )


# ------------------------------------------------------------------
# Orchestration + LangGraph node
# ------------------------------------------------------------------

async def run_synthesis_and_integrity(selected_papers: list[Candidate]) -> dict:
    logger.info("Agent 3: building evidence table for %d selected paper(s)", len(selected_papers))
    evidence_table = await build_evidence_table(selected_papers)

    with_full_text = sum(1 for r in evidence_table if r.get("full_text_available"))
    retracted = sum(1 for r in evidence_table if r.get("retracted") is True)
    unverified = sum(1 for r in evidence_table if r.get("retraction_status") == "unknown")
    logger.info("Evidence table: %d rows, %d with full text, %d retracted, %d unverified",
                len(evidence_table), with_full_text, retracted, unverified)

    contradictions, status = await detect_contradictions(evidence_table)
    logger.info("Contradictions: %d [%s]", len(contradictions), status["code"])

    return {
        "evidence_table": evidence_table,
        "contradictions": contradictions,
        "contradictions_status": status,
    }


async def synthesis_integrity_node(state: ResearchState) -> dict:
    """LangGraph node. Writes only evidence_table, contradictions and
    contradictions_status, per the state-ownership rule -- Agent 3 must not
    touch protocol, candidates, or anything Agent 4 owns."""
    selected_papers = state.get("selected_papers")
    if not selected_papers:
        # A real guard, not a type-checker workaround: an empty selection
        # means the human checkpoint hasn't run, or the user selected
        # nothing. Fail clearly here rather than silently emitting an empty
        # evidence table that reads downstream as "we found nothing".
        raise ValueError(
            "synthesis_integrity_node requires a non-empty state['selected_papers'] -- "
            "the human selection checkpoint must run before Agent 3."
        )
    return await run_synthesis_and_integrity(selected_papers)
