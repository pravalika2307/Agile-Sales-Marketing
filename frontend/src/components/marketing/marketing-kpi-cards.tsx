"use client";

import * as React from "react";
import { Card, CardContent } from "@/components/ui/card";
import {
  TrendingUp,
  TrendingDown,
  Users,
  Percent,
  MousePointerClick,
  CalendarCheck,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { fetchMarketingKpis } from "@/services/marketingService";

interface SparklineProps {
  data: number[];
  color?: string;
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

  const points = data.map((val, idx) => {
    const x = (idx / (data.length - 1)) * width;
    const y = height - paddingY - ((val - min) / range) * availableHeight;
    return { x, y };
  });

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
  change: string;
  isPositive?: boolean;
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
    value: "404",
    change: "+210.8%",
    isPositive: true,
    subtext: "Goal: 130 for October 2026",
    icon: Users,
    sparklineData: [18, 56, 74, 98, 115, 130, 404],
    color: "#10b981",
    iconBg: "bg-indigo-50",
    iconColor: "text-indigo-600",
  },
  {
    id: "engagement-rate",
    title: "Engagement Rate",
    value: "6.70%",
    change: "+18.4%",
    isPositive: true,
    subtext: "Goal: 16.0% (Peak pillar: 38.5%)",
    icon: Percent,
    sparklineData: [4.5, 9.9, 11.0, 19.5, 22.5, 38.5, 6.7],
    color: "#10b981",
    iconBg: "bg-purple-50",
    iconColor: "text-purple-600",
  },
  {
    id: "link-clicks",
    title: "Link Clicks",
    value: "63",
    change: "+14.5%",
    isPositive: true,
    subtext: "Goal: 55 for October 2026",
    icon: MousePointerClick,
    sparklineData: [5, 11, 18, 26, 40, 52, 63],
    color: "#10b981",
    iconBg: "bg-blue-50",
    iconColor: "text-blue-600",
  },
  {
    id: "demo-requests",
    title: "Demo Requests",
    value: "3",
    change: "+50.0%",
    isPositive: true,
    subtext: "Goal: 2 for October 2026",
    icon: CalendarCheck,
    sparklineData: [0, 1, 1, 2, 2, 3],
    color: "#10b981",
    iconBg: "bg-emerald-50",
    iconColor: "text-emerald-600",
  },
];

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  "total-reach": Users,
  "engagement-rate": Percent,
  "link-clicks": MousePointerClick,
  "demo-requests": CalendarCheck,
};

export const MarketingKpiCards: React.FC<{ items?: KpiMetricItem[] }> = ({
  items: propItems,
}) => {
  const [liveCards, setLiveCards] = React.useState<KpiMetricItem[]>(() => propItems || DEFAULT_KPIS);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let isMounted = true;

    async function loadKpiData() {
      try {
        setLoading(true);
        const data = await fetchMarketingKpis();
        if (isMounted && data.cards && data.cards.length > 0) {
          const mappedCards: KpiMetricItem[] = data.cards.map((c) => ({
            id: c.id,
            title: c.title,
            value: c.value,
            change: c.change,
            isPositive: c.isPositive !== false,
            subtext: c.subtext,
            icon: ICON_MAP[c.id] || Users,
            sparklineData: c.sparklineData || [10, 20, 30],
            color: c.color || (c.isPositive !== false ? "#10b981" : "#ef4444"),
            iconBg: c.iconBg || "bg-indigo-50",
            iconColor: c.iconColor || "text-indigo-600",
          }));
          setLiveCards(mappedCards);
          setError(null);
        }
      } catch (err: unknown) {
        console.warn("Could not fetch live marketing KPIs, falling back to local defaults:", err);
        if (isMounted) {
          setError("Failed to refresh live data");
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    loadKpiData();

    return () => {
      isMounted = false;
    };
  }, []);

  const cardsToRender = liveCards;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cardsToRender.map((kpi, idx) => {
        const Icon = kpi.icon;
        const gradientId = `sparkline-grad-${kpi.id}-${idx}`;
        const isPositive = kpi.isPositive ?? !kpi.change.startsWith("-");

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
                    {/* Percentage Change Indicator (Green for positive, red for negative) */}
                    <span
                      className={cn(
                        "inline-flex items-center text-xs font-bold px-1.5 py-0.5 rounded-md border",
                        isPositive
                          ? "text-emerald-700 bg-emerald-50 border-emerald-200/70"
                          : "text-rose-700 bg-rose-50 border-rose-200/70"
                      )}
                    >
                      {isPositive ? (
                        <TrendingUp className="w-3 h-3 mr-0.5" />
                      ) : (
                        <TrendingDown className="w-3 h-3 mr-0.5" />
                      )}
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
              <div className="flex items-center justify-between mt-2">
                <p className="text-[11px] text-slate-400 font-medium">
                  {kpi.subtext}
                </p>
                {loading && (
                  <RefreshCw className="w-2.5 h-2.5 animate-spin text-slate-300 shrink-0" />
                )}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
};
