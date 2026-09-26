// Where an answer came from, one chip per source, styled by kind so a report,
// an uploaded document and a web page are always visibly distinct.
import type { ChatSource } from "../types";

const CHIP_BASE = "inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium";

const KIND_STYLES: Record<ChatSource["kind"], string> = {
  report: "border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-800 dark:bg-violet-950/30 dark:text-violet-300",
  document: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/30 dark:text-sky-300",
  web: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-300",
};

const KIND_PREFIX: Record<ChatSource["kind"], string> = {
  report: "Report",
  document: "Doc",
  web: "Web",
};

function KindIcon({ kind }: { kind: ChatSource["kind"] }) {
  if (kind === "web") {
    return (
      <svg className="shrink-0" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3a14 14 0 010 18M12 3a14 14 0 000 18" />
      </svg>
    );
  }
  return (
    <svg className="shrink-0" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}

// Web source URLs come from a search provider's response, so only plain
// http(s) links are ever rendered as clickable -- never javascript: or data:.
export function isSafeHttpUrl(value: string | null): value is string {
  if (!value) return false;
  try {
    const protocol = new URL(value).protocol;
    return protocol === "https:" || protocol === "http:";
  } catch {
    return false;
  }
}

export default function ChatSourceChips({ sources }: { sources: ChatSource[] }) {
  if (sources.length === 0) return null;

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {sources.map((source, index) => {
        const content = (
          <>
            <KindIcon kind={source.kind} />
            <span className="truncate">
              {source.kind === "report" ? source.label : `${KIND_PREFIX[source.kind]} · ${source.label}`}
            </span>
          </>
        );
        const key = `${source.kind}-${source.id ?? source.url ?? index}`;

        if (source.kind === "web" && isSafeHttpUrl(source.url)) {
          return (
            <a
              key={key}
              href={source.url}
              target="_blank"
              rel="noreferrer"
              title={source.label}
              className={`${CHIP_BASE} ${KIND_STYLES.web} transition hover:brightness-95`}
            >
              {content}
            </a>
          );
        }
        return (
          <span key={key} title={source.label} className={`${CHIP_BASE} ${KIND_STYLES[source.kind]}`}>
            {content}
          </span>
        );
      })}
    </div>
  );
}
