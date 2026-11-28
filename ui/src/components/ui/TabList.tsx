import type { ComponentProps, ReactNode } from "react";
import { Tabs as RadixTabs } from "radix-ui";
import { cn } from "../../lib/cn";
import { focusRing } from "./Button";

export interface TabListProps
  extends Omit<ComponentProps<"div">, "onChange" | "defaultValue" | "dir"> {
  value: string;
  onChange: (value: string) => void;
  /** Accessible name for the tab list. */
  label?: string;
  children: ReactNode;
}

/** The tab row only. Pages render the matching panel themselves from `value`. */
export function TabList({
  value,
  onChange,
  label,
  className,
  children,
  ...rest
}: TabListProps) {
  return (
    <RadixTabs.Root value={value} onValueChange={onChange} {...rest}>
      <RadixTabs.List
        aria-label={label}
        className={cn(
          "flex max-w-full items-end gap-1 overflow-x-auto overflow-y-hidden border-b [scrollbar-width:none] border-line",
          className,
        )}
      >
        {children}
      </RadixTabs.List>
    </RadixTabs.Root>
  );
}

export interface TabProps
  extends Omit<ComponentProps<"button">, "value" | "children" | "disabled"> {
  value: string;
  label: string;
  icon?: ReactNode;
  endContent?: ReactNode;
}

export function Tab({
  value,
  label,
  icon,
  endContent,
  className,
  ...rest
}: TabProps) {
  return (
    <RadixTabs.Trigger
      value={value}
      {...rest}
      // Radix points aria-controls at its own Content, which we never render.
      aria-controls={undefined}
      className={cn(
        "inline-flex shrink-0 cursor-pointer items-center whitespace-nowrap rounded-t-md border-b-2 border-transparent font-medium text-fg-muted transition-colors",
        "hover:text-fg data-[state=active]:border-fg data-[state=active]:text-fg",
        "[&_svg]:shrink-0",
        focusRing,
        "focus-visible:ring-inset",
        "h-8 px-2.5 gap-1.5 text-xs",
        className,
      )}
    >
      {icon}
      <span>{label}</span>
      {endContent}
    </RadixTabs.Trigger>
  );
}
