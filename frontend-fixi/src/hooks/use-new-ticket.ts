import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { request } from "@/api/client";
import { fetchProperties, submitOperatorIntake } from "@/api/endpoints";
import type { OperatorIntakeRequest } from "@/api/types";
import { useAuthedCreds } from "@/lib/auth-context";

/** The real property directory, used by the New Ticket form's picker.
 *
 * Replaces the retired demo seed-reference endpoint. Cached briefly rather
 * than indefinitely: properties are now created and edited in the app, so
 * a stale list would hide one the operator just added. */
export function usePropertyOptions(search?: string) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["property-options", search ?? ""],
    queryFn: () => fetchProperties(creds, { q: search, limit: 200 }),
    staleTime: 30_000,
  });
}

export interface TenantOption {
  id: string;
  display_name: string;
  contact_allowed: boolean;
}

/** Tenants at one property. A case is always raised against a specific
 * tenant, so the form cannot submit until one is chosen -- guessing would
 * attach the report to the wrong household. */
export function useTenantOptions(propertyId: string | null) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["tenant-options", propertyId],
    enabled: propertyId !== null,
    queryFn: () =>
      request<{ items: TenantOption[] }>(
        creds,
        `/api/v1/tenants?property_id=${encodeURIComponent(propertyId!)}&limit=100`,
      ),
  });
}

export function useCreateTicket() {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: OperatorIntakeRequest) => submitOperatorIntake(creds, body),
    onSuccess: () => {
      // A new case changes the list, the dashboard counts, the property's
      // history and every category/recurrence figure derived from it.
      for (const key of [
        ["cases"],
        ["dashboard-metrics"],
        ["agent-status"],
        ["overview"],
        ["insights"],
        ["property-history"],
        ["property-stats"],
      ]) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
      toast.success("Ticket created");
    },
    onError: (error: Error) => toast.error(`Could not create ticket: ${error.message}`),
  });
}
