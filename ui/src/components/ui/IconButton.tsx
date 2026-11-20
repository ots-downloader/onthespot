import type { ComponentProps, ReactNode } from "react";
import { cn } from "../../lib/cn";
import {
  buttonBaseClass,
  buttonVariantClass,
  focusRing,
  type ButtonSize,
  type ButtonVariant,
} from "./Button";

const sizeClass: Record<ButtonSize, string> = {
  sm: "size-8",
  md: "size-9",
};

export interface IconButtonProps
  extends Omit<ComponentProps<"button">, "children" | "disabled"> {
  /** Accessible name; also shown as the tooltip. */
  label: string;
  icon: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
}

export function IconButton({
  label,
  icon,
  variant = "ghost",
  size = "md",
  type = "button",
  title,
  className,
  ...rest
}: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={title ?? label}
      className={cn(
        buttonBaseClass,
        focusRing,
        buttonVariantClass[variant],
        sizeClass[size],
        "p-0",
        className,
      )}
      {...rest}
    >
      {icon}
    </button>
  );
}
