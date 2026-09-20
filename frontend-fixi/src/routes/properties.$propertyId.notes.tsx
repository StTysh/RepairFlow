import { createFileRoute } from "@tanstack/react-router";
import { StickyNote } from "lucide-react";
import { useState } from "react";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { EmptyState, ErrorState, LoadingRows } from "@/components/fixi/EmptyState";
import { PropertyTabs } from "@/components/fixi/PropertyTabs";
import { Button } from "@/components/ui/button";
import {
  useCreateNote,
  useDeleteNote,
  useNotes,
  useUpdateNote,
  type NoteItem,
} from "@/hooks/use-property";
import { formatDateTime, initials } from "@/lib/format";

export const Route = createFileRoute("/properties/$propertyId/notes")({
  head: () => ({
    meta: [
      { title: "Property notes — Fixi" },
      { name: "description", content: "Operator notes recorded against this property." },
    ],
  }),
  component: NotesPage,
});

function NotesPage() {
  const { propertyId } = Route.useParams();
  const searchParams =
    typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const address = searchParams?.get("address") ?? undefined;
  const postcode = searchParams?.get("postcode") ?? undefined;

  const notes = useNotes(propertyId);
  const createNote = useCreateNote(propertyId);
  const updateNote = useUpdateNote(propertyId);
  const deleteNote = useDeleteNote(propertyId);
  const items = [...(notes.data?.items ?? [])].sort((a, b) =>
    b.created_at.localeCompare(a.created_at),
  );

  const [draft, setDraft] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    try {
      await createNote.mutateAsync(draft.trim());
      setDraft("");
    } catch {
      // handled by onError toast
    }
  }

  return (
    <AppShell>
      <PropertyTabs
        propertyId={propertyId}
        active="notes"
        fallbackAddress={address}
        fallbackPostcode={postcode}
      >
        <Card className="p-4">
          <form onSubmit={(e) => void handleSubmit(e)}>
            <label className="sr-only" htmlFor="new-note-body">
              New note
            </label>
            <textarea
              id="new-note-body"
              className="h-20 w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
              placeholder="Add a note about this property…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
            <div className="mt-2 flex justify-end">
              <Button type="submit" size="sm" disabled={!draft.trim() || createNote.isPending}>
                {createNote.isPending ? "Adding…" : "Add note"}
              </Button>
            </div>
          </form>
        </Card>

        <div className="mt-3">
          {notes.isLoading && <LoadingRows rows={3} />}
          {notes.isError && (
            <ErrorState
              {...(notes.error instanceof Error ? { detail: notes.error.message } : {})}
              onRetry={() => void notes.refetch()}
            />
          )}
          {!notes.isLoading && !notes.isError && items.length === 0 && (
            <EmptyState
              icon={StickyNote}
              title="No notes recorded for this property yet"
              description="Notes are operator-authored and editable -- unlike the case timeline, they're not part of the audit record."
            />
          )}
          {items.length > 0 && (
            <div className="space-y-2">
              {items.map((note) => (
                <NoteRow
                  key={note.id}
                  note={note}
                  onSave={(body) => updateNote.mutateAsync({ noteId: note.id, body })}
                  onDelete={() => deleteNote.mutate(note.id)}
                  saving={updateNote.isPending}
                  deleting={deleteNote.isPending}
                />
              ))}
            </div>
          )}
        </div>
      </PropertyTabs>
    </AppShell>
  );
}

function NoteRow({
  note,
  onSave,
  onDelete,
  saving,
  deleting,
}: {
  note: NoteItem;
  onSave: (body: string) => Promise<unknown>;
  onDelete: () => void;
  saving: boolean;
  deleting: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(note.body);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const edited = note.updated_at !== note.created_at;

  async function handleSave() {
    if (!draft.trim()) return;
    try {
      await onSave(draft.trim());
      setEditing(false);
    } catch {
      // handled by onError toast
    }
  }

  return (
    <Card className="p-4">
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-status-purple text-[11px] font-semibold text-status-purple-foreground">
          {initials(note.author)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-[13px] font-semibold">{note.author}</div>
            <div className="text-[11px] text-muted-foreground">
              {formatDateTime(note.created_at)}
              {edited && " (edited)"}
            </div>
          </div>
          {editing ? (
            <div className="mt-2">
              <textarea
                autoFocus
                className="h-20 w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setDraft(note.body);
                    setEditing(false);
                  }
                }}
              />
              <div className="mt-2 flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setDraft(note.body);
                    setEditing(false);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  size="sm"
                  disabled={!draft.trim() || saving}
                  onClick={() => void handleSave()}
                >
                  {saving ? "Saving…" : "Save"}
                </Button>
              </div>
            </div>
          ) : (
            <p className="mt-1.5 whitespace-pre-wrap text-[13px] leading-relaxed">{note.body}</p>
          )}

          {!editing && (
            <div className="mt-2 flex items-center gap-2">
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="text-[11px] font-medium text-primary hover:underline"
              >
                Edit
              </button>
              {confirmingDelete ? (
                <span className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={onDelete}
                    disabled={deleting}
                    className="text-[11px] font-medium text-destructive hover:underline disabled:opacity-50"
                  >
                    {deleting ? "Deleting…" : "Confirm delete"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmingDelete(false)}
                    className="text-[11px] font-medium text-muted-foreground hover:underline"
                  >
                    Cancel
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirmingDelete(true)}
                  className="text-[11px] font-medium text-muted-foreground hover:text-destructive hover:underline"
                >
                  Delete
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
