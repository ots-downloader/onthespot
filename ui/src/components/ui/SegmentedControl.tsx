import {
  createContext,
  useContext,
  type ComponentProps,
  type ReactNode,
} from "react";
import { ToggleGroup } from "radix-ui";
import { cn } from "../../lib/cn";
import { focusRing } from "./Button";

export type SegmentedControlSize = "sm" | "md";

const SegmentSizeContext = createContext<SegmentedControlSize>("md");

const sizeClass: Record<SegmentedControlSize, string> = {
  sm: "h-7 px-2.5 gap-1.5 text-xs",
  md: "h-8 px-3 gap-1.5 text-sm",
};

export interface SegmentedControlProps
  extends Omit<
    ComponentProps<"div">,
    "onChange" | "defaultValue" | "dir" | "children"
  > {
  value: string;
  onChange: (value: string) => void;
  /** Accessible name for the group. */
  label: string;
  size?: SegmentedControlSize;
  children: ReactNode;
}

export function SegmentedControl({
  value,
  onChange,
  label,
  size = "md",
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
        "inline-flex max-w-full items-center gap-0.5 overflow-x-auto overflow-y-hidden rounded-lg border border-line bg-raised p-0.5",
        className,
      )}
      {...rest}
    >
      <SegmentSizeContext.Provider value={size}>{children}</SegmentSizeContext.Provider>
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
  const size = useContext(SegmentSizeContext);
  return (
    <ToggleGroup.Item
      value={value}
      className={cn(
        "inline-flex shrink-0 cursor-pointer items-center justify-center whitespace-nowrap rounded-md font-medium text-fg-muted transition-colors",
        "hover:text-fg data-[state=on]:bg-surface data-[state=on]:text-fg data-[state=on]:shadow-xs",
        "[&_svg]:shrink-0",
        focusRing,
        sizeClass[size],
        className,
      )}
      {...rest}
    >
      {icon}
      <span>{label}</span>
    </ToggleGroup.Item>
  );
}
