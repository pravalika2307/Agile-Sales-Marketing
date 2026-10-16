import * as React from "react";
import { cn } from "@/lib/utils";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";

export interface ChartLegendItem {
  label: string;
  color: string;
}

export interface ChartCardProps {
  title: string;
  description?: string;
  legends?: ChartLegendItem[];
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export const ChartCard: React.FC<ChartCardProps> = ({
  title,
  description,
  legends,
  actions,
  children,
  className,
}) => {
  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4">
        <div>
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {legends && legends.length > 0 && (
            <div className="flex items-center gap-3 mr-2">
              {legends.map((item, idx) => (
                <div key={idx} className="flex items-center gap-1.5 text-xs text-slate-600">
                  <span
                    className="w-2.5 h-2.5 rounded-xs shrink-0"
                    style={{ backgroundColor: item.color }}
                  />
                  <span>{item.label}</span>
                </div>
              ))}
            </div>
          )}
          {actions}
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
};
