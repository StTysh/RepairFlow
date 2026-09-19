import { createFileRoute, Link } from "@tanstack/react-router";
import { BarChart3, CheckCircle2, ChevronDown, ChevronRight, Clock3, FileText, MessageCircle, MoreHorizontal } from "lucide-react";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { UtilityBar } from "@/components/fixi/UtilityBar";
import { PriorityBadge, StatusBadge } from "@/components/fixi/Badge";
import { tickets } from "@/lib/fixi-data";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import houseExterior from "@/assets/house-exterior.jpg";

export const Route = createFileRoute("/maintenance/")({
  head: () => ({ meta: [
    { title: "Maintenance Dashboard — Fixi" },
    { name: "description", content: "Track property maintenance tickets, upcoming visits and resolution performance." },
    { property: "og:title", content: "Maintenance Dashboard — Fixi" },
    { property: "og:description", content: "Track property issues from report to resolution." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: MaintenancePage,
});

const filters = ["All", "Open", "In progress", "Waiting", "Resolved"];
const kpis = [
  { value: "24", label: "Open tickets", trend: "↑ 12%", note: "vs last month", tone: "red", Icon: FileText },
  { value: "8", label: "In progress", trend: "↓ 20%", note: "vs last month", tone: "blue", Icon: Clock3 },
  { value: "12", label: "Awaiting response", trend: "↓ 8%", note: "vs last month", tone: "amber", Icon: MessageCircle },
  { value: "156", label: "Resolved (30 days)", trend: "↑ 18%", note: "vs last month", tone: "green", Icon: CheckCircle2 },
  { value: "4.7 days", label: "Average time to resolve", trend: "↓ 32%", note: "vs last month", tone: "gray", Icon: BarChart3 },
] as const;
const toneClass = { red: "bg-status-red text-status-red-foreground", blue: "bg-status-blue text-status-blue-foreground", amber: "bg-status-amber text-status-amber-foreground", green: "bg-status-green text-status-green-foreground", gray: "bg-status-gray text-status-gray-foreground" };
const propertyImages = Array.from({ length: 8 }, () => houseExterior);
const visits = [
  { day: "14", company: "ABC Roofing", address: "14 King Street, E17", time: "15:00 – 17:00" },
  { day: "15", company: "HeatRight", address: "12 Oak Avenue, SE3", time: "10:00 – 12:00" },
  { day: "16", company: "PowerFix", address: "90 Riverdale Rd, SW6", time: "13:00 – 15:00" },
];

function MaintenancePage() {
  return <AppShell><div className="mx-auto max-w-[1510px] px-6 py-4 xl:px-7">
    <UtilityBar />
    <header className="mt-2"><h1 className="text-[28px] font-bold">Maintenance</h1><p className="mt-0.5 text-sm text-muted-foreground">All property issues, from report to resolution.</p></header>
    <section className="mt-4 grid grid-cols-2 gap-3 xl:grid-cols-5">
      {kpis.map(({ value, label, trend, note, tone, Icon }) => <Card key={label} className="flex min-h-24 items-center gap-3 px-3.5 py-3">
        <span className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-full", toneClass[tone])}><Icon className="h-5 w-5" /></span>
        <div className="min-w-0"><div className="text-xl font-bold">{value}</div><div className="truncate text-xs text-muted-foreground">{label}</div><div className={cn("mt-2 text-[10px] font-semibold", tone === "red" ? "text-destructive" : "text-primary")}>{trend} <span className="ml-2 font-normal text-muted-foreground">{note}</span></div></div>
      </Card>)}
    </section>
    <section className="mt-4 flex flex-wrap items-center justify-between gap-3">
      <div className="flex gap-2">{filters.map((f, i) => <Button key={f} size="sm" variant={i === 0 ? "default" : "outline"} className="rounded-xl">{f}</Button>)}</div>
      <div className="flex gap-2">{["All priorities", "All properties", "All contractors"].map(d => <Button key={d} size="sm" variant="outline" className="min-w-32 justify-between rounded-xl bg-card">{d}<ChevronDown /></Button>)}</div>
    </section>
    <div className="mt-4 grid items-start gap-4 2xl:grid-cols-[minmax(0,1fr)_255px]">
      <Card className="overflow-x-auto"><table className="w-full min-w-[900px] text-[11px]"><thead><tr className="border-b border-border text-left text-muted-foreground">
        <th className="w-9 px-3 py-2"><input aria-label="Select all" type="checkbox" className="h-3.5 w-3.5 accent-primary" /></th><th className="w-10 px-1 py-2"></th><th className="px-2 py-2 font-medium">#</th><th className="px-2 py-2 font-medium">Issue</th><th className="px-2 py-2 font-medium">Address</th><th className="px-2 py-2 font-medium">Priority</th><th className="px-2 py-2 font-medium">Status</th><th className="px-2 py-2 font-medium">Assigned to</th><th className="px-2 py-2 font-medium">Updated ↓</th><th className="w-8" />
      </tr></thead><tbody>{tickets.map((t, i) => { const isCase = t.id === 1042; return <tr key={t.id} className={cn("border-b border-border last:border-0 hover:bg-muted/60", isCase && "bg-primary-soft/50")}>
        <td className="px-3 py-2"><input aria-label={`Select ticket ${t.id}`} type="checkbox" className="h-3.5 w-3.5 accent-primary" /></td><td className="px-1 py-1.5"><img src={propertyImages[i]} alt="" loading="lazy" width={912} height={736} className="h-8 w-8 rounded-md object-cover" /></td>
        <td className="px-2 py-2 text-muted-foreground">{isCase ? <Link to="/maintenance/tickets/$ticketId/{-$section}" params={{ticketId:"1042",section:undefined}}>#{t.id}</Link> : `#${t.id}`}</td>
        <td className="px-2 py-2 font-medium">{isCase ? <Link className="hover:underline" to="/maintenance/tickets/$ticketId/{-$section}" params={{ticketId:"1042",section:undefined}}>{t.issue}</Link> : t.issue}</td>
        <td className="px-2 py-2 text-muted-foreground">{t.address}</td><td className="px-2 py-2"><PriorityBadge priority={t.priority}/></td><td className="px-2 py-2"><StatusBadge status={t.status}/></td><td className="px-2 py-2 text-muted-foreground">{t.assignedTo ?? "—"}</td><td className="px-2 py-2 text-muted-foreground">{t.updated}</td><td><Button aria-label={`More actions for ${t.id}`} variant="ghost" size="icon" className="h-7 w-7"><MoreHorizontal/></Button></td>
      </tr>})}</tbody></table></Card>
      <aside className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-1"><Card className="p-3.5"><div className="flex justify-between"><h2 className="text-sm font-semibold">Upcoming visits</h2><button className="text-[10px] font-medium text-primary">View all</button></div>
        <div className="mt-2 divide-y divide-border">{visits.map(v => <div key={v.day} className="flex items-center gap-2 py-2"><div className="flex h-12 w-10 shrink-0 flex-col items-center justify-center rounded-lg border border-border bg-muted"><span className="text-[8px] font-semibold">SEP</span><span className="text-base font-bold">{v.day}</span></div><div className="min-w-0 flex-1"><div className="text-xs font-semibold">{v.company}</div><div className="truncate text-[10px] text-muted-foreground">{v.address}</div><div className="text-[10px] text-muted-foreground">{v.time}</div></div><ChevronRight className="h-4 w-4 text-muted-foreground"/></div>)}</div>
      </Card><div className="relative min-h-36 overflow-hidden rounded-xl shadow-card"><img src={houseExterior} alt="London terraced property" width={912} height={736} className="absolute inset-0 h-full w-full object-cover"/><div className="absolute inset-0 bg-foreground/65"/><div className="relative flex h-full flex-col justify-end p-4 text-primary-foreground"><h2 className="text-base font-semibold">Keep properties<br/>in better shape</h2><p className="mt-1 text-[10px] opacity-90">Track history, spot recurring<br/>issues and plan ahead.</p><Button asChild variant="secondary" size="sm" className="mt-3 w-fit rounded-lg"><Link to="/properties/14-king-street/history">View property insights <ChevronRight/></Link></Button></div></div></aside>
    </div>
  </div></AppShell>;
}