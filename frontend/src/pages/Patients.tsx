import { useNavigate } from "react-router-dom";
import PatientsPanel from "@/pages/Dashboard";
import { useAssistantContext } from "@/components/layout/AppLayout";

export default function Patients() {
  const navigate = useNavigate();
  const { setSelectedPatient } = useAssistantContext();

  function openInAssistant(patientId: string) {
    setSelectedPatient(patientId);
    navigate("/assistant/chat");
  }

  return (
    <div className="h-full overflow-y-auto">
      <PatientsPanel onSelectPatient={openInAssistant} />
    </div>
  );
}
