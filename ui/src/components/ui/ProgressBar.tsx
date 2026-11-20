import { useId, type ComponentProps } from "react";
import { cn } from "../../lib/cn";

export type ProgressBarVariant = "accent" | "success" | "error";

const fillClass: Record<ProgressBarVariant, string> = {
  accent: "bg-accent",
  success: "bg-success",
  error: "bg-danger",
};

export interface ProgressBarProps
  extends Omit<ComponentProps<"div">, "children"> {
  value?: number;
  max?: number;
  /** Accessible name. */
  label: string;
  isLabelHidden?: boolean;
  variant?: ProgressBarVariant;
}

export function ProgressBar({
  value = 0,
  max = 100,
  label,
  isLabelHidden = false,
  variant = "accent",
  className,
  ...rest
}: ProgressBarProps) {
  const labelId = `progress-${useId()}`;
  const clamped = Math.min(Math.max(Number.isFinite(value) ? value : 0, 0), max);
  const percent = (clamped / max) * 100;

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
        aria-valuemax={max}
        aria-valuenow={clamped}
        className="h-1.5 w-full overflow-hidden rounded-full bg-raised"
      >
        <div
          className={cn("h-full rounded-full transition-[width] duration-300", fillClass[variant])}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
