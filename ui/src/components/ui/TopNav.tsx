import type { ComponentProps, ReactNode } from "react";
import { cn } from "../../lib/cn";

export interface TopNavProps extends Omit<ComponentProps<"header">, "children"> {
  /** Accessible name of the header landmark. */
  label?: string;
  /** Brand or page title, at the start. */
  heading?: ReactNode;
  /** Centred in the free space; shrinks first on narrow screens. */
  centerContent?: ReactNode;
  /** At the end. Always rendered; the page decides what hides on phones. */
  endContent?: ReactNode;
}

export function TopNav({
  label,
  heading,
  centerContent,
  endContent,
  className,
  ...rest
}: TopNavProps) {
  return (
    <header
      aria-label={label}
      className={cn(
        "flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface px-3 text-fg sm:px-4",
        className,
      )}
      {...rest}
    >
      {heading && <div className="flex shrink-0 items-center">{heading}</div>}
      <div className="flex min-w-0 flex-1 items-center justify-center overflow-hidden">
        {centerContent}
      </div>
      {endContent && <div className="flex shrink-0 items-center">{endContent}</div>}
    </header>
  );
}
