import type { ComponentProps, ReactNode } from "react";
import { cn } from "../../lib/cn";
import { paddingClass, type SpacingStep } from "./Card";

/** "elevated" adds a shadow to the side nav so it stands off the page. */
export type AppShellVariant = "wash" | "elevated";

export interface AppShellProps extends Omit<ComponentProps<"div">, "children"> {
  topNav?: ReactNode;
  /** On phones (below `sm`) this shows as a scrolling bar under the top nav. */
  sideNav?: ReactNode;
  /** "fill": shell fills the viewport and the content scrolls. Default "fill". */
  height?: "fill" | "auto";
  /** Padding of the content area, on the 4px scale. Default 4. */
  contentPadding?: SpacingStep;
  variant?: AppShellVariant;
  children: ReactNode;
}

export function AppShell({
  topNav,
  sideNav,
  height = "fill",
  contentPadding = 4,
  variant = "wash",
  className,
  children,
  ...rest
}: AppShellProps) {
  const fill = height === "fill";
  return (
    <div
      className={cn(
        "flex w-full flex-col bg-body text-fg",
        fill ? "h-dvh overflow-hidden" : "min-h-dvh",
        className,
      )}
      {...rest}
    >
      {topNav}
      <div
        className={cn(
          "flex min-h-0 flex-1 flex-col sm:flex-row",
          variant === "elevated" && "[&>nav]:shadow-xs",
        )}
      >
        {sideNav}
        <main
          className={cn(
            "min-h-0 min-w-0 flex-1",
            fill && "overflow-y-auto",
            paddingClass[contentPadding],
          )}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
