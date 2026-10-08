import * as React from "react";
import { getDatabaseStats, getRecentActivity } from "@/api/admin";
import type { DatabaseStats, RecentActivity } from "@/types";

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function AdminStatsBar() {
  const [stats, setStats] = React.useState<DatabaseStats | null>(null);
  const [activity, setActivity] = React.useState<RecentActivity | null>(null);

  React.useEffect(() => {
    getDatabaseStats().then(setStats).catch(() => setStats(null));
    getRecentActivity().then(setActivity).catch(() => setActivity(null));
  }, []);

  if (!stats) return null;

  const items: [string, number][] = [
    ["Patients", stats.patients],
    ["Knowledge", stats.knowledge_records],
    ["Documents", stats.documents],
    ["Vectors", stats.vectors],
  ];

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {items.map(([label, value]) => (
          <div key={label} className="rounded-lg border bg-card px-3 py-2">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="text-lg font-semibold">{value.toLocaleString()}</p>
          </div>
        ))}
      </div>

      {activity && (activity.recent_uploads.length > 0 || activity.recent_security_events.length > 0) && (
        <div className="grid gap-3 sm:grid-cols-2">
          {activity.recent_uploads.length > 0 && (
            <div className="rounded-lg border bg-card px-3 py-2">
              <p className="mb-1.5 text-xs font-medium text-muted-foreground">Recent uploads</p>
              <ul className="flex flex-col gap-1 text-xs">
                {activity.recent_uploads.map((u, i) => (
                  <li key={i} className="flex items-center justify-between gap-2 text-muted-foreground">
                    <span className="truncate">{u.file_name}</span>
                    <span>{u.patient_id ?? u.status}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {activity.recent_security_events.length > 0 && (
            <div className="rounded-lg border bg-card px-3 py-2">
              <p className="mb-1.5 text-xs font-medium text-muted-foreground">Recent security events</p>
              <ul className="flex flex-col gap-1 text-xs">
                {activity.recent_security_events.map((e, i) => (
                  <li key={i} className="flex items-center justify-between gap-2 text-muted-foreground">
                    <span>
                      {e.status} {e.role ? `· ${e.role}` : ""}
                    </span>
                    <span>{formatTimestamp(e.timestamp)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
