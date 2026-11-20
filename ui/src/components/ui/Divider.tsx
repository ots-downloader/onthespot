import type { ComponentProps } from "react";
import { cn } from "../../lib/cn";

export type DividerProps = Omit<ComponentProps<"div">, "children">;

export function Divider({ className, ...rest }: DividerProps) {
  return (
    <div role="separator" className={cn("w-full border-t border-line", className)} {...rest} />
  );
}
