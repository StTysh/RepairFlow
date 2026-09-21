import { useQuery } from "@tanstack/react-query";
import { fetchGlobalSearch } from "@/api/endpoints";
import { useAuthedCreds } from "@/lib/auth-context";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

/** The backend rejects anything shorter than this outright (returns an empty
 * result rather than dumping the dataset -- backend/app/api/search.py's
 * MIN_QUERY_LENGTH), so there is no point spending a request on it. */
export const MIN_SEARCH_LENGTH = 2;

/** Cross-entity search behind the UtilityBar box.
 *
 * `GET /api/v1/search` has existed since the migration and had ZERO callers
 * until 2026-09-21: the box wrote into CaseSearchContext, which only the
 * Maintenance list read, so it client-filtered already-loaded tickets while
 * its placeholder promised addresses, tenants and contractors. Typing a
 * contractor's name found nothing even though the API answers it correctly.
 *
 * Debounced so a request goes out per pause, not per keystroke. Kept fresh
 * for a few seconds because results are navigational, not live telemetry --
 * re-opening the same query should not re-fetch.
 */
export function useGlobalSearch(rawQuery: string) {
  const creds = useAuthedCreds();
  const query = useDebouncedValue(rawQuery.trim(), 250);
  const enabled = query.length >= MIN_SEARCH_LENGTH;

  return useQuery({
    queryKey: ["global-search", query],
    queryFn: () => fetchGlobalSearch(creds, query),
    enabled,
    staleTime: 5000,
    // Deliberately no placeholderData: keeping the previous query's hits on
    // screen under a newer query reads as a wrong answer. (tsconfig sets
    // exactOptionalPropertyTypes, so this must be omitted, not set to
    // undefined.)
  });
}
