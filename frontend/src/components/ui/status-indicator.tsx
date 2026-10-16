import * as React from "react";
import { cn } from "@/lib/utils";

export type StatusType =
  | "active"
  | "success"
  | "warning"
  | "error"
  | "neutral"
  | "pending";

export interface StatusIndicatorProps {
  status: StatusType;
  label?: string;
  pulse?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  status,
  label,
  pulse = false,
  size = "md",
  className,
}) => {
  const dotColor = {
    active: "bg-agile-red",
    success: "bg-emerald-500",
    warning: "bg-amber-500",
    error: "bg-agile-red",
    neutral: "bg-slate-400",
    pending: "bg-agile-orange",
  }[status];

  const dotSize = {
    sm: "w-1.5 h-1.5",
    md: "w-2 h-2",
    lg: "w-2.5 h-2.5",
  }[size];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 text-xs font-medium text-slate-700",
        className
      )}
    >
      <span className="relative flex items-center justify-center">
        {pulse && (
          <span
            className={cn(
              "absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping",
              dotColor
            )}
          />
        )}
        <span className={cn("relative rounded-full", dotColor, dotSize)} />
      </span>
      {label && <span>{label}</span>}
    </span>
  );
};
