import AssistantPanel from "@/components/chat/AssistantPanel";
import { useAssistantContext } from "@/components/layout/AppLayout";

export default function ClinicalChat() {
  const { selectedPatient, setSelectedPatient } = useAssistantContext();
  return (
    <AssistantPanel
      patientId={selectedPatient}
      onClearPatient={() => setSelectedPatient(null)}
      onSelectPatient={setSelectedPatient}
    />
  );
}
