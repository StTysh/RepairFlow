import * as Dialog from "@radix-ui/react-dialog";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  BarChart3,
  Building2,
  FileText,
  HardHat,
  Home,
  MessageSquare,
  Users,
  Wrench,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { UtilityBar } from "@/components/fixi/UtilityBar";
import { useAgentStatus } from "@/hooks/use-agent-status";
import { useGlobalUnreadCount } from "@/hooks/use-unread-count";
import { useAuthedCreds } from "@/lib/auth-context";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

// All eight reference destinations, each pointing at a real screen. An
// earlier build dropped five of them because they had no backing data
// model; they now do, so the reference navigation is restored in full and
// in the reference's own order.
const nav = [
  { label: "Overview", icon: Home, to: "/" as const, exact: true },
  { label: "Maintenance", icon: Wrench, to: "/maintenance" as const },
  { label: "Properties", icon: Building2, to: "/properties" as const },
  { label: "Contractors", icon: HardHat, to: "/contractors" as const },
  { label: "Tenants", icon: Users, to: "/tenants" as const },
  { label: "Insights", icon: BarChart3, to: "/insights" as const },
  { label: "Messages", icon: MessageSquare, to: "/messages" as const },
  { label: "Reports", icon: FileText, to: "/reports" as const },
];

export function FixiLogo() {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-soft text-primary">
        <svg
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M3 11.5 12 4l9 7.5" />
          <path d="M5 10v9h14v-9" />
          <path d="M10 19v-5h4v5" />
        </svg>
      </div>
      <div className="leading-tight">
        <div className="text-[17px] font-bold tracking-tight text-foreground">Fixi</div>
        <div className="text-[10.5px] text-muted-foreground">Properties, solved.</div>
      </div>
    </div>
  );
}

/** The eight primary destinations, shared verbatim between the desktop
 * sidebar and the sub-1024px drawer (AppShell below) so the two can never
 * drift into different navigation sets. `onNavigate` closes the drawer on
 * the mobile side; the desktop `<aside>` never passes it, since there is
 * nothing to close. */
function SidebarNav({
  pathname,
  unreadCount,
  onNavigate,
}: {
  pathname: string;
  unreadCount: number;
  onNavigate?: () => void;
}) {
  return (
    <nav className="mt-7 flex flex-col gap-1" aria-label="Main">
      {nav.map((item) => {
        const isActive = item.exact
          ? pathname === item.to
          : pathname === item.to || pathname.startsWith(`${item.to}/`);
        return (
          <Link
            key={item.label}
            to={item.to}
            onClick={onNavigate}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "flex h-10 items-center gap-3 rounded-lg px-3 text-[13px] font-medium transition-colors",
              isActive
                ? "bg-sidebar-primary text-sidebar-primary-foreground"
                : "text-sidebar-foreground hover:bg-sidebar-accent",
            )}
          >
            <item.icon className="h-4 w-4" strokeWidth={1.9} />
            {item.label}
            {/* The reference shows a hardcoded "3" here. This is the
             * real unread count and disappears at zero rather than
             * advertising unread mail that does not exist. */}
            {item.label === "Messages" && unreadCount > 0 && (
              <span className="ml-auto rounded-full bg-status-green px-2 py-0.5 text-[10px] font-semibold text-status-green-foreground">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

/** The operator-identity row at the foot of the sidebar/drawer -- see
 * AgentStatusPanel's comment below: this shows the one identity actually
 * known (the signed-in operator credential), never an invented user. */
function AccountRow({ username }: { username: string }) {
  return (
    <div className="flex items-center gap-2.5 px-1">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-status-purple text-[11px] font-semibold text-status-purple-foreground">
        {initials(username)}
      </div>
      <div className="min-w-0 leading-tight">
        <div className="truncate text-xs font-semibold">{username}</div>
        <div className="text-[11px] text-muted-foreground">Signed in</div>
      </div>
    </div>
  );
}

/** The sidebar's bottom panel. Every word of it is a live reading.
 *
 * The reference hardcodes "AI agent active / Handling 24 tasks". Both
 * halves are claims about the system's current state, so both are read
 * from the backend: the dot and label follow whether a coordinator run or
 * a due job is genuinely in flight, and the count is the real number of
 * active cases. When the agent is idle it says so -- an indicator that is
 * always green tells the operator nothing. */
function AgentStatusPanel() {
  const status = useAgentStatus();
  const active = status.data?.agent_active ?? false;
  const caseCount = status.data?.active;

  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-sidebar-border bg-card px-3 py-2.5 shadow-card">
      <span
        className={cn(
          "h-2.5 w-2.5 shrink-0 rounded-full",
          active ? "bg-timeline-done" : "bg-muted-foreground/40",
        )}
      />
      <div className="min-w-0 leading-tight">
        <div className="truncate text-xs font-semibold">
          {status.isError
            ? "Agent status unavailable"
            : active
              ? "AI agent working"
              : "AI agent idle"}
        </div>
        <div className="truncate text-[11px] text-muted-foreground">
          {caseCount === undefined
            ? status.isError
              ? "Backend unreachable"
              : "Checking…"
            : `${caseCount} active case${caseCount === 1 ? "" : "s"}`}
        </div>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const creds = useAuthedCreds();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const unread = useGlobalUnreadCount();
  const unreadCount = unread.data?.unread_count ?? 0;
  // Below 1024px the <aside> is hidden with nothing replacing it -- every
  // destination except whichever page you're already on was unreachable
  // without hand-editing the URL (docs/audit/08 HIGH-1). This drawer is
  // that replacement: same eight links, same status panel, same account
  // row, opened from the menu button UtilityBar renders at that width.
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // Radix's modal Dialog locks <body> scroll while open regardless of which
  // breakpoint its content is visible at -- lg:hidden only hides the
  // overlay/content visually. Without this, rotating a tablet (or resizing
  // a window) past 1024px with the drawer open would leave the app
  // scroll-locked behind an invisible overlay, recoverable only via
  // Escape.
  useEffect(() => {
    const query = window.matchMedia("(min-width: 1024px)");
    function closeIfDesktop(e: MediaQueryListEvent | MediaQueryList) {
      if (e.matches) setMobileNavOpen(false);
    }
    closeIfDesktop(query);
    query.addEventListener("change", closeIfDesktop);
    return () => query.removeEventListener("change", closeIfDesktop);
  }, []);

  return (
    <div className="flex min-h-screen w-full bg-background font-sans text-foreground antialiased">
      {/* print:hidden here rather than in each printable page: the Reports
       * print view needs the chrome gone, and a route-scoped stylesheet
       * reaching up into the shell to hide it is the kind of action at a
       * distance that breaks the next time the shell changes. */}
      <aside className="sticky top-0 hidden h-screen w-[218px] shrink-0 flex-col border-r border-sidebar-border bg-sidebar px-3.5 py-4 print:hidden lg:flex">
        <FixiLogo />
        <SidebarNav pathname={pathname} unreadCount={unreadCount} />
        <div className="mt-auto space-y-3">
          <AgentStatusPanel />
          {/* The reference shows a fixed "Vlad Shuliar / Roche Properties".
           * There is no user or organisation model in this API, so this
           * shows the one thing that is actually known: the operator
           * credential this session signed in with. */}
          <AccountRow username={creds.username} />
        </div>
      </aside>

      {/* Radix Dialog gives this focus-trapping, Escape-to-close and
       * focus-return for free -- lg:hidden on both the overlay and content
       * means the trigger (UtilityBar) never renders above 1024px either,
       * so this can never be opened where the real sidebar is visible. */}
      <Dialog.Root open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/25 backdrop-blur-[1px] lg:hidden" />
          <Dialog.Content className="fixed inset-y-0 left-0 z-50 flex h-screen w-[248px] max-w-[82vw] flex-col overflow-y-auto border-r border-sidebar-border bg-sidebar px-3.5 py-4 shadow-panel lg:hidden">
            <Dialog.Title className="sr-only">Navigation</Dialog.Title>
            <Dialog.Description className="sr-only">
              Jump to another part of Fixi, or check the AI agent&apos;s status and your account.
            </Dialog.Description>
            <div className="flex items-center justify-between">
              <FixiLogo />
              <Dialog.Close asChild>
                <button
                  type="button"
                  aria-label="Close menu"
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sidebar-foreground transition-colors hover:bg-sidebar-accent"
                >
                  <X className="h-4 w-4" />
                </button>
              </Dialog.Close>
            </div>
            <SidebarNav
              pathname={pathname}
              unreadCount={unreadCount}
              onNavigate={() => setMobileNavOpen(false)}
            />
            <div className="mt-auto space-y-3">
              <AgentStatusPanel />
              <AccountRow username={creds.username} />
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <main className="min-w-0 flex-1">
        {/* Hoisted above every page so it is consistent and never
         * duplicated; matches the max-w-[1510px]/px-6 container the page
         * content uses so the bar's right edge lines up with the content
         * below it on a wide screen. */}
        <div className="mx-auto w-full max-w-[1510px] px-6 pt-4 print:hidden xl:px-7">
          <UtilityBar onOpenMenu={() => setMobileNavOpen(true)} />
        </div>
        {children}
      </main>
    </div>
  );
}

/** Standard page container: the shared max width, gutters and heading
 * block every destination uses, so eight screens written separately still
 * line up with each other and with the utility bar above them. */
export function PageContainer({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto w-full max-w-[1510px] px-6 py-6 xl:px-7">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>
      <div className="mt-6">{children}</div>
    </div>
  );
}

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("rounded-xl border border-border bg-card shadow-card", className)}>
      {children}
    </div>
  );
}
