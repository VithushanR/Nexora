const STYLES: Record<string, string> = {
  INCLUDE: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  EXCLUDE: "bg-rose-50 text-rose-700 ring-rose-200",
  UNCERTAIN: "bg-amber-50 text-amber-700 ring-amber-200",
};

export default function VerdictBadge({ verdict }: { verdict: string }) {
  const cls = STYLES[verdict] ?? "bg-slate-100 text-slate-600 ring-slate-200";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}
    >
      {verdict}
    </span>
  );
}