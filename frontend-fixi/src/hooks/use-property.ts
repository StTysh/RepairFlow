import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError, authHeader, BASE_URL, request, type OperatorCredentials } from "@/api/client";
import { useAuthedCreds } from "@/lib/auth-context";

// Bundled property photos (frontend-fixi/src/assets) -- a property row
// carries a `photo_key` naming one of these, or null. house-exterior.jpg is
// the neutral placeholder for null/unknown keys: it's a generic exterior,
// not tied to a specific seeded address, so it never misrepresents one
// building as another (CLAUDE.md-adjacent: no fabricated evidence).
import houseExterior from "@/assets/house-exterior.jpg";
import birchLane from "@/assets/property-birch-lane.jpg";
import churchRoad from "@/assets/property-church-road.jpg";
import mapleRoad from "@/assets/property-maple-road.jpg";
import oakAvenue from "@/assets/property-oak-avenue.jpg";
import riverdaleRoad from "@/assets/property-riverdale-road.jpg";
import stationView from "@/assets/property-station-view.jpg";
import wellingtonClose from "@/assets/property-wellington-close.jpg";

// ---------------------------------------------------------------------------
// Types
//
// The properties/notes/documents backend routes (backend/app/api/*.py) don't
// exist yet -- another agent is adding them in this same session (see the
// task brief). backend/app/models.py's PropertyModel/NoteModel/DocumentModel
// and app/schemas.py's RecordSubject/RoofResponsibility enums DO already
// exist and are read directly (not guessed) to keep these types honest.
//
// These types intentionally do NOT live in src/api/types.ts: that file is
// owned by another in-flight agent this session (already modified in git
// status) and api/types.ts's existing `Property`/`Tenant` interfaces model a
// different, narrower shape (the one nested in CaseSnapshot) -- not this
// screen's full property record. See NEEDS_FROM_ROOT_properties.md for the
// suggestion to fold these into api/types.ts + api/endpoints.ts later.
// ---------------------------------------------------------------------------

/** backend/app/schemas.py RoofResponsibility. */
export type RoofResponsibility = "LANDLORD" | "OTHER" | "UNKNOWN";

export const ROOF_RESPONSIBILITY_OPTIONS: { value: RoofResponsibility; label: string }[] = [
  { value: "LANDLORD", label: "Landlord" },
  { value: "OTHER", label: "Other" },
  { value: "UNKNOWN", label: "Unknown" },
];

/** backend/app/models.py PropertyModel.property_type is a free-form
 * nullable string column (no backend enum exists) -- this is a UI-side
 * shortlist for the picker, not a contract. A property whose stored value
 * isn't in this list (e.g. imported archive data) still displays fine via
 * titleCase() fallback in the UI; it just won't pre-select an option. */
export const PROPERTY_TYPE_OPTIONS = [
  { value: "TERRACED_HOUSE", label: "Terraced house" },
  { value: "SEMI_DETACHED_HOUSE", label: "Semi-detached house" },
  { value: "DETACHED_HOUSE", label: "Detached house" },
  { value: "FLAT", label: "Flat" },
  { value: "MAISONETTE", label: "Maisonette" },
  { value: "BUNGALOW", label: "Bungalow" },
  { value: "OTHER", label: "Other" },
] as const;

export interface PropertyListItem {
  id: string;
  address_line: string;
  postcode: string;
  landlord_reference: string;
  property_type: string | null;
  bedrooms: number | null;
  build_year: number | null;
  photo_key: string | null;
  timezone: string;
  roof_responsibility: RoofResponsibility;
  access_notes: string | null;
  is_archived: boolean;
  open_case_count: number;
  total_case_count: number;
  tenant_count: number;
}

export interface PropertyListResponse {
  items: PropertyListItem[];
  total: number;
  has_more: boolean;
}

/** Matches properties.py's TenantSummary exactly -- this projection never
 * carries phone_e164/email (docs/audit/07 Finding 2); full contact detail
 * lives on the tenant's own profile (GET /tenants/{id}), linked from the
 * card that renders this. */
export interface PropertyTenant {
  id: string;
  display_name: string;
  contact_allowed: boolean;
}

/** GET /properties/{id}: record + tenants[] + counts, per the task brief's
 * API contract. */
export interface PropertyDetail extends PropertyListItem {
  tenants: PropertyTenant[];
}

export interface CreatePropertyRequest {
  address_line: string;
  postcode: string;
  landlord_reference: string;
  property_type: string | null;
  bedrooms: number | null;
  build_year: number | null;
  access_notes: string | null;
  photo_key: string | null;
}

export interface UpdatePropertyRequest {
  address_line?: string;
  postcode?: string;
  landlord_reference?: string;
  property_type?: string | null;
  bedrooms?: number | null;
  build_year?: number | null;
  access_notes?: string | null;
  photo_key?: string | null;
  roof_responsibility?: RoofResponsibility;
  timezone?: string;
}

/** backend/app/schemas.py RecordSubject. */
export type NoteSubjectType = "PROPERTY" | "CASE" | "CONTRACTOR" | "TENANT";

export interface NoteItem {
  id: string;
  subject_type: NoteSubjectType;
  subject_id: string;
  body: string;
  author: string;
  created_at: string;
  updated_at: string;
}

export interface NotesResponse {
  items: NoteItem[];
}

export interface DocumentItem {
  id: string;
  subject_type: NoteSubjectType;
  subject_id: string;
  display_name: string;
  content_type: string;
  size_bytes: number;
  description: string | null;
  uploaded_by: string;
  uploaded_at: string;
}

export interface DocumentsResponse {
  items: DocumentItem[];
}

// ---------------------------------------------------------------------------
// Photo asset map
// ---------------------------------------------------------------------------

// house-exterior.jpg is a real, selectable bundled photo (the task brief
// lists it alongside the seven property-*.jpg files), not a stand-in for
// "no photo" -- a null/unknown photo_key gets a non-photographic tile
// instead (see PropertyTabs.tsx's PropertyPhoto), so a placeholder is never
// mistaken for a real photo of some other building.
const PROPERTY_PHOTOS: Record<string, string> = {
  "house-exterior.jpg": houseExterior,
  "property-birch-lane.jpg": birchLane,
  "property-church-road.jpg": churchRoad,
  "property-maple-road.jpg": mapleRoad,
  "property-oak-avenue.jpg": oakAvenue,
  "property-riverdale-road.jpg": riverdaleRoad,
  "property-station-view.jpg": stationView,
  "property-wellington-close.jpg": wellingtonClose,
};

/** Every bundled photo a "New property"/edit form may pick from, keyed the
 * same way the backend's `photo_key` column expects (a bare filename). */
export const SELECTABLE_PROPERTY_PHOTOS: { key: string; src: string }[] = Object.entries(
  PROPERTY_PHOTOS,
).map(([key, src]) => ({ key, src }));

/** photo_key -> bundled asset, or null for "no photo on file". Callers
 * render null as a plain icon tile (PropertyTabs.tsx's PropertyPhoto), never
 * as a substitute photograph -- a real photo of *a* house standing in for
 * "no photo of *this* house" is exactly the misrepresentation the task
 * brief rules out. */
export function resolvePropertyPhoto(key: string | null | undefined): string | null {
  if (!key) return null;
  return PROPERTY_PHOTOS[key] ?? null;
}

// ---------------------------------------------------------------------------
// Fetch functions (mirrors src/api/endpoints.ts's shape, kept local -- see
// the file-level comment above)
// ---------------------------------------------------------------------------

export interface ListPropertiesParams {
  q: string;
  limit: number;
  offset: number;
  includeArchived: boolean;
}

function propertyListQuery(params: ListPropertiesParams): string {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  search.set("include_archived", String(params.includeArchived));
  return search.toString();
}

function fetchProperties(creds: OperatorCredentials, params: ListPropertiesParams) {
  return request<PropertyListResponse>(creds, `/api/v1/properties?${propertyListQuery(params)}`);
}

function fetchProperty(creds: OperatorCredentials, id: string) {
  return request<PropertyDetail>(creds, `/api/v1/properties/${id}`);
}

function createPropertyRequest(creds: OperatorCredentials, body: CreatePropertyRequest) {
  return request<PropertyListItem>(creds, "/api/v1/properties", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

function updatePropertyRequest(
  creds: OperatorCredentials,
  id: string,
  body: UpdatePropertyRequest,
) {
  return request<PropertyDetail>(creds, `/api/v1/properties/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

function fetchNotes(creds: OperatorCredentials, subjectType: NoteSubjectType, subjectId: string) {
  return request<NotesResponse>(
    creds,
    `/api/v1/notes?subject_type=${subjectType}&subject_id=${subjectId}`,
  );
}

function createNoteRequest(creds: OperatorCredentials, subjectId: string, body: string) {
  return request<NoteItem>(creds, "/api/v1/notes", {
    method: "POST",
    body: JSON.stringify({ subject_type: "PROPERTY", subject_id: subjectId, body }),
  });
}

function updateNoteRequest(creds: OperatorCredentials, noteId: string, body: string) {
  return request<NoteItem>(creds, `/api/v1/notes/${noteId}`, {
    method: "PATCH",
    body: JSON.stringify({ body }),
  });
}

function deleteNoteRequest(creds: OperatorCredentials, noteId: string) {
  return request<void>(creds, `/api/v1/notes/${noteId}`, { method: "DELETE" });
}

function fetchDocuments(
  creds: OperatorCredentials,
  subjectType: NoteSubjectType,
  subjectId: string,
) {
  return request<DocumentsResponse>(
    creds,
    `/api/v1/documents?subject_type=${subjectType}&subject_id=${subjectId}`,
  );
}

function deleteDocumentRequest(creds: OperatorCredentials, documentId: string) {
  return request<void>(creds, `/api/v1/documents/${documentId}`, { method: "DELETE" });
}

/** GET /documents/{id}/content -- never fetched via a bare `<img src>`/`<a
 * href>` (the browser won't attach the operator's HTTP Basic credentials to
 * either), always through fetchAuthedBlob below. `download: true` matches
 * the API's documented force-download query flag. */
export function documentContentUrl(id: string, opts?: { download?: boolean }): string {
  return `${BASE_URL}/api/v1/documents/${id}/content${opts?.download ? "?download=true" : ""}`;
}

/** Shared by document preview (image/PDF) and download: fetches the
 * authenticated bytes once and hands back a Blob the caller turns into an
 * object URL, per RecordingPlayer's established pattern (see
 * maintenance.tickets.$ticketId route). */
export async function fetchAuthedBlob(creds: OperatorCredentials, url: string): Promise<Blob> {
  const res = await fetch(url, { headers: { Authorization: authHeader(creds) } });
  if (!res.ok) throw new ApiError(res.status, res.statusText || `HTTP ${res.status}`);
  return res.blob();
}

async function parseXhrErrorDetail(xhr: XMLHttpRequest): Promise<string> {
  try {
    const body: unknown = JSON.parse(xhr.responseText);
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (detail !== undefined) return JSON.stringify(detail);
    }
    return JSON.stringify(body);
  } catch {
    return xhr.statusText || `HTTP ${xhr.status}`;
  }
}

/** POST /documents as multipart/form-data via XMLHttpRequest rather than
 * fetch, specifically so real upload progress can be reported (fetch has no
 * upload-progress event). Never sets Content-Type itself -- the browser
 * must write the multipart boundary, exactly like a plain <form> submit. */
export function uploadDocument(
  creds: OperatorCredentials,
  params: { subjectId: string; file: File; description?: string },
  onProgress?: (percent: number) => void,
): Promise<DocumentItem> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE_URL}/api/v1/documents`);
    xhr.setRequestHeader("Authorization", authHeader(creds));
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as DocumentItem);
        } catch {
          reject(new ApiError(xhr.status, "Server returned a malformed response"));
        }
      } else {
        void parseXhrErrorDetail(xhr).then((detail) => reject(new ApiError(xhr.status, detail)));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));
    xhr.onabort = () => reject(new ApiError(0, "Upload cancelled"));
    const form = new FormData();
    form.set("subject_type", "PROPERTY");
    form.set("subject_id", params.subjectId);
    if (params.description) form.set("description", params.description);
    form.set("file", params.file);
    xhr.send(form);
  });
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useProperties(params: ListPropertiesParams) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["properties", params],
    queryFn: () => fetchProperties(creds, params),
  });
}

export function useProperty(propertyId: string | null) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["property", propertyId],
    enabled: propertyId !== null,
    queryFn: () => fetchProperty(creds, propertyId!),
  });
}

export function useCreateProperty() {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreatePropertyRequest) => createPropertyRequest(creds, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["properties"] });
      toast.success("Property added");
    },
    onError: (error: Error) => toast.error(`Could not add property: ${error.message}`),
  });
}

export function useUpdateProperty(propertyId: string) {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdatePropertyRequest) => updatePropertyRequest(creds, propertyId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["property", propertyId] });
      void queryClient.invalidateQueries({ queryKey: ["properties"] });
      // build_year flows straight into GET /properties/{id}/stats's response
      // (backend/app/api/cases.py get_property_stats passes prop.build_year
      // through), so the history tab's "Build year" card needs this too --
      // the 10s poll would eventually catch it, but there's no reason to
      // show stale data for up to 10s after a save that just changed it.
      void queryClient.invalidateQueries({ queryKey: ["property-stats", propertyId] });
      toast.success("Property updated");
    },
    onError: (error: Error) => {
      if (error instanceof ApiError && error.status === 409) {
        toast.error("This is a sample-history property and can't be edited.");
      } else {
        toast.error(`Could not save changes: ${error.message}`);
      }
    },
  });
}

export function useNotes(subjectId: string | null) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["notes", "PROPERTY", subjectId],
    enabled: subjectId !== null,
    queryFn: () => fetchNotes(creds, "PROPERTY", subjectId!),
  });
}

export function useCreateNote(subjectId: string) {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => createNoteRequest(creds, subjectId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notes", "PROPERTY", subjectId] });
      toast.success("Note added");
    },
    onError: (error: Error) => toast.error(`Could not add note: ${error.message}`),
  });
}

export function useUpdateNote(subjectId: string) {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ noteId, body }: { noteId: string; body: string }) =>
      updateNoteRequest(creds, noteId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notes", "PROPERTY", subjectId] });
    },
    onError: (error: Error) => toast.error(`Could not save note: ${error.message}`),
  });
}

export function useDeleteNote(subjectId: string) {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (noteId: string) => deleteNoteRequest(creds, noteId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notes", "PROPERTY", subjectId] });
      toast.success("Note deleted");
    },
    onError: (error: Error) => toast.error(`Could not delete note: ${error.message}`),
  });
}

export function useDocuments(subjectId: string | null) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["documents", "PROPERTY", subjectId],
    enabled: subjectId !== null,
    queryFn: () => fetchDocuments(creds, "PROPERTY", subjectId!),
  });
}

export function useDeleteDocument(subjectId: string) {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) => deleteDocumentRequest(creds, documentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["documents", "PROPERTY", subjectId] });
      toast.success("Document deleted");
    },
    onError: (error: Error) => toast.error(`Could not delete document: ${error.message}`),
  });
}
