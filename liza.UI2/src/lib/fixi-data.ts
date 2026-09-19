export type Priority = "High" | "Medium" | "Low";
export type StatusTone = "blue" | "amber" | "purple" | "green" | "gray";

export interface Ticket {
  id: number;
  issue: string;
  address: string;
  priority: Priority;
  status: string;
  assignedTo: string | null;
  updated: string;
}

export const tickets: Ticket[] = [
  { id: 1042, issue: "Roof leak", address: "14 King Street, E17", priority: "High", status: "In progress", assignedTo: "ABC Roofing", updated: "2h ago" },
  { id: 1041, issue: "No heating", address: "27 Maple Road, N1", priority: "High", status: "Awaiting tenant", assignedTo: "London Heat Ltd", updated: "5h ago" },
  { id: 1040, issue: "Leaking pipe", address: "8 Station View, W3", priority: "Medium", status: "Diagnosing", assignedTo: null, updated: "6h ago" },
  { id: 1039, issue: "Broken boiler", address: "12 Oak Avenue, SE3", priority: "High", status: "Contractor booked", assignedTo: "HeatRight", updated: "1 day ago" },
  { id: 1038, issue: "Electrical issue", address: "90 Riverdale Rd, SW6", priority: "Medium", status: "In progress", assignedTo: "PowerFix", updated: "1 day ago" },
  { id: 1037, issue: "Mould in bathroom", address: "3 Wellington Close, AL8", priority: "Medium", status: "Awaiting response", assignedTo: null, updated: "2 days ago" },
  { id: 1036, issue: "Window won't close", address: "21 Birch Lane, N8", priority: "Low", status: "Scheduled", assignedTo: "HomeFix", updated: "2 days ago" },
  { id: 1035, issue: "Water pressure", address: "5 Church Road, E11", priority: "Low", status: "Resolved", assignedTo: "FlowTech", updated: "3 days ago" },
];

export function statusTone(status: string): StatusTone {
  const s = status.toLowerCase();
  if (s.includes("awaiting") || s.includes("waiting")) return "amber";
  if (s.includes("booked")) return "purple";
  if (s.includes("resolved") || s.includes("scheduled")) return "green";
  if (s.includes("diagnos")) return "gray";
  return "blue";
}

export const kpis = [
  { value: "24", label: "Open tickets" },
  { value: "8", label: "In progress" },
  { value: "12", label: "Awaiting response" },
  { value: "156", label: "Resolved (30 days)" },
  { value: "4.7 days", label: "Average time to resolve", badge: "↓ 32%" },
];

export const caseDetails = {
  id: 1042,
  issue: "Roof leak",
  address: "14 King Street, Walthamstow, E17 6QX",
  priority: "High" as Priority,
  status: "In progress",
  summary:
    "Tenant reports water coming through the ceiling in the bedroom after heavy rain. Similar issue reported 4 months ago. Contractor on site inspecting the roof. Next step depends on findings (possible scaffolding required).",
  tenant: { name: "James Doe", phone: "+44 7700 123456", initials: "JD" },
  contractor: { name: "ABC Roofing", role: "Roofing Specialist", phone: "+44 20 7946 0011", initials: "AR" },
  appointment: { date: "Tomorrow, 14 Sep 2026", time: "15:00 – 17:00" },
  steps: [
    { label: "Reported", time: "12 Sep, 10:24", state: "done" },
    { label: "Diagnosing", time: "12 Sep, 11:02", state: "done" },
    { label: "Contractor on site", time: "Current", state: "current" },
    { label: "Follow up", time: "", state: "future" },
    { label: "Resolved", time: "", state: "future" },
  ] as const,
};

export type TimelineState = "done" | "current" | "future";

export const agentTimeline: { title: string; body: string; time?: string; state: TimelineState }[] = [
  { title: "Analysed issue", body: "Identified as likely roof leak based on tenant description and photos.", time: "12 Sep, 10:26", state: "done" },
  { title: "Checked property history", body: "Found similar issue in May 2026. Previous repair may not have fully resolved the underlying cause.", time: "12 Sep, 10:27", state: "done" },
  { title: "Selected contractor", body: "Chose ABC Roofing (highest rating, available this week).", time: "12 Sep, 10:31", state: "done" },
  { title: "Contacted tenant", body: "Confirmed access for inspection.", time: "12 Sep, 10:34", state: "done" },
  { title: "Contractor on site", body: "ABC Roofing has arrived and is inspecting the roof.", time: "12 Sep, 12:05", state: "current" },
  { title: "Waiting for contractor update", body: "Contractor will provide findings and next steps.", state: "future" },
  { title: "Plan next steps", body: "May require scaffolding or further investigation.", state: "future" },
];

export type SenderType = "Contractor" | "Tenant" | "AI Agent";

export interface Message {
  sender: string;
  type: SenderType;
  time: string;
  text: string;
  attachments?: "tenant" | "contractor";
}

export const messages: Message[] = [
  { sender: "Contractor (ABC Roofing)", type: "Contractor", time: "12:05", text: "On site now. Initial inspection shows possible flashing issue. Need to check under tiles. Will update shortly.", attachments: "contractor" },
  { sender: "AI Agent", type: "AI Agent", time: "12:06", text: "Thanks. Please take photos of the flashing and let me know if scaffolding is required." },
  { sender: "Tenant (James Doe)", type: "Tenant", time: "11:48", text: "That's great. I'm at work today — please use the back entrance if needed." },
  { sender: "AI Agent", type: "AI Agent", time: "11:49", text: "Noted. I've informed the contractor about access. I'll keep you updated." },
  { sender: "Tenant (James Doe)", type: "Tenant", time: "10:28", text: "Here are some more photos of the ceiling. The leak seems worse after last night's rain.", attachments: "tenant" },
];

export interface HistoryItem {
  date: string;
  issue: string;
  state: "Resolved";
  outcome: string;
  contractor: string;
  cost: string;
}

export const propertyHistory: HistoryItem[] = [
  { date: "May 2026", issue: "Roof leak", state: "Resolved", outcome: "Flashing replaced", contractor: "ABC Roofing", cost: "£620" },
  { date: "Nov 2025", issue: "Gutter blockage", state: "Resolved", outcome: "Gutters cleared", contractor: "City Gutters", cost: "£180" },
  { date: "Feb 2025", issue: "Damp in bedroom", state: "Resolved", outcome: "No further issues", contractor: "HomeFix", cost: "£350" },
  { date: "Oct 2024", issue: "Roof leak", state: "Resolved", outcome: "Minor repair", contractor: "ABC Roofing", cost: "£240" },
  { date: "Jun 2024", issue: "Broken tile", state: "Resolved", outcome: "Tile replaced", contractor: "Local Builders", cost: "£120" },
  { date: "Jan 2024", issue: "Boiler service", state: "Resolved", outcome: "Annual service", contractor: "HeatRight", cost: "£90" },
  { date: "Aug 2023", issue: "Leak under sink", state: "Resolved", outcome: "Pipe replaced", contractor: "PlumbPro", cost: "£210" },
  { date: "Mar 2023", issue: "Electrical issue", state: "Resolved", outcome: "Socket replaced", contractor: "PowerFix", cost: "£160" },
  { date: "Sep 2022", issue: "Damp in hallway", state: "Resolved", outcome: "Ventilation improved", contractor: "HomeFix", cost: "£300" },
  { date: "Apr 2022", issue: "Roof inspection", state: "Resolved", outcome: "No issues found", contractor: "ABC Roofing", cost: "£80" },
  { date: "Nov 2021", issue: "Heating issue", state: "Resolved", outcome: "Thermostat replaced", contractor: "HeatRight", cost: "£180" },
];

export const propertyStats = [
  { value: "3", label: "Active tickets" },
  { value: "8", label: "Total tickets" },
  { value: "2", label: "Repeat issues" },
  { value: "2021", label: "Built" },
];
