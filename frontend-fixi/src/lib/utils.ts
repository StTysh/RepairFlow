import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * tailwind-merge, taught about this project's own design tokens.
 *
 * This is not a nicety. tailwind-merge classifies `text-<word>` by
 * looking the word up in Tailwind's built-in font sizes; anything it does
 * not recognise it assumes is a COLOUR. Every size on this app's scale is
 * a custom name -- `text-micro`, `text-body`, `text-strong`,
 * `text-section`, `text-title`, `text-metric` -- so plain twMerge filed
 * all six under `text-color`, decided they conflicted with the text
 * colour sitting beside them in the same cn() call, and deleted them:
 *
 *     twMerge("text-strong text-sidebar-foreground")
 *       -> "text-sidebar-foreground"
 *
 * The class vanished from the DOM with no error, no warning and no build
 * failure, and the element silently fell back to the 16px browser
 * default. That is how eight sidebar links ended up as the largest text
 * on a dashboard whose table rows are 12px, while the source said 13px
 * and the compiled stylesheet contained a correct `.text-strong` rule.
 *
 * The other four groups had a milder version of the same problem: both
 * classes survived and the cascade picked a winner, so `cn(..., "duration-200")`
 * could not actually override `duration-fast`. Registered here too, so an
 * override at a call site means what it says.
 *
 * Any new token added to @theme in styles.css must be added here as well.
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: ["micro", "body", "strong", "section", "title", "metric"] }],
      "max-w": [{ "max-w": ["page", "prose-fixi"] }],
      duration: [{ duration: ["instant", "fast", "base", "slow"] }],
      ease: [{ ease: ["fixi", "fixi-out", "fixi-in"] }],
      animate: [{ animate: ["value-flash", "agent-ring", "shimmer"] }],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
