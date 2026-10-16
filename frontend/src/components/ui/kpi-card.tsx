import * as React from "react";
import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus, Info } from "lucide-react";

export interface KpiCardProps {
  title: string;
  subtitle?: string;
  value: string | number;
  trend?: {
    value: string | number;
    direction: "up" | "down" | "neutral";
    label?: string;
  };
  accentColor?: "peach" | "coral" | "navy" | "none";
  breakdown?: Array<{
    label: string;
    value: string | number;
  }>;
  tooltipText?: string;
  icon?: React.ReactNode;
  className?: string;
}

export const KpiCard: React.FC<KpiCardProps> = ({
  title,
  subtitle,
  value,
  trend,
  accentColor = "peach",
  breakdown,
  tooltipText,
  icon,
  className,
}) => {
  return (
    <div
      className={cn(
        "relative rounded-xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] transition-all hover:shadow-[0_4px_12px_rgba(0,0,0,0.06)] flex flex-col justify-between",
        accentColor === "peach" && "border-t-[3px] border-t-agile-orange",
        accentColor === "coral" && "border-t-[3px] border-t-agile-red",
        accentColor === "navy" && "border-t-[3px] border-t-header",
        className
      )}
    >
      <div>
        {/* Top row: Title, Subtitle, Tooltip / Icon */}
        <div className="flex items-start justify-between gap-2 mb-2">
          <div>
            <div className="flex items-center gap-1.5">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                {title}
              </h4>
              {tooltipText && (
                <span
                  title={tooltipText}
                  className="cursor-help text-slate-400 hover:text-slate-600 transition-colors"
                >
                  <Info className="w-3.5 h-3.5" />
                </span>
              )}
            </div>
            {subtitle && (
              <p className="text-[11px] text-slate-400 font-normal mt-0.5">
                {subtitle}
              </p>
            )}
          </div>
          {icon && (
            <div className="p-2 rounded-lg bg-agile-lightorange/70 text-agile-red border border-agile-outlinered/20">
              {icon}
            </div>
          )}
        </div>

        {/* Primary Metric Value */}
        <div className="mt-2 flex items-baseline gap-2.5">
          <span className="text-2xl md:text-3xl font-bold tracking-tight text-header">
            {value}
          </span>

          {/* Trend Pill */}
          {trend && (
            <span
              className={cn(
                "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium",
                trend.direction === "up" &&
                  "bg-emerald-50 text-emerald-700 border border-emerald-200/60",
                trend.direction === "down" &&
                  "bg-agile-lightorange text-agile-red border border-agile-outlinered/40",
                trend.direction === "neutral" &&
                  "bg-slate-100 text-slate-600 border border-slate-200"
              )}
            >
              {trend.direction === "up" && <TrendingUp className="w-3 h-3" />}
              {trend.direction === "down" && <TrendingDown className="w-3 h-3" />}
              {trend.direction === "neutral" && <Minus className="w-3 h-3" />}
              <span>{trend.value}</span>
              {trend.label && (
                <span className="text-[10px] text-slate-400 font-normal ml-0.5">
                  {trend.label}
                </span>
              )}
            </span>
          )}
        </div>
      </div>

      {/* Optional ticker / category breakdown row */}
      {breakdown && breakdown.length > 0 && (
        <div className="mt-4 pt-3 border-t border-slate-100 grid grid-cols-2 sm:grid-cols-3 gap-2">
          {breakdown.map((item, idx) => (
            <div key={idx} className="flex flex-col">
              <span className="text-[10px] uppercase font-semibold text-slate-400">
                {item.label}
              </span>
              <span className="text-xs font-semibold text-slate-700">
                {item.value}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
