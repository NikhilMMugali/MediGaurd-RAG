import { apiRequest } from "@/api/client";
import type { DatabaseStats, RecentActivity } from "@/types";

export function getDatabaseStats() {
  return apiRequest<DatabaseStats>("/api/admin/database/stats");
}

export function getRecentActivity() {
  return apiRequest<RecentActivity>("/api/admin/activity");
}
