"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  UserSearch,
  Users,
  Send,
  PhoneCall,
  KanbanSquare,
  BarChart3,
  Layers,
  Settings,
  ChevronLeft,
  ChevronRight,
  Share2,
  Calendar,
  Zap,
} from "lucide-react";
import { useAppMode } from "@/contexts/AppModeContext";

export interface NavItem {
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string | number;
}

export const salesNavigationItems: NavItem[] = [
  { name: "Dashboard", href: "/sales", icon: LayoutDashboard },
  { name: "Find Leads", href: "/sales/find-leads", icon: UserSearch, badge: "Active" },
  { name: "Leads", href: "/sales/leads", icon: Users },
  { name: "Campaigns", href: "/sales/campaigns", icon: Send },
  { name: "Outreach", href: "/sales/outreach", icon: PhoneCall },
  { name: "Pipeline", href: "/sales/pipeline", icon: KanbanSquare },
  { name: "Analytics", href: "/sales/analytics", icon: BarChart3 },
];

export const marketingNavigationItems: NavItem[] = [
  { name: "Dashboard", href: "/marketing", icon: LayoutDashboard, badge: "Active" },
  { name: "Campaigns", href: "/marketing/campaigns", icon: Send },
  { name: "Content Calendar", href: "/marketing/content-calendar", icon: Calendar },
  { name: "Social Media", href: "/marketing/social-media", icon: Share2 },
  { name: "Analytics", href: "/marketing/analytics", icon: BarChart3 },
  { name: "Automation", href: "/marketing/automation", icon: Zap },
];

export const secondaryNavigationItems: NavItem[] = [
  { name: "Integrations", href: "/sales/integrations", icon: Layers },
  { name: "Settings", href: "/sales/settings", icon: Settings },
];

export interface SidebarProps {
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  className?: string;
}

export const Sidebar: React.FC<SidebarProps> = ({
  collapsed = false,
  onToggleCollapse,
  className,
}) => {
  const pathname = usePathname();
  const { mode } = useAppMode();
  const isMarketing = mode === "marketing";

  const navigationItems = isMarketing ? marketingNavigationItems : salesNavigationItems;
  const brandHref = isMarketing ? "/marketing" : "/sales";
  const settingsHref = isMarketing ? "/marketing/settings" : "/sales/settings";

  return (
    <aside
      className={cn(
        "relative flex flex-col select-none transition-all duration-200 ease-in-out",
        isMarketing
          ? "bg-[#0B132B] text-slate-300 border-r border-slate-800/90"
          : "bg-white text-slate-800 border-r border-slate-200",
        collapsed ? "w-16" : "w-60",
        className
      )}
    >
      {/* Brand Header */}
      <div
        className={cn(
          "h-16 flex items-center justify-between px-4 border-b",
          isMarketing ? "border-slate-800/80 bg-[#0B132B]" : "border-slate-100"
        )}
      >
        <Link href={brandHref} className="flex items-center gap-2.5 overflow-hidden">
          {/* Brand Mark */}
          <div
            className={cn(
              "w-8 h-8 rounded-lg flex items-center justify-center font-bold text-sm shadow-xs shrink-0 transition-colors duration-200",
              isMarketing
                ? "bg-gradient-to-br from-indigo-500 via-indigo-600 to-purple-600 text-white shadow-indigo-500/20 shadow-sm"
                : "bg-agile-red text-white"
            )}
          >
            A
          </div>
          {!collapsed && (
            <div className="flex flex-col truncate">
              <span
                className={cn(
                  "font-bold text-sm tracking-tight leading-tight",
                  isMarketing ? "text-white" : "text-header"
                )}
              >
                Agile{" "}
                <span
                  className={cn(
                    "font-semibold transition-colors",
                    isMarketing ? "text-indigo-400" : "text-agile-red"
                  )}
                >
                  AR
                </span>
              </span>
              <span
                className={cn(
                  "text-[10px] font-medium tracking-wide",
                  isMarketing ? "text-slate-400" : "text-slate-400"
                )}
              >
                {isMarketing ? "Marketing Cloud" : "Sales & Marketing"}
              </span>
            </div>
          )}
        </Link>
        {onToggleCollapse && (
          <button
            onClick={onToggleCollapse}
            className={cn(
              "p-1 rounded-md transition-colors hidden md:flex",
              isMarketing
                ? "text-slate-400 hover:text-white hover:bg-slate-800/80"
                : "text-slate-400 hover:text-slate-600 hover:bg-slate-100"
            )}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? (
              <ChevronRight className="w-4 h-4" />
            ) : (
              <ChevronLeft className="w-4 h-4" />
            )}
          </button>
        )}
      </div>

      {/* Main Navigation */}
      <div className="flex-1 px-3 py-3 space-y-4 overflow-y-auto">
        <nav className="space-y-1">
          {navigationItems.map((item) => {
            const Icon = item.icon;
            const isDashboard = item.href === "/sales" || item.href === "/marketing";
            const isActive = isDashboard
              ? isMarketing
                ? pathname === "/marketing" || pathname === "/"
                : pathname === "/sales" || pathname === "/"
              : pathname === item.href || pathname?.startsWith(`${item.href}/`);

            return (
              <Link
                key={item.name}
                href={item.href}
                title={collapsed ? item.name : undefined}
                className={cn(
                  "group flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 relative",
                  isMarketing
                    ? isActive
                      ? "bg-indigo-600/20 text-white border border-indigo-500/40 font-semibold shadow-xs"
                      : "text-slate-400 hover:text-white hover:bg-slate-800/60 border border-transparent"
                    : isActive
                      ? "bg-agile-lightorange text-agile-red border border-agile-outlinered/40 font-semibold shadow-xs"
                      : "text-slate-600 hover:text-header hover:bg-slate-50 border border-transparent"
                )}
              >
                <Icon
                  className={cn(
                    "w-4 h-4 shrink-0 transition-colors",
                    isMarketing
                      ? isActive
                        ? "text-indigo-400"
                        : "text-slate-400 group-hover:text-slate-200"
                      : isActive
                        ? "text-agile-red"
                        : "text-slate-400 group-hover:text-slate-600"
                  )}
                />
                {!collapsed && (
                  <span className="truncate flex-1">{item.name}</span>
                )}
                {!collapsed && item.badge && (
                  <span
                    className={cn(
                      "text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0",
                      isMarketing
                        ? isActive
                          ? "bg-indigo-600 text-white"
                          : "bg-slate-800 text-slate-300"
                        : isActive
                          ? "bg-agile-red text-white"
                          : "bg-slate-100 text-slate-500"
                    )}
                  >
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Secondary Sub-group for non-marketing or extra integrations */}
        {!isMarketing && (
          <div className="pt-2 border-t border-slate-100">
            {!collapsed && (
              <p className="px-3 pb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Settings &amp; Integrations
              </p>
            )}
            <nav className="space-y-1">
              {secondaryNavigationItems.map((item) => {
                const Icon = item.icon;
                const isActive = pathname === item.href;

                return (
                  <Link
                    key={item.name}
                    href={item.href}
                    title={collapsed ? item.name : undefined}
                    className={cn(
                      "group flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-150",
                      isActive
                        ? "bg-agile-lightorange text-agile-red border border-agile-outlinered/40 font-semibold shadow-xs"
                        : "text-slate-600 hover:text-header hover:bg-slate-50 border border-transparent"
                    )}
                  >
                    <Icon
                      className={cn(
                        "w-4 h-4 shrink-0 transition-colors",
                        isActive
                          ? "text-agile-red"
                          : "text-slate-400 group-hover:text-slate-600"
                      )}
                    />
                    {!collapsed && (
                      <span className="truncate flex-1">{item.name}</span>
                    )}
                  </Link>
                );
              })}
            </nav>
          </div>
        )}
      </div>

      {/* Settings at the bottom */}
      <div
        className={cn(
          "p-3 border-t",
          isMarketing ? "border-slate-800/80 bg-[#0B132B]" : "border-slate-100"
        )}
      >
        <Link
          href={settingsHref}
          title={collapsed ? "Settings" : undefined}
          className={cn(
            "group flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-150 mb-2",
            isMarketing
              ? pathname === "/marketing/settings" || pathname === "/settings"
                ? "bg-indigo-600/20 text-white font-semibold"
                : "text-slate-400 hover:text-white hover:bg-slate-800/60"
              : pathname === "/sales/settings" || pathname === "/settings"
                ? "bg-agile-lightorange text-agile-red font-semibold"
                : "text-slate-600 hover:text-header hover:bg-slate-50"
          )}
        >
          <Settings
            className={cn(
              "w-4 h-4 shrink-0 transition-colors",
              isMarketing
                ? "text-slate-400 group-hover:text-slate-200"
                : "text-slate-400 group-hover:text-slate-600"
            )}
          />
          {!collapsed && <span className="truncate flex-1">Settings</span>}
        </Link>

        {/* Footer Info / Environment */}
        {!collapsed ? (
          <div
            className={cn(
              "rounded-lg p-2 border flex items-center justify-between text-xs",
              isMarketing
                ? "bg-slate-900/60 border-slate-800 text-slate-400"
                : "bg-slate-50/70 border-slate-200/60 text-slate-500"
            )}
          >
            <span className="text-[11px] font-medium flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Connected
            </span>
            <span
              className={cn(
                "text-[10px] font-mono",
                isMarketing ? "text-slate-500" : "text-slate-400"
              )}
            >
              v1.0
            </span>
          </div>
        ) : (
          <div className="flex justify-center">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          </div>
        )}
      </div>
    </aside>
  );
};
