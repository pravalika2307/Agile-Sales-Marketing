"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface BarDatum {
  label: string;
  value: number;
  secondaryValue?: number;
}

export interface BarChartProps {
  data: BarDatum[];
  height?: number;
  primaryColor?: string; // Defaults to #d7525a (Agile coral)
  secondaryColor?: string; // Defaults to #ebad8f (Agile peach)
  primaryLabel?: string;
  secondaryLabel?: string;
  formatValue?: (val: number) => string;
  className?: string;
}

export const BarChart: React.FC<BarChartProps> = ({
  data,
  height = 220,
  primaryColor = "#d7525a",
  secondaryColor = "#ebad8f",
  primaryLabel = "Primary",
  secondaryLabel,
  formatValue = (v) => v.toString(),
  className,
}) => {
  const [hoveredIdx, setHoveredIdx] = React.useState<number | null>(null);

  const maxVal = React.useMemo(() => {
    let m = 0;
    data.forEach((d) => {
      if (d.value > m) m = d.value;
      if (d.secondaryValue && d.secondaryValue > m) m = d.secondaryValue;
    });
    return m > 0 ? m * 1.15 : 100;
  }, [data]);

  if (data.length === 0) {
    return (
      <div
        className={cn(
          "w-full flex flex-col items-center justify-center text-center p-6 border border-dashed border-slate-200 rounded-lg bg-slate-50/40 text-slate-400 select-none",
          className
        )}
        style={{ height }}
      >
        <p className="text-xs font-medium text-slate-500">No outreach data available yet</p>
        <p className="text-[11px] text-slate-400 mt-0.5">
          Values will calculate automatically once live outreach events exist.
        </p>
      </div>
    );
  }

  return (
    <div className={cn("w-full flex flex-col select-none", className)}>
      {/* Chart visualization */}
      <div
        className="w-full relative flex items-end justify-between gap-2 pt-6 pb-2 border-b border-slate-200"
        style={{ height }}
      >
        {/* Subtle horizontal grid lines */}
        <div className="absolute inset-0 flex flex-col justify-between pointer-events-none pb-2 pt-6">
          <div className="w-full border-b border-dashed border-slate-200/60" />
          <div className="w-full border-b border-dashed border-slate-200/60" />
          <div className="w-full border-b border-dashed border-slate-200/60" />
        </div>

        {data.map((item, idx) => {
          const pHeightPercent = Math.max(
            4,
            Math.round((item.value / maxVal) * 100)
          );
          const sHeightPercent = item.secondaryValue
            ? Math.max(4, Math.round((item.secondaryValue / maxVal) * 100))
            : 0;

          const isHovered = hoveredIdx === idx;

          return (
            <div
              key={idx}
              className="flex-1 h-full flex flex-col justify-end items-center relative group cursor-pointer"
              onMouseEnter={() => setHoveredIdx(idx)}
              onMouseLeave={() => setHoveredIdx(null)}
            >
              {/* Tooltip on hover */}
              {isHovered && (
                <div className="absolute -top-10 z-20 whitespace-nowrap rounded-md bg-header px-2.5 py-1 text-[11px] font-medium text-white shadow-lg pointer-events-none">
                  <div className="font-semibold text-slate-200 mb-0.5">
                    {item.label}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-1">
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{ backgroundColor: primaryColor }}
                      />
                      <span>
                        {primaryLabel}: {formatValue(item.value)}
                      </span>
                    </span>
                    {item.secondaryValue !== undefined && (
                      <span className="flex items-center gap-1 text-slate-300">
                        <span
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: secondaryColor }}
                        />
                        <span>
                          {secondaryLabel}: {formatValue(item.secondaryValue)}
                        </span>
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Bar Group */}
              <div className="w-full max-w-[44px] flex items-end justify-center gap-1 h-full">
                {/* Primary Bar (Coral) */}
                <div
                  className="w-full rounded-t-sm transition-all duration-200"
                  style={{
                    height: `${pHeightPercent}%`,
                    backgroundColor: primaryColor,
                    opacity: hoveredIdx !== null && !isHovered ? 0.6 : 1,
                  }}
                />

                {/* Secondary Bar (Peach) */}
                {item.secondaryValue !== undefined && (
                  <div
                    className="w-full rounded-t-sm transition-all duration-200"
                    style={{
                      height: `${sHeightPercent}%`,
                      backgroundColor: secondaryColor,
                      opacity: hoveredIdx !== null && !isHovered ? 0.6 : 1,
                    }}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* X-Axis Labels */}
      <div className="flex items-center justify-between pt-2 px-1 text-[11px] font-medium text-slate-500">
        {data.map((item, idx) => (
          <div key={idx} className="flex-1 text-center truncate px-0.5">
            {item.label}
          </div>
        ))}
      </div>
    </div>
  );
};
