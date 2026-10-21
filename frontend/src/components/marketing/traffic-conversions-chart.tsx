"use client";

import * as React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { TrendingUp, ArrowUpRight } from "lucide-react";

export interface DataPoint {
  date: string;
  displayDate: string;
  organicTraffic: number;
  paidConversions: number;
}

const DATA_7D: DataPoint[] = [
  { date: "2026-10-15", displayDate: "Oct 15", organicTraffic: 1420, paidConversions: 54 },
  { date: "2026-10-16", displayDate: "Oct 16", organicTraffic: 1680, paidConversions: 62 },
  { date: "2026-10-17", displayDate: "Oct 17", organicTraffic: 1540, paidConversions: 58 },
  { date: "2026-10-18", displayDate: "Oct 18", organicTraffic: 1890, paidConversions: 74 },
  { date: "2026-10-19", displayDate: "Oct 19", organicTraffic: 2150, paidConversions: 89 },
  { date: "2026-10-20", displayDate: "Oct 20", organicTraffic: 2420, paidConversions: 98 },
  { date: "2026-10-21", displayDate: "Oct 21", organicTraffic: 2650, paidConversions: 112 },
];

const DATA_30D: DataPoint[] = [
  { date: "2026-09-22", displayDate: "Sep 22", organicTraffic: 980, paidConversions: 38 },
  { date: "2026-09-26", displayDate: "Sep 26", organicTraffic: 1140, paidConversions: 44 },
  { date: "2026-09-30", displayDate: "Sep 30", organicTraffic: 1350, paidConversions: 52 },
  { date: "2026-10-04", displayDate: "Oct 04", organicTraffic: 1520, paidConversions: 59 },
  { date: "2026-10-08", displayDate: "Oct 08", organicTraffic: 1780, paidConversions: 71 },
  { date: "2026-10-12", displayDate: "Oct 12", organicTraffic: 1950, paidConversions: 76 },
  { date: "2026-10-16", displayDate: "Oct 16", organicTraffic: 2240, paidConversions: 88 },
  { date: "2026-10-20", displayDate: "Oct 20", organicTraffic: 2510, paidConversions: 104 },
  { date: "2026-10-21", displayDate: "Oct 21", organicTraffic: 2780, paidConversions: 116 },
];

const DATA_90D: DataPoint[] = [
  { date: "2026-07-25", displayDate: "Jul 25", organicTraffic: 24000, paidConversions: 920 },
  { date: "2026-08-10", displayDate: "Aug 10", organicTraffic: 28500, paidConversions: 1140 },
  { date: "2026-08-25", displayDate: "Aug 25", organicTraffic: 33200, paidConversions: 1350 },
  { date: "2026-09-10", displayDate: "Sep 10", organicTraffic: 39400, paidConversions: 1580 },
  { date: "2026-09-25", displayDate: "Sep 25", organicTraffic: 44800, paidConversions: 1790 },
  { date: "2026-10-10", displayDate: "Oct 10", organicTraffic: 51200, paidConversions: 2040 },
  { date: "2026-10-21", displayDate: "Oct 21", organicTraffic: 58900, paidConversions: 2360 },
];

function generateBezierPath(points: { x: number; y: number }[]): string {
  if (points.length < 2) return "";
  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i === 0 ? 0 : i - 1];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2 < points.length ? i + 2 : i + 1];

    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;

    d += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }
  return d;
}

export const TrafficConversionsChart: React.FC = () => {
  const [timeRange, setTimeRange] = React.useState<"7d" | "30d" | "90d">("30d");
  const [hoveredIndex, setHoveredIndex] = React.useState<number | null>(null);
  const [showOrganic, setShowOrganic] = React.useState(true);
  const [showConversions, setShowConversions] = React.useState(true);

  const data = React.useMemo(() => {
    switch (timeRange) {
      case "7d":
        return DATA_7D;
      case "90d":
        return DATA_90D;
      case "30d":
      default:
        return DATA_30D;
    }
  }, [timeRange]);

  // Aggregate sums for quick KPI display
  const totalOrganic = React.useMemo(
    () => data.reduce((acc, curr) => acc + curr.organicTraffic, 0),
    [data]
  );
  const totalConversions = React.useMemo(
    () => data.reduce((acc, curr) => acc + curr.paidConversions, 0),
    [data]
  );
  const conversionRate = React.useMemo(
    () => ((totalConversions / (totalOrganic || 1)) * 100).toFixed(2),
    [totalOrganic, totalConversions]
  );

  // Chart coordinates
  const svgWidth = 800;
  const svgHeight = 280;
  const paddingLeft = 50;
  const paddingRight = 40;
  const paddingTop = 25;
  const paddingBottom = 45;

  const chartW = svgWidth - paddingLeft - paddingRight;
  const chartH = svgHeight - paddingTop - paddingBottom;

  // Max scales
  const maxOrganic = Math.max(...data.map((d) => d.organicTraffic)) * 1.15 || 1000;
  const maxConversions = Math.max(...data.map((d) => d.paidConversions)) * 1.2 || 100;

  // Compute point coordinates
  const organicPoints = data.map((d, i) => ({
    x: paddingLeft + (i / (data.length - 1)) * chartW,
    y: paddingTop + chartH - (d.organicTraffic / maxOrganic) * chartH,
  }));

  const conversionPoints = data.map((d, i) => ({
    x: paddingLeft + (i / (data.length - 1)) * chartW,
    y: paddingTop + chartH - (d.paidConversions / maxConversions) * chartH,
  }));

  const organicPathD = generateBezierPath(organicPoints);
  const organicAreaD = organicPoints.length
    ? `${organicPathD} L ${organicPoints[organicPoints.length - 1].x} ${
        paddingTop + chartH
      } L ${organicPoints[0].x} ${paddingTop + chartH} Z`
    : "";

  const conversionPathD = generateBezierPath(conversionPoints);
  const conversionAreaD = conversionPoints.length
    ? `${conversionPathD} L ${conversionPoints[conversionPoints.length - 1].x} ${
        paddingTop + chartH
      } L ${conversionPoints[0].x} ${paddingTop + chartH} Z`
    : "";

  return (
    <Card className="rounded-xl border border-slate-200/80 bg-white shadow-xs hover:shadow-sm transition-all duration-200">
      <CardHeader className="p-4 sm:p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <CardTitle className="text-base sm:text-lg font-bold text-slate-900 tracking-tight">
              Traffic &amp; Conversions
            </CardTitle>
            <span className="inline-flex items-center text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
              <TrendingUp className="w-3 h-3 mr-1" />
              +24.8% YoY
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Multi-stream correlation between inbound organic audience and paid ad conversions.
          </p>
        </div>

        {/* Controls: Legend Toggles + Time-range dropdown (Specification 4) */}
        <div className="flex items-center gap-3">
          {/* Legend Toggles */}
          <div className="hidden md:flex items-center gap-3 text-xs">
            <button
              type="button"
              onClick={() => setShowOrganic(!showOrganic)}
              className={cn(
                "flex items-center gap-1.5 px-2 py-1 rounded-md transition-colors",
                showOrganic ? "text-slate-800 font-semibold" : "text-slate-400 opacity-60"
              )}
            >
              <span className="w-2.5 h-2.5 rounded-full bg-indigo-600" />
              <span>Organic Traffic</span>
            </button>
            <button
              type="button"
              onClick={() => setShowConversions(!showConversions)}
              className={cn(
                "flex items-center gap-1.5 px-2 py-1 rounded-md transition-colors",
                showConversions ? "text-slate-800 font-semibold" : "text-slate-400 opacity-60"
              )}
            >
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
              <span>Paid Conversions</span>
            </button>
          </div>

          {/* Time-Range Dropdown */}
          <div className="w-36">
            <Select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value as "7d" | "30d" | "90d")}
              className="h-8 text-xs bg-slate-50 border-slate-200 rounded-lg font-medium"
              options={[
                { value: "7d", label: "Last 7 days" },
                { value: "30d", label: "Last 30 days" },
                { value: "90d", label: "Last 90 days" },
              ]}
            />
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-4 sm:p-5">
        {/* Top Summary Stat Pills */}
        <div className="grid grid-cols-3 gap-3 mb-4 pb-3 border-b border-slate-100 text-xs">
          <div>
            <span className="text-[11px] text-slate-400 font-medium">Total Organic Traffic</span>
            <p className="text-base sm:text-lg font-extrabold text-indigo-950 mt-0.5">
              {totalOrganic.toLocaleString()}
            </p>
          </div>
          <div>
            <span className="text-[11px] text-slate-400 font-medium">Total Paid Conversions</span>
            <p className="text-base sm:text-lg font-extrabold text-emerald-950 mt-0.5">
              {totalConversions.toLocaleString()}
            </p>
          </div>
          <div>
            <span className="text-[11px] text-slate-400 font-medium">Blended Conversion Rate</span>
            <p className="text-base sm:text-lg font-extrabold text-slate-900 mt-0.5 flex items-center gap-1">
              {conversionRate}%
              <ArrowUpRight className="w-3.5 h-3.5 text-emerald-600" />
            </p>
          </div>
        </div>

        {/* Multi-Line / Area Chart Container with Smooth Curves */}
        <div className="relative w-full overflow-hidden select-none" style={{ height: svgHeight }}>
          {/* Interactive Floating Tooltip */}
          {hoveredIndex !== null && data[hoveredIndex] && (
            <div
              className="absolute z-20 pointer-events-none -translate-x-1/2 rounded-xl bg-slate-900/95 text-white p-2.5 shadow-xl border border-slate-700/60 backdrop-blur-xs text-xs animate-in fade-in duration-100"
              style={{
                left: `${(organicPoints[hoveredIndex].x / svgWidth) * 100}%`,
                top: Math.max(8, Math.min(organicPoints[hoveredIndex].y, conversionPoints[hoveredIndex].y) - 64),
              }}
            >
              <div className="font-bold text-slate-300 border-b border-slate-700/80 pb-1 mb-1.5 flex items-center justify-between gap-4">
                <span>{data[hoveredIndex].displayDate}</span>
                <span className="text-[10px] text-slate-400">2026</span>
              </div>
              <div className="space-y-1">
                <div className="flex items-center justify-between gap-4">
                  <span className="flex items-center gap-1.5 text-indigo-300">
                    <span className="w-2 h-2 rounded-full bg-indigo-400" />
                    Organic:
                  </span>
                  <span className="font-bold text-white">
                    {data[hoveredIndex].organicTraffic.toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span className="flex items-center gap-1.5 text-emerald-300">
                    <span className="w-2 h-2 rounded-full bg-emerald-400" />
                    Conversions:
                  </span>
                  <span className="font-bold text-white">
                    {data[hoveredIndex].paidConversions.toLocaleString()}
                  </span>
                </div>
              </div>
            </div>
          )}

          <svg
            viewBox={`0 0 ${svgWidth} ${svgHeight}`}
            className="w-full h-full overflow-visible"
            preserveAspectRatio="none"
          >
            <defs>
              {/* Organic Traffic Gradient */}
              <linearGradient id="organicGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#6366f1" stopOpacity="0.32" />
                <stop offset="100%" stopColor="#6366f1" stopOpacity="0.0" />
              </linearGradient>

              {/* Paid Conversions Gradient */}
              <linearGradient id="conversionGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#10b981" stopOpacity="0.28" />
                <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {/* Horizontal Grid lines */}
            {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
              const y = paddingTop + chartH * pct;
              return (
                <line
                  key={i}
                  x1={paddingLeft}
                  y1={y}
                  x2={svgWidth - paddingRight}
                  y2={y}
                  stroke="#e2e8f0"
                  strokeDasharray="4 4"
                  strokeWidth="1"
                />
              );
            })}

            {/* Area Fills with Smooth Curves */}
            {showOrganic && <path d={organicAreaD} fill="url(#organicGrad)" />}
            {showConversions && <path d={conversionAreaD} fill="url(#conversionGrad)" />}

            {/* Smooth Curve Lines */}
            {showOrganic && (
              <path
                d={organicPathD}
                fill="none"
                stroke="#6366f1"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            )}
            {showConversions && (
              <path
                d={conversionPathD}
                fill="none"
                stroke="#10b981"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            )}

            {/* Active Vertical Crosshair */}
            {hoveredIndex !== null && (
              <line
                x1={organicPoints[hoveredIndex].x}
                y1={paddingTop}
                x2={organicPoints[hoveredIndex].x}
                y2={paddingTop + chartH}
                stroke="#64748b"
                strokeWidth="1.5"
                strokeDasharray="3 3"
              />
            )}

            {/* Interactive Data Dots */}
            {data.map((_, i) => {
              const isHovered = hoveredIndex === i;
              return (
                <g key={i}>
                  {showOrganic && (
                    <circle
                      cx={organicPoints[i].x}
                      cy={organicPoints[i].y}
                      r={isHovered ? 5.5 : 3}
                      fill="#ffffff"
                      stroke="#6366f1"
                      strokeWidth={isHovered ? 3 : 2}
                      className="transition-all duration-100 cursor-pointer"
                    />
                  )}
                  {showConversions && (
                    <circle
                      cx={conversionPoints[i].x}
                      cy={conversionPoints[i].y}
                      r={isHovered ? 5.5 : 3}
                      fill="#ffffff"
                      stroke="#10b981"
                      strokeWidth={isHovered ? 3 : 2}
                      className="transition-all duration-100 cursor-pointer"
                    />
                  )}
                </g>
              );
            })}

            {/* Date-based X-Axis Labels */}
            {data.map((d, i) => {
              const x = paddingLeft + (i / (data.length - 1)) * chartW;
              return (
                <text
                  key={d.date}
                  x={x}
                  y={svgHeight - 12}
                  textAnchor="middle"
                  className={cn(
                    "text-[11px] font-medium transition-colors",
                    hoveredIndex === i ? "fill-slate-900 font-bold" : "fill-slate-400"
                  )}
                >
                  {d.displayDate}
                </text>
              );
            })}

            {/* Invisible Hover Rectangles along X-axis for smooth mouse detection */}
            {data.map((_, i) => {
              const prevX = i === 0 ? paddingLeft : (organicPoints[i - 1].x + organicPoints[i].x) / 2;
              const nextX =
                i === data.length - 1
                  ? svgWidth - paddingRight
                  : (organicPoints[i].x + organicPoints[i + 1].x) / 2;
              return (
                <rect
                  key={`hover-${i}`}
                  x={prevX}
                  y={paddingTop}
                  width={nextX - prevX}
                  height={chartH}
                  fill="transparent"
                  className="cursor-pointer"
                  onMouseEnter={() => setHoveredIndex(i)}
                  onMouseLeave={() => setHoveredIndex(null)}
                />
              );
            })}
          </svg>
        </div>
      </CardContent>
    </Card>
  );
};
