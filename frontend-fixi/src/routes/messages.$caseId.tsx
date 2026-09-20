import { createFileRoute, Link } from "@tanstack/react-router";
import { format, isToday, isYesterday } from "date-fns";
import { ArrowLeft, ExternalLink, Mail, Paperclip, PhoneCall } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { authHeader, BASE_URL } from "@/api/client";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import { ErrorState, LoadingRows } from "@/components/fixi/EmptyState";
import { ThreadFilterBar, ThreadListBody } from "@/routes/messages.index";
import {
  filtersToSearch,
  normalizeAttachment,
  useMarkMessageUnread,
  useMarkThreadRead,
  useMessageThread,
  useMessageThreads,
  useSendMessage,
  useThreadListFilters,
  type MessageAttachment,
  type MessageChannel,
  type DeliveryState,
  type ThreadMessage,
} from "@/hooks/use-messaging";
import { useAuthedCreds } from "@/lib/auth-context";
import { formatTime, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/messages/$caseId")({
  head: ({ params }) => ({
    meta: [
      { title: `Conversation — Fixi` },
      { name: "description", content: `Message thread for case ${params.caseId}.` },
    ],
  }),
  component: ThreadPage,
});

const DELIVERY_TONE: Record<DeliveryState, "gray" | "purple" | "amber" | "blue" | "green" | "red"> =
  {
    DRAFT: "gray",
    INTERNAL_NOTE: "purple",
    QUEUED: "amber",
    SENT: "blue",
    DELIVERED: "green",
    FAILED: "red",
    RECEIVED: "gray",
  };

const DELIVERY_LABEL: Record<DeliveryState, string> = {
  DRAFT: "Draft — not sent",
  INTERNAL_NOTE: "Internal note",
  QUEUED: "Queued",
  SENT: "Sent",
  DELIVERED: "Delivered",
  FAILED: "Failed",
  RECEIVED: "Received",
};

const SENDER_TONE: Record<string, "gray" | "green" | "purple" | "blue"> = {
  TENANT: "gray",
  CONTRACTOR: "green",
  OPERATOR: "purple",
};

function senderTone(t: string) {
  return SENDER_TONE[t.toUpperCase()] ?? "blue";
}

function dayLabel(iso: string): string {
  const d = new Date(iso);
  if (isToday(d)) return "Today";
  if (isYesterday(d)) return "Yesterday";
  return format(d, "d MMM yyyy");
}

function groupByDay(
  items: ThreadMessage[],
): Array<{ key: string; label: string; items: ThreadMessage[] }> {
  const groups: Array<{ key: string; label: string; items: ThreadMessage[] }> = [];
  for (const m of items) {
    const key = m.created_at.slice(0, 10);
    let group = groups[groups.length - 1];
    if (!group || group.key !== key) {
      group = { key, label: dayLabel(m.created_at), items: [] };
      groups.push(group);
    }
    group.items.push(m);
  }
  return groups;
}

function ThreadPage() {
  const { caseId } = Route.useParams();
  const [filters, setFilters] = useThreadListFilters();
  const search = filtersToSearch(filters);
  const [limit, setLimit] = useState(50);
  const threads = useMessageThreads(filters, limit);
  const thread = useMessageThread(caseId);
  const markRead = useMarkThreadRead(caseId);

  // Fire "mark thread read" exactly once per case opened -- not in a plain
  // effect keyed on the polled thread data (that would re-fire every poll
  // tick and stomp the per-message "mark unread" action the moment
  // someone clicked it).
  const markedRef = useRef<string | null>(null);
  useEffect(() => {
    if (thread.isSuccess && markedRef.current !== caseId) {
      markedRef.current = caseId;
      markRead.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- markRead intentionally excluded, see above
  }, [thread.isSuccess, caseId]);

  return (
    <AppShell>
      <div className="mx-auto max-w-[1510px] px-6 py-4 xl:px-7">
        <Link
          to="/messages"
          search={search}
          className="flex w-fit items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground lg:hidden"
        >
          <ArrowLeft className="h-4 w-4" /> Back to messages
        </Link>

        <div className="mt-2 grid h-[75vh] min-h-[560px] gap-4 lg:mt-0 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
          {/* Wide screens only -- on narrow, this thread is the whole
           * screen and the list is reached via Back above. */}
          <Card className="hidden flex-col overflow-hidden lg:flex">
            <ThreadFilterBar filters={filters} setFilters={setFilters} />
            <ThreadListBody
              threads={threads}
              activeCaseId={caseId}
              search={search}
              limit={limit}
              setLimit={setLimit}
            />
          </Card>

          <Card className="flex min-h-[560px] flex-col overflow-hidden">
            <ThreadDetail caseId={caseId} thread={thread} />
          </Card>
        </div>
      </div>
    </AppShell>
  );
}

function ThreadDetail({
  caseId,
  thread,
}: {
  caseId: string;
  thread: ReturnType<typeof useMessageThread>;
}) {
  if (thread.isLoading) {
    return (
      <div className="p-5">
        <LoadingRows rows={5} />
      </div>
    );
  }
  if (thread.isError || !thread.data) {
    return (
      <ErrorState
        className="border-0 shadow-none"
        detail={
          thread.error instanceof Error ? thread.error.message : "Could not load this thread."
        }
        onRetry={() => void thread.refetch()}
      />
    );
  }

  const { items, case_number, case_title } = thread.data;
  const groups = groupByDay(items);

  return (
    <>
      <div className="flex items-center justify-between gap-3 border-b border-border p-4">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">
            {case_title ?? `Case ${caseId}`}
            {case_number !== null && (
              <span className="text-muted-foreground"> · #{case_number}</span>
            )}
          </div>
          <div className="text-[11px] text-muted-foreground">
            {items.length} message{items.length === 1 ? "" : "s"}
          </div>
        </div>
        <Link
          to="/maintenance/tickets/$ticketId/{-$section}"
          params={{ ticketId: caseId, section: undefined }}
          className="flex shrink-0 items-center gap-1 text-xs font-medium text-primary hover:underline"
        >
          Open case <ExternalLink className="h-3.5 w-3.5" />
        </Link>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {items.length === 0 ? (
          <p className="py-8 text-center text-xs text-muted-foreground">
            No messages on this case yet — start the conversation below.
          </p>
        ) : (
          <div className="space-y-5">
            {groups.map((g) => (
              <div key={g.key}>
                <div className="mb-2 flex items-center gap-2">
                  <span className="h-px flex-1 bg-border" />
                  <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                    {g.label}
                  </span>
                  <span className="h-px flex-1 bg-border" />
                </div>
                <ul className="space-y-2.5">
                  {g.items.map((m) => (
                    <MessageRow key={m.id} caseId={caseId} message={m} />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>

      <Composer caseId={caseId} />
    </>
  );
}

function MessageRow({ caseId, message }: { caseId: string; message: ThreadMessage }) {
  const markUnread = useMarkMessageUnread(caseId);

  if (message.channel === "VOICE") {
    return (
      <li className="rounded-lg border border-border bg-muted/40 p-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent">
              <PhoneCall className="h-3.5 w-3.5" />
            </span>
            <div className="min-w-0">
              <div className="text-[13px] font-semibold">{message.sender_name}</div>
              <p className="text-xs text-muted-foreground">
                A recorded phone call, not a chat message — see the transcript and recording.
              </p>
            </div>
          </div>
          <Link
            to="/maintenance/tickets/$ticketId/{-$section}"
            params={{ ticketId: caseId, section: "calls" }}
            className="shrink-0 text-xs font-medium text-primary hover:underline"
          >
            View in Calls →
          </Link>
        </div>
      </li>
    );
  }

  return (
    <li className="group rounded-lg border border-border p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 text-[13px] font-semibold">
            {message.sender_name}
            <Pill tone={senderTone(message.sender_type)}>
              {titleCase(message.sender_type || "unknown")}
            </Pill>
            <Pill tone={DELIVERY_TONE[message.delivery_state]}>
              {DELIVERY_LABEL[message.delivery_state]}
            </Pill>
          </div>
          <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed">{message.text}</p>
          {message.delivery_detail && (
            <p className="mt-1 text-[11px] text-muted-foreground">{message.delivery_detail}</p>
          )}
          {message.attachments.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {message.attachments.map((a) => (
                <AttachmentLink key={normalizeAttachment(a).id} attachment={a} />
              ))}
            </div>
          )}
          {message.photo_url && <PhotoThumb url={message.photo_url} />}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <span className="text-[11px] text-muted-foreground">
            {formatTime(message.created_at)}
          </span>
          <button
            type="button"
            title="Mark this message unread"
            aria-label="Mark message unread"
            onClick={() => markUnread.mutate(message.id)}
            disabled={markUnread.isPending}
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
          >
            <Mail className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </li>
  );
}

function AttachmentLink({ attachment }: { attachment: MessageAttachment }) {
  const creds = useAuthedCreds();
  const [busy, setBusy] = useState(false);
  const { id, label } = normalizeAttachment(attachment);

  async function open() {
    setBusy(true);
    try {
      const res = await fetch(`${BASE_URL}/api/v1/documents/${id}/content`, {
        headers: { Authorization: authHeader(creds) },
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      toast.error("Could not open attachment.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={() => void open()}
      disabled={busy}
      className="flex items-center gap-1 rounded-md border border-border bg-muted px-2 py-1 text-[11px] font-medium hover:bg-accent disabled:opacity-50"
    >
      <Paperclip className="h-3 w-3" /> {busy ? "Opening…" : label}
    </button>
  );
}

/** No message-photo upload path or media-serving route exists yet (see
 * MessagesPanel.tsx's identical caveat on the old read-only thread) --
 * rendered as a direct <img src>, with a graceful fallback rather than a
 * broken-image icon if it 404s/401s. */
function PhotoThumb({ url }: { url: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <p className="mt-2 text-[11px] text-muted-foreground">Photo unavailable.</p>;
  return (
    <img
      src={url}
      alt="Message attachment"
      loading="lazy"
      onError={() => setFailed(true)}
      className="mt-2 h-16 w-24 rounded-md border border-border object-cover"
    />
  );
}

const CHANNEL_OPTIONS: Array<{ value: MessageChannel; label: string }> = [
  { value: "INTERNAL", label: "Internal note" },
  { value: "EMAIL", label: "Email" },
  { value: "SMS", label: "SMS" },
];

function Composer({ caseId }: { caseId: string }) {
  const [channel, setChannel] = useState<MessageChannel>("INTERNAL");
  const [text, setText] = useState("");
  const send = useSendMessage(caseId);

  const trimmed = text.trim();
  const canSubmit = trimmed.length > 0 && !send.isPending;

  async function handleSubmit() {
    if (!canSubmit) return;
    try {
      await send.mutateAsync({ text: trimmed, channel });
      setText("");
    } catch {
      // Surfaced via toast in useSendMessage's onError; keep the draft
      // text in the box so the operator can retry without retyping.
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      void handleSubmit();
    }
  }

  const buttonLabel = channel === "INTERNAL" ? "Add internal note" : "Save draft";

  return (
    <div className="border-t border-border p-4">
      <div className="flex gap-1.5">
        {CHANNEL_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => setChannel(opt.value)}
            aria-pressed={channel === opt.value}
            className={cn(
              "h-8 rounded-lg border px-3 text-xs font-medium transition-colors",
              channel === opt.value
                ? "border-foreground bg-foreground text-background"
                : "border-border bg-card text-foreground hover:bg-accent",
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
      {channel !== "INTERNAL" && (
        <p className="mt-2 text-[11px] text-muted-foreground">
          No delivery transport is configured for {channel === "EMAIL" ? "email" : "SMS"} yet — this
          will be saved as a draft, not sent to the tenant.
        </p>
      )}
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={send.isPending}
        placeholder={channel === "INTERNAL" ? "Add an internal note…" : "Draft a message…"}
        aria-label="Message text"
        className="mt-2 h-20 w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring disabled:opacity-60"
      />
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="text-[10px] text-muted-foreground">Ctrl/Cmd + Enter to submit</span>
        <button
          type="button"
          onClick={() => void handleSubmit()}
          disabled={!canSubmit}
          className="flex h-9 items-center rounded-lg bg-primary px-4 text-xs font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        >
          {send.isPending ? "Saving…" : buttonLabel}
        </button>
      </div>
    </div>
  );
}
