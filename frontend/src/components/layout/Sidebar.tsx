import * as React from "react";
import { NavLink, useLocation } from "react-router-dom";
import { BarChart3, ChevronDown, FileText, LogOut, MessageSquare, ShieldPlus, Users } from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { CAN_VIEW_DOCUMENTS, CAN_VIEW_INSIGHTS, ROLE_ICON } from "@/lib/roles";

const ASSISTANT_LINKS = [
  { to: "/assistant/chat", label: "Clinical Chat", icon: MessageSquare },
  { to: "/assistant/documents", label: "Document Intelligence", icon: FileText },
  { to: "/assistant/insights", label: "Hospital Insights", icon: BarChart3 },
];

function navLinkClass(isActive: boolean): string {
  return [
    "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors",
    isActive ? "bg-primary/10 font-medium text-primary" : "text-foreground/80 hover:bg-accent hover:text-foreground",
  ].join(" ");
}

export default function Sidebar() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const onAssistantRoute = location.pathname.startsWith("/assistant");
  const [assistantOpen, setAssistantOpen] = React.useState(onAssistantRoute);

  React.useEffect(() => {
    if (onAssistantRoute) setAssistantOpen(true);
  }, [onAssistantRoute]);

  if (!user) return null;

  const RoleIcon = ROLE_ICON[user.role];
  const assistantLinks = ASSISTANT_LINKS.filter((link) => {
    if (link.to === "/assistant/documents") return CAN_VIEW_DOCUMENTS.includes(user.role);
    if (link.to === "/assistant/insights") return CAN_VIEW_INSIGHTS.includes(user.role);
    return true;
  });

  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col justify-between border-r bg-card px-3 py-4">
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-2 px-1.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <ShieldPlus className="h-4 w-4" />
          </div>
          <span className="text-base font-semibold">MediGuard</span>
        </div>

        <nav className="flex flex-col gap-4">
          <div>
            <p className="px-2.5 pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              General
            </p>
            <NavLink to="/patients" className={({ isActive }) => navLinkClass(isActive)}>
              <Users className="h-4 w-4" />
              Patients
            </NavLink>
          </div>

          <div>
            <button
              type="button"
              onClick={() => setAssistantOpen((v) => !v)}
              aria-expanded={assistantOpen}
              className="flex w-full items-center justify-between rounded-md px-2.5 pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground"
            >
              AI Assistant
              <ChevronDown className={`h-3.5 w-3.5 transition-transform ${assistantOpen ? "" : "-rotate-90"}`} />
            </button>
            {assistantOpen && (
              <div className="flex flex-col gap-0.5">
                {assistantLinks.map((link) => (
                  <NavLink key={link.to} to={link.to} className={({ isActive }) => navLinkClass(isActive)}>
                    <link.icon className="h-4 w-4" />
                    {link.label}
                  </NavLink>
                ))}
              </div>
            )}
          </div>
        </nav>
      </div>

      <div>
        <Separator className="mb-3" />
        <div className="flex items-center gap-2 px-1 pb-2">
          <Avatar>
            <AvatarFallback>
              <RoleIcon className="h-4 w-4" />
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{user.full_name}</p>
            <p className="truncate text-xs text-muted-foreground">
              {user.role}
              {user.department ? ` · ${user.department}` : ""}
            </p>
          </div>
        </div>
        <Button variant="ghost" className="w-full justify-start gap-2 text-muted-foreground" onClick={logout}>
          <LogOut className="h-4 w-4" />
          Logout
        </Button>
      </div>
    </aside>
  );
}
