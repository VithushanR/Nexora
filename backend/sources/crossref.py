"""
Crossref API client.

Responsibility:
- Retraction / correction lookup for Agent 3's integrity check.

Which field actually carries a retraction
-----------------------------------------
Crossref models retraction as a relation between two records, and the
direction matters:

  * On the RETRACTION NOTICE, `update-to` points back at the paper it
    retracts.
  * On the ORIGINAL PAPER, `updated-by` points forward at the notice.

Agent 3 always looks up the original paper, so `updated-by` is the field
that matters, and checking only `update-to` silently misses real
retractions. Verified against the live API: the Wakefield 1998 Lancet
paper (10.1016/S0140-6736(97)11096-0) carries its retraction solely in
`updated-by`, while Mehra 2020 (10.1016/S0140-6736(20)31180-6) happens to
carry one in `update-to`. Both are checked, plus the "RETRACTED:" title
prefix publishers add, since no single signal is reliable alone.

Honest-unknown contract
-----------------------
A failed lookup is NEVER reported as "not retracted". Crossref being
unreachable, or simply not indexing a work, tells us nothing about the
paper, and defaulting to clean would launder an unverified claim into the
evidence table. `retracted` is therefore tri-state:

    True  -> Crossref records a retraction for this work
    False -> Crossref answered and recorded none
    None  -> could not verify (no DOI, no record, lookup failed)
"""

import logging
from typing import Optional, TypedDict

import httpx

from backend.sources.base import (
    CONTACT_EMAIL, DEFAULT_HEADERS, DEFAULT_TIMEOUT, RATE_LIMITS, retryable,
)

logger = logging.getLogger("nexora.sources.crossref")

BASE_URL = "https://api.crossref.org/works"

# Relation types meaning the work should no longer be relied upon.
# "correction" and "expression_of_concern" are deliberately excluded --
# they are genuine integrity signals but they are not retractions, and
# conflating them would overstate the flag.
RETRACTION_TYPES = {"retraction", "withdrawal", "removal"}

TITLE_PREFIXES = ("retracted", "withdrawn")


class RetractionStatus(TypedDict):
    retracted: Optional[bool]
    status: str          # "retracted" | "clean" | "unknown"
    note: str


def _unknown(note: str) -> RetractionStatus:
    return {"retracted": None, "status": "unknown", "note": note}


async def _fetch_work(client: httpx.AsyncClient, doi: str) -> Optional[dict]:
    """Returns the Crossref `message` object, or None if Crossref has no
    record for this DOI.

    Deliberately not routed through base.get_json: a 404 here is a
    meaningful answer ("not indexed"), not a transient failure, and
    get_json's retry policy would burn three requests on every arXiv
    preprint and unregistered DOI before giving up. 5xx and timeouts still
    retry through the shared policy.
    """
    @retryable()
    async def _do() -> Optional[dict]:
        async with RATE_LIMITS["crossref"]:
            r = await client.get(f"{BASE_URL}/{doi}", headers=DEFAULT_HEADERS,
                                 timeout=DEFAULT_TIMEOUT, params={"mailto": CONTACT_EMAIL})
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return (r.json() or {}).get("message") or {}

    return await _do()


def _has_retraction_relation(message: dict) -> bool:
    for field in ("updated-by", "update-to"):
        for update in message.get(field) or []:
            if (update.get("type") or "").lower().replace("-", "_") in RETRACTION_TYPES:
                return True
    return False


def _title_marked_retracted(message: dict) -> bool:
    """Publishers prefix the title with "RETRACTED:" / "WITHDRAWN:". A
    weaker signal than the relation fields, but it catches records where
    the relation has not propagated yet."""
    titles = message.get("title") or []
    return any((t or "").strip().lower().startswith(TITLE_PREFIXES) for t in titles)


async def check_retraction(client: httpx.AsyncClient, doi: Optional[str]) -> RetractionStatus:
    """Looks up `doi` and reports whether Crossref records a retraction."""
    if not doi:
        return _unknown("No DOI on this paper -- retraction status could not be verified.")

    try:
        message = await _fetch_work(client, doi)
    except Exception as e:
        logger.warning("Crossref lookup failed for %s: %s", doi, e)
        return _unknown("Crossref lookup failed -- retraction status could not be verified.")

    if message is None:
        return _unknown(f"Crossref has no record for {doi} -- retraction status "
                        f"could not be verified.")

    by_relation = _has_retraction_relation(message)
    by_title = _title_marked_retracted(message)

    if by_relation or by_title:
        evidence = "a retraction relation" if by_relation else "a 'RETRACTED' title prefix"
        return {"retracted": True, "status": "retracted",
                "note": f"Crossref records {evidence} for this DOI."}

    return {"retracted": False, "status": "clean",
            "note": "Checked against Crossref -- no retraction recorded."}


async def search(client: httpx.AsyncClient, query: str) -> list[dict]:
    """Not implemented on purpose. Crossref is not one of Agent 2's
    retrieval sources (see SOURCE_CLIENTS in agents/retrieval_screening.py)
    -- it is used here only for integrity lookups. Implement this if
    Crossref is ever promoted to a retrieval source."""
    raise NotImplementedError("Crossref is an integrity-check source, not a retrieval source.")
