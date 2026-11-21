import type { ComponentProps, ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "../../lib/cn";

export type ButtonVariant =
  | "primary"
  | "accent"
  | "secondary"
  | "ghost"
  | "destructive";
export type ButtonSize = "sm" | "md";

export const focusRing =
  "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring";

export const buttonVariantClass: Record<ButtonVariant, string> = {
  primary: "bg-inverse text-fg-on-inverse hover:bg-inverse/85",
  accent: "bg-accent text-fg-on-accent hover:bg-accent-hover",
  secondary: "bg-surface border border-line-strong text-fg hover:bg-raised",
  ghost: "bg-transparent text-fg hover:bg-raised",
  destructive: "bg-danger text-white hover:bg-danger-hover",
};

const sizeClass: Record<ButtonSize, string> = {
  sm: "h-8 px-3 gap-1.5 text-xs",
  md: "h-9 px-3.5 gap-2 text-sm",
};

export const buttonBaseClass =
  "inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-lg font-medium transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 [&_svg]:shrink-0";

export interface ButtonProps
  extends Omit<ComponentProps<"button">, "children" | "disabled"> {
  /** Visible text. */
  label: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Shown before the label; replaced by a spinner while loading. */
  icon?: ReactNode;
  /** Shows a spinner and disables the button. */
  isLoading?: boolean;
  isDisabled?: boolean;
}

export function Button({
  label,
  variant = "secondary",
  size = "md",
  icon,
  isLoading = false,
  isDisabled = false,
  type = "button",
  className,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={isDisabled || isLoading}
      aria-busy={isLoading || undefined}
      className={cn(
        buttonBaseClass,
        focusRing,
        buttonVariantClass[variant],
        sizeClass[size],
        className,
      )}
      {...rest}
    >
      {isLoading ? (
        <Loader2 aria-hidden="true" className="size-3.5 animate-spin" />
      ) : (
        icon
      )}
      <span>{label}</span>
    </button>
  );
}
