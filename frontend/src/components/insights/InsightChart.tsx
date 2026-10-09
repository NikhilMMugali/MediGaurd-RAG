import type { Breakdown } from "@/types";

// A plain horizontal bar list rather than a charting library — the data here
// is a handful of categories at most, and CSS bars render it clearly without
// pulling in a dependency the rest of the stack doesn't otherwise need
// (section 6E "avoid a heavy charting library when the existing stack can
// handle it simply").
export default function InsightChart({ breakdown }: { breakdown: Breakdown }) {
  const max = Math.max(1, ...breakdown.items.map(([, count]) => count));

  return (
    <div className="rounded-lg border bg-card p-3.5">
      <p className="mb-2.5 text-xs font-medium text-muted-foreground">{breakdown.label}</p>
      <ul className="flex flex-col gap-2" role="list" aria-label={breakdown.label}>
        {breakdown.items.map(([label, count]) => (
          <li key={label} className="flex items-center gap-2.5 text-xs" aria-label={`${label}: ${count}`}>
            <span className="w-28 shrink-0 truncate text-muted-foreground">{label}</span>
            <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary" style={{ width: `${(count / max) * 100}%` }} />
            </div>
            <span className="w-8 shrink-0 text-right font-medium">{count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
