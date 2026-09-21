import { Link } from "@tanstack/react-router";
import { ArrowRight, MessageSquare } from "lucide-react";
import { Card } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import {
  normalizeAttachment,
  useMessageThread,
  type DeliveryState,
  type MessageChannel,
  type ThreadMessage,
} from "@/hooks/use-messaging";
import { formatRelative } from "@/lib/format";

const senderTone: Record<string, "gray" | "green" | "purple"> = {
  TENANT: "gray",
  CONTRACTOR: "green",
  OPERATOR: "purple",
};

const senderLabel: Record<string, string> = {
  TENANT: "Tenant",
  CONTRACTOR: "Contractor",
  OPERATOR: "Operator",
};

/** How a message actually ended up, in the operator's words.
 *
 * Saving is not sending -- an outward message with no transport behind it
 * persists as DRAFT and must never be shown as though it went out. This
 * is the one place on the ticket page that can misrepresent that, so the
 * label is derived from `delivery_state` and nothing else. */
const DELIVERY_LABEL: Record<DeliveryState, string> = {
  DRAFT: "Draft — not sent",
  INTERNAL_NOTE: "Internal note",
  QUEUED: "Queued",
  SENT: "Sent",
  DELIVERED: "Delivered",
  FAILED: "Failed to send",
  RECEIVED: "Received",
};

const DELIVERY_TONE: Record<DeliveryState, "gray" | "green" | "amber" | "red" | "blue"> = {
  DRAFT: "amber",
  INTERNAL_NOTE: "gray",
  QUEUED: "blue",
  SENT: "green",
  DELIVERED: "green",
  FAILED: "red",
  RECEIVED: "gray",
};

const CHANNEL_LABEL: Record<MessageChannel, string> = {
  INTERNAL: "Internal",
  EMAIL: "Email",
  SMS: "SMS",
  VOICE: "Voice",
};

/** The conversation on this ticket.
 *
 * Reads the real thread (`GET /messages/threads/{case_id}`) rather than
 * the older read-only `GET /cases/{id}/messages`. That older endpoint
 * returns no channel and no delivery state, so this panel could not tell
 * a sent message from an unsent draft -- on the one screen where that
 * distinction matters most. Its previous docstring also claimed no
 * send endpoint existed; one has existed since the migration, and the
 * Messages destination uses it.
 *
 * Composing deliberately lives on that full conversation page rather than
 * being duplicated here: this panel is context while you work the ticket,
 * and one composer with one set of delivery semantics is easier to keep
 * honest than two. The link goes there. */
export function MessagesPanel({ caseId }: { caseId: string }) {
  const thread = useMessageThread(caseId);
  const items = thread.data?.items ?? [];

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-semibold">Messages</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Tenant, contractor and operator messages on this ticket. Not read by the AI agent — chat
            history is never authoritative state.
          </p>
        </div>
        <Link
          to="/messages/$caseId"
          params={{ caseId }}
          className="flex shrink-0 items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium transition-colors hover:bg-accent"
        >
          Open conversation <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>

      {thread.isLoading && <p className="mt-4 text-xs text-muted-foreground">Loading…</p>}
      {thread.isError && <p className="mt-4 text-xs text-destructive">Could not load messages.</p>}
      {!thread.isLoading && !thread.isError && items.length === 0 && (
        <p className="mt-4 text-xs text-muted-foreground">No messages on this ticket yet.</p>
      )}

      <ul className="mt-4 space-y-3">
        {items.map((m) => (
          <MessageRow key={m.id} message={m} />
        ))}
      </ul>
    </Card>
  );
}

function MessageRow({ message }: { message: ThreadMessage }) {
  const attachments = (message.attachments ?? []).map(normalizeAttachment);

  return (
    <li className="rounded-lg border border-border p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2.5">
          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent">
            <MessageSquare className="h-3.5 w-3.5" />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-[13px] font-semibold">
              {message.sender_name}
              <Pill tone={senderTone[message.sender_type] ?? "gray"}>
                {senderLabel[message.sender_type] ?? message.sender_type}
              </Pill>
              <Pill tone={DELIVERY_TONE[message.delivery_state] ?? "gray"}>
                {DELIVERY_LABEL[message.delivery_state] ?? message.delivery_state}
              </Pill>
              {message.channel !== "INTERNAL" && (
                <span className="text-[11px] font-normal text-muted-foreground">
                  {CHANNEL_LABEL[message.channel] ?? message.channel}
                </span>
              )}
            </div>
            <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{message.text}</p>
            {attachments.length > 0 && (
              <ul className="mt-1.5 flex flex-wrap gap-1.5">
                {attachments.map((a) => (
                  <li
                    key={a.id}
                    className="rounded-md border border-border px-1.5 py-px text-[10px] text-muted-foreground"
                  >
                    {a.label}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        <span className="shrink-0 text-[11px] text-muted-foreground">
          {formatRelative(message.created_at)}
        </span>
      </div>
    </li>
  );
}
