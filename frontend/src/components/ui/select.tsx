import * as React from "react";
import { cn } from "@/lib/utils";
import { ChevronDown, AlertCircle } from "lucide-react";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps
  extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  helperText?: string;
  optional?: boolean;
  options?: SelectOption[];
  icon?: React.ReactNode;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  (
    {
      className,
      label,
      error,
      helperText,
      optional,
      options,
      children,
      icon,
      id,
      required,
      suppressHydrationWarning = true,
      ...props
    },
    ref
  ) => {
    const generatedId = React.useId();
    const selectId = id || generatedId;
    const errorId = `${selectId}-error`;
    const helperId = `${selectId}-helper`;

    const describedBy = [
      error ? errorId : null,
      helperText ? helperId : null,
      props["aria-describedby"],
    ]
      .filter(Boolean)
      .join(" ") || undefined;

    return (
      <div className="w-full space-y-1.5">
        {label && (
          <label
            htmlFor={selectId}
            className="block text-xs font-semibold text-slate-700"
          >
            <span>{label}</span>
            {required && !label.includes("*") && (
              <>
                <span className="text-agile-red ml-0.5" aria-hidden="true">
                  *
                </span>
                <span className="sr-only"> (required)</span>
              </>
            )}
            {optional && (
              <span className="text-slate-400 font-normal text-[11px] ml-1.5">
                (optional)
              </span>
            )}
          </label>
        )}
        <div className="relative">
          {icon && (
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
              {icon}
            </div>
          )}
          <select
            id={selectId}
            ref={ref}
            required={required}
            aria-invalid={Boolean(error)}
            aria-describedby={describedBy}
            suppressHydrationWarning={suppressHydrationWarning}
            className={cn(
              "w-full h-9 appearance-none rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-[#09272B] shadow-2xs transition-all focus:border-[#d7525a] focus:outline-none focus:ring-2 focus:ring-[#d7525a]/15 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400 pr-9",
              icon && "pl-9",
              error && "border-rose-500 focus:border-rose-500 focus:ring-rose-500/20",
              className
            )}
            {...props}
          >
            {options
              ? options.map((opt) => (
                  <option
                    key={opt.value}
                    value={opt.value}
                    disabled={opt.disabled}
                  >
                    {opt.label}
                  </option>
                ))
              : children}
          </select>
          <div className="absolute inset-y-0 right-0 pr-2.5 flex items-center pointer-events-none text-slate-400">
            <ChevronDown className="w-4 h-4" />
          </div>
        </div>
        {error && (
          <p
            id={errorId}
            role="alert"
            className="text-xs text-rose-600 font-medium flex items-center gap-1 mt-1"
          >
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            <span>{error}</span>
          </p>
        )}
        {helperText && !error && (
          <p id={helperId} className="mt-1 text-[11px] text-slate-500 leading-normal">
            {helperText}
          </p>
        )}
      </div>
    );
  }
);
Select.displayName = "Select";
