import { Stethoscope, HeartPulse, Wallet, ClipboardList, ShieldCheck, type LucideIcon } from "lucide-react";
import type { Role } from "@/types";

export const ROLES: Role[] = ["DOCTOR", "NURSE", "FINANCE", "RECEPTION", "ADMIN"];

export const ROLE_ICON: Record<Role, LucideIcon> = {
  DOCTOR: Stethoscope,
  NURSE: HeartPulse,
  FINANCE: Wallet,
  RECEPTION: ClipboardList,
  ADMIN: ShieldCheck,
};

export const ROLE_ASSISTANT_NAME: Record<Role, string> = {
  DOCTOR: "Clinical Assistant",
  NURSE: "Nursing Assistant",
  FINANCE: "Finance Assistant",
  RECEPTION: "Operations Assistant",
  ADMIN: "Hospital Assistant",
};

export const ROLE_PLACEHOLDER: Record<Role, string> = {
  DOCTOR: "Ask about an assigned patient...",
  NURSE: "Ask about your assigned patients...",
  FINANCE: "Ask about claims, payments, or payer information...",
  RECEPTION: "Ask about patients and encounters...",
  ADMIN: "Ask MediGaurd anything you are authorized to access...",
};

export const ROLE_QUICK_PROMPTS: Record<Role, string[]> = {
  DOCTOR: ["Recent observations", "Current medications", "What conditions does this patient have?", "Last visit"],
  NURSE: ["Recent observations", "Current medications", "Last visit"],
  FINANCE: ["What is the outstanding amount?", "Which payer is associated with this patient?"],
  RECEPTION: ["Last visit", "Encounter history"],
  ADMIN: ["What is the patient's name, age and gender?", "Recent observations", "Outstanding amount"],
};

// Demo-only convenience (never a security mechanism — the backend still
// verifies the stored role on every login, see docs/SECURITY.md).
export const DEMO_CREDENTIALS: Record<Role, { username: string; password: string }> = {
  DOCTOR: { username: "doctor01", password: "medigaurd123" },
  NURSE: { username: "nurse01", password: "medigaurd123" },
  FINANCE: { username: "finance01", password: "medigaurd123" },
  RECEPTION: { username: "reception01", password: "medigaurd123" },
  ADMIN: { username: "admin01", password: "medigaurd123" },
};

export const CAN_UPLOAD: Role[] = ["DOCTOR", "NURSE", "ADMIN"];

// Document Intelligence is backed by endpoints that require DOCTOR/NURSE/ADMIN
// server-side (app.api.upload._DOC_ROLES) — kept in sync here only to decide
// whether to show the nav link at all; the server-side check is what
// actually enforces it (section 10 "never duplicate security logic in the
// frontend" — this is a visibility convenience, not an access control).
export const CAN_VIEW_DOCUMENTS: Role[] = ["DOCTOR", "NURSE", "ADMIN"];

// Hospital Insights is admin-only, server-side (app.api.insights —
// require_roles(RoleEnum.ADMIN)) — kept in sync here only to decide whether
// to show the nav link at all, same caveat as CAN_VIEW_DOCUMENTS above.
export const CAN_VIEW_INSIGHTS: Role[] = ["ADMIN"];
