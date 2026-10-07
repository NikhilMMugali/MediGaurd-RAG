import * as React from "react";
import { getDatabaseStats } from "@/api/admin";
import type { DatabaseStats } from "@/types";

export default function AdminStatsBar() {
  const [stats, setStats] = React.useState<DatabaseStats | null>(null);

  React.useEffect(() => {
    getDatabaseStats().then(setStats).catch(() => setStats(null));
  }, []);

  if (!stats) return null;

  const items: [string, number][] = [
    ["Patients", stats.patients],
    ["Conditions", stats.conditions],
    ["Medications", stats.medications],
    ["Claims", stats.claims],
    ["Knowledge Records", stats.knowledge_records],
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      {items.map(([label, value]) => (
        <div key={label} className="rounded-lg border bg-card px-3 py-2">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-lg font-semibold">{value.toLocaleString()}</p>
        </div>
      ))}
    </div>
  );
}
