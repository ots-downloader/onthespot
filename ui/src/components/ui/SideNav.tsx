import {
  createContext,
  useContext,
  useId,
  useState,
  type ComponentProps,
  type ReactNode,
} from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { cn } from "../../lib/cn";
import { focusRing } from "./Button";

/*
 * Layout by breakpoint:
 * - below `sm`: a horizontal bar that scrolls sideways, section titles
 *   visually hidden, collapse ignored;
 * - `sm` and up: a vertical column on the left that can collapse to icons.
 */

const SideNavContext = createContext<{ isCollapsed: boolean }>({
  isCollapsed: false,
});

export interface SideNavProps extends Omit<ComponentProps<"nav">, "children"> {
  /** Adds a collapse button (from `sm` up) that shrinks the nav to icons. */
  collapsible?: boolean;
  children: ReactNode;
}

export function SideNav({
  collapsible = false,
  className,
  children,
  ...rest
}: SideNavProps) {
  const [innerCollapsed, setInnerCollapsed] = useState(false);
  const isCollapsed = collapsible && innerCollapsed;

  return (
    <SideNavContext.Provider value={{ isCollapsed }}>
      <nav
        aria-label="Main"
        className={cn(
          "flex shrink-0 border-b border-line bg-surface sm:flex-col sm:border-b-0 sm:border-r sm:transition-[width]",
          isCollapsed ? "sm:w-14" : "sm:w-60",
          className,
        )}
        {...rest}
      >
        <div
          className={cn(
            "relative flex min-w-0 flex-1 flex-row items-center gap-3 overflow-x-auto px-2 py-1.5 [scrollbar-width:none]",
            "sm:flex-col sm:items-stretch sm:gap-5 sm:overflow-y-auto sm:overflow-x-hidden sm:py-4 sm:[scrollbar-width:thin]",
            isCollapsed ? "sm:px-2" : "sm:px-3",
          )}
        >
          {children}
        </div>
        {collapsible && (
          <div
            className={cn(
              "hidden shrink-0 border-t border-line py-2 sm:flex sm:flex-col sm:gap-2",
              isCollapsed ? "sm:items-center sm:px-2" : "sm:px-3",
            )}
          >
            <button
              type="button"
              onClick={() => setInnerCollapsed(!isCollapsed)}
              aria-expanded={!isCollapsed}
              aria-label={isCollapsed ? "Expand navigation" : "Collapse navigation"}
              title={isCollapsed ? "Expand navigation" : "Collapse navigation"}
              className={cn(
                "flex size-8 cursor-pointer items-center justify-center rounded-lg text-fg-subtle transition-colors hover:bg-raised hover:text-fg",
                focusRing,
              )}
            >
              {isCollapsed ? (
                <PanelLeftOpen aria-hidden="true" className="size-4" />
              ) : (
                <PanelLeftClose aria-hidden="true" className="size-4" />
              )}
            </button>
          </div>
        )}
      </nav>
    </SideNavContext.Provider>
  );
}

export interface SideNavSectionProps
  extends Omit<ComponentProps<"div">, "title" | "children"> {
  title: string;
  children: ReactNode;
}

export function SideNavSection({
  title,
  className,
  children,
  ...rest
}: SideNavSectionProps) {
  const { isCollapsed } = useContext(SideNavContext);
  const titleId = `sidenav-section-${useId()}`;
  return (
    <div
      role="group"
      aria-labelledby={titleId}
      className={cn("flex shrink-0 flex-row gap-1 sm:flex-col", className)}
      {...rest}
    >
      <div
        id={titleId}
        className={cn(
          "sr-only px-2.5 pb-1",
          !isCollapsed && "sm:not-sr-only",
        )}
      >
        <div className="text-[11px] font-semibold uppercase tracking-wider text-fg-subtle">
          {title}
        </div>
      </div>
      {children}
    </div>
  );
}

export interface SideNavItemProps
  extends Omit<ComponentProps<"button">, "children" | "disabled"> {
  label: string;
  icon?: ReactNode;
  isSelected?: boolean;
  /** Badge or count after the label. Hidden while the nav is collapsed. */
  endContent?: ReactNode;
}

export function SideNavItem({
  label,
  icon,
  isSelected = false,
  endContent,
  type = "button",
  className,
  ...rest
}: SideNavItemProps) {
  const { isCollapsed } = useContext(SideNavContext);
  return (
    <button
      type={type}
      aria-current={isSelected ? "page" : undefined}
      title={isCollapsed ? label : undefined}
      className={cn(
        "flex h-8 shrink-0 cursor-pointer items-center gap-2 whitespace-nowrap rounded-lg px-2.5 text-xs font-medium transition-colors",
        "sm:h-9 sm:w-full sm:text-sm",
        isCollapsed && "sm:justify-center sm:px-0",
        isSelected
          ? "bg-raised text-fg"
          : "text-fg-muted hover:bg-raised hover:text-fg",
        "[&_svg]:shrink-0",
        focusRing,
        className,
      )}
      {...rest}
    >
      {icon && (
        <span aria-hidden="true" className="flex items-center">
          {icon}
        </span>
      )}
      <span className={cn("min-w-0 truncate text-left sm:flex-1", isCollapsed && "sm:sr-only")}>
        {label}
      </span>
      {endContent && (
        <span className={cn("flex shrink-0 items-center", isCollapsed && "sm:hidden")}>
          {endContent}
        </span>
      )}
    </button>
  );
}
