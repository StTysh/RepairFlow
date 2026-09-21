import { useQuery } from "@tanstack/react-query";
import { fetchCaseEvents } from "@/api/endpoints";
import type { OperatorCredentials } from "@/api/client";
import type { CaseEvent } from "@/api/types";
import { useAuthedCreds } from "@/lib/auth-context";

const POLL_INTERVAL_MS = 4000;

/** The server caps `limit` at 100 (`ge=1, le=100` on the endpoint), so a
 * single request cannot return a long case's whole history. */
const PAGE_SIZE = 100;

/** Stop after this many pages. A case with 2,000 events is a bug
 * somewhere, and silently issuing twenty requests every poll tick to
 * render it would turn that bug into a second one. `truncated` says so
 * out loud instead. */
const MAX_PAGES = 10;

export interface CaseEventsPage {
  items: CaseEvent[];
  /** True when MAX_PAGES was exhausted and older events remain unread. */
  truncated: boolean;
}

/** Every event on a case, paged.
 *
 * This used to request a flat `limit: 100` and stop, with a comment
 * conceding it was "the simplest thing that works at demo scale". That
 * held while no case had 100 events. It stopped holding when the archival
 * generator began writing a full event log per case: past 100, the
 * Timeline and the case-flow graph would quietly lose the *start* of the
 * story -- the intake and first decisions -- which is the part that
 * explains everything after it. Losing the beginning silently is worse
 * than showing nothing.
 *
 * Pages forward with `after_seq` (seq is monotonic per case) rather than
 * by offset, so a new event arriving mid-page cannot cause a skip.
 */
async function fetchAllCaseEvents(
  creds: OperatorCredentials,
  caseId: string,
): Promise<CaseEventsPage> {
  const items: CaseEvent[] = [];
  let afterSeq = 0;

  for (let page = 0; page < MAX_PAGES; page += 1) {
    const res = await fetchCaseEvents(creds, caseId, { after_seq: afterSeq, limit: PAGE_SIZE });
    items.push(...res.items);
    if (res.items.length < PAGE_SIZE) return { items, truncated: false };
    afterSeq = res.items[res.items.length - 1]!.seq;
  }
  return { items, truncated: true };
}

/** Backs the ticket detail Timeline and the case-flow graph -- the agent's
 * own audit trail, distinct from the read-only tenant/contractor/operator
 * Messages tab (see components/fixi/MessagesPanel.tsx). */
export function useCaseEvents(caseId: string | null) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["case-events", caseId],
    enabled: caseId !== null,
    refetchInterval: POLL_INTERVAL_MS,
    queryFn: () => fetchAllCaseEvents(creds, caseId!),
  });
}
