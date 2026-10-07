import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { PatientStatusLabel } from "@/types";

const STATUS_VARIANT: Record<PatientStatusLabel, "success" | "warning" | "muted"> = {
  Stable: "success",
  Attention: "warning",
  "No Recent Information": "muted",
};

interface PatientCardProps {
  patientId: string;
  status: PatientStatusLabel | null;
  onOpen: (patientId: string) => void;
}

export default function PatientCard({ patientId, status, onOpen }: PatientCardProps) {
  return (
    <Card className="flex flex-col justify-between">
      <CardContent className="pt-4">
        <p className="truncate font-mono text-sm font-medium" title={patientId}>
          {patientId.length > 12 ? `${patientId.slice(0, 8)}…` : patientId}
        </p>
        {status ? (
          <Badge variant={STATUS_VARIANT[status]} className="mt-2">
            {status}
          </Badge>
        ) : (
          <div className="mt-2 h-5 w-20 animate-pulse rounded-full bg-muted" />
        )}
      </CardContent>
      <CardContent className="pt-0">
        <Button variant="outline" size="sm" className="w-full" onClick={() => onOpen(patientId)}>
          Open in Assistant
        </Button>
      </CardContent>
    </Card>
  );
}
