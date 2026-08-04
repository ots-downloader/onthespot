import React from "react";
import { ChevronDown } from "lucide-react";

type OtsSelectProps = React.SelectHTMLAttributes<HTMLSelectElement>;

/**
 * A browser-independent select shell. Native select arrows vary between
 * Chromium builds (and can appear in the top-left on Linux), so the visual
 * indicator lives outside the native control while the select stays fully
 * keyboard and screen-reader accessible.
 */
export const OtsSelect: React.FC<OtsSelectProps> = ({ className = "", children, ...props }) => (
  <span className={`ots-select-control ${className}`}>
    <select {...props} className="ots-select h-full w-full">
      {children}
    </select>
    <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8f8f8f]" />
  </span>
);
