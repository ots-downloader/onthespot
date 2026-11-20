import { useId, type ReactNode } from "react";
import { Select as RadixSelect } from "radix-ui";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "../../lib/cn";
import { focusRing } from "./Button";
import {
  fieldBoxClass,
  fieldDescriptionClass,
  fieldLabelClass,
  type TextInputSize,
} from "./TextInput";

export interface SelectOption {
  value: string;
  label: string;
}

export type SelectSize = TextInputSize;

const sizeClass: Record<SelectSize, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-9 px-3 text-sm",
};

/*
 * Radix forbids "" as an item value, because it uses "" to mean "nothing
 * chosen". An option whose value is "" is stored under this stand-in and
 * turned back into "" before onChange runs.
 */
const EMPTY_VALUE = "__ots_select_empty__";
const encode = (value: string) => (value === "" ? EMPTY_VALUE : value);
const decode = (value: string) => (value === EMPTY_VALUE ? "" : value);

export interface SelectProps {
  label: string;
  isLabelHidden?: boolean;
  value: string;
  onChange: (value: string) => void;
  options: ReadonlyArray<SelectOption>;
  description?: ReactNode;
  size?: SelectSize;
  /** Id of the trigger button, so an outside <label htmlFor> still works. */
  id?: string;
  /** Class for the trigger button. */
  className?: string;
  /** Class for the outer wrapper. */
  wrapperClassName?: string;
}

export function Select({
  label,
  isLabelHidden = false,
  value,
  onChange,
  options,
  description,
  size = "md",
  id,
  className,
  wrapperClassName,
}: SelectProps) {
  const autoId = useId();
  const triggerId = id ?? `select-${autoId}`;
  const descriptionId = description ? `${triggerId}-description` : undefined;

  const hasMatch = options.some((option) => option.value === value);
  // "" with no matching option shows the "Select…" placeholder.
  const rootValue = hasMatch ? encode(value) : "";

  return (
    <div className={cn("w-full", wrapperClassName)}>
      <label
        htmlFor={triggerId}
        className={cn(fieldLabelClass, isLabelHidden && "sr-only")}
      >
        {label}
      </label>
      <RadixSelect.Root
        value={rootValue}
        onValueChange={(next) => onChange(decode(next))}
      >
        <RadixSelect.Trigger
          id={triggerId}
          aria-describedby={descriptionId}
          className={cn(
            fieldBoxClass,
            focusRing,
            "flex cursor-pointer items-center justify-between gap-2 text-left data-[placeholder]:text-fg-subtle",
            sizeClass[size],
            className,
          )}
        >
          <span className="min-w-0 truncate">
            <RadixSelect.Value placeholder="Select…" />
          </span>
          <RadixSelect.Icon asChild>
            <ChevronDown aria-hidden="true" className="size-4 shrink-0 text-fg-subtle" />
          </RadixSelect.Icon>
        </RadixSelect.Trigger>
        <RadixSelect.Portal>
          <RadixSelect.Content
            position="popper"
            sideOffset={4}
            className="z-[100] max-h-[min(var(--radix-select-content-available-height),20rem)] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-lg border border-line bg-overlay text-fg shadow-lg"
          >
            <RadixSelect.Viewport className="p-1">
              {options.map((option) => (
                <RadixSelect.Item
                  key={option.value}
                  value={encode(option.value)}
                  className={cn(
                    "relative flex cursor-pointer select-none items-center rounded-md py-1.5 pl-7 pr-3 outline-none",
                    size === "sm" ? "text-xs" : "text-sm",
                    "data-[highlighted]:bg-raised data-[state=checked]:font-medium",
                  )}
                >
                  <RadixSelect.ItemIndicator className="absolute left-2 inline-flex items-center">
                    <Check aria-hidden="true" className="size-3.5" />
                  </RadixSelect.ItemIndicator>
                  <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
                </RadixSelect.Item>
              ))}
            </RadixSelect.Viewport>
          </RadixSelect.Content>
        </RadixSelect.Portal>
      </RadixSelect.Root>
      {description && (
        <p id={descriptionId} className={fieldDescriptionClass}>
          {description}
        </p>
      )}
    </div>
  );
}
