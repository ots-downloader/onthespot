import { useId, type ComponentProps } from "react";
import { cn } from "../../lib/cn";

export type ProgressBarVariant = "accent" | "info" | "success" | "error" | "neutral";

const fillClass: Record<ProgressBarVariant, string> = {
  accent: "bg-accent",
  info: "bg-info",
  success: "bg-success",
  error: "bg-danger",
  neutral: "bg-line-strong",
};

export interface ProgressBarProps
  extends Omit<ComponentProps<"div">, "children"> {
  value?: number;
  max?: number;
  /** Accessible name. */
  label: string;
  isLabelHidden?: boolean;
  variant?: ProgressBarVariant;
  /** Track height: "sm" 6px, "md" 8px. Default "sm". */
  size?: "sm" | "md";
}

export function ProgressBar({
  value = 0,
  max = 100,
  label,
  isLabelHidden = false,
  variant = "accent",
  size = "sm",
  className,
  ...rest
}: ProgressBarProps) {
  const labelId = `progress-${useId()}`;
  const top = Number.isFinite(max) && max > 0 ? max : 100;
  const clamped = Math.min(Math.max(Number.isFinite(value) ? value : 0, 0), top);
  const percent = (clamped / top) * 100;

  return (
    <div className={cn("w-full", className)} {...rest}>
      <div
        id={labelId}
        className={cn("mb-1 text-xs font-medium text-fg-muted", isLabelHidden && "sr-only")}
      >
        {label}
      </div>
      <div
        role="progressbar"
        aria-labelledby={labelId}
        aria-valuemin={0}
        aria-valuemax={top}
        aria-valuenow={clamped}
        className={cn(
          "w-full overflow-hidden rounded-full bg-raised",
          size === "md" ? "h-2" : "h-1.5",
        )}
      >
        <div
          className={cn("h-full rounded-full transition-[width] duration-300", fillClass[variant])}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
