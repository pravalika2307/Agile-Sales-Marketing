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
  LogOut,
  Users,
  MessageSquare,
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
  if (!name || !name.trim()) return "AR";
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
  const [teamModalOpen, setTeamModalOpen] = React.useState(false);
  const [chatModalOpen, setChatModalOpen] = React.useState(false);
  const [notificationsOpen, setNotificationsOpen] = React.useState(false);

  const menuRef = React.useRef<HTMLDivElement>(null);
  const notifRef = React.useRef<HTMLDivElement>(null);

  const [currentUser, setCurrentUser] = React.useState({
    name: "Agile Admin",
    role: "Marketing Director",
    email: "admin@agilereceivables.com",
    organization: "Agile Sales & Marketing",
    tenantId: "0d85dc9f-1520-4bcb-8af4-8aad025255cb",
  });

  // Load genuine session user on mount
  React.useEffect(() => {
    async function loadUser() {
      try {
        const match = document.cookie.match(/(?:^|;\s*)agile_user=([^;]+)/);
        if (match && match[1]) {
          const parsed = JSON.parse(decodeURIComponent(match[1]));
          setCurrentUser({
            name: parsed.name || "Agile Admin",
            role: parsed.role || "Marketing Director",
            email: parsed.email || "admin@agilereceivables.com",
            organization: parsed.organization_name || "Agile Sales & Marketing",
            tenantId: parsed.organization_id || "0d85dc9f-1520-4bcb-8af4-8aad025255cb",
          });
          return;
        }
      } catch {}

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

  // Close dropdowns on outside click
  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setUserMenuOpen(false);
      }
      if (notifRef.current && !notifRef.current.contains(event.target as Node)) {
        setNotificationsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const handleSignOut = async () => {
    setUserMenuOpen(false);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {}
    setTimeout(() => {
      window.location.href = "/login";
    }, 600);
  };

  return (
    <>
      <header
        className={cn(
          "h-16 bg-white border-b border-slate-200/80 px-4 md:px-6 flex items-center justify-between gap-4 sticky top-0 z-30 shadow-[0_1px_2px_rgba(0,0,0,0.03)]",
          className
        )}
      >
        {/* Left: Mobile Menu button + Mode Toggle + Global Search Input Field (Specification 2) */}
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

          {/* Application Domain Mode Switch (Sales vs Marketing) */}
          <ModeToggle size="sm" />

          {/* Global Search Input Field */}
          <div className="w-full relative max-w-md hidden sm:block">
            <Input
              icon={<Search className="w-4 h-4 text-slate-400" />}
              placeholder={
                isMarketing
                  ? "Search campaigns, content calendar, analytics, posts..."
                  : "Search leads, campaigns, call logs..."
              }
              className="h-9 text-xs md:text-sm bg-slate-50/70 border-slate-200 focus:bg-white focus:ring-1 focus:ring-indigo-500 rounded-lg"
            />
          </div>
        </div>

        {/* Right: Cluster of Icons (Team members, Chat/support, Notifications with red unread badge, User profile avatar) */}
        <div className="flex items-center gap-1.5 sm:gap-2.5">
          {/* Action CTA: New Campaign (optional quick trigger) */}
          {onNewCampaignClick && (
            <Button
              variant="primary"
              size="sm"
              onClick={onNewCampaignClick}
              className={cn(
                "hidden lg:inline-flex items-center gap-1.5 shadow-xs text-xs font-semibold mr-1",
                isMarketing ? "bg-indigo-600 hover:bg-indigo-700 text-white" : ""
              )}
            >
              <Plus className="w-3.5 h-3.5" />
              <span>{isMarketing ? "New Campaign" : "New Campaign"}</span>
            </Button>
          )}

          {/* 1. Team Members Icon */}
          <button
            type="button"
            onClick={() => setTeamModalOpen(true)}
            className="p-2 rounded-lg text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition-colors relative"
            title="Team Members"
            aria-label="Team Members"
          >
            <Users className="w-4 h-4" />
          </button>

          {/* 2. Chat / Support Icon */}
          <button
            type="button"
            onClick={() => setChatModalOpen(true)}
            className="p-2 rounded-lg text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition-colors relative"
            title="Chat & Support"
            aria-label="Chat & Support"
          >
            <MessageSquare className="w-4 h-4" />
          </button>

          {/* 3. Notifications Icon with Red Unread Badge */}
          <div className="relative" ref={notifRef}>
            <button
              type="button"
              onClick={() => setNotificationsOpen((prev) => !prev)}
              className="p-2 rounded-lg text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition-colors relative"
              title="Notifications"
              aria-label="Notifications"
            >
              <Bell className="w-4 h-4" />
              {/* Red unread badge as specified */}
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-rose-500 ring-2 ring-white" />
            </button>

            {/* Notifications Popover */}
            {notificationsOpen && (
              <div className="absolute right-0 mt-2 w-80 rounded-xl bg-white border border-slate-200/90 shadow-xl py-2 z-50 animate-in fade-in slide-in-from-top-1 duration-150">
                <div className="px-4 py-2 border-b border-slate-100 flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-800">Notifications</span>
                  <span className="text-[10px] font-semibold text-rose-600 bg-rose-50 px-2 py-0.5 rounded-full">
                    3 Unread
                  </span>
                </div>
                <div className="divide-y divide-slate-100 max-h-72 overflow-y-auto text-xs">
                  <div className="p-3 hover:bg-slate-50 transition-colors">
                    <p className="font-semibold text-slate-800">n8n Approval Webhook Ready</p>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      Client approved &quot;Q4 CFO Working Capital Report&quot;. Dispatched via n8n webhook.
                    </p>
                    <span className="text-[10px] text-slate-400 mt-1 block">5m ago</span>
                  </div>
                  <div className="p-3 hover:bg-slate-50 transition-colors">
                    <p className="font-semibold text-slate-800">Budget Utilization Milestone</p>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      Active Meta Ad Campaign reached 85% budget utilization with 3.4x ROAS.
                    </p>
                    <span className="text-[10px] text-slate-400 mt-1 block">1h ago</span>
                  </div>
                  <div className="p-3 hover:bg-slate-50 transition-colors">
                    <p className="font-semibold text-slate-800">Content Scheduled</p>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      &quot;Voice Telephony Automation&quot; scheduled for LinkedIn &amp; X tomorrow 8:30 AM.
                    </p>
                    <span className="text-[10px] text-slate-400 mt-1 block">3h ago</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 4. User Profile Avatar */}
          <div className="relative pl-2 border-l border-slate-200" ref={menuRef}>
            <button
              type="button"
              onClick={() => setUserMenuOpen((prev) => !prev)}
              className="flex items-center gap-2 hover:opacity-85 transition-opacity focus:outline-hidden"
              aria-expanded={userMenuOpen}
              aria-haspopup="true"
            >
              <div
                className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs text-white shadow-xs ring-2 ring-slate-100",
                  isMarketing ? "bg-gradient-to-br from-indigo-500 to-purple-600" : "bg-agile-red"
                )}
              >
                {userInitials}
              </div>
              <div className="hidden xl:flex flex-col text-left">
                <span className="text-xs font-semibold text-slate-800 leading-tight">
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

            {/* Profile Dropdown Menu */}
            {userMenuOpen && (
              <div className="absolute right-0 mt-2 w-56 rounded-xl bg-white border border-slate-200 shadow-xl py-1.5 z-50 animate-in fade-in slide-in-from-top-1 duration-150">
                <div className="px-3.5 py-2 border-b border-slate-100">
                  <p className="text-xs font-semibold text-slate-800 truncate">{currentUser.name}</p>
                  <p className="text-[11px] text-slate-400 truncate">{currentUser.email}</p>
                  <span className="inline-block mt-1 text-[10px] font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full">
                    {currentUser.role}
                  </span>
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
                    <span>Account Profile</span>
                  </button>
                  <Link
                    href="/settings"
                    onClick={() => setUserMenuOpen(false)}
                    className="w-full flex items-center gap-2 px-3.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50 transition-colors text-left"
                  >
                    <SettingsIcon className="w-3.5 h-3.5 text-slate-400" />
                    <span>Workspace Settings</span>
                  </Link>
                </div>

                <div className="pt-1 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={handleSignOut}
                    className="w-full flex items-center gap-2 px-3.5 py-1.5 text-xs text-rose-600 hover:bg-rose-50 transition-colors text-left font-medium"
                  >
                    <LogOut className="w-3.5 h-3.5 text-rose-500" />
                    <span>Sign Out</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Team Members Modal */}
      <Modal
        isOpen={teamModalOpen}
        onClose={() => setTeamModalOpen(false)}
        title="Agile Marketing Team"
        description="Collaborators with access to campaign approvals, scheduling, and ad channels."
        maxWidth="md"
      >
        <div className="space-y-3 py-2">
          {[
            { name: "Pravalika Palle", role: "VP Marketing & Strategy", status: "Online", email: "pravalika@agilereceivables.com" },
            { name: "Lakshay Narula", role: "Growth & Telephony Ops", status: "Online", email: "lakshay@agilereceivables.com" },
            { name: "Elena Rostova", role: "Content & Social Lead", status: "Active 10m ago", email: "elena@agilereceivables.com" },
            { name: "Marcus Chen", role: "Performance Paid Media", status: "Offline", email: "marcus@agilereceivables.com" },
          ].map((member) => (
            <div key={member.email} className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:bg-slate-50 transition-colors">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-indigo-100 text-indigo-700 font-bold text-xs flex items-center justify-center">
                  {getInitials(member.name)}
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-800">{member.name}</h4>
                  <p className="text-[11px] text-slate-400">{member.role}</p>
                </div>
              </div>
              <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                {member.status}
              </span>
            </div>
          ))}
        </div>
      </Modal>

      {/* Chat & Support Modal */}
      <Modal
        isOpen={chatModalOpen}
        onClose={() => setChatModalOpen(false)}
        title="Marketing Operations Support"
        description="Connect with internal operations or trigger AI campaign assistance."
        maxWidth="md"
      >
        <div className="space-y-4 py-2">
          <div className="p-3 bg-indigo-50 border border-indigo-100 rounded-lg text-xs text-indigo-900">
            <span className="font-semibold block mb-0.5">Need help with n8n approval automation or campaign delivery?</span>
            Our automated dispatch webhook validates client approvals and schedules multi-platform creatives instantly.
          </div>
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-700">Quick Support Note</label>
            <textarea
              rows={3}
              placeholder="Describe your question or campaign issue..."
              className="w-full p-2.5 text-xs rounded-lg border border-slate-200 focus:outline-hidden focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setChatModalOpen(false)}>
              Close
            </Button>
            <Button
              variant="primary"
              size="sm"
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
              onClick={() => {
                setChatModalOpen(false);
                alert("Support ticket logged with Marketing Ops.");
              }}
            >
              Send Message
            </Button>
          </div>
        </div>
      </Modal>

      {/* User Profile Modal */}
      <Modal
        isOpen={profileModalOpen}
        onClose={() => setProfileModalOpen(false)}
        title="User Profile"
        description="Active authenticated identity and tenant workspace."
        maxWidth="md"
      >
        <div className="space-y-4 py-2">
          <div className="flex items-center gap-4 p-4 rounded-xl bg-slate-50 border border-slate-200">
            <div className="w-12 h-12 rounded-full bg-indigo-600 text-white font-bold text-sm flex items-center justify-center shadow-xs">
              {userInitials}
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-800">{currentUser.name}</h3>
              <p className="text-xs text-slate-500">{currentUser.email}</p>
              <span className="inline-block mt-1 text-[10px] font-semibold text-indigo-700 bg-indigo-100 px-2 py-0.5 rounded-full">
                {currentUser.role}
              </span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="p-3 rounded-lg border border-slate-100 bg-white">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Workspace</span>
              <p className="font-semibold text-slate-800 mt-0.5">{currentUser.organization}</p>
            </div>
            <div className="p-3 rounded-lg border border-slate-100 bg-white">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Domain Access</span>
              <p className="font-semibold text-indigo-600 mt-0.5">Marketing &amp; Sales (Full)</p>
            </div>
          </div>
        </div>
      </Modal>
    </>
  );
};
