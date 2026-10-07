import { apiRequest } from "@/api/client";
import type { DatabaseStats } from "@/types";

export function getDatabaseStats() {
  return apiRequest<DatabaseStats>("/api/admin/database/stats");
}
