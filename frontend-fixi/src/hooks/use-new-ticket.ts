import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { fetchDemoSeedRefs, submitDemoIntake } from "@/api/endpoints";
import type { DemoIntakeRequest } from "@/api/types";
import { useAuthedCreds } from "@/lib/auth-context";

/** The demo seed property/tenant ids ("+ New Ticket" has nowhere else to
 * source these from -- docs/16 doesn't define a properties/tenants list
 * endpoint, this is demo-only glue per the endpoint's own docstring).
 * Doesn't change at runtime, so cache it indefinitely. */
export function useSeedRefs() {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["demo-seed-refs"],
    queryFn: () => fetchDemoSeedRefs(creds),
    staleTime: Infinity,
  });
}

export function useCreateTicket() {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DemoIntakeRequest) => submitDemoIntake(creds, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cases"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard-metrics"] });
      toast.success("Ticket created");
    },
    onError: (error: Error) => toast.error(`Could not create ticket: ${error.message}`),
  });
}
