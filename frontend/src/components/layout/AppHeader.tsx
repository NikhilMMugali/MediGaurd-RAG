import { useLocation } from "react-router-dom";
import { Menu } from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const TITLES: Record<string, string> = {
  "/patients": "Patients",
  "/assistant/chat": "Clinical Chat",
  "/assistant/documents": "Document Intelligence",
  "/assistant/insights": "Hospital Insights",
};

interface AppHeaderProps {
  onMenuClick: () => void;
}

// Desktop already gets a page title and role context from the sidebar and
// each page's own header bar (e.g. AssistantPanel's patient chip) — a second
// full-width header there would just be decorative chrome. This one exists
// for the one case that genuinely needs it: the sidebar is hidden on narrow
// screens, so something has to carry navigation access and orientation.
export default function AppHeader({ onMenuClick }: AppHeaderProps) {
  const { user } = useAuth();
  const location = useLocation();
  const title = TITLES[location.pathname] ?? "MediGuard";

  if (!user) return null;

  return (
    <header className="flex items-center justify-between border-b bg-card px-4 py-2.5 md:hidden">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onMenuClick} aria-label="Open navigation">
          <Menu className="h-4 w-4" />
        </Button>
        <span className="text-sm font-semibold">{title}</span>
      </div>
      <Badge variant="secondary">{user.role}</Badge>
    </header>
  );
}
