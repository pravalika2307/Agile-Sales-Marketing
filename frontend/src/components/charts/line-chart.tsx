"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface LinePoint {
  label: string;
  value: number;
}

export interface LineChartProps {
  data: LinePoint[];
  height?: number;
  strokeColor?: string; // Defaults to #d7525a (Agile coral)
  fillColor?: string; // Defaults to #fff6f0 (Agile light orange)
  pointColor?: string; // Defaults to #d7525a
  formatValue?: (val: number) => string;
  className?: string;
}

export const LineChart: React.FC<LineChartProps> = ({
  data,
  height = 200,
  strokeColor = "#d7525a",
  fillColor = "rgba(215, 82, 90, 0.08)",
  pointColor = "#d7525a",
  formatValue = (v) => v.toString(),
  className,
}) => {
  const [activeIdx, setActiveIdx] = React.useState<number | null>(null);

  if (data.length === 0) {
    return (
      <div
        className={cn(
          "w-full flex flex-col items-center justify-center text-center p-6 border border-dashed border-slate-200 rounded-lg bg-slate-50/40 text-slate-400 select-none",
          className
        )}
        style={{ height }}
      >
        <p className="text-xs font-medium text-slate-500">No pipeline velocity data available yet</p>
        <p className="text-[11px] text-slate-400 mt-0.5">
          Opportunity progression will be calculated as deals advance through stages.
        </p>
      </div>
    );
  }

  const maxVal = Math.max(...data.map((d) => d.value)) * 1.15 || 100;
  const minVal = 0;

  const width = 600;
  const svgHeight = height;
  const paddingX = 20;
  const paddingY = 24;

  const availableWidth = width - paddingX * 2;
  const availableHeight = svgHeight - paddingY * 2;

  // Calculate coordinates for SVG path
  const points = data.map((d, i) => {
    const x = paddingX + (i / (data.length - 1)) * availableWidth;
    const y =
      paddingY + availableHeight - (d.value / (maxVal - minVal)) * availableHeight;
    return { x, y, ...d };
  });

  const pathD = points.reduce((acc, curr, i) => {
    return i === 0 ? `M ${curr.x} ${curr.y}` : `${acc} L ${curr.x} ${curr.y}`;
  }, "");

  const areaD = `${pathD} L ${points[points.length - 1].x} ${
    paddingY + availableHeight
  } L ${points[0].x} ${paddingY + availableHeight} Z`;

  return (
    <div className={cn("w-full flex flex-col select-none", className)}>
      <div className="relative w-full overflow-hidden" style={{ height }}>
        {/* Active Hover Tooltip */}
        {activeIdx !== null && (
          <div
            className="absolute z-20 -translate-x-1/2 rounded-md bg-header px-2.5 py-1 text-[11px] font-medium text-white shadow-md pointer-events-none"
            style={{
              left: `${(points[activeIdx].x / width) * 100}%`,
              top: Math.max(0, points[activeIdx].y - 38),
            }}
          >
            <div className="font-semibold text-slate-300">
              {data[activeIdx].label}
            </div>
            <div className="text-white">
              {formatValue(data[activeIdx].value)}
            </div>
          </div>
        )}

        <svg
          viewBox={`0 0 ${width} ${svgHeight}`}
          className="w-full h-full overflow-visible"
          preserveAspectRatio="none"
        >
          {/* Grid lines */}
          <line
            x1={paddingX}
            y1={paddingY}
            x2={width - paddingX}
            y2={paddingY}
            stroke="#e2e8f0"
            strokeDasharray="4 4"
            strokeWidth="1"
          />
          <line
            x1={paddingX}
            y1={paddingY + availableHeight / 2}
            x2={width - paddingX}
            y2={paddingY + availableHeight / 2}
            stroke="#e2e8f0"
            strokeDasharray="4 4"
            strokeWidth="1"
          />
          <line
            x1={paddingX}
            y1={paddingY + availableHeight}
            x2={width - paddingX}
            y2={paddingY + availableHeight}
            stroke="#e2e8f0"
            strokeWidth="1"
          />

          {/* Area Fill */}
          <path d={areaD} fill={fillColor} />

          {/* Line Stroke */}
          <path
            d={pathD}
            fill="none"
            stroke={strokeColor}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Points */}
          {points.map((p, i) => (
            <g key={i}>
              <circle
                cx={p.x}
                cy={p.y}
                r={activeIdx === i ? 5.5 : 4}
                fill="#ffffff"
                stroke={pointColor}
                strokeWidth={activeIdx === i ? 3 : 2}
                className="transition-all cursor-pointer"
                onMouseEnter={() => setActiveIdx(i)}
                onMouseLeave={() => setActiveIdx(null)}
              />
            </g>
          ))}
        </svg>
      </div>

      {/* X Axis */}
      <div className="flex items-center justify-between pt-2 px-2 text-[11px] font-medium text-slate-500">
        {data.map((item, idx) => (
          <span key={idx} className="truncate">
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
};
