import React from "react";
import { cn } from "@/lib/utils";
import { AlertCircle } from "lucide-react";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  optional?: boolean;
  icon?: React.ReactNode;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  (
    {
      className,
      label,
      error,
      helperText,
      optional,
      icon,
      type = "text",
      id,
      required,
      suppressHydrationWarning = true,
      ...props
    },
    ref
  ) => {
    const generatedId = React.useId();
    const inputId = id || generatedId;
    const errorId = `${inputId}-error`;
    const helperId = `${inputId}-helper`;

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
            htmlFor={inputId}
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
        <div className="w-full relative">
          {icon && (
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
              {icon}
            </div>
          )}
          <input
            id={inputId}
            type={type}
            ref={ref}
            required={required}
            aria-invalid={Boolean(error)}
            aria-describedby={describedBy}
            suppressHydrationWarning={suppressHydrationWarning}
            className={cn(
              "w-full h-9 rounded-lg bg-white border border-slate-200 text-sm text-[#09272B] placeholder:text-slate-400 py-1.5 transition-all shadow-2xs",
              icon ? "pl-9 pr-3" : "px-3",
              "outline-none focus:border-[#d7525a] focus:ring-2 focus:ring-[#d7525a]/15 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400",
              error && "border-rose-500 focus:border-rose-500 focus:ring-rose-500/20",
              className
            )}
            {...props}
          />
        </div>
        {error && (
          <p
            id={errorId}
            role="alert"
            className="mt-1 text-xs text-rose-600 font-medium flex items-center gap-1"
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

Input.displayName = "Input";
