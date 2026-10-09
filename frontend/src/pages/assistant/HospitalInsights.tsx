import * as React from "react";
import { BarChart3, ShieldAlert } from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import { CAN_VIEW_INSIGHTS } from "@/lib/roles";
import { getInsightsOverview } from "@/api/insights";
import { ApiError } from "@/api/client";
import type { InsightsOverviewResponse } from "@/types";
import InsightMetricCard from "@/components/insights/InsightMetricCard";
import InsightChart from "@/components/insights/InsightChart";
import AIInsightSummary from "@/components/insights/AIInsightSummary";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/StateViews";

export default function HospitalInsights() {
  const { user } = useAuth();
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
    // Skip the call entirely for a role that can't use this page — the
    // server would 403 it anyway (app.api.insights — admin-only), but
    // there's no reason to even make the request.
    if (user && CAN_VIEW_INSIGHTS.includes(user.role)) load();
  }, [load, user]);

  if (!user) return null;

  if (!CAN_VIEW_INSIGHTS.includes(user.role)) {
    return (
      <div className="p-6">
        <EmptyState
          icon={ShieldAlert}
          title="Hospital Insights is admin-only"
          description="This view is limited to administrators."
        />
      </div>
    );
  }

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
