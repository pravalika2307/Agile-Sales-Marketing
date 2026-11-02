"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface EmptyStateProps {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon,
  title,
  description,
  action,
  className,
}) => {
  return (
    <div
      className={cn(
        "rounded-xl border border-dashed border-slate-200/90 bg-slate-50/40 p-8 text-center flex flex-col items-center justify-center",
        className
      )}
    >
      {Icon && (
        <div className="w-10 h-10 rounded-xl bg-slate-100 text-slate-500 flex items-center justify-center mb-3">
          <Icon className="w-5 h-5" />
        </div>
      )}
      <h3 className="text-sm font-semibold text-[#09272B] mb-1">{title}</h3>
      <p className="text-xs text-slate-500 max-w-sm mb-4 leading-relaxed">
        {description}
      </p>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
};
