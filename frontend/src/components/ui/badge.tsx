import React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "coral" | "peach" | "success" | "warning" | "neutral" | "info";
  size?: "sm" | "md";
  dot?: boolean;
}

export const Badge: React.FC<BadgeProps> = ({
  className,
  variant = "neutral",
  size = "md",
  dot = false,
  children,
  ...props
}) => {
  const variantStyles = {
    // Coral: Agile primary accent
    coral: "bg-[#fff6f0] text-[#d7525a] border-[#e45e5e]/30",
    // Peach: Agile secondary accent
    peach: "bg-[#ebad8f]/15 text-[#b85d38] border-[#ebad8f]/40",
    // Success: Green
    success: "bg-emerald-50 text-emerald-700 border-emerald-200",
    // Warning: Amber
    warning: "bg-amber-50 text-amber-700 border-amber-200",
    // Neutral: Slate gray
    neutral: "bg-slate-100 text-slate-700 border-slate-200",
    // Info: Light blue
    info: "bg-sky-50 text-sky-700 border-sky-200",
  };

  const dotColor = {
    coral: "bg-[#d7525a]",
    peach: "bg-[#ebad8f]",
    success: "bg-emerald-500",
    warning: "bg-amber-500",
    neutral: "bg-slate-400",
    info: "bg-sky-500",
  };

  const sizeStyles = {
    sm: "text-[11px] px-2 py-0.5 rounded-full font-medium border",
    md: "text-xs px-2.5 py-1 rounded-full font-medium border",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 select-none",
        variantStyles[variant],
        sizeStyles[size],
        className
      )}
      {...props}
    >
      {dot && <span className={cn("w-1.5 h-1.5 rounded-full", dotColor[variant])} />}
      {children}
    </span>
  );
};
