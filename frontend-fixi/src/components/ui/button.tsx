import { forwardRef } from "react";
import { cn } from "@/lib/utils";

// The reference UI imports `@/components/ui/button` but that file is a
// local, uncommitted addition in Liza's checkout -- it is not on the
// liza.UI2 branch and there is no on-disk copy of that workspace here. This
// is a shadcn-shaped equivalent written against the same design tokens the
// reference stylesheet defines, so the reference markup (`<Button
// variant="outline" size="icon">`, `<Button className="rounded-xl px-4">`)
// renders as intended without guessing at the original source.

type Variant = "default" | "outline" | "ghost" | "destructive" | "secondary" | "link";
type Size = "default" | "sm" | "lg" | "icon" | "iconSm";

const variantClasses: Record<Variant, string> = {
  default: "bg-primary text-primary-foreground shadow-card hover:bg-primary/90",
  outline: "border border-border bg-transparent hover:bg-accent hover:text-accent-foreground",
  ghost: "hover:bg-accent hover:text-accent-foreground",
  destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
  secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
  link: "text-primary underline-offset-4 hover:underline",
};

const sizeClasses: Record<Size, string> = {
  default: "h-9 px-4 py-2 text-xs font-semibold",
  sm: "h-8 rounded-lg px-3 text-[11px] font-semibold",
  lg: "h-10 rounded-xl px-6 text-sm font-semibold",
  icon: "h-9 w-9",
  iconSm: "h-8 w-8",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "default", size = "default", type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        // `[&_svg]:size-4` matches shadcn's own behaviour, which the
        // reference relies on: it writes `<Button><Plus/>New Ticket</Button>`
        // with no size on the icon and expects 16px.
        "inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg",
        "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        "focus-visible:ring-offset-1 focus-visible:ring-offset-background",
        "disabled:pointer-events-none disabled:opacity-50",
        "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    />
  );
});
