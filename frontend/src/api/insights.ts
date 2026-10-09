import { apiRequest } from "@/api/client";
import type { InsightsOverviewResponse, InsightsQueryResponse } from "@/types";

export function getInsightsOverview() {
  return apiRequest<InsightsOverviewResponse>("/api/insights/overview");
}

export function queryInsights(question: string) {
  return apiRequest<InsightsQueryResponse>("/api/insights/query", {
    method: "POST",
    body: { question },
  });
}
