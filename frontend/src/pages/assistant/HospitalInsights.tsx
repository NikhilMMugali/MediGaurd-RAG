import * as React from "react";
import { BarChart3 } from "lucide-react";
import { getInsightsOverview } from "@/api/insights";
import { ApiError } from "@/api/client";
import type { InsightsOverviewResponse } from "@/types";
import InsightMetricCard from "@/components/insights/InsightMetricCard";
import InsightChart from "@/components/insights/InsightChart";
import AIInsightSummary from "@/components/insights/AIInsightSummary";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/StateViews";

export default function HospitalInsights() {
  const [overview, setOverview] = React.useState<InsightsOverviewResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setOverview(null);
    setError(null);
    getInsightsOverview()
      .then(setOverview)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load hospital insights."));
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto p-6">
      <div>
        <h1 className="text-lg font-semibold">Hospital Insights</h1>
        <p className="text-sm text-muted-foreground">
          {overview ? `${overview.role} · ${overview.period}` : "Role-aware metrics computed from authorized records."}
        </p>
      </div>

      {overview === null && !error && <LoadingState label="Computing authorized metrics..." />}
      {error && <ErrorState message={error} onRetry={load} />}

      {overview && overview.metrics.length === 0 && (
        <EmptyState icon={BarChart3} title="No data available" description={overview.note ?? "No authorized metrics could be computed."} />
      )}

      {overview && overview.metrics.length > 0 && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {overview.metrics.map((m) => (
              <InsightMetricCard key={m.key} metric={m} />
            ))}
          </div>

          {overview.breakdown && <InsightChart breakdown={overview.breakdown} />}

          <AIInsightSummary />
        </>
      )}
    </div>
  );
}
