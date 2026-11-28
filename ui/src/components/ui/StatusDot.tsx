import type { ComponentProps } from "react";
import { cn } from "../../lib/cn";

export type StatusDotVariant = "success" | "error";

const variantClass: Record<StatusDotVariant, string> = {
  success: "bg-success",
  error: "bg-danger",
};

export interface StatusDotProps
  extends Omit<ComponentProps<"span">, "children"> {
  variant: StatusDotVariant;
  /** Accessible name; also the tooltip. */
  label: string;
}

export function StatusDot({
  variant,
  label,
  title,
  className,
  ...rest
}: StatusDotProps) {
  return (
    <span
      role="img"
      aria-label={label}
      title={title ?? label}
      className={cn(
        "inline-block size-2 shrink-0 rounded-full",
        variantClass[variant],
        className,
      )}
      {...rest}
    />
  );
}
