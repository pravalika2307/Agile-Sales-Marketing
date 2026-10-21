"use client";

import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import {
  Search,
  Bell,
  Plus,
  Menu,
  ChevronDown,
  User,
  Settings as SettingsIcon,
  Layers,
  LogOut,
  Shield,
  Building,
} from "lucide-react";
import { ModeToggle } from "./mode-toggle";
import { useAppMode } from "@/contexts/AppModeContext";

export interface HeaderProps {
  onToggleMobileMenu?: () => void;
  className?: string;
  onNewCampaignClick?: () => void;
}

/**
 * Derives user initials from their full name (e.g. "Pravalika Palle" -> "PP").
 * Supports single names, multiple tokens, and handles edge cases gracefully.
 */
export function getInitials(name: string): string {
  if (!name || !name.trim()) return "U";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) {
    return parts[0].substring(0, 2).toUpperCase();
  }
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export const Header: React.FC<HeaderProps> = ({
  onToggleMobileMenu,
  className,
  onNewCampaignClick,
}) => {
  const { mode } = useAppMode();
  const isMarketing = mode === "marketing";

  const [userMenuOpen, setUserMenuOpen] = React.useState(false);
  const [profileModalOpen, setProfileModalOpen] = React.useState(false);
  const [signedOut, setSignedOut] = React.useState(false);

  const menuRef = React.useRef<HTMLDivElement>(null);

  const [currentUser, setCurrentUser] = React.useState({
    name: "Agile Admin",
    role: "owner",
    email: "admin@agilereceivables.com",
    organization: "Agile Sales & Marketing",
    tenantId: "0d85dc9f-1520-4bcb-8af4-8aad025255cb",
  });

  // Load genuine session user on mount
  React.useEffect(() => {
    async function loadUser() {
      // 1. Try reading agile_user cookie
      try {
        const match = document.cookie.match(/(?:^|;\s*)agile_user=([^;]+)/);
        if (match && match[1]) {
          const parsed = JSON.parse(decodeURIComponent(match[1]));
          setCurrentUser({
            name: parsed.name || "Agile Admin",
            role: parsed.role || "owner",
            email: parsed.email || "admin@agilereceivables.com",
            organization: parsed.organization_name || "Agile Sales & Marketing",
            tenantId: parsed.organization_id || "0d85dc9f-1520-4bcb-8af4-8aad025255cb",
          });
          return;
        }
      } catch {}

      // 2. Fetch /api/auth/me
      try {
        const resp = await fetch("/api/auth/me");
        if (resp.ok) {
          const data = await resp.json();
          setCurrentUser((prev) => ({
            ...prev,
            name: data.full_name || prev.name,
            role: data.role || prev.role,
            email: data.email || prev.email,
            tenantId: data.organization_id || prev.tenantId,
          }));
        }
      } catch {}
    }
    loadUser();
  }, []);

  const userInitials = getInitials(currentUser.name);

  // Close dropdown on outside click
  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    if (userMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [userMenuOpen]);

  const handleSignOut = async () => {
    setUserMenuOpen(false);
    setSignedOut(true);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {}
    setTimeout(() => {
      window.location.href = "/login";
    }, 600);
  };

  return (
    <header
      className={cn(
        "h-16 bg-white border-b border-slate-200/80 px-4 md:px-6 flex items-center justify-between gap-4 sticky top-0 z-30",
        className
      )}
    >
      {/* Left: Mobile Menu button + Mode Toggle + Global Search */}
      <div className="flex items-center gap-3 flex-1 max-w-xl">
        {onToggleMobileMenu && (
          <button
            type="button"
            onClick={onToggleMobileMenu}
            className="md:hidden p-2 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors"
            aria-label="Toggle navigation menu"
          >
            <Menu className="w-5 h-5" />
          </button>
        )}

        {/* Top-Left Application Domain Mode Switch (Sales vs Marketing) */}
        <ModeToggle size="sm" />

        <div className="w-full relative max-w-md hidden sm:block">
          <Input
            icon={<Search className="w-4 h-4" />}
            placeholder={
              isMarketing
                ? "Search audiences, campaigns, social posts, templates..."
                : "Search leads, campaigns, call logs..."
            }
            className="h-9 text-xs md:text-sm bg-slate-50/60 border-slate-200 focus:bg-white"
          />
        </div>
      </div>

      {/* Right: Actions, Notifications, Profile */}
      <div className="flex items-center gap-2 md:gap-3">
        {/* Primary CTA: New Campaign */}
        <Button
          variant="primary"
          size="sm"
          onClick={onNewCampaignClick}
          className="hidden sm:inline-flex items-center gap-1.5 shadow-xs"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>New Campaign</span>
        </Button>

        {/* Notifications */}
        <div className="relative">
          <button
            type="button"
            className="relative p-2 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors"
            aria-label="Notifications"
          >
            <Bell className="w-4 h-4" />
            <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-agile-red ring-2 ring-white" />
          </button>
        </div>

        {/* User Account / Organization Profile Dropdown */}
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setUserMenuOpen((prev) => !prev)}
            className="flex items-center gap-2 pl-2 border-l border-slate-200/80 hover:opacity-80 transition-opacity focus:outline-hidden"
            aria-expanded={userMenuOpen}
            aria-haspopup="true"
          >
            <div className="w-8 h-8 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center font-semibold text-xs text-header">
              {userInitials}
            </div>
            <div className="hidden xl:flex flex-col text-left">
              <span className="text-xs font-semibold text-header leading-tight">
                {currentUser.name}
              </span>
              <span className="text-[10px] text-slate-400 font-medium">
                {currentUser.role}
              </span>
            </div>
            <ChevronDown
              className={cn(
                "w-3.5 h-3.5 text-slate-400 hidden xl:block transition-transform duration-150",
                userMenuOpen && "rotate-180"
              )}
            />
          </button>

          {/* Functional Profile Dropdown Menu */}
          {userMenuOpen && (
            <div className="absolute right-0 mt-2 w-56 rounded-lg bg-white border border-slate-200 shadow-lg py-1.5 z-50 animate-in fade-in slide-in-from-top-1 duration-150">
              <div className="px-3.5 py-2 border-b border-slate-100">
                <p className="text-xs font-semibold text-header truncate">{currentUser.name}</p>
                <p className="text-[11px] text-slate-400 truncate">{currentUser.email}</p>
              </div>

              <div className="py-1">
                <button
                  type="button"
                  onClick={() => {
                    setUserMenuOpen(false);
                    setProfileModalOpen(true);
                  }}
                  className="w-full flex items-center gap-2 px-3.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50 transition-colors text-left"
                >
                  <User className="w-3.5 h-3.5 text-slate-400" />
                  <span>Profile Information</span>
                </button>

                <Link
                  href="/integrations"
                  onClick={() => setUserMenuOpen(false)}
                  className="w-full flex items-center gap-2 px-3.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50 transition-colors text-left"
                >
                  <Layers className="w-3.5 h-3.5 text-slate-400" />
                  <span>Integrations</span>
                </Link>

                <Link
                  href="/settings"
                  onClick={() => setUserMenuOpen(false)}
                  className="w-full flex items-center gap-2 px-3.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50 transition-colors text-left"
                >
                  <SettingsIcon className="w-3.5 h-3.5 text-slate-400" />
                  <span>Settings</span>
                </Link>
              </div>

              <div className="pt-1 border-t border-slate-100">
                <button
                  type="button"
                  onClick={handleSignOut}
                  className="w-full flex items-center gap-2 px-3.5 py-1.5 text-xs text-rose-600 hover:bg-rose-50 transition-colors text-left"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span>Sign Out</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Profile Modal */}
      <Modal
        isOpen={profileModalOpen}
        onClose={() => setProfileModalOpen(false)}
        title="User Profile"
        description="Your operator profile and organization details."
        maxWidth="sm"
        footer={
          <Button variant="secondary" size="sm" onClick={() => setProfileModalOpen(false)}>
            Close
          </Button>
        }
      >
        <div className="space-y-4 pt-1">
          <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-50 border border-slate-200/80">
            <div className="w-12 h-12 rounded-full bg-white border border-slate-200 flex items-center justify-center font-bold text-base text-agile-red shadow-xs">
              {userInitials}
            </div>
            <div>
              <h4 className="font-semibold text-sm text-header">{currentUser.name}</h4>
              <p className="text-xs text-slate-500">{currentUser.email}</p>
              <div className="flex items-center gap-1.5 mt-1">
                <span className="text-[10px] font-medium bg-slate-200/70 text-slate-700 px-1.5 py-0.5 rounded">
                  {currentUser.role}
                </span>
                <span className="text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 px-1.5 py-0.5 rounded">
                  Active
                </span>
              </div>
            </div>
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between py-1.5 border-b border-slate-100">
              <span className="text-slate-500 flex items-center gap-1.5">
                <Building className="w-3.5 h-3.5 text-slate-400" />
                Organization
              </span>
              <span className="font-semibold text-slate-800">{currentUser.organization}</span>
            </div>
            <div className="flex items-center justify-between py-1.5 border-b border-slate-100">
              <span className="text-slate-500 flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5 text-slate-400" />
                Tenant ID
              </span>
              <span className="font-mono text-[11px] text-slate-600 truncate max-w-[170px]" title={currentUser.tenantId}>
                {currentUser.tenantId}
              </span>
            </div>
          </div>
        </div>
      </Modal>

      {/* Sign Out Feedback Modal */}
      {signedOut && (
        <Modal
          isOpen={signedOut}
          onClose={() => {}}
          title="Signed Out"
          maxWidth="sm"
        >
          <div className="py-4 text-center space-y-2">
            <p className="text-sm font-medium text-slate-700">Signing out of operator session...</p>
            <p className="text-xs text-slate-400">Redirecting to login / home</p>
          </div>
        </Modal>
      )}
    </header>
  );
};
