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
  DOCTOR: ["Latest clinical information", "Current medications", "Recent observations"],
  NURSE: ["Recent observations", "Medications", "Assigned patient information"],
  FINANCE: ["Outstanding balance", "Claim status", "Payer information"],
  RECEPTION: ["Latest encounter", "Encounter history", "Operational information"],
  ADMIN: ["Patient information", "Claims", "Clinical information"],
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
