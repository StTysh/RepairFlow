// Real status/urgency taxonomy + display helpers backing Badge.tsx.
//
// This used to hold hardcoded mock tickets/case details/messages/property
// history (Lovable placeholder data). All of that is gone now that every
// screen fetches from the Fixi API (see src/api and src/hooks) --
// this file's only remaining job is the small set of pure display helpers
// that turn the backend's real enums into badge colors/labels, which is
// why it keeps its original name and import path.

// The 5 real case statuses (backend: app/schemas.py CaseStatus). Not the
// ~10 fictional statuses the original Lovable mock used ("In progress",
// "Awaiting tenant", "Contractor booked", ...) -- see docs/07 state machine.
export type CaseStatus =
  "ACTIVE" | "AWAITING_CONFIRMATION" | "RESOLVED" | "ESCALATED" | "CANCELLED";

export const CASE_STATUSES: CaseStatus[] = [
  "ACTIVE",
  "AWAITING_CONFIRMATION",
  "RESOLVED",
  "ESCALATED",
  "CANCELLED",
];

export const STATUS_LABEL: Record<CaseStatus, string> = {
  ACTIVE: "Active",
  AWAITING_CONFIRMATION: "Awaiting confirmation",
  RESOLVED: "Resolved",
  ESCALATED: "Escalated",
  CANCELLED: "Cancelled",
};

// Urgency is a SEPARATE axis from status (backend: RiskAssessment.urgency,
// surfaced on CaseListItem/RepairCase.risk). It backs what the mockup
// called the "priority" badge -- kept visually distinct from the status
// badge throughout the UI.
export type Urgency = "EMERGENCY" | "URGENT" | "ROUTINE" | "UNKNOWN";

export const URGENCIES: Urgency[] = ["EMERGENCY", "URGENT", "ROUTINE", "UNKNOWN"];

export const URGENCY_LABEL: Record<Urgency, string> = {
  EMERGENCY: "Emergency",
  URGENT: "Urgent",
  ROUTINE: "Routine",
  UNKNOWN: "Unknown",
};

export type StatusTone = "blue" | "amber" | "purple" | "green" | "gray" | "red" | "orange";

/** Plain 5-way switch -- replaces the old substring-matching heuristic
 * that guessed a tone from ~10 fictional status strings. */
export function statusTone(status: CaseStatus): StatusTone {
  switch (status) {
    case "ACTIVE":
      return "blue";
    case "AWAITING_CONFIRMATION":
      return "amber";
    case "RESOLVED":
      return "green";
    case "ESCALATED":
      return "red";
    case "CANCELLED":
      return "gray";
    default:
      return "gray";
  }
}

export function urgencyTone(urgency: Urgency): StatusTone {
  switch (urgency) {
    case "EMERGENCY":
      return "red";
    case "URGENT":
      return "orange";
    case "ROUTINE":
      return "green";
    case "UNKNOWN":
    default:
      return "gray";
  }
}
