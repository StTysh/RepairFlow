import { useEffect, useState } from "react";

/** Debounces a fast-changing value (e.g. a search input) so callers can key
 * a network request off the debounced value instead of firing one per
 * keystroke. */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);

  return debounced;
}
