import type { ComponentProps, ReactNode } from "react";
import { cn } from "../../lib/cn";

/**
 * The five status variants plus the hue names the catalog services use.
 * There are no hue roles in the theme, so each hue maps to the closest role.
 */
export type BadgeVariant =
  | "neutral"
  | "info"
  | "success"
  | "warning"
  | "error"
  | "blue"
  | "teal"
  | "purple";

const info = "bg-info-subtle text-info-fg";

const variantClass: Record<BadgeVariant, string> = {
  neutral: "bg-raised text-fg-muted",
  info,
  success: "bg-success-subtle text-success-fg",
  warning: "bg-warning-subtle text-warning-fg",
  error: "bg-danger-subtle text-danger-fg",
  blue: info,
  teal: "bg-accent-subtle text-accent",
  purple: "bg-inverse/10 text-fg",
};

export interface BadgeProps extends Omit<ComponentProps<"span">, "children"> {
  variant?: BadgeVariant;
  label: ReactNode;
}

export function Badge({
  variant = "neutral",
  label,
  className,
  ...rest
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full shrink-0 items-center whitespace-nowrap rounded-md px-1.5 py-0.5 text-[11px] font-medium leading-4",
        variantClass[variant],
        className,
      )}
      {...rest}
    >
      <span className="truncate">{label}</span>
    </span>
  );
}
