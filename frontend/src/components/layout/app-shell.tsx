"use client";

import * as React from "react";
import { Sidebar } from "./sidebar";
import { Header } from "./header";
import { cn } from "@/lib/utils";
import { useAppMode } from "@/contexts/AppModeContext";

export interface AppShellProps {
  children: React.ReactNode;
  onNewCampaignClick?: () => void;
}

export const AppShell: React.FC<AppShellProps> = ({
  children,
  onNewCampaignClick,
}) => {
  const [collapsed, setCollapsed] = React.useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = React.useState(false);
  const { mode } = useAppMode();
  const isMarketing = mode === "marketing";

  return (
    <div
      className={cn(
        "min-h-screen flex antialiased font-sans select-none",
        isMarketing ? "bg-[#F8FAFC] text-slate-800" : "bg-mainbg text-slate-800"
      )}
    >
      {/* Desktop Fixed Left Sidebar */}
      <div className="hidden md:flex shrink-0">
        <Sidebar
          collapsed={collapsed}
          onToggleCollapse={() => setCollapsed(!collapsed)}
          className="h-screen sticky top-0"
        />
      </div>

      {/* Mobile Drawer Backdrop & Sidebar */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex">
          <div
            className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs"
            onClick={() => setMobileMenuOpen(false)}
            aria-hidden="true"
          />
          <div className="relative w-64 h-full z-10 shadow-2xl">
            <Sidebar onToggleCollapse={() => setMobileMenuOpen(false)} />
          </div>
        </div>
      )}

      {/* Scrollable Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-y-auto">
        <Header
          onToggleMobileMenu={() => setMobileMenuOpen(!mobileMenuOpen)}
          onNewCampaignClick={onNewCampaignClick}
        />
        <main
          className={cn(
            "flex-1 p-4 sm:p-6 md:p-8 w-full mx-auto space-y-6",
            isMarketing ? "max-w-[1600px]" : "max-w-7xl"
          )}
        >
          {children}
        </main>
      </div>
    </div>
  );
};
