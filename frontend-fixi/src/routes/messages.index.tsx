import { createFileRoute, Link } from "@tanstack/react-router";
import { Archive, MessageSquare, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell, Card, PageContainer } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import { EmptyState, ErrorState, LoadingRows } from "@/components/fixi/EmptyState";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import {
  filtersToSearch,
  useMessageThreads,
  useThreadListFilters,
  type ThreadListFilters,
  type ThreadListItem,
} from "@/hooks/use-messaging";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

// The standalone Messages screen (this file) and the per-thread page
// (messages.$caseId.tsx) are two separate file routes rather than one
// route + client-side "selected thread" state, specifically so the thread
// list + detail behave as a real master-detail pair: /messages/$caseId is
// independently deep-linkable and back/forward moves between threads for
// free, which a single-route local-state version wouldn't give without
// reimplementing exactly this. On narrow screens the two panes collapse
// to whichever route is active instead of both trying to fit one
// viewport.
//
// `ThreadFilterBar`/`ThreadListBody` are exported so messages.$caseId.tsx
// can render the identical list pane rather than duplicating it -- both
// files are owned by this same slice, so importing between them (instead
// of introducing a third shared component file outside the owned list)
// keeps the two screens visually identical with one implementation.

export const Route = createFileRoute("/messages/")({
  head: () => ({
    meta: [
      { title: "Messages — Fixi" },
      {
        name: "description",
        content: "Every tenant, contractor and operator conversation thread, across every case.",
      },
    ],
  }),
  component: MessagesIndexPage,
});

function MessagesIndexPage() {
  const [filters, setFilters] = useThreadListFilters();
  const [limit, setLimit] = useState(50);
  const threads = useMessageThreads(filters, limit);
  const search = filtersToSearch(filters);

  return (
    <AppShell>
      <PageContainer
        title="Messages"
        description="Every conversation thread, one per case, across tenants, contractors and operators."
      >
        <div className="grid min-h-[560px] gap-4 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
          <Card className="flex flex-col overflow-hidden p-0">
            <ThreadFilterBar filters={filters} setFilters={setFilters} />
            <ThreadListBody
              threads={threads}
              activeCaseId={null}
              search={search}
              limit={limit}
              setLimit={setLimit}
            />
          </Card>

          {/* Wide screens only -- on narrow, picking a thread navigates to
           * /messages/$caseId instead of splitting this same viewport. */}
          <Card className="hidden min-h-[420px] items-center justify-center lg:flex">
            <EmptyState
              icon={MessageSquare}
              title="Select a conversation"
              description="Choose a thread from the list to read the full conversation and reply."
            />
          </Card>
        </div>
      </PageContainer>
    </AppShell>
  );
}

export function ThreadFilterBar({
  filters,
  setFilters,
}: {
  filters: ThreadListFilters;
  setFilters: (patch: Partial<ThreadListFilters>) => void;
}) {
  const [searchInput, setSearchInput] = useState(filters.q);
  const debounced = useDebouncedValue(searchInput, 300);

  // Push the debounced value into the URL. Guarded against re-firing when
  // `filters.q` itself changed the input (e.g. a back/forward navigation)
  // rather than the other way round.
  useEffect(() => {
    if (debounced !== filters.q) setFilters({ q: debounced });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- filters/setFilters intentionally excluded, see above
  }, [debounced]);

  useEffect(() => {
    setSearchInput(filters.q);
  }, [filters.q]);

  return (
    <div className="border-b border-border p-3">
      <label className="flex h-9 items-center gap-2 rounded-lg border border-border bg-background px-3 text-muted-foreground">
        <Search className="h-3.5 w-3.5 shrink-0" />
        <input
          aria-label="Search messages"
          className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground"
          placeholder="Search text, case title or tenant…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
      </label>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <ToggleChip
          active={filters.unreadOnly}
          onClick={() => setFilters({ unreadOnly: !filters.unreadOnly })}
        >
          Unread only
        </ToggleChip>
        <ToggleChip
          active={filters.includeArchived}
          onClick={() => setFilters({ includeArchived: !filters.includeArchived })}
        >
          <Archive className="h-3 w-3" /> Include archived
        </ToggleChip>
      </div>
    </div>
  );
}

function ToggleChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "flex h-7 items-center gap-1 rounded-md border px-2.5 text-[11px] font-medium transition-colors",
        active
          ? "border-foreground bg-foreground text-background"
          : "border-border bg-card text-foreground hover:bg-accent",
      )}
    >
      {children}
    </button>
  );
}

export function ThreadListBody({
  threads,
  activeCaseId,
  search,
  limit,
  setLimit,
}: {
  threads: ReturnType<typeof useMessageThreads>;
  activeCaseId: string | null;
  search: Record<string, string>;
  limit: number;
  setLimit: (n: number) => void;
}) {
  const items = threads.data ?? [];

  if (threads.isLoading) {
    return <LoadingRows rows={6} className="p-3" />;
  }
  if (threads.isError) {
    return (
      <ErrorState
        className="border-0 shadow-none"
        detail={threads.error instanceof Error ? threads.error.message : "Unknown error"}
        onRetry={() => void threads.refetch()}
      />
    );
  }
  if (items.length === 0) {
    return (
      <EmptyState
        className="border-0 shadow-none"
        icon={MessageSquare}
        title="No conversations yet"
        description="Messages appear here once a tenant, contractor or operator sends one on a case."
      />
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      <ul>
        {items.map((item) => (
          <ThreadRow key={item.case_id} item={item} active={item.case_id === activeCaseId} search={search} />
        ))}
      </ul>
      {items.length >= limit && (
        <button
          type="button"
          onClick={() => setLimit(limit + 50)}
          className="border-t border-border py-2.5 text-center text-xs font-medium text-primary hover:underline"
        >
          Load more
        </button>
      )}
    </div>
  );
}

function ThreadRow({
  item,
  active,
  search,
}: {
  item: ThreadListItem;
  active: boolean;
  search: Record<string, string>;
}) {
  const unread = item.unread_count > 0;
  return (
    <li>
      <Link
        to="/messages/$caseId"
        params={{ caseId: item.case_id }}
        search={search}
        className={cn(
          "block border-b border-border px-4 py-3 transition-colors hover:bg-accent",
          active && "bg-accent",
        )}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className={cn("truncate text-[13px]", unread ? "font-semibold" : "font-medium")}>
              {item.tenant_name}
              <span className="font-normal text-muted-foreground"> · #{item.case_number}</span>
            </div>
            <div className="truncate text-[11px] text-muted-foreground">{item.property_address}</div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <span className="text-[10px] text-muted-foreground">
              {formatRelative(item.last_message_at)}
            </span>
            {unread && (
              <span className="rounded-full bg-status-green px-1.5 py-0.5 text-[10px] font-semibold text-status-green-foreground">
                {item.unread_count} new
              </span>
            )}
          </div>
        </div>
        <p className={cn("mt-1 line-clamp-1 text-xs", unread ? "text-foreground" : "text-muted-foreground")}>
          {item.last_sender ? `${item.last_sender}: ` : ""}
          {item.last_message_preview ?? "No messages yet."}
        </p>
        {item.is_archived && (
          <Pill tone="gray" className="mt-1.5">
            Archived
          </Pill>
        )}
      </Link>
    </li>
  );
}
