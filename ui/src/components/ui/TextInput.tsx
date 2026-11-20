import {
  useId,
  useRef,
  type ComponentProps,
  type ReactNode,
} from "react";
import { X } from "lucide-react";
import { cn } from "../../lib/cn";
import { focusRing } from "./Button";

export type TextInputSize = "sm" | "md";

const sizeClass: Record<TextInputSize, string> = {
  sm: "h-8 text-xs",
  md: "h-9 text-sm",
};

/** Shared look for the input box, used by TextInput and Select. */
export const fieldBoxClass =
  "w-full rounded-lg border border-line-strong bg-surface text-fg placeholder:text-fg-subtle transition-colors";

export const fieldLabelClass = "mb-1.5 block text-xs font-medium text-fg-muted";
export const fieldDescriptionClass = "mt-1 text-[11px] text-fg-subtle";

export interface TextInputProps
  extends Omit<
    ComponentProps<"input">,
    "onChange" | "value" | "size" | "disabled" | "defaultValue" | "ref"
  > {
  label: string;
  /** Keeps a real <label> for screen readers but hides it on screen. */
  isLabelHidden?: boolean;
  value: string;
  onChange?: (value: string) => void;
  description?: ReactNode;
  startIcon?: ReactNode;
  /** Shows a clear button while the field has a value. */
  hasClear?: boolean;
  size?: TextInputSize;
}

export function TextInput({
  label,
  isLabelHidden = false,
  value,
  onChange,
  description,
  startIcon,
  hasClear = false,
  size = "md",
  type = "text",
  id,
  className,
  ...rest
}: TextInputProps) {
  const autoId = useId();
  const inputId = id ?? `text-input-${autoId}`;
  const descriptionId = description ? `${inputId}-description` : undefined;
  const inputRef = useRef<HTMLInputElement>(null);
  const showClear = hasClear && value.length > 0;

  return (
    <div className="w-full">
      <label
        htmlFor={inputId}
        className={cn(fieldLabelClass, isLabelHidden && "sr-only")}
      >
        {label}
      </label>
      <div className="relative">
        {startIcon && (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-fg-subtle"
          >
            {startIcon}
          </span>
        )}
        <input
          ref={inputRef}
          id={inputId}
          type={type}
          value={value}
          aria-describedby={descriptionId}
          onChange={(event) => onChange?.(event.target.value)}
          className={cn(
            fieldBoxClass,
            focusRing,
            sizeClass[size],
            startIcon ? "pl-9" : "pl-3",
            showClear ? "pr-9" : "pr-3",
            className,
          )}
          {...rest}
        />
        {showClear && (
          <button
            type="button"
            aria-label={`Clear ${label}`}
            title="Clear"
            onClick={() => {
              onChange?.("");
              inputRef.current?.focus();
            }}
            className={cn(
              "absolute inset-y-0 right-1.5 my-auto flex size-6 items-center justify-center rounded-md text-fg-subtle hover:bg-raised hover:text-fg cursor-pointer",
              focusRing,
            )}
          >
            <X aria-hidden="true" className="size-3.5" />
          </button>
        )}
      </div>
      {description && (
        <p id={descriptionId} className={fieldDescriptionClass}>
          {description}
        </p>
      )}
    </div>
  );
}
