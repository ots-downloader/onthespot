import type { ComponentProps, ReactNode } from "react";
import { cn } from "../../lib/cn";

export interface AppShellProps extends Omit<ComponentProps<"div">, "children"> {
  topNav?: ReactNode;
  /** On phones (below `sm`) this shows as a scrolling bar under the top nav. */
  sideNav?: ReactNode;
  children: ReactNode;
}

/** Fills the viewport; only the content area scrolls. */
export function AppShell({
  topNav,
  sideNav,
  className,
  children,
  ...rest
}: AppShellProps) {
  return (
    <div
      className={cn(
        "relative flex w-full flex-col bg-body text-fg h-dvh overflow-hidden",
        className,
      )}
      {...rest}
    >
      {topNav}
      <div className="flex min-h-0 flex-1 flex-col sm:flex-row [&>nav]:shadow-xs">
        {sideNav}
        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto p-4">{children}</main>
      </div>
    </div>
  );
}
