import type { ComponentProps } from "react";
import { cn } from "../../lib/cn";

export type DividerVariant = "subtle" | "strong";

export interface DividerProps extends Omit<ComponentProps<"div">, "children"> {
  variant?: DividerVariant;
}

export function Divider({
  variant = "subtle",
  className,
  ...rest
}: DividerProps) {
  const line = variant === "strong" ? "border-line-strong" : "border-line";

  return (
    <div role="separator" className={cn("w-full border-t", line, className)} {...rest} />
  );
}
