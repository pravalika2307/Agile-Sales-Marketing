"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface TabsContextValue {
  value: string;
  onValueChange: (val: string) => void;
  variant?: "underline" | "pills";
}

const TabsContext = React.createContext<TabsContextValue | null>(null);

export interface TabsProps {
  defaultValue?: string;
  value?: string;
  onValueChange?: (val: string) => void;
  variant?: "underline" | "pills";
  className?: string;
  children: React.ReactNode;
}

export const Tabs: React.FC<TabsProps> = ({
  defaultValue,
  value: controlledValue,
  onValueChange,
  variant = "underline",
  className,
  children,
}) => {
  const [uncontrolledValue, setUncontrolledValue] = React.useState(
    defaultValue || ""
  );
  const isControlled = controlledValue !== undefined;
  const activeValue = isControlled ? controlledValue : uncontrolledValue;

  const handleValueChange = React.useCallback(
    (newVal: string) => {
      if (!isControlled) {
        setUncontrolledValue(newVal);
      }
      onValueChange?.(newVal);
    },
    [isControlled, onValueChange]
  );

  return (
    <TabsContext.Provider
      value={{
        value: activeValue,
        onValueChange: handleValueChange,
        variant,
      }}
    >
      <div className={cn("w-full space-y-4", className)}>{children}</div>
    </TabsContext.Provider>
  );
};

export const TabsList: React.FC<{
  className?: string;
  children: React.ReactNode;
}> = ({ className, children }) => {
  const ctx = React.useContext(TabsContext);
  const variant = ctx?.variant || "underline";

  return (
    <div
      className={cn(
        "flex items-center gap-1",
        variant === "underline" && "border-b border-slate-200 gap-6",
        variant === "pills" && "p-1 bg-slate-100 rounded-lg",
        className
      )}
      role="tablist"
    >
      {children}
    </div>
  );
};

export const TabsTrigger: React.FC<{
  value: string;
  disabled?: boolean;
  className?: string;
  children: React.ReactNode;
}> = ({ value, disabled, className, children }) => {
  const ctx = React.useContext(TabsContext);
  if (!ctx) throw new Error("TabsTrigger must be used within Tabs");

  const isActive = ctx.value === value;
  const variant = ctx.variant;

  return (
    <button
      type="button"
      role="tab"
      aria-selected={isActive}
      disabled={disabled}
      onClick={() => ctx.onValueChange(value)}
      className={cn(
        "inline-flex items-center justify-center whitespace-nowrap text-sm font-medium transition-all focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50",
        variant === "underline" && [
          "pb-2.5 pt-1 border-b-2 -mb-px text-slate-500 hover:text-slate-800",
          isActive
            ? "border-agile-red text-agile-red font-semibold"
            : "border-transparent",
        ],
        variant === "pills" && [
          "px-3 py-1.5 rounded-md text-xs font-semibold text-slate-600 hover:text-slate-900",
          isActive &&
            "bg-white text-agile-red shadow-sm border border-slate-200/60",
        ],
        className
      )}
    >
      {children}
    </button>
  );
};

export const TabsContent: React.FC<{
  value: string;
  className?: string;
  children: React.ReactNode;
}> = ({ value, className, children }) => {
  const ctx = React.useContext(TabsContext);
  if (!ctx) throw new Error("TabsContent must be used within Tabs");

  if (ctx.value !== value) return null;

  return (
    <div
      role="tabpanel"
      className={cn(
        "mt-2 ring-offset-background focus-visible:outline-none",
        className
      )}
    >
      {children}
    </div>
  );
};
