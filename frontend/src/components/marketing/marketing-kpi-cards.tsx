"use client";

import * as React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { TrendingUp, Users, Percent, MousePointerClick, CalendarCheck } from "lucide-react";
import { cn } from "@/lib/utils";

interface SparklineProps {
  data: number[];
  color?: string; // hex or CSS color
  fillColor?: string;
  gradientId: string;
  width?: number;
  height?: number;
}

export const Sparkline: React.FC<SparklineProps> = ({
  data,
  color = "#10b981",
  gradientId,
  width = 110,
  height = 36,
}) => {
  if (!data || data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const paddingY = 4;
  const availableHeight = height - paddingY * 2;

  // Calculate points
  const points = data.map((val, idx) => {
    const x = (idx / (data.length - 1)) * width;
    const y = height - paddingY - ((val - min) / range) * availableHeight;
    return { x, y };
  });

  // Generate smooth cubic bezier SVG path
  let pathD = `M ${points[0].x} ${points[0].y}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i === 0 ? 0 : i - 1];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2 < points.length ? i + 2 : i + 1];

    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;

    pathD += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }

  const areaD = `${pathD} L ${points[points.length - 1].x} ${height} L ${points[0].x} ${height} Z`;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="overflow-visible select-none shrink-0"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0.0" />
        </linearGradient>
      </defs>
      <path d={areaD} fill={`url(#${gradientId})`} />
      <path
        d={pathD}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Final point indicator */}
      <circle
        cx={points[points.length - 1].x}
        cy={points[points.length - 1].y}
        r="2.5"
        fill="#ffffff"
        stroke={color}
        strokeWidth="2"
      />
    </svg>
  );
};

export interface KpiMetricItem {
  id: string;
  title: string;
  value: string;
  change: string; // e.g. "+18.4%"
  subtext: string;
  icon: React.ComponentType<{ className?: string }>;
  sparklineData: number[];
  color: string;
  iconBg: string;
  iconColor: string;
}

const DEFAULT_KPIS: KpiMetricItem[] = [
  {
    id: "total-reach",
    title: "Total Reach",
    value: "148,290",
    change: "+18.4%",
    subtext: "vs. 125,200 previous 30 days",
    icon: Users,
    sparklineData: [42, 55, 51, 68, 62, 79, 85, 92, 108, 124, 138, 148],
    color: "#10b981", // Emerald green for positive indicator
    iconBg: "bg-indigo-50",
    iconColor: "text-indigo-600",
  },
  {
    id: "engagement-rate",
    title: "Engagement Rate",
    value: "5.82%",
    change: "+2.6%",
    subtext: "Industry benchmark: 4.10%",
    icon: Percent,
    sparklineData: [3.8, 4.1, 4.0, 4.5, 4.3, 4.9, 5.1, 5.0, 5.4, 5.6, 5.5, 5.82],
    color: "#10b981",
    iconBg: "bg-purple-50",
    iconColor: "text-purple-600",
  },
  {
    id: "link-clicks",
    title: "Link Clicks",
    value: "24,615",
    change: "+12.1%",
    subtext: "8.2k unique UTM sessions",
    icon: MousePointerClick,
    sparklineData: [120, 145, 138, 160, 155, 182, 195, 210, 205, 230, 240, 246],
    color: "#10b981",
    iconBg: "bg-blue-50",
    iconColor: "text-blue-600",
  },
  {
    id: "demo-requests",
    title: "Demo Requests",
    value: "184",
    change: "+28.5%",
    subtext: "High-intent inbound MQLs",
    icon: CalendarCheck,
    sparklineData: [12, 16, 14, 22, 19, 28, 31, 35, 38, 44, 49, 56],
    color: "#10b981",
    iconBg: "bg-emerald-50",
    iconColor: "text-emerald-600",
  },
];

export const MarketingKpiCards: React.FC<{ items?: KpiMetricItem[] }> = ({
  items = DEFAULT_KPIS,
}) => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {items.map((kpi, idx) => {
        const Icon = kpi.icon;
        const gradientId = `sparkline-grad-${kpi.id}-${idx}`;

        return (
          <Card
            key={kpi.id}
            className="rounded-xl border border-slate-200/80 bg-white shadow-xs hover:shadow-sm transition-all duration-200"
          >
            <CardContent className="p-4 sm:p-5 flex flex-col justify-between h-full">
              {/* Header: Title & Icon */}
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  {kpi.title}
                </span>
                <div
                  className={cn(
                    "w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
                    kpi.iconBg,
                    kpi.iconColor
                  )}
                >
                  <Icon className="w-4 h-4" />
                </div>
              </div>

              {/* Metric Number & Sparkline */}
              <div className="mt-3 flex items-end justify-between gap-3">
                <div>
                  <div className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 leading-none">
                    {kpi.value}
                  </div>
                  <div className="mt-2 flex items-center gap-1.5">
                    {/* Percentage Change Indicator (Green for positive as specified) */}
                    <span className="inline-flex items-center text-xs font-bold text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded-md border border-emerald-200/60">
                      <TrendingUp className="w-3 h-3 mr-0.5" />
                      {kpi.change}
                    </span>
                  </div>
                </div>

                {/* Inline SVG Sparkline Chart */}
                <div className="shrink-0 pb-1">
                  <Sparkline
                    data={kpi.sparklineData}
                    color={kpi.color}
                    gradientId={gradientId}
                    width={105}
                    height={38}
                  />
                </div>
              </div>

              {/* Subtitle / Contextual Note */}
              <p className="text-[11px] text-slate-400 mt-2 font-medium">
                {kpi.subtext}
              </p>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
};
