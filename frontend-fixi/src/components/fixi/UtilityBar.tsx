import * as Popover from "@radix-ui/react-popover";
import { Link } from "@tanstack/react-router";
import { Bell, Search } from "lucide-react";
import { NewTicketDialog } from "@/components/fixi/NewTicketDialog";
import { useNotifications } from "@/hooks/use-notifications";
import { useCaseSearch } from "@/lib/case-search-context";
import { formatRelative } from "@/lib/format";

/** Global search + notifications + "New Ticket", hoisted into AppShell so it
 * renders once above every page instead of being duplicated per-route (see
 * AppShell.tsx). Search writes into the shared CaseSearchContext; only the
 * Maintenance list currently reads it back out to filter its case list --
 * on any other page the box still works, it just has nothing to filter yet. */
export function UtilityBar() {
  const { search, setSearch } = useCaseSearch();
  return (
    <div className="flex items-center justify-end gap-2.5 py-2">
      <label className="flex h-9 w-[340px] max-w-[42vw] items-center gap-2 rounded-xl border border-border bg-card px-3 text-muted-foreground shadow-card">
        <Search className="h-4 w-4 shrink-0" />
        <input
          aria-label="Search"
          className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground"
          placeholder="Search tickets, addresses, tenants or contractors..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </label>
      <NotificationsBell />
      <NewTicketDialog />
    </div>
  );
}

/** Bell icon + unread badge (real unread_count off GET /notifications, never
 * a hardcoded number) with a popover listing each item linking through to
 * its case. */
function NotificationsBell() {
  const notifications = useNotifications();
  const unreadCount = notifications.data?.unread_count ?? 0;
  const items = notifications.data?.items ?? [];

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={unreadCount > 0 ? `Notifications (${unreadCount} unread)` : "Notifications"}
          className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border bg-card text-foreground shadow-card transition-colors hover:bg-accent"
        >
          <Bell className="h-4 w-4" />
          {unreadCount > 0 && (
            <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[9px] font-semibold text-destructive-foreground ring-2 ring-card">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          className="z-50 w-80 max-w-[90vw] rounded-xl border border-border bg-card p-2 shadow-panel"
        >
          <div className="px-2 py-1.5 text-xs font-semibold text-foreground">Notifications</div>
          {items.length === 0 ? (
            <p className="px-2 py-4 text-center text-xs text-muted-foreground">
              {notifications.isLoading
                ? "Loading…"
                : notifications.isError
                  ? "Could not load notifications."
                  : "Nothing to show."}
            </p>
          ) : (
            <div className="max-h-80 space-y-0.5 overflow-y-auto">
              {items.map((n) => (
                <Popover.Close asChild key={n.id}>
                  <Link
                    to="/maintenance/tickets/$ticketId/{-$section}"
                    params={{ ticketId: n.case_id, section: undefined }}
                    className="block rounded-lg px-2 py-2 hover:bg-accent"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-xs font-medium text-foreground">
                        #{n.case_number} · {n.case_title}
                      </span>
                      {n.unread && (
                        <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                      )}
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">
                      {n.message}
                    </p>
                    <p className="mt-0.5 text-[10px] text-muted-foreground">
                      {formatRelative(n.occurred_at)}
                    </p>
                  </Link>
                </Popover.Close>
              ))}
            </div>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
