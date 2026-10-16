import React from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "destructive";
  size?: "sm" | "md" | "lg" | "icon";
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
      ...props
    },
    ref
  ) => {
    const baseStyles =
      "inline-flex items-center justify-center font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none cursor-pointer select-none";

    const variantStyles = {
      // Primary: Agile coral #d7525a, hover: softer peach/coral #c5444c or #ebad8f
      primary:
        "bg-[#d7525a] hover:bg-[#c5444c] text-white shadow-sm focus-visible:ring-[#d7525a]",
      // Secondary: Clean white surface with subtle gray border, dark text
      secondary:
        "bg-white hover:bg-slate-50 text-[#09272B] border border-slate-200 shadow-sm focus-visible:ring-slate-300",
      // Outline: Transparent with coral or slate outline
      outline:
        "bg-transparent hover:bg-[#fff6f0] text-[#d7525a] border border-[#d7525a] focus-visible:ring-[#d7525a]",
      // Ghost: Minimal hover surface
      ghost:
        "bg-transparent hover:bg-slate-100 text-[#09272B] focus-visible:ring-slate-300",
      // Destructive: Coral/red variant for deletions
      destructive:
        "bg-rose-600 hover:bg-rose-700 text-white shadow-sm focus-visible:ring-rose-500",
    };

    const sizeStyles = {
      sm: "h-8 px-3 text-xs rounded-md gap-1.5",
      md: "h-9 px-4 text-sm rounded-lg gap-2",
      lg: "h-11 px-6 text-base rounded-lg gap-2.5",
      icon: "h-9 w-9 p-0 rounded-lg",
    };

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={cn(baseStyles, variantStyles[variant], sizeStyles[size], className)}
        {...props}
      >
        {isLoading && (
          <svg
            className="animate-spin -ml-1 mr-2 h-4 w-4 text-current"
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
