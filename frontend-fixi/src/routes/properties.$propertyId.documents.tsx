import { createFileRoute } from "@tanstack/react-router";
import {
  Download,
  File as FileIcon,
  FileText,
  Image as ImageIcon,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { EmptyState, ErrorState, LoadingRows } from "@/components/fixi/EmptyState";
import { PropertyTabs } from "@/components/fixi/PropertyTabs";
import {
  documentContentUrl,
  fetchAuthedBlob,
  uploadDocument,
  useDeleteDocument,
  useDocuments,
  type DocumentItem,
} from "@/hooks/use-property";
import { useAuthedCreds } from "@/lib/auth-context";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/properties/$propertyId/documents")({
  head: () => ({
    meta: [
      { title: "Property documents — Fixi" },
      { name: "description", content: "Files on record for this property." },
    ],
  }),
  component: DocumentsPage,
});

interface PendingUpload {
  key: string;
  name: string;
  size: number;
  progress: number;
  error: string | null;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function DocumentsPage() {
  const { propertyId } = Route.useParams();
  const searchParams =
    typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const address = searchParams?.get("address") ?? undefined;
  const postcode = searchParams?.get("postcode") ?? undefined;

  const creds = useAuthedCreds();
  const documents = useDocuments(propertyId);
  const deleteDocument = useDeleteDocument(propertyId);
  const items = documents.data?.items ?? [];

  const [pending, setPending] = useState<PendingUpload[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function startUploads(files: FileList | File[]) {
    for (const file of Array.from(files)) {
      const key = `${file.name}-${file.size}-${Date.now()}-${Math.random()}`;
      setPending((prev) => [
        ...prev,
        { key, name: file.name, size: file.size, progress: 0, error: null },
      ]);
      uploadDocument(creds, { subjectId: propertyId, file }, (percent) => {
        setPending((prev) => prev.map((p) => (p.key === key ? { ...p, progress: percent } : p)));
      })
        .then(() => {
          setPending((prev) => prev.filter((p) => p.key !== key));
          void documents.refetch();
        })
        .catch((error: unknown) => {
          setPending((prev) =>
            prev.map((p) =>
              p.key === key
                ? { ...p, error: error instanceof Error ? error.message : "Upload failed" }
                : p,
            ),
          );
        });
    }
  }

  function dismissPending(key: string) {
    setPending((prev) => prev.filter((p) => p.key !== key));
  }

  return (
    <AppShell>
      <PropertyTabs
        propertyId={propertyId}
        active="documents"
        fallbackAddress={address}
        fallbackPostcode={postcode}
      >
        {/* A plain div, not <Card> -- Card.tsx (AppShell.tsx, reused as-is)
         * only accepts className/children, not DOM event handler props, so
         * the drag handlers below need an element that forwards them.
         * Styled to match Card's own rounded-xl/border/shadow-card look. */}
        <div
          className={cn(
            "flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed bg-card p-8 text-center shadow-card transition-colors",
            dragOver ? "border-primary bg-accent" : "border-border",
          )}
          onDragOver={(e: React.DragEvent<HTMLDivElement>) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e: React.DragEvent<HTMLDivElement>) => {
            e.preventDefault();
            setDragOver(false);
            if (e.dataTransfer.files.length > 0) startUploads(e.dataTransfer.files);
          }}
        >
          <Upload className="h-6 w-6 text-muted-foreground" />
          <p className="text-[13px] font-medium">Drag files here, or</p>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-medium shadow-card hover:bg-accent"
          >
            Browse files
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            aria-label="Upload document"
            className="hidden"
            onChange={(e) => {
              if (e.target.files && e.target.files.length > 0) startUploads(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        {pending.length > 0 && (
          <div className="mt-3 space-y-2">
            {pending.map((p) => (
              <Card key={p.key} className="flex items-center gap-3 px-4 py-2.5">
                <FileIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate font-medium">{p.name}</span>
                    <span className="shrink-0 text-muted-foreground">{formatBytes(p.size)}</span>
                  </div>
                  {p.error ? (
                    <p className="mt-1 text-[11px] text-destructive">{p.error}</p>
                  ) : (
                    <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary transition-all"
                        style={{ width: `${p.progress}%` }}
                      />
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  aria-label={`Dismiss ${p.name}`}
                  onClick={() => dismissPending(p.key)}
                  className="shrink-0 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </Card>
            ))}
          </div>
        )}

        <div className="mt-3">
          {documents.isLoading && <LoadingRows rows={3} />}
          {documents.isError && (
            <ErrorState
              {...(documents.error instanceof Error ? { detail: documents.error.message } : {})}
              onRetry={() => void documents.refetch()}
            />
          )}
          {!documents.isLoading && !documents.isError && items.length === 0 && (
            <EmptyState
              icon={FileText}
              title="No documents uploaded for this property yet"
              description="Lease agreements, gas safety certificates, EPCs and photos live here -- upload one above."
            />
          )}
          {items.length > 0 && (
            <div className="space-y-2">
              {items.map((doc) => (
                <DocumentRow
                  key={doc.id}
                  doc={doc}
                  onDelete={() => deleteDocument.mutate(doc.id)}
                  deleting={deleteDocument.isPending}
                />
              ))}
            </div>
          )}
        </div>
      </PropertyTabs>
    </AppShell>
  );
}

function DocumentRow({
  doc,
  onDelete,
  deleting,
}: {
  doc: DocumentItem;
  onDelete: () => void;
  deleting: boolean;
}) {
  const creds = useAuthedCreds();
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const isImage = doc.content_type.startsWith("image/");
  const isPdf = doc.content_type === "application/pdf";
  const previewable = isImage || isPdf;

  // Revoke on close and on unmount -- never leak the blob URL.
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
    // Deps on previewUrl deliberately -- this must revoke both when the
    // preview changes (a stale blob URL replaced by a fresh one) AND on
    // unmount. An empty dep array would close over the first render's
    // `previewUrl` (always null), so unmount would never actually revoke
    // anything and every opened preview would leak its blob URL.
  }, [previewUrl]);

  async function togglePreview() {
    if (previewOpen) {
      setPreviewOpen(false);
      return;
    }
    if (previewUrl) {
      setPreviewOpen(true);
      return;
    }
    setLoadingPreview(true);
    setPreviewError(null);
    try {
      const blob = await fetchAuthedBlob(creds, documentContentUrl(doc.id));
      setPreviewUrl(URL.createObjectURL(blob));
      setPreviewOpen(true);
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "Could not load preview.");
    } finally {
      setLoadingPreview(false);
    }
  }

  async function handleDownload() {
    setDownloading(true);
    try {
      const blob = await fetchAuthedBlob(creds, documentContentUrl(doc.id, { download: true }));
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = doc.display_name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setPreviewError("Could not download this file.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <Card className="p-4">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-muted-foreground">
          {isImage ? (
            <ImageIcon className="h-4 w-4" />
          ) : isPdf ? (
            <FileText className="h-4 w-4" />
          ) : (
            <FileIcon className="h-4 w-4" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-[13px] font-medium">{doc.display_name}</div>
              <div className="text-[11px] text-muted-foreground">
                {doc.content_type} · {formatBytes(doc.size_bytes)} · uploaded by {doc.uploaded_by} ·{" "}
                {formatDateTime(doc.uploaded_at)}
              </div>
              {doc.description && (
                <p className="mt-1 text-xs text-muted-foreground">{doc.description}</p>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              {previewable && (
                <button
                  type="button"
                  onClick={() => void togglePreview()}
                  disabled={loadingPreview}
                  className="rounded-lg border border-border bg-card px-2.5 py-1.5 text-[11px] font-medium shadow-card hover:bg-accent disabled:opacity-50"
                >
                  {loadingPreview ? "Loading…" : previewOpen ? "Hide preview" : "Preview"}
                </button>
              )}
              <button
                type="button"
                aria-label={`Download ${doc.display_name}`}
                onClick={() => void handleDownload()}
                disabled={downloading}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground shadow-card hover:bg-accent hover:text-foreground disabled:opacity-50"
              >
                <Download className="h-3.5 w-3.5" />
              </button>
              {confirmingDelete ? (
                <span className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={onDelete}
                    disabled={deleting}
                    className="rounded-lg bg-destructive px-2.5 py-1.5 text-[11px] font-medium text-destructive-foreground disabled:opacity-50"
                  >
                    {deleting ? "Deleting…" : "Confirm delete"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmingDelete(false)}
                    className="rounded-lg border border-border bg-card px-2.5 py-1.5 text-[11px] font-medium hover:bg-accent"
                  >
                    Cancel
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  aria-label={`Delete ${doc.display_name}`}
                  onClick={() => setConfirmingDelete(true)}
                  className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground shadow-card hover:bg-accent hover:text-destructive"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>
          {previewError && <p className="mt-2 text-[11px] text-destructive">{previewError}</p>}
          {previewOpen && previewUrl && (
            <div className="mt-3 overflow-hidden rounded-lg border border-border">
              {isImage ? (
                <img
                  src={previewUrl}
                  alt={doc.display_name}
                  className="max-h-96 w-full object-contain"
                />
              ) : (
                <object data={previewUrl} type="application/pdf" className="h-96 w-full">
                  <p className="p-4 text-xs text-muted-foreground">
                    This browser can't preview PDFs inline.{" "}
                    <a
                      href={previewUrl}
                      download={doc.display_name}
                      className="text-primary underline"
                    >
                      Download it
                    </a>{" "}
                    instead.
                  </p>
                </object>
              )}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
