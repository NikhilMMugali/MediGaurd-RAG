import type { Metric } from "@/types";

function formatValue(value: number | string): string {
  if (typeof value === "number") return value.toLocaleString();
  return value;
}

export default function InsightMetricCard({ metric }: { metric: Metric }) {
  return (
    <div className="rounded-lg border bg-card px-3.5 py-3">
      <p className="text-xs text-muted-foreground">{metric.label}</p>
      <p className="mt-0.5 text-xl font-semibold">
        {metric.unit === "USD" && "$"}
        {formatValue(metric.value)}
        {metric.unit && metric.unit !== "USD" && <span className="ml-1 text-sm font-normal text-muted-foreground">{metric.unit}</span>}
      </p>
    </div>
  );
}
