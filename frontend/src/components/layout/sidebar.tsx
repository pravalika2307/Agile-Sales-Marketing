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
  ListOrdered,
  ShieldCheck,
  ShieldAlert,
  Inbox,
} from "lucide-react";

export interface NavItem {
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string | number;
}

export const navigationItems: NavItem[] = [
  { name: "Dashboard", href: "/", icon: LayoutDashboard },
  { name: "Find Leads", href: "/find-leads", icon: UserSearch, badge: "Active" },
  { name: "Leads", href: "/leads", icon: Users },
  { name: "Campaigns", href: "/campaigns", icon: Send },
  { name: "Outreach", href: "/outreach", icon: PhoneCall },
  { name: "Support Inbox", href: "/inbox", icon: Inbox },
  { name: "Pipeline", href: "/pipeline", icon: KanbanSquare },
  { name: "Analytics", href: "/analytics", icon: BarChart3 },
];

export const secondaryNavigationItems: NavItem[] = [
  { name: "Channels & Plans", href: "/settings/entitlements", icon: ShieldCheck },
  { name: "Admin Upgrades", href: "/admin/upgrades", icon: ShieldAlert },
  { name: "Integrations", href: "/integrations", icon: Layers },
  { name: "Settings", href: "/settings", icon: Settings },
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

  return (
    <aside
      className={cn(
        "relative flex flex-col bg-white border-r border-slate-200 select-none transition-all duration-200 ease-in-out",
        collapsed ? "w-16" : "w-60",
        className
      )}
    >
      {/* Brand Header */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-slate-100">
        <Link href="/" className="flex items-center gap-2.5 overflow-hidden">
          {/* Brand Mark: Agile Coral Hexagon/Square */}
          <div className="w-8 h-8 rounded-lg bg-agile-red text-white flex items-center justify-center font-bold text-sm shadow-xs shrink-0">
            A
          </div>
          {!collapsed && (
            <div className="flex flex-col truncate">
              <span className="font-bold text-sm tracking-tight text-header leading-tight">
                Agile <span className="text-agile-red font-medium">S&M</span>
              </span>
              <span className="text-[10px] text-slate-400 font-medium tracking-wide">
                Sales & Marketing
              </span>
            </div>
          )}
        </Link>
        {onToggleCollapse && (
          <button
            onClick={onToggleCollapse}
            className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors hidden md:flex"
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
            const isActive =
              pathname === item.href ||
              (item.href !== "/" && pathname?.startsWith(item.href));

            return (
              <Link
                key={item.name}
                href={item.href}
                title={collapsed ? item.name : undefined}
                className={cn(
                  "group flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-150 relative",
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
                {!collapsed && item.badge && (
                  <span
                    className={cn(
                      "text-[10px] font-semibold px-1.5 py-0.2 rounded shrink-0",
                      isActive
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

        {/* Secondary Sub-group */}
        <div className="pt-2 border-t border-slate-100">
          {!collapsed && (
            <p className="px-3 pb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Settings & Integrations
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
      </div>

      {/* Footer Info / Environment */}
      <div className="p-3 border-t border-slate-100">
        {!collapsed ? (
          <div className="rounded-lg bg-slate-50/70 p-2 border border-slate-200/60 flex items-center justify-between text-xs">
            <span className="text-[11px] font-medium text-slate-500 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              Connected
            </span>
            <span className="text-[10px] font-mono text-slate-400">v1.0</span>
          </div>
        ) : (
          <div className="flex justify-center">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
          </div>
        )}
      </div>
    </aside>
  );
};
