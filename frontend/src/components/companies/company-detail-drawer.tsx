"use client";

import * as React from "react";
import { CompanyAccount } from "@/services/companyService";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  X,
  Building2,
  Globe,
  MapPin,
  Users,
  Briefcase,
  Mail,
  Phone,
  PhoneCall,
  Send,
  MessageSquare,
  ShieldCheck,
  ChevronRight,
  TrendingUp,
} from "lucide-react";

export interface CompanyDetailDrawerProps {
  company: CompanyAccount | null;
  isOpen: boolean;
  onClose: () => void;
  onAddToCampaign?: (company: CompanyAccount) => void;
}

export const CompanyDetailDrawer: React.FC<CompanyDetailDrawerProps> = ({
  company,
  isOpen,
  onClose,
  onAddToCampaign,
}) => {
  // ESC key handler
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (isOpen) {
      document.body.style.overflow = "hidden";
      window.addEventListener("keydown", handleKeyDown);
    } else {
      document.body.style.overflow = "unset";
    }
    return () => {
      document.body.style.overflow = "unset";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen || !company) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/30 backdrop-blur-xs transition-opacity animate-in fade-in duration-150"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer Surface */}
      <div className="relative w-full max-w-lg bg-white h-full shadow-2xl border-l border-slate-200 z-10 flex flex-col overflow-hidden animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-5 border-b border-slate-100 flex items-start justify-between gap-3 bg-slate-50/50">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Company Account
              </span>
              <span className="text-slate-300">•</span>
              <span className="font-mono text-[11px] text-slate-400">
                {company.id}
              </span>
            </div>
            <h2 className="text-lg font-bold text-header leading-tight">
              {company.name}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {company.industry} • {company.employeeCountRange} employees
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
            aria-label="Close drawer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Action Header Strip */}
        <div className="px-5 py-3 border-b border-slate-100 bg-white flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            {company.status === "ACTIVE" && (
              <Badge variant="success" dot>
                ACTIVE
              </Badge>
            )}
            {company.status === "NEW" && (
              <Badge variant="neutral">NEW</Badge>
            )}
            {company.status === "INACTIVE" && (
              <Badge variant="neutral">INACTIVE</Badge>
            )}
            <span className="text-xs text-slate-500 font-medium ml-1">
              {company.contactsCount} contacts • {company.leadsCount} leads
            </span>
          </div>

          <Button
            variant="primary"
            size="sm"
            onClick={() => onAddToCampaign?.(company)}
            className="text-xs shadow-xs"
          >
            Add to Campaign
          </Button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6 text-xs text-slate-700">
          {/* Section: Company Overview */}
          <div className="space-y-3">
            <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Company Overview
            </h4>
            <div className="rounded-lg border border-slate-200/80 p-3.5 bg-slate-50/50 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Industry</span>
                <span className="text-slate-800 font-semibold">
                  {company.industry}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Company Size</span>
                <span className="text-slate-800 font-medium">
                  {company.employeeCountRange} employees
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500 flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5 text-slate-400" />
                  Location
                </span>
                <span className="text-slate-800 font-medium">
                  {company.location}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500 flex items-center gap-1.5">
                  <Globe className="w-3.5 h-3.5 text-slate-400" />
                  Website
                </span>
                <a
                  href={company.website}
                  target="_blank"
                  rel="noreferrer"
                  className="text-agile-red hover:underline font-medium"
                >
                  {company.domain}
                </a>
              </div>
            </div>
          </div>

          {/* Section: Associated Contacts */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Associated Contacts ({(company.contacts || []).length})
              </h4>
            </div>

            {(company.contacts || []).length > 0 ? (
              <div className="space-y-2">
                {company.contacts.map((contact) => (
                  <div
                    key={contact.id}
                    className="p-3 rounded-lg border border-slate-200/80 bg-white shadow-xs flex items-start justify-between gap-2"
                  >
                    <div className="space-y-0.5">
                      <span className="font-semibold text-slate-800 block text-xs">
                        {contact.fullName}
                      </span>
                      <span className="text-[11px] text-slate-500 block">
                        {contact.jobTitle}
                      </span>
                      <div className="flex items-center gap-3 pt-1 text-[11px] text-slate-500">
                        <span className="font-mono text-slate-600 flex items-center gap-1">
                          <Mail className="w-3 h-3 text-slate-400" />
                          {contact.email}
                        </span>
                        {contact.phone && (
                          <span className="font-mono text-slate-600 flex items-center gap-1">
                            <Phone className="w-3 h-3 text-slate-400" />
                            {contact.phone}
                          </span>
                        )}
                      </div>
                    </div>
                    {contact.seniority && (
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
                        {contact.seniority}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-400 italic">No contacts associated with this company account.</p>
            )}
          </div>

          {/* Section: Active Leads */}
          <div className="space-y-3">
            <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Associated Leads ({(company.leads || []).length})
            </h4>

            {(company.leads || []).length > 0 ? (
              <div className="space-y-2">
                {company.leads.map((l) => (
                  <div
                    key={l.id}
                    className="p-3 rounded-lg border border-slate-200/80 bg-slate-50/50 flex items-center justify-between gap-2"
                  >
                    <div>
                      <span className="font-semibold text-slate-800 block">
                        {l.name}
                      </span>
                      <span className="text-[11px] text-slate-500">
                        {l.jobTitle} • Status: <span className="uppercase">{l.status}</span>
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {l.score !== null ? (
                        <span
                          className={`text-xs font-bold px-2 py-0.5 rounded border ${
                            l.score >= 85
                              ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                              : "bg-amber-50 text-amber-700 border-amber-200"
                          }`}
                        >
                          {l.score}
                        </span>
                      ) : (
                        <span className="text-xs font-medium px-2 py-0.5 rounded border bg-slate-50 text-slate-400 border-slate-200">
                          Unscored
                        </span>
                      )}
                      {l.temperature === "HOT" && (
                        <Badge variant="coral" dot>
                          HOT
                        </Badge>
                      )}
                      {l.temperature === "WARM" && (
                        <Badge variant="peach" dot>
                          WARM
                        </Badge>
                      )}
                      {l.temperature === "COLD" && (
                        <Badge variant="neutral">COLD</Badge>
                      )}
                      {l.temperature === "UNASSESSED" && (
                        <span className="text-xs text-slate-400">—</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-400 italic">No leads associated with this company account.</p>
            )}
          </div>

          {/* Section: Campaigns */}
          <div className="space-y-3">
            <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Target Campaigns
            </h4>
            {(company.campaigns || []).length > 0 ? (
              <div className="space-y-1.5">
                {company.campaigns.map((camp, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 rounded-lg border border-agile-outlinered/30 bg-agile-lightorange/40 flex items-center justify-between text-xs text-header font-medium"
                  >
                    <span>{camp}</span>
                    <Badge variant="coral">Targeting</Badge>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-400 italic">No campaigns currently assigned.</p>
            )}
          </div>

          {/* Section: Recent Activity Timeline */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Recent Account Activity
              </h4>
              <span className="text-[10px] text-slate-400">
                {(company.activities || []).length} events
              </span>
            </div>

            {(company.activities || []).length > 0 ? (
              <div className="space-y-2">
                {company.activities.map((act) => (
                  <div
                    key={act.id}
                    className="p-3 rounded-lg border border-slate-200/80 bg-white shadow-xs space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-800 flex items-center gap-1.5">
                        {act.type === "voice_call" && (
                          <PhoneCall className="w-3.5 h-3.5 text-agile-red" />
                        )}
                        {act.type === "email" && (
                          <Send className="w-3.5 h-3.5 text-slate-500" />
                        )}
                        {act.type === "reply" && (
                          <MessageSquare className="w-3.5 h-3.5 text-emerald-600" />
                        )}
                        {act.type === "status" && (
                          <ShieldCheck className="w-3.5 h-3.5 text-agile-orange" />
                        )}
                        {act.type === "campaign" && (
                          <Briefcase className="w-3.5 h-3.5 text-slate-500" />
                        )}
                        <span>{act.title}</span>
                      </span>
                      <span className="text-[10px] text-slate-400 font-medium">
                        {act.timestamp}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-600 pl-5">
                      {act.description}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-400 italic">No recent activity recorded for this company account.</p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-100 bg-slate-50/50 flex items-center justify-between gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={onClose}
            className="text-xs"
          >
            Close
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={() => onAddToCampaign?.(company)}
            className="text-xs shadow-xs"
          >
            Add to Campaign
          </Button>
        </div>
      </div>
    </div>
  );
};
