import * as React from "react";
import { getCurrentUser, login as loginRequest } from "@/api/auth";
import { setToken, setUnauthorizedHandler } from "@/api/client";
import type { AuthUser, Role } from "@/types";

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  login: (username: string, password: string, role: Role) => Promise<void>;
  logout: () => void;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);

  const logout = React.useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  React.useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
  }, []);

  React.useEffect(() => {
    const token = sessionStorage.getItem("medigaurd_token");
    if (!token) {
      setIsLoading(false);
      return;
    }
    getCurrentUser()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setIsLoading(false));
  }, []);

  const login = React.useCallback(async (username: string, password: string, role: Role) => {
    const response = await loginRequest(username, password, role);
    setToken(response.access_token);
    setUser({
      username: response.username,
      full_name: response.full_name,
      role: response.role,
      department: response.department,
    });
  }, []);

  return <AuthContext.Provider value={{ user, isLoading, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
