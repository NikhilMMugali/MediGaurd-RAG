import * as React from "react";
import { useAuth } from "@/auth/AuthContext";
import Login from "@/pages/Login";
import PatientsPanel from "@/pages/Dashboard";
import Sidebar from "@/components/layout/Sidebar";
import AssistantPanel from "@/components/chat/AssistantPanel";

export default function App() {
  const { user, isLoading } = useAuth();
  const [tab, setTab] = React.useState<"patients" | "assistant">("patients");
  const [selectedPatient, setSelectedPatient] = React.useState<string | null>(null);

  if (isLoading) return null;
  if (!user) return <Login />;

  function openPatientInAssistant(patientId: string) {
    setSelectedPatient(patientId);
    setTab("assistant");
  }

  return (
    <div className="flex h-screen">
      <Sidebar active={tab} onNavigate={setTab} />
      <main className="flex-1 overflow-hidden">
        {tab === "patients" ? (
          <div className="h-full overflow-y-auto">
            <PatientsPanel onSelectPatient={openPatientInAssistant} />
          </div>
        ) : (
          <AssistantPanel patientId={selectedPatient} onClearPatient={() => setSelectedPatient(null)} />
        )}
      </main>
    </div>
  );
}
