"use client";

import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { ChevronRight } from "lucide-react";

export interface PageHeaderBreadcrumb {
  label: string;
  href?: string;
}

export interface PageHeaderCategory {
  icon?: React.ComponentType<{ className?: string }>;
  label: string;
}

export interface PageHeaderProps {
  title: string;
  description?: string;
  breadcrumbs?: PageHeaderBreadcrumb[];
  category?: PageHeaderCategory;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  description,
  breadcrumbs,
  category,
  badge,
  actions,
  className,
  children,
}) => {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 pb-5 border-b border-slate-200/80",
        className
      )}
    >
      {/* Optional Breadcrumb or Category Bar */}
      {(breadcrumbs || category) && (
        <div className="flex items-center gap-1.5 text-xs text-slate-500 font-medium">
          {category && (
            <div className="flex items-center gap-1.5 uppercase tracking-wider text-[11px] font-semibold text-slate-500">
              {category.icon && (
                <category.icon className="w-3.5 h-3.5 text-[#d7525a]" />
              )}
              <span>{category.label}</span>
            </div>
          )}

          {breadcrumbs && (
            <nav aria-label="Breadcrumb" className="flex items-center gap-1.5">
              {breadcrumbs.map((crumb, idx) => {
                const isLast = idx === breadcrumbs.length - 1;
                return (
                  <React.Fragment key={idx}>
                    {idx > 0 && (
                      <ChevronRight className="w-3 h-3 text-slate-300 shrink-0" />
                    )}
                    {crumb.href && !isLast ? (
                      <Link
                        href={crumb.href}
                        className="hover:text-slate-900 transition-colors text-slate-500"
                      >
                        {crumb.label}
                      </Link>
                    ) : (
                      <span
                        className={cn(
                          isLast ? "font-semibold text-[#09272B]" : "text-slate-500"
                        )}
                      >
                        {crumb.label}
                      </span>
                    )}
                  </React.Fragment>
                );
              })}
            </nav>
          )}
        </div>
      )}

      {/* Main Title & Action Row */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[#09272B]">
              {title}
            </h1>
            {badge && <div className="shrink-0">{badge}</div>}
          </div>
          {description && (
            <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-3xl leading-relaxed">
              {description}
            </p>
          )}
        </div>

        {actions && (
          <div className="flex items-center gap-2.5 flex-wrap sm:shrink-0">
            {actions}
          </div>
        )}
      </div>

      {/* Optional sub-header controls/tabs */}
      {children && <div className="pt-2">{children}</div>}
    </div>
  );
};
