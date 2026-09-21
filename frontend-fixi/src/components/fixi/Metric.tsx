import { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "@/hooks/use-prefers-reduced-motion";
import { interpolate, parseMetric, progress, renderMetric } from "@/lib/metric-format";
import { cn } from "@/lib/utils";

/**
 * A KPI value that counts up when it first arrives and flashes when it
 * changes underneath the operator.
 *
 * Why this is worth animating at all: every KPI on this app's dashboards
 * is polled, so numbers change while somebody is looking at a different
 * part of the screen. A figure that silently rewrites itself from 12 to
 * 13 is the one change an operator is most likely to miss and most needs
 * to catch. The flash is the point; the count-up is the cheap way to make
 * the first paint feel like it resolved rather than snapped.
 *
 * It takes the already-formatted display string rather than a number
 * because the callers format in a dozen different ways (currency, hours,
 * percentages, em-dash for "no data"). Splitting the string back apart
 * keeps every one of those formats working here with no call-site change,
 * and anything that is not numeric at all renders verbatim.
 */

const DURATION_MS = 620;

export function Metric({
  value: rawValue,
  className,
}: {
  // Numbers are accepted as well as display strings: several callers
  // hold a raw count and formatting it just to have this parse it back
  // would be a round trip for nothing.
  value: string | number;
  className?: string | undefined;
}) {
  const value = String(rawValue);
  const reduced = usePrefersReducedMotion();
  const parsed = parseMetric(value);
  const [shown, setShown] = useState(value);
  const [flashing, setFlashing] = useState(false);
  // The number we are counting *from*: the last value actually displayed,
  // or 0 on the first arrival so the figure rises into place.
  const fromRef = useRef<number>(0);
  const firstRef = useRef(true);

  useEffect(() => {
    if (!parsed || reduced) {
      setShown(value);
      if (parsed) fromRef.current = parsed.value;
      // A change still has to be *noticed* without motion, so the flash
      // is dropped but the value is not silently swapped either -- the
      // global reduced-motion rule shortens the flash rather than
      // removing it, which is the honest compromise.
      if (!firstRef.current) {
        setFlashing(true);
        const t = window.setTimeout(() => setFlashing(false), 700);
        return () => window.clearTimeout(t);
      }
      firstRef.current = false;
      return;
    }

    const from = fromRef.current;
    const to = parsed.value;
    if (from === to) {
      setShown(value);
      return;
    }

    const wasFirst = firstRef.current;
    firstRef.current = false;
    if (!wasFirst) setFlashing(true);

    let frame = 0;
    const started = performance.now();
    const step = (now: number) => {
      const t = progress(now, started, DURATION_MS);
      if (t < 1) {
        setShown(renderMetric(interpolate(from, to, t), parsed));
        frame = requestAnimationFrame(step);
      } else {
        // The last frame shows `value`, not a reconstruction of it.
        // renderMetric round-trips the shape it parsed, which is only as
        // precise as that shape: "£8,295.00" parses as one decimal
        // place and would land as "£8,295.0". The caller already did
        // the formatting; the animation's job is the frames in between.
        setShown(value);
        fromRef.current = to;
      }
    };
    frame = requestAnimationFrame(step);

    // requestAnimationFrame is suspended entirely while a document is
    // not being rendered -- a backgrounded tab, an occluded window, a
    // minimised browser. Without this the counter would sit on whatever
    // frame it had reached (or, on a change, on the PREVIOUS value)
    // until the tab came back. Timers are throttled there but still
    // fire, so this guarantees the true value is displayed either way.
    const settle = window.setTimeout(() => {
      setShown(value);
      fromRef.current = to;
    }, DURATION_MS + 150);

    const flashTimer = window.setTimeout(() => setFlashing(false), 700);
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(settle);
      window.clearTimeout(flashTimer);
      // Whatever we were mid-way through, the truth is the target: leave
      // the counter's origin at `to` so an unmount mid-count cannot make
      // the next change animate from a number never fully reached.
      fromRef.current = to;
    };
    // `parsed` is derived from `value` on every render, so `value` is the
    // real dependency; depending on the object would re-run every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, reduced]);

  return (
    <span
      className={cn(
        "inline-block rounded px-0.5 -mx-0.5 tabular-nums",
        flashing && "animate-value-flash",
        className,
      )}
    >
      {shown}
    </span>
  );
}
