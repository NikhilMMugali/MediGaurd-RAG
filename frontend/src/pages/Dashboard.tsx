import * as React from "react";
import { listPatients, getPatientStatus } from "@/api/patients";
import { mapWithConcurrency } from "@/lib/concurrency";
import { useAuth } from "@/auth/AuthContext";
import { CAN_UPLOAD } from "@/lib/roles";
import PatientCard from "@/components/dashboard/PatientCard";
import AdminStatsBar from "@/components/dashboard/AdminStatsBar";
import UploadDialog from "@/components/upload/UploadDialog";
import type { PatientStatusLabel } from "@/types";
import { ApiError } from "@/api/client";

interface PatientsPanelProps {
  onSelectPatient: (patientId: string) => void;
}

export default function PatientsPanel({ onSelectPatient }: PatientsPanelProps) {
  const { user } = useAuth();
  const [patientIds, setPatientIds] = React.useState<string[] | null>(null);
  const [total, setTotal] = React.useState(0);
  const [statuses, setStatuses] = React.useState<Record<string, PatientStatusLabel>>({});
  const [error, setError] = React.useState<string | null>(null);
  const [refreshKey, setRefreshKey] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    setPatientIds(null);
    setStatuses({});

    listPatients()
      .then(async (list) => {
        if (cancelled) return;
        setPatientIds(list.patient_ids);
        setTotal(list.total);

        await mapWithConcurrency(list.patient_ids, 4, async (id) => {
          try {
            const status = await getPatientStatus(id);
            if (!cancelled) setStatuses((prev) => ({ ...prev, [id]: status.status }));
          } catch {
            if (!cancelled) setStatuses((prev) => ({ ...prev, [id]: "No Recent Information" }));
          }
        });
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load patients."));

    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (!user) return null;

  return (
    <div className="flex flex-col gap-5 p-6">
      {user.role === "ADMIN" && <AdminStatsBar />}

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Your Patients</h2>
          <p className="text-sm text-muted-foreground">{total}</p>
        </div>
        {CAN_UPLOAD.includes(user.role) && <UploadDialog onIndexed={() => setRefreshKey((k) => k + 1)} />}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {patientIds === null && !error && (
        <p className="text-sm text-muted-foreground">Loading authorized patients...</p>
      )}

      {patientIds !== null && patientIds.length === 0 && (
        <p className="text-sm text-muted-foreground">No authorized patients to show.</p>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {patientIds?.map((id) => (
          <PatientCard key={id} patientId={id} status={statuses[id] ?? null} onOpen={onSelectPatient} />
        ))}
      </div>
    </div>
  );
}
