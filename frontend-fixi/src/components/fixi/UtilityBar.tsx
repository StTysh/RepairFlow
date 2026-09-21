import * as Popover from "@radix-ui/react-popover";
import { Link } from "@tanstack/react-router";
import { Bell, Building2, HardHat, Menu, Search, Users, Wrench } from "lucide-react";
import { useState } from "react";
import type { SearchResultItem } from "@/api/types";
import { NewTicketDialog } from "@/components/fixi/NewTicketDialog";
import { MIN_SEARCH_LENGTH, useGlobalSearch } from "@/hooks/use-global-search";
import { useNotifications } from "@/hooks/use-notifications";
import { useCaseSearch } from "@/lib/case-search-context";
import { formatRelative } from "@/lib/format";

/** Global search + notifications + "New Ticket", hoisted into AppShell so it
 * renders once above every page instead of being duplicated per-route (see
 * AppShell.tsx).
 *
 * Below 1024px this is also the app's only persistent header, so it carries
 * the menu button that opens AppShell's navigation drawer (see HIGH-1,
 * docs/audit/08) -- hidden at lg and up, where the real sidebar is visible
 * instead. */
export function UtilityBar({ onOpenMenu }: { onOpenMenu: () => void }) {
  return (
    <div className="flex items-center justify-end gap-2.5 py-2">
      <button
        type="button"
        onClick={onOpenMenu}
        aria-label="Open navigation menu"
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border bg-card text-foreground shadow-card transition-colors hover:bg-accent lg:hidden"
      >
        <Menu className="h-4 w-4" />
      </button>
      <GlobalSearch />
      <NotificationsBell />
      <NewTicketDialog />
    </div>
  );
}

const RESULT_ICON = {
  case: Wrench,
  property: Building2,
  tenant: Users,
  contractor: HardHat,
} as const;

const GROUP_LABEL: Record<string, string> = {
  case: "Tickets",
  property: "Properties",
  tenant: "Tenants",
  contractor: "Contractors",
};

/** One hit, as a typed <Link>.
 *
 * The API also returns a ready-made `route` string, but this app's router is
 * typed and the four result kinds map onto exactly four known routes, so
 * switching on `type` keeps the link checked at compile time instead of
 * casting a server string into the route table. If a fifth result type is
 * ever added server-side it will fail here loudly rather than 404 silently. */
function SearchHit({ item, onNavigate }: { item: SearchResultItem; onNavigate: () => void }) {
  const Icon = RESULT_ICON[item.type];
  const className =
    "flex items-start gap-2.5 rounded-lg px-2 py-2 text-left hover:bg-accent focus-visible:bg-accent focus-visible:outline-none";
  const body = (
    <>
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={1.8} />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="truncate text-xs font-medium text-foreground">{item.label}</span>
          {item.is_archived && (
            <span className="shrink-0 rounded-full bg-muted px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">
              Sample
            </span>
          )}
        </span>
        {item.sublabel && (
          <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
            {item.sublabel}
          </span>
        )}
      </span>
    </>
  );

  switch (item.type) {
    case "case":
      return (
        <Link
          to="/maintenance/tickets/$ticketId/{-$section}"
          params={{ ticketId: item.id, section: undefined }}
          className={className}
          onClick={onNavigate}
        >
          {body}
        </Link>
      );
    case "property":
      return (
        <Link
          to="/properties/$propertyId/history"
          params={{ propertyId: item.id }}
          className={className}
          onClick={onNavigate}
        >
          {body}
        </Link>
      );
    case "tenant":
      return (
        <Link
          to="/tenants/$tenantId"
          params={{ tenantId: item.id }}
          className={className}
          onClick={onNavigate}
        >
          {body}
        </Link>
      );
    case "contractor":
      return (
        <Link
          to="/contractors/$contractorId"
          params={{ contractorId: item.id }}
          className={className}
          onClick={onNavigate}
        >
          {body}
        </Link>
      );
  }
}

/** The search box, wired to GET /api/v1/search.
 *
 * Until 2026-09-21 this box called nothing: it wrote into CaseSearchContext,
 * which only the Maintenance list read, so it client-filtered the tickets
 * already on screen while the placeholder promised addresses, tenants and
 * contractors. Typing a contractor's name found nothing even though the API
 * answered it correctly. It still writes to the context -- the Maintenance
 * list's inline filter is genuinely useful while you are looking at it --
 * but now it also queries the real endpoint and offers every match. */
function GlobalSearch() {
  const { search, setSearch } = useCaseSearch();
  const [focused, setFocused] = useState(false);
  const results = useGlobalSearch(search);

  const trimmed = search.trim();
  const longEnough = trimmed.length >= MIN_SEARCH_LENGTH;
  const open = focused && longEnough;
  const groups = (results.data?.groups ?? []).filter((g) => g.items.length > 0);
  const totalHits = groups.reduce((n, g) => n + g.items.length, 0);

  return (
    <Popover.Root open={open}>
      <Popover.Anchor asChild>
        <label className="flex h-9 w-[340px] max-w-[42vw] items-center gap-2 rounded-xl border border-border bg-card px-3 text-muted-foreground shadow-card">
          <Search className="h-4 w-4 shrink-0" />
          <input
            aria-label="Search"
            role="combobox"
            aria-expanded={open}
            aria-controls="global-search-results"
            autoComplete="off"
            className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground"
            placeholder="Search tickets, addresses, tenants or contractors..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setFocused(false);
            }}
          />
        </label>
      </Popover.Anchor>
      <Popover.Portal>
        <Popover.Content
          id="global-search-results"
          align="start"
          sideOffset={6}
          // Keep the caret in the input: without this, mousing down on a
          // result blurs the field, `focused` flips false, and the popover
          // unmounts before the click ever lands on the link.
          onMouseDown={(e) => e.preventDefault()}
          onOpenAutoFocus={(e) => e.preventDefault()}
          className="z-50 w-[380px] max-w-[92vw] rounded-xl border border-border bg-card p-2 shadow-panel"
        >
          {results.isLoading ? (
            <p className="px-2 py-4 text-center text-xs text-muted-foreground">Searching…</p>
          ) : results.isError ? (
            <p className="px-2 py-4 text-center text-xs text-muted-foreground">
              Could not reach search.
            </p>
          ) : totalHits === 0 ? (
            <p className="px-2 py-4 text-center text-xs text-muted-foreground">
              Nothing matches “{trimmed}”.
            </p>
          ) : (
            <div className="max-h-[420px] overflow-y-auto">
              {groups.map((group) => (
                <div key={group.type} className="mb-1 last:mb-0">
                  <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {GROUP_LABEL[group.type] ?? group.type}
                  </div>
                  <div className="space-y-0.5">
                    {group.items.map((item) => (
                      <SearchHit
                        key={`${item.type}:${item.id}`}
                        item={item}
                        onNavigate={() => setFocused(false)}
                      />
                    ))}
                  </div>
                  {group.has_more && (
                    <p className="px-2 py-1 text-[10px] text-muted-foreground">
                      More {GROUP_LABEL[group.type]?.toLowerCase() ?? group.type} match — keep
                      typing to narrow.
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
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
