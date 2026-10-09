import * as React from "react";
import { Outlet, useLocation, useOutletContext } from "react-router-dom";
import Sidebar from "@/components/layout/Sidebar";
import AppHeader from "@/components/layout/AppHeader";

export interface AssistantOutletContext {
  selectedPatient: string | null;
  setSelectedPatient: (id: string | null) => void;
}

export function useAssistantContext() {
  return useOutletContext<AssistantOutletContext>();
}

export default function AppLayout() {
  const [selectedPatient, setSelectedPatient] = React.useState<string | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = React.useState(false);
  const location = useLocation();

  React.useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  return (
    <div className="flex h-screen">
      <div className="hidden md:flex">
        <Sidebar />
      </div>

      {mobileNavOpen && (
        <div className="fixed inset-0 z-50 flex md:hidden">
          <Sidebar />
          <div className="flex-1 bg-black/30" onClick={() => setMobileNavOpen(false)} aria-hidden="true" />
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <AppHeader onMenuClick={() => setMobileNavOpen(true)} />
        <main className="flex-1 overflow-hidden">
          <Outlet context={{ selectedPatient, setSelectedPatient } satisfies AssistantOutletContext} />
        </main>
      </div>
    </div>
  );
}
