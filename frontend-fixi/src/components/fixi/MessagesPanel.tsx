import { useState } from "react";
import { MessageSquare } from "lucide-react";
import { Card } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import { useCaseMessages } from "@/hooks/use-case-messages";
import { formatRelative } from "@/lib/format";
import type { Message, MessageSenderType } from "@/api/types";

const senderTone: Record<MessageSenderType, "gray" | "green" | "purple"> = {
  TENANT: "gray",
  CONTRACTOR: "green",
  OPERATOR: "purple",
};

const senderLabel: Record<MessageSenderType, string> = {
  TENANT: "Tenant",
  CONTRACTOR: "Contractor",
  OPERATOR: "Operator",
};

/** Read-only tenant/contractor/operator message thread -- GET
 * /api/v1/cases/{id}/messages (backend/app/schemas.py Message). Display
 * only: chat history is never authoritative state and the AI coordinator
 * never reads it (CLAUDE.md). There's also no write/send endpoint yet, so
 * this renders only what the API returns -- no composer with nothing to
 * call behind it. */
export function MessagesPanel({ caseId }: { caseId: string }) {
  const messages = useCaseMessages(caseId);
  const items = messages.data?.items ?? [];

  return (
    <Card className="p-5">
      <div>
        <h2 className="text-[15px] font-semibold">Messages</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Tenant, contractor and operator messages on this ticket -- display only, not read by the
          AI agent.
        </p>
      </div>
      {messages.isLoading && <p className="mt-4 text-xs text-muted-foreground">Loading…</p>}
      {messages.isError && (
        <p className="mt-4 text-xs text-destructive">Could not load messages.</p>
      )}
      {!messages.isLoading && !messages.isError && items.length === 0 && (
        <p className="mt-4 text-xs text-muted-foreground">No messages yet.</p>
      )}
      <ul className="mt-4 space-y-3">
        {items.map((m) => (
          <MessageRow key={m.id} message={m} />
        ))}
      </ul>
    </Card>
  );
}

function MessageRow({ message }: { message: Message }) {
  return (
    <li className="rounded-lg border border-border p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2.5">
          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent">
            <MessageSquare className="h-3.5 w-3.5" />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[13px] font-semibold">
              {message.sender_name}
              <Pill tone={senderTone[message.sender_type]}>{senderLabel[message.sender_type]}</Pill>
            </div>
            <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{message.text}</p>
            {message.photo_url && <MessagePhoto url={message.photo_url} />}
          </div>
        </div>
        <span className="shrink-0 text-[11px] text-muted-foreground">
          {formatRelative(message.created_at)}
        </span>
      </div>
    </li>
  );
}

/** No message-photo upload path or media-serving route exists yet
 * (backend: photo_url is a plain nullable column with nothing that writes
 * to it in this phase -- see backend/app/models.py MessageModel), so
 * whatever shape a future producer puts there is untested here. Rendered
 * as a direct <img src>, same as any other URL field, but with a graceful
 * fallback rather than a broken-image icon if it 404s/401s. */
function MessagePhoto({ url }: { url: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return <p className="mt-2 text-[11px] text-muted-foreground">Photo unavailable.</p>;
  }
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
