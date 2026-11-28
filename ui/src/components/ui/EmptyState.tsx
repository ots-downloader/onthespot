import type { ComponentProps, ReactNode } from "react";
import { cn } from "../../lib/cn";

export interface EmptyStateProps
  extends Omit<ComponentProps<"div">, "title" | "children"> {
  title: string;
  description?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
}

export function EmptyState({
  title,
  description,
  icon,
  actions,
  className,
  ...rest
}: EmptyStateProps) {
  return (
    <div
      className={cn("flex flex-col items-center gap-2 py-8 text-center", className)}
      {...rest}
    >
      {icon && (
        <div aria-hidden="true" className="mb-1 text-fg-subtle">
          {icon}
        </div>
      )}
      <h3 className="text-base font-semibold text-fg">{title}</h3>
      {description && (
        <div className="max-w-md text-sm text-fg-muted">
          {description}
        </div>
      )}
      {actions && <div className="mt-2 flex flex-wrap justify-center gap-2">{actions}</div>}
    </div>
  );
}
