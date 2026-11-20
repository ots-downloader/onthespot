import type { ReactNode } from "react";
import { Dialog as RadixDialog } from "radix-ui";
import { X } from "lucide-react";
import { cn } from "../../lib/cn";
import { focusRing } from "./Button";

export type DialogSize = "md" | "lg";

const sizeClass: Record<DialogSize, string> = {
  md: "max-w-lg",
  lg: "max-w-2xl",
};

export interface DialogProps {
  isOpen: boolean;
  /** Runs on the close button and, when dismissible, on Escape and scrim click. */
  onClose: () => void;
  /** False keeps the dialog open on Escape and scrim click. Default true. */
  dismissible?: boolean;
  title: ReactNode;
  description?: ReactNode;
  /** Shown in a tile before the title. */
  icon?: ReactNode;
  size?: DialogSize;
  children?: ReactNode;
  /** Pinned below the scrolling body. */
  footer?: ReactNode;
  /** Accessible name of the close button. */
  closeLabel?: string;
  /** Id on the dialog panel. */
  id?: string;
  /** Class for the dialog panel. */
  className?: string;
  /** Class for the scrolling body. */
  bodyClassName?: string;
}

export function Dialog({
  isOpen,
  onClose,
  dismissible = true,
  title,
  description,
  icon,
  size = "md",
  children,
  footer,
  closeLabel = "Close dialog",
  id,
  className,
  bodyClassName,
}: DialogProps) {
  return (
    <RadixDialog.Root
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-50 bg-scrim backdrop-blur-xs" />
        <RadixDialog.Content
          id={id}
          onEscapeKeyDown={dismissible ? undefined : (event) => event.preventDefault()}
          onInteractOutside={dismissible ? undefined : (event) => event.preventDefault()}
          // Without a description Radix warns unless this is set to undefined.
          {...(description ? {} : { "aria-describedby": undefined })}
          className={cn(
            "fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl border border-line bg-overlay text-fg shadow-2xl focus:outline-none",
            sizeClass[size],
            className,
          )}
        >
          <div className="flex shrink-0 items-start justify-between gap-4 border-b border-line px-5 py-4 sm:px-6">
            <div className="flex min-w-0 items-start gap-3">
              {icon && (
                <div
                  aria-hidden="true"
                  className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent-subtle text-accent [&_svg]:size-5"
                >
                  {icon}
                </div>
              )}
              <div className="min-w-0">
                <RadixDialog.Title className="text-base font-semibold text-fg">
                  {title}
                </RadixDialog.Title>
                {description && (
                  <RadixDialog.Description className="mt-1 text-xs text-fg-muted">
                    {description}
                  </RadixDialog.Description>
                )}
              </div>
            </div>
            <RadixDialog.Close
              aria-label={closeLabel}
              title={closeLabel}
              className={cn(
                "flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-lg text-fg-subtle transition-colors hover:bg-raised hover:text-fg",
                focusRing,
              )}
            >
              <X aria-hidden="true" className="size-4" />
            </RadixDialog.Close>
          </div>

          <div
            className={cn(
              "min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5 sm:px-6",
              bodyClassName,
            )}
          >
            {children}
          </div>

          {footer && (
            <div className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-line px-5 py-4 sm:px-6">
              {footer}
            </div>
          )}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
