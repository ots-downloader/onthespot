import { useId, type ReactNode } from "react";
import { Switch as RadixSwitch } from "radix-ui";
import { cn } from "../../lib/cn";
import { focusRing } from "./Button";

export interface SwitchProps {
  label: string;
  description?: ReactNode;
  value: boolean;
  onChange?: (checked: boolean) => void;
  className?: string;
}

/** Label and description on the left, the switch at the right edge. */
export function Switch({
  label,
  description,
  value,
  onChange,
  className,
}: SwitchProps) {
  const switchId = `switch-${useId()}`;
  const descriptionId = description ? `${switchId}-description` : undefined;

  const control = (
    <RadixSwitch.Root
      id={switchId}
      checked={value}
      onCheckedChange={(checked) => onChange?.(checked)}
      aria-describedby={descriptionId}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border border-transparent transition-colors",
        "data-[state=checked]:bg-accent data-[state=unchecked]:bg-line-strong",
        focusRing,
        "focus-visible:ring-offset-2 focus-visible:ring-offset-body",
      )}
    >
      <RadixSwitch.Thumb className="pointer-events-none block size-4 rounded-full bg-white shadow-sm transition-transform data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0.5" />
    </RadixSwitch.Root>
  );

  const text = (
    <div className="min-w-0">
      <label htmlFor={switchId} className="block cursor-pointer text-sm font-medium text-fg">
        {label}
      </label>
      {description && (
        <p id={descriptionId} className="mt-0.5 text-[11px] text-fg-subtle">
          {description}
        </p>
      )}
    </div>
  );

  return (
    <div className={cn("flex items-start gap-3 w-full justify-between", className)}>
      {text}
      <div className="pt-0.5">{control}</div>
    </div>
  );
}
