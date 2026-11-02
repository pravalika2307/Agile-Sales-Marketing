import React from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "primary-outline" | "ghost" | "destructive";
  size?: "xs" | "sm" | "md" | "lg" | "icon";
  isLoading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = "primary",
      size = "md",
      isLoading = false,
      disabled,
      children,
      suppressHydrationWarning = true,
      ...props
    },
    ref
  ) => {
    const baseStyles =
      "inline-flex items-center justify-center font-medium transition-all duration-150 ease-in-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 disabled:opacity-50 disabled:pointer-events-none cursor-pointer select-none active:scale-[0.99]";

    const variantStyles = {
      // Primary: Agile coral #d7525a
      primary:
        "bg-[#d7525a] hover:bg-[#c5444c] active:bg-[#b53a42] text-white shadow-xs focus-visible:ring-[#d7525a]/30",
      // Secondary: Clean white surface with slate border, dark text
      secondary:
        "bg-white hover:bg-slate-50 active:bg-slate-100 text-[#09272B] border border-slate-200/90 shadow-xs focus-visible:ring-slate-300",
      // Outline: Neutral outline with slate border
      outline:
        "bg-transparent hover:bg-slate-100/80 active:bg-slate-200/60 text-slate-700 border border-slate-200 focus-visible:ring-slate-300",
      // Primary Outline: Transparent with agile coral outline
      "primary-outline":
        "bg-transparent hover:bg-[#fff6f0] active:bg-[#ffede2] text-[#d7525a] border border-[#d7525a]/80 focus-visible:ring-[#d7525a]/30",
      // Ghost: Minimal hover surface
      ghost:
        "bg-transparent hover:bg-slate-100 active:bg-slate-200/60 text-slate-700 focus-visible:ring-slate-300",
      // Destructive: Clean rose for critical/irreversible actions
      destructive:
        "bg-rose-600 hover:bg-rose-700 active:bg-rose-800 text-white shadow-xs focus-visible:ring-rose-500/30",
    };

    const sizeStyles = {
      xs: "h-7 px-2.5 text-[11px] rounded-md gap-1",
      sm: "h-8 px-3 text-xs rounded-lg gap-1.5",
      md: "h-9 px-3.5 text-xs font-semibold rounded-lg gap-1.5",
      lg: "h-10 px-5 text-sm font-semibold rounded-lg gap-2",
      icon: "h-9 w-9 p-0 rounded-lg",
    };

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        suppressHydrationWarning={suppressHydrationWarning}
        className={cn(baseStyles, variantStyles[variant], sizeStyles[size], className)}
        {...props}
      >
        {isLoading && (
          <svg
            className="animate-spin -ml-0.5 mr-1.5 h-3.5 w-3.5 text-current shrink-0"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        )}
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";
