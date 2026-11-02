"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { ChevronDown, ChevronRight } from "lucide-react";

export interface FormSectionProps {
  title: string;
  description?: string;
  children: React.ReactNode;
  collapsible?: boolean;
  defaultOpen?: boolean;
  className?: string;
  badge?: React.ReactNode;
}

export const FormSection: React.FC<FormSectionProps> = ({
  title,
  description,
  children,
  collapsible = false,
  defaultOpen = true,
  className,
  badge,
}) => {
  const [isOpen, setIsOpen] = React.useState(defaultOpen);
  const sectionId = React.useId();

  if (!collapsible) {
    return (
      <div className={cn("space-y-3 pt-2 first:pt-0", className)}>
        <div className="flex items-center justify-between border-b border-slate-100 pb-1.5">
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600">
              {title}
            </h4>
            {description && (
              <p className="text-[11px] text-slate-400 mt-0.5">{description}</p>
            )}
          </div>
          {badge}
        </div>
        <div className="space-y-3">{children}</div>
      </div>
    );
  }

  return (
    <div className={cn("border border-slate-200/80 rounded-xl overflow-hidden bg-white", className)}>
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={sectionId}
        onClick={() => setIsOpen((prev) => !prev)}
        className="w-full p-3 sm:p-3.5 flex items-center justify-between bg-slate-50/60 hover:bg-slate-50 transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          {isOpen ? (
            <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
          ) : (
            <ChevronRight className="w-4 h-4 text-slate-400 shrink-0" />
          )}
          <div>
            <span className="text-xs font-bold text-slate-700 block">
              {title}
            </span>
            {description && (
              <span className="text-[11px] text-slate-400 block mt-0.5 font-normal">
                {description}
              </span>
            )}
          </div>
        </div>
        {badge}
      </button>

      {isOpen && (
        <div id={sectionId} className="p-3.5 sm:p-4 space-y-3 border-t border-slate-100 animate-in fade-in duration-100">
          {children}
        </div>
      )}
    </div>
  );
};
