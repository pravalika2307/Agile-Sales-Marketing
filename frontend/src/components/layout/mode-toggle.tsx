"use client";

import * as React from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAppMode } from "@/contexts/AppModeContext";
import { cn } from "@/lib/utils";
import { TrendingUp, Megaphone } from "lucide-react";

export interface ModeToggleProps {
  className?: string;
  size?: "sm" | "md";
}

export const ModeToggle: React.FC<ModeToggleProps> = ({
  className,
  size = "md",
}) => {
  const router = useRouter();
  const pathname = usePathname();
  const { mode, setMode, canToggle, isLoading } = useAppMode();

  // If user does not have "both" access, hide the toggle completely
  if (!canToggle || isLoading) {
    return null;
  }

  const isSales = mode === "sales";
  const isMarketing = mode === "marketing";

  const handleSwitchToSales = () => {
    setMode("sales");
    if (pathname?.startsWith("/marketing/campaigns")) {
      router.push("/sales/campaigns");
    } else if (pathname?.startsWith("/marketing/analytics")) {
      router.push("/sales/analytics");
    } else if (pathname?.startsWith("/marketing/settings")) {
      router.push("/sales/settings");
    } else if (pathname?.startsWith("/marketing")) {
      router.push("/sales");
    }
  };

  const handleSwitchToMarketing = () => {
    setMode("marketing");
    if (pathname?.startsWith("/sales/campaigns")) {
      router.push("/marketing/campaigns");
    } else if (pathname?.startsWith("/sales/analytics")) {
      router.push("/marketing/analytics");
    } else if (pathname?.startsWith("/sales/settings")) {
      router.push("/marketing/settings");
    } else if (pathname?.startsWith("/sales")) {
      router.push("/marketing");
    }
  };

  return (
    <div
      role="group"
      aria-label="Application domain mode switch"
      className={cn(
        "inline-flex items-center rounded-xl bg-slate-100/90 p-1 border border-slate-200/80 shadow-2xs backdrop-blur-xs transition-all duration-200 select-none",
        size === "sm" ? "h-8 text-xs" : "h-9 text-xs font-semibold",
        className
      )}
    >
      {/* Sales Button */}
      <button
        type="button"
        onClick={handleSwitchToSales}
        aria-pressed={isSales}
        className={cn(
          "flex items-center gap-1.5 px-3 py-1 rounded-lg transition-all duration-200 font-medium text-xs tracking-tight",
          isSales
            ? "bg-white text-slate-900 shadow-xs border border-slate-200/60 font-semibold"
            : "text-slate-500 hover:text-slate-800 hover:bg-slate-200/40"
        )}
      >
        <TrendingUp
          className={cn(
            "w-3.5 h-3.5 transition-colors",
            isSales ? "text-agile-red" : "text-slate-400"
          )}
        />
        <span>Sales</span>
        {isSales && (
          <span className="w-1.5 h-1.5 rounded-full bg-agile-red animate-pulse ml-0.5" />
        )}
      </button>

      {/* Marketing Button */}
      <button
        type="button"
        onClick={handleSwitchToMarketing}
        aria-pressed={isMarketing}
        className={cn(
          "flex items-center gap-1.5 px-3 py-1 rounded-lg transition-all duration-200 font-medium text-xs tracking-tight",
          isMarketing
            ? "bg-white text-slate-900 shadow-xs border border-slate-200/60 font-semibold"
            : "text-slate-500 hover:text-slate-800 hover:bg-slate-200/40"
        )}
      >
        <Megaphone
          className={cn(
            "w-3.5 h-3.5 transition-colors",
            isMarketing ? "text-purple-600" : "text-slate-400"
          )}
        />
        <span>Marketing</span>
        {isMarketing && (
          <span className="w-1.5 h-1.5 rounded-full bg-purple-600 animate-pulse ml-0.5" />
        )}
      </button>
    </div>
  );
};
