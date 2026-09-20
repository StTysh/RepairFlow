import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import { useMemo } from "react";
import { toast } from "sonner";
import { request, type OperatorCredentials } from "@/api/client";
import { useAuthedCreds } from "@/lib/auth-context";

// This app's house pattern keeps wire types in src/api/types.ts and
// fetchers in src/api/endpoints.ts -- but that file's `Message`/
// `CaseMessagesResponse` are the OLD read-only per-case thread shape
// (sender_type/sender_name/text/photo_url only, no channel or delivery
// state -- see MessagesPanel.tsx). Importing those here would typecheck
// while being silently wrong. The messaging backend (GET/POST
// /api/v1/messages/threads...) is being built concurrently by another
// agent in this same working tree and isn't on disk yet (see
// NEEDS_FROM_ROOT_messaging.md), so the types and fetch calls below live
// here instead of in the shared api/ files, against the documented
// contract. Once the backend lands and api/types.ts +. api/endpoints.ts
// are extended for real, these should be hoisted there and this file
// trimmed to just the hooks.

export type DeliveryState =
  | "DRAFT"
  | "INTERNAL_NOTE"
  | "QUEUED"
  | "SENT"
  | "DELIVERED"
  | "FAILED"
  | "RECEIVED";

export type MessageChannel = "INTERNAL" | "EMAIL" | "SMS" | "VOICE";

export interface ThreadListItem {
  case_id: string;
  case_number: number;
  case_title: string;
  property_address: string;
  tenant_name: string;
  last_message_preview: string | null;
  last_message_at: string | null;
  last_sender: string | null;
  unread_count: number;
  total_count: number;
  is_archived: boolean;
}

interface ThreadsListResponseRaw {
  items?: ThreadListItem[];
  threads?: ThreadListItem[];
}

/** Raw attachment shape isn't specified beyond "attachments[]" -- accept
 * either a bare document-id string or an object carrying one, and
 * normalize with `normalizeAttachment` below rather than guessing one
 * shape and breaking on the other. */
export type MessageAttachment = string | { id: string; name?: string | null; filename?: string | null };

export interface ThreadMessage {
  id: string;
  sender_type: string;
  sender_name: string;
  text: string;
  created_at: string;
  channel: MessageChannel;
  delivery_state: DeliveryState;
  delivery_detail: string | null;
  attachments: MessageAttachment[];
  read_at: string | null;
  communication_id: string | null;
  photo_url: string | null;
}

interface ThreadDetailResponseRaw {
  case_id?: string;
  case_number?: number;
  case_title?: string;
  items?: ThreadMessage[];
  messages?: ThreadMessage[];
}

export interface ThreadDetail {
  case_id: string;
  case_number: number | null;
  case_title: string | null;
  items: ThreadMessage[];
}

export function normalizeAttachment(a: MessageAttachment): { id: string; label: string } {
  if (typeof a === "string") return { id: a, label: a };
  const label = a.name ?? a.filename ?? a.id;
  return { id: a.id, label };
}

// --- Thread list filters, persisted in the URL query string -----------------
//
// Deliberately NOT using validateSearch -- see properties.$propertyId.
// history.tsx's Route comment: it froze this app's renderer on every load.
// Reads via useRouterState's location.searchStr (reactive across
// back/forward, unlike a one-off window.location.search read) and writes
// via a plain, unvalidated useNavigate({ search }) call.

export interface ThreadListFilters {
  q: string;
  unreadOnly: boolean;
  includeArchived: boolean;
}

const EMPTY_FILTERS: ThreadListFilters = { q: "", unreadOnly: false, includeArchived: false };

export function useThreadListFilters(): [ThreadListFilters, (patch: Partial<ThreadListFilters>) => void] {
  const searchStr = useRouterState({ select: (s) => s.location.searchStr });
  // This hook is shared by both /messages and /messages/$caseId (deliberately
  // -- see messages.index.tsx's file comment), so it has no single static
  // `from` to bind useNavigate() to. Without one, TanStack Router can't
  // resolve a concrete search schema for the (equally dynamic) target route
  // and types the search reducer as accepting only `never`. Search here is
  // intentionally unvalidated on both routes (no validateSearch -- see
  // properties.$propertyId.history.tsx's Route comment for why this app
  // avoids it), so a plain query-string rewrite is genuinely safe; the loose
  // signature below reflects that rather than fighting the generic with
  // per-callsite `as never` casts.
  const navigate = useNavigate() as unknown as (opts: {
    search: () => Record<string, string>;
    replace?: boolean;
  }) => void;

  const filters = useMemo<ThreadListFilters>(() => {
    if (!searchStr) return EMPTY_FILTERS;
    const params = new URLSearchParams(searchStr);
    return {
      q: params.get("q") ?? "",
      unreadOnly: params.get("unread") === "1",
      includeArchived: params.get("archived") === "1",
    };
  }, [searchStr]);

  function setFilters(patch: Partial<ThreadListFilters>) {
    const next = { ...filters, ...patch };
    const params = new URLSearchParams();
    if (next.q.trim()) params.set("q", next.q.trim());
    if (next.unreadOnly) params.set("unread", "1");
    if (next.includeArchived) params.set("archived", "1");
    // No `to` -- defaults to the current route ('.'), so this only ever
    // rewrites the query string, on whichever of /messages or
    // /messages/$caseId is currently mounted.
    void navigate({
      search: () => Object.fromEntries(params.entries()),
      replace: true,
    });
  }

  return [filters, setFilters];
}

/** Builds the current filter state as a plain search object, for handing to
 * a <Link search={...}> so filters survive navigating between threads. */
export function filtersToSearch(filters: ThreadListFilters): Record<string, string> {
  const params = new URLSearchParams();
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.unreadOnly) params.set("unread", "1");
  if (filters.includeArchived) params.set("archived", "1");
  return Object.fromEntries(params.entries());
}

// --- Queries / mutations -----------------------------------------------------

function threadsQueryParams(filters: ThreadListFilters, limit: number): string {
  const params = new URLSearchParams();
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.unreadOnly) params.set("unread_only", "true");
  if (filters.includeArchived) params.set("include_archived", "true");
  params.set("limit", String(limit));
  params.set("offset", "0");
  return params.toString();
}

export function useMessageThreads(filters: ThreadListFilters, limit: number) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["messages-threads", filters, limit],
    refetchInterval: 5000,
    queryFn: async () => {
      const raw = await request<ThreadsListResponseRaw>(
        creds,
        `/api/v1/messages/threads?${threadsQueryParams(filters, limit)}`,
      );
      return raw.items ?? raw.threads ?? [];
    },
  });
}

export function useMessageThread(caseId: string | null) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["messages-thread", caseId],
    enabled: caseId !== null,
    refetchInterval: 4000,
    queryFn: async () => {
      const raw = await request<ThreadDetailResponseRaw>(creds, `/api/v1/messages/threads/${caseId}`);
      const items = raw.items ?? raw.messages ?? [];
      const detail: ThreadDetail = {
        case_id: raw.case_id ?? caseId!,
        case_number: raw.case_number ?? null,
        case_title: raw.case_title ?? null,
        items,
      };
      return detail;
    },
  });
}

export interface SendMessageBody {
  text: string;
  channel: MessageChannel;
  attachments?: string[];
}

function invalidateMessaging(
  queryClient: ReturnType<typeof useQueryClient>,
  caseId: string,
  { unreadCount = false }: { unreadCount?: boolean } = {},
) {
  void queryClient.invalidateQueries({ queryKey: ["messages-thread", caseId] });
  void queryClient.invalidateQueries({ queryKey: ["messages-threads"] });
  if (unreadCount) void queryClient.invalidateQueries({ queryKey: ["messages-unread-count"] });
}

/** Posts a new message. Deliberately writes nothing optimistic to the
 * cache -- the only honest way to satisfy "never render a message as sent
 * unless delivery_state actually says so" is to let the server's real
 * delivery_state come back on refetch, not to paint a fake "Sent" bubble
 * ahead of it. The composer clears its input only once this resolves. */
export function useSendMessage(caseId: string) {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SendMessageBody) =>
      request<ThreadMessage>(creds, `/api/v1/messages/threads/${caseId}`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => invalidateMessaging(queryClient, caseId),
    onError: (error: Error) => toast.error(`Could not save message: ${error.message}`),
  });
}

/** Marks the whole thread read. Fired once per opened case by the thread
 * route (guarded with a ref there so the poll interval can't re-fire it,
 * and so it can never race the per-message "mark unread" action). */
export function useMarkThreadRead(caseId: string) {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      request<unknown>(creds, `/api/v1/messages/threads/${caseId}/read`, { method: "POST" }),
    onSuccess: () => invalidateMessaging(queryClient, caseId, { unreadCount: true }),
    onError: () => toast.error("Could not mark this thread as read."),
  });
}

export function useMarkMessageUnread(caseId: string) {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) =>
      request<unknown>(creds, `/api/v1/messages/${messageId}/unread`, { method: "POST" }),
    onSuccess: () => {
      invalidateMessaging(queryClient, caseId, { unreadCount: true });
      toast.success("Marked as unread");
    },
    onError: (error: Error) => toast.error(`Could not mark as unread: ${error.message}`),
  });
}

export type { OperatorCredentials };
