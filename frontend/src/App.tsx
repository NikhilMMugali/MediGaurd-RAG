import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import Login from "@/pages/Login";
import AppLayout from "@/components/layout/AppLayout";
import Patients from "@/pages/Patients";
import ClinicalChat from "@/pages/assistant/ClinicalChat";
import DocumentIntelligence from "@/pages/assistant/DocumentIntelligence";
import HospitalInsights from "@/pages/assistant/HospitalInsights";

export default function App() {
  const { user, isLoading } = useAuth();

  if (isLoading) return null;
  if (!user) return <Login />;

  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/patients" replace />} />
        <Route path="/patients" element={<Patients />} />
        <Route path="/assistant" element={<Navigate to="/assistant/chat" replace />} />
        <Route path="/assistant/chat" element={<ClinicalChat />} />
        <Route path="/assistant/documents" element={<DocumentIntelligence />} />
        <Route path="/assistant/insights" element={<HospitalInsights />} />
        <Route path="*" element={<Navigate to="/patients" replace />} />
      </Route>
    </Routes>
  );
}
