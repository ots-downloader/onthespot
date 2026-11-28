import type { ComponentProps, ReactNode } from "react";
import { ToggleGroup } from "radix-ui";
import { cn } from "../../lib/cn";
import { focusRing } from "./Button";

export interface SegmentedControlProps
  extends Omit<
    ComponentProps<"div">,
    "onChange" | "defaultValue" | "dir" | "children"
  > {
  value: string;
  onChange: (value: string) => void;
  /** Accessible name for the group. */
  label: string;
  children: ReactNode;
}

export function SegmentedControl({
  value,
  onChange,
  label,
  className,
  children,
  ...rest
}: SegmentedControlProps) {
  return (
    <ToggleGroup.Root
      type="single"
      value={value}
      // Radix sends "" when the chosen item is pressed again. Keep the choice.
      onValueChange={(next) => {
        if (next) onChange(next);
      }}
      aria-label={label}
      className={cn(
        "inline-flex max-w-full items-center gap-0.5 overflow-x-auto overflow-y-hidden rounded-lg [scrollbar-width:none] border border-line bg-raised p-0.5",
        className,
      )}
      {...rest}
    >
      {children}
    </ToggleGroup.Root>
  );
}

export interface SegmentedControlItemProps
  extends Omit<ComponentProps<"button">, "value" | "children" | "disabled"> {
  value: string;
  label: string;
  icon?: ReactNode;
}

export function SegmentedControlItem({
  value,
  label,
  icon,
  className,
  ...rest
}: SegmentedControlItemProps) {
  return (
    <ToggleGroup.Item
      value={value}
      className={cn(
        "inline-flex shrink-0 cursor-pointer items-center justify-center whitespace-nowrap rounded-md font-medium text-fg-muted transition-colors",
        "hover:text-fg data-[state=on]:bg-surface data-[state=on]:text-fg data-[state=on]:shadow-xs",
        "[&_svg]:shrink-0",
        focusRing,
        "h-7 px-2.5 gap-1.5 text-xs",
        className,
      )}
      {...rest}
    >
      {icon}
      <span>{label}</span>
    </ToggleGroup.Item>
  );
}
