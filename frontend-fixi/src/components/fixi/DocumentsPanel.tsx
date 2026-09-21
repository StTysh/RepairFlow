import * as AlertDialog from "@radix-ui/react-alert-dialog";
import { Download, FileText, ImageOff, Loader2, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Card } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import { Button } from "@/components/ui/button";
import { ErrorState, LoadingRows } from "@/components/fixi/EmptyState";
import {
  fetchDocumentObjectUrl,
  useDeleteDocument,
  useDocuments,
  useUploadDocument,
  type DocumentRecord,
} from "@/hooks/use-case-content";
import { useAuthedCreds } from "@/lib/auth-context";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function isPreviewable(contentType: string): boolean {
  return contentType.startsWith("image/") || contentType === "application/pdf";
}

// --- Evidence photographs (from the issue's evidence_refs) ----------------
//
// backend/app/schemas.py's RepairIssue.evidence_refs is `list[EvidenceRef]`,
// but api/types.ts (not owned by this file -- see the ticket route's
// ownership notes) types it as `unknown[]`. Declared and runtime-checked
// locally rather than widening that shared type.

interface EvidenceRefLike {
  source_type: string;
  source_id: string;
  locator: string | null;
  observed_at: string;
  provenance: "LIVE" | "SIMULATED" | "FIXTURE";
}

function isEvidenceRefLike(value: unknown): value is EvidenceRefLike {
  if (!value || typeof value !== "object") return false;
  const r = value as Record<string, unknown>;
  return (
    typeof r["source_type"] === "string" &&
    typeof r["observed_at"] === "string" &&
    typeof r["provenance"] === "string"
  );
}

// In this codebase evidence_refs are populated only from voice-tool
// observations, whose `locator` is spoken text, not an image (see
// backend/app/domain/services.py's evidence_ref_dict calls) -- so on
// today's data this filter is almost always empty. It's still written
// defensively rather than skipped: a future producer (e.g. a photo
// attached during a contractor call) only needs to put an image URL/path
// in `locator` for this to render it correctly, with no code change here.
const IMAGE_LOCATOR_RE = /\.(png|jpe?g|gif|webp|avif)(\?.*)?$/i;

function isImageLocator(locator: string | null): locator is string {
  if (!locator) return false;
  if (!/^https?:\/\//i.test(locator) && !locator.startsWith("/")) return false;
  return IMAGE_LOCATOR_RE.test(locator);
}

const SOURCE_LABEL: Record<string, string> = {
  EVENT: "System event",
  REPORT: "Contractor report",
  TRANSCRIPT: "Call transcript",
  VOICE_TOOL: "Voice call",
  WEB: "Web research",
  OPERATOR: "Operator",
};

function EvidenceImage({ evidence }: { evidence: EvidenceRefLike }) {
  const [failed, setFailed] = useState(false);
  // "Marked as an illustrative sample" has no dedicated boolean on
  // EvidenceRef -- provenance is the real signal available: anything not
  // LIVE (SIMULATED/FIXTURE) did not come from an actual observation of
  // this property, so it is labelled as a sample, never presented as a
  // photograph of the case.
  const illustrative = evidence.provenance !== "LIVE";
  if (failed || !evidence.locator) {
    return (
      <div className="flex aspect-square items-center justify-center rounded-lg border border-dashed border-border text-muted-foreground">
        <ImageOff className="h-4 w-4" />
      </div>
    );
  }
  return (
    <div className="relative overflow-hidden rounded-lg border border-border">
      <img
        src={evidence.locator}
        alt={illustrative ? "Illustrative sample image" : "Reported evidence"}
        loading="lazy"
        onError={() => setFailed(true)}
        className="aspect-square w-full object-cover"
      />
      <span className="absolute bottom-1 left-1 right-1 truncate rounded bg-foreground/70 px-1.5 py-0.5 text-micro font-medium text-background">
        {illustrative
          ? "Illustrative sample — not a photo of this property"
          : (SOURCE_LABEL[evidence.source_type] ?? evidence.source_type)}
      </span>
    </div>
  );
}

function EvidencePhotos({ evidenceRefs }: { evidenceRefs: unknown[] }) {
  const refs = evidenceRefs.filter(isEvidenceRefLike);
  if (refs.length === 0) return null;
  const images = refs.filter((r) => isImageLocator(r.locator));
  const other = refs.filter((r) => !isImageLocator(r.locator));

  return (
    <div className="mt-5 border-t border-border pt-4">
      <div className="text-strong font-semibold">Reported evidence</div>
      <p className="mt-0.5 text-xs text-muted-foreground">
        What was recorded as evidence for this issue, labelled by its source.
      </p>
      {images.length > 0 && (
        <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
          {images.map((ref, i) => (
            <EvidenceImage key={`${ref.source_id}-${i}`} evidence={ref} />
          ))}
        </div>
      )}
      {other.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {other.map((ref, i) => (
            <li
              key={`${ref.source_id}-${i}`}
              className="rounded-lg border border-border p-2 text-xs"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">
                  {SOURCE_LABEL[ref.source_type] ?? ref.source_type}
                </span>
                <Pill tone={ref.provenance === "LIVE" ? "blue" : "gray"}>{ref.provenance}</Pill>
              </div>
              {ref.locator && <p className="mt-1 text-muted-foreground">{ref.locator}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --- One uploaded document row ---------------------------------------------

function DocumentRow({ doc, caseId }: { doc: DocumentRecord; caseId: string }) {
  const creds = useAuthedCreds();
  const del = useDeleteDocument("CASE", caseId);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const canPreview = isPreviewable(doc.content_type);

  async function handleDelete() {
    try {
      await del.mutateAsync(doc.id);
      setConfirmOpen(false);
    } catch {
      // toasted by the hook; keep the confirmation open so the operator
      // can see the pending state clear and retry.
    }
  }

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  async function togglePreview() {
    if (!canPreview) return;
    if (previewOpen) {
      setPreviewOpen(false);
      return;
    }
    setPreviewOpen(true);
    if (previewUrl) return;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      setPreviewUrl(await fetchDocumentObjectUrl(creds, doc.id, false));
    } catch {
      setPreviewError("Could not load a preview.");
    } finally {
      setPreviewLoading(false);
    }
  }

  async function handleDownload() {
    try {
      const url = await fetchDocumentObjectUrl(creds, doc.id, true);
      const a = document.createElement("a");
      a.href = url;
      a.download = doc.display_name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Could not download this file.");
    }
  }

  return (
    <li className="rounded-lg border border-border p-3">
      <div className="flex items-start justify-between gap-3">
        <button
          type="button"
          onClick={() => void togglePreview()}
          disabled={!canPreview}
          className="flex min-w-0 flex-1 items-start gap-2.5 text-left disabled:cursor-default"
          title={canPreview ? "Toggle inline preview" : "No inline preview for this file type"}
        >
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent text-muted-foreground">
            <FileText className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <div className="truncate text-strong font-semibold">{doc.display_name}</div>
            <div className="mt-0.5 text-micro text-muted-foreground">
              {doc.content_type} · {formatBytes(doc.size_bytes)} · {doc.uploaded_by} ·{" "}
              {formatDateTime(doc.uploaded_at)}
            </div>
            {doc.description && (
              <p className="mt-1 text-micro text-muted-foreground">{doc.description}</p>
            )}
          </div>
        </button>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            aria-label={`Download ${doc.display_name}`}
            onClick={() => void handleDownload()}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <Download className="h-3.5 w-3.5" />
          </button>
          <AlertDialog.Root open={confirmOpen} onOpenChange={setConfirmOpen}>
            <AlertDialog.Trigger asChild>
              <button
                type="button"
                aria-label={`Delete ${doc.display_name}`}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground hover:border-destructive hover:bg-destructive/10 hover:text-destructive"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </AlertDialog.Trigger>
            <AlertDialog.Portal>
              <AlertDialog.Overlay className="fixed inset-0 z-50 bg-foreground/20" />
              <AlertDialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-card p-5 shadow-panel">
                <AlertDialog.Title className="text-section font-semibold">
                  Delete this file?
                </AlertDialog.Title>
                <AlertDialog.Description className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  “{doc.display_name}” will be permanently removed. This can't be undone.
                </AlertDialog.Description>
                <div className="mt-4 flex justify-end gap-2">
                  <AlertDialog.Cancel asChild>
                    <Button variant="ghost" size="sm" disabled={del.isPending}>
                      Cancel
                    </Button>
                  </AlertDialog.Cancel>
                  {/* A plain Button, not AlertDialog.Action -- Radix closes
                   * the dialog on Action's click by default, which would
                   * unmount this before `del.isPending` ever had a chance
                   * to render "Deleting...". The dialog stays open,
                   * controlled by `confirmOpen`, until the mutation
                   * actually settles. */}
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={del.isPending}
                    onClick={() => void handleDelete()}
                  >
                    {del.isPending ? "Deleting…" : "Delete"}
                  </Button>
                </div>
              </AlertDialog.Content>
            </AlertDialog.Portal>
          </AlertDialog.Root>
        </div>
      </div>
      {previewOpen && canPreview && (
        <div className="mt-3 border-t border-border pt-3">
          {previewLoading && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" /> Loading preview…
            </p>
          )}
          {previewError && <p className="text-xs text-destructive">{previewError}</p>}
          {previewUrl && doc.content_type.startsWith("image/") && (
            <img
              src={previewUrl}
              alt={doc.display_name}
              className="max-h-80 w-full rounded-lg border border-border object-contain"
            />
          )}
          {previewUrl && doc.content_type === "application/pdf" && (
            <iframe
              src={previewUrl}
              title={doc.display_name}
              className="h-96 w-full rounded-lg border border-border"
            />
          )}
        </div>
      )}
    </li>
  );
}

// --- Panel -------------------------------------------------------------

/** Replaces the old placeholder Files tab. Real upload (input + drag/drop),
 * real list, real download and delete, inline preview for images/PDFs --
 * every control here does something against
 * GET|POST /api/v1/documents, GET /api/v1/documents/{id}/content and
 * DELETE /api/v1/documents/{id} (backend/app/api/documents.py). */
export function DocumentsPanel({
  caseId,
  evidenceRefs,
}: {
  caseId: string;
  evidenceRefs: unknown[];
}) {
  const docs = useDocuments("CASE", caseId);
  const upload = useUploadDocument("CASE", caseId);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    for (const file of Array.from(files)) {
      // .mutate, not .mutateAsync -- there's no result here to await, and
      // an unhandled rejection would otherwise hit the console on every
      // failed upload (413, network error, ...) even though onError
      // already toasts it.
      upload.mutate({ file });
    }
  }

  const items = docs.data?.items ?? [];

  return (
    <Card className="p-5">
      <div>
        <h2 className="text-section font-semibold">Files</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Documents and photos attached to this case.
        </p>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFiles(e.dataTransfer.files);
        }}
        className={cn(
          "mt-4 flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors",
          dragOver ? "border-primary bg-accent" : "border-border",
        )}
      >
        <Upload className="h-5 w-5 text-muted-foreground" />
        <p className="text-xs text-muted-foreground">
          Drag a file here, or{" "}
          <button
            type="button"
            className="font-medium text-primary underline underline-offset-2"
            onClick={() => inputRef.current?.click()}
          >
            browse
          </button>
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
        {upload.isPending && (
          <p className="flex items-center gap-1.5 text-micro text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> Uploading…
          </p>
        )}
      </div>

      <div className="mt-4">
        {docs.isLoading && <LoadingRows rows={3} />}
        {docs.isError && (
          <ErrorState
            detail={docs.error instanceof Error ? docs.error.message : undefined}
            onRetry={() => void docs.refetch()}
          />
        )}
        {/* One empty state, not two. The dropzone above already says
         * "Drag a file here, or browse" and already invites the action;
         * a second full EmptyState beneath it repeated the same message
         * in ~230px of extra height (docs/27). A single quiet line is
         * enough once the dropzone is doing the work. */}
        {!docs.isLoading && !docs.isError && items.length === 0 && (
          <p className="mt-3 text-body text-muted-foreground">
            No files yet. Attach photos, quotes or reports so everyone working this case sees the
            same evidence.
          </p>
        )}
        {!docs.isLoading && !docs.isError && items.length > 0 && (
          <ul className="space-y-2">
            {items.map((doc) => (
              <DocumentRow key={doc.id} doc={doc} caseId={caseId} />
            ))}
          </ul>
        )}
      </div>

      <EvidencePhotos evidenceRefs={evidenceRefs} />
    </Card>
  );
}
