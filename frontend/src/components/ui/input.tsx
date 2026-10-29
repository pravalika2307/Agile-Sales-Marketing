import React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  icon?: React.ReactNode;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, icon, type = "text", id, suppressHydrationWarning = true, ...props }, ref) => {
    const inputId = id || React.useId();
    return (
      <div className="w-full space-y-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-xs font-semibold text-slate-700"
          >
            {label}
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
            suppressHydrationWarning={suppressHydrationWarning}
            className={cn(
              "w-full rounded-lg bg-white border border-slate-200 text-sm text-[#09272B] placeholder:text-slate-400 py-2 transition-all",
              icon ? "pl-9 pr-3" : "px-3",
              "outline-none focus:border-[#d7525a] focus:ring-2 focus:ring-[#d7525a]/15",
              error && "border-rose-500 focus:border-rose-500 focus:ring-rose-500/20",
              className
            )}
            {...props}
          />
        </div>
        {error && <p className="mt-1 text-xs text-rose-600 font-medium">{error}</p>}
      </div>
    );
  }
);

Input.displayName = "Input";
