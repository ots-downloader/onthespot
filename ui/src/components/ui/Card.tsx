import type { ComponentProps } from "react";
import { cn } from "../../lib/cn";

/** Steps on the 4px scale, as in Astryx: 4 = 16px. */
export type SpacingStep = 0 | 3 | 4 | 5 | 6;
export type Elevation = "none" | "low";

// Written out in full so Tailwind finds every class in the source.
export const paddingClass: Record<SpacingStep, string> = {
  0: "p-0",
  3: "p-3",
  4: "p-4",
  5: "p-5",
  6: "p-6",
};

const elevationClass: Record<Elevation, string> = {
  none: "shadow-none",
  low: "shadow-xs",
};

export interface CardProps extends ComponentProps<"div"> {
  padding?: SpacingStep;
  elevation?: Elevation;
}

export function Card({
  padding = 4,
  elevation = "none",
  className,
  ...rest
}: CardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-line bg-surface text-fg",
        paddingClass[padding],
        elevationClass[elevation],
        className,
      )}
      {...rest}
    />
  );
}
