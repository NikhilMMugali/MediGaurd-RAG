import { LogOut, Users, MessageSquare } from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ROLE_ICON } from "@/lib/roles";

interface SidebarProps {
  active: "patients" | "assistant";
  onNavigate: (tab: "patients" | "assistant") => void;
}

export default function Sidebar({ active, onNavigate }: SidebarProps) {
  const { user, logout } = useAuth();
  if (!user) return null;

  const RoleIcon = ROLE_ICON[user.role];
  const initials = user.full_name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <aside className="flex h-screen w-56 flex-col justify-between border-r bg-card px-3 py-4">
      <div>
        <div className="px-2 pb-4 text-base font-semibold">MediGaurd</div>
        <nav className="flex flex-col gap-1">
          <Button
            variant={active === "patients" ? "secondary" : "ghost"}
            className="justify-start gap-2"
            onClick={() => onNavigate("patients")}
          >
            <Users className="h-4 w-4" />
            Patients
          </Button>
          <Button
            variant={active === "assistant" ? "secondary" : "ghost"}
            className="justify-start gap-2"
            onClick={() => onNavigate("assistant")}
          >
            <MessageSquare className="h-4 w-4" />
            Assistant
          </Button>
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
            <p className="truncate text-sm font-medium">{initials ? user.full_name : user.username}</p>
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
