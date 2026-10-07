import { apiRequest } from "@/api/client";
import type { AuthUser, LoginResponse, Role } from "@/types";

export function login(username: string, password: string, role: Role) {
  return apiRequest<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: { username, password, role },
  });
}

export function getCurrentUser() {
  return apiRequest<AuthUser>("/api/auth/me");
}
