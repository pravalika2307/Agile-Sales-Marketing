"use client";

import * as React from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  ArrowLeft,
  CheckCircle2,
  PhoneCall,
  Layers,
} from "lucide-react";

export default function SalesSettingsPage() {
  const [savedToast, setSavedToast] = React.useState(false);
  const [callerId, setCallerId] = React.useState("+1 (800) 555-0199");
  const [agentId, setAgentId] = React.useState("agent_46fb4b1901d63d803e5ef3030e");

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSavedToast(true);
    setTimeout(() => setSavedToast(false), 4000);
  };

  return (
    <AppShell>
      <div className="space-y-6 max-w-4xl">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-200/80">
          <div>
            <div className="flex items-center gap-2">
              <Link
                href="/sales"
                className="text-xs font-semibold text-slate-500 hover:text-slate-800 flex items-center gap-1 transition-colors"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Sales</span>
              </Link>
              <span className="text-slate-300">/</span>
              <span className="text-xs font-semibold text-agile-red">Settings</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-header mt-1">
              Sales Platform Settings
            </h1>
            <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
              Manage telephony dispatch parameters, CRM sync rules, and SDR team settings.
            </p>
          </div>
        </div>

        {savedToast && (
          <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2 animate-in fade-in">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span className="font-semibold">Sales settings saved successfully.</span>
          </div>
        )}

        {/* Retell AI Voice Configuration */}
        <Card className="rounded-xl border border-slate-200/80 bg-white shadow-xs">
          <CardHeader className="p-4 sm:p-5 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <PhoneCall className="w-4 h-4 text-agile-red" />
              <CardTitle className="text-sm sm:text-base font-bold text-header">
                Retell AI Voice Telephony Configuration
              </CardTitle>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Default telephony endpoints and voice follow-up agent assignments.
            </p>
          </CardHeader>
          <CardContent className="p-4 sm:p-5">
            <form onSubmit={handleSave} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-bold text-slate-700 block mb-1">
                    Default Outbound Caller ID
                  </label>
                  <input
                    type="text"
                    value={callerId}
                    onChange={(e) => setCallerId(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-mono rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-hidden focus:ring-1 focus:ring-agile-red"
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-slate-700 block mb-1">
                    Primary Voice Agent ID
                  </label>
                  <input
                    type="text"
                    value={agentId}
                    onChange={(e) => setAgentId(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-mono rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-hidden focus:ring-1 focus:ring-agile-red"
                  />
                </div>
              </div>

              <div className="p-3 rounded-lg bg-agile-lightorange/60 border border-agile-outlinered/30 text-xs text-slate-700">
                <strong>Data Truth Protection:</strong> All prospect email addresses and contact phone numbers are encrypted in transit and never overwritten by synthetic payloads.
              </div>

              <div className="flex justify-end pt-2">
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  className="bg-agile-red hover:bg-[#c5444c] text-white text-xs font-semibold"
                >
                  Save Telephony Settings
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        {/* CRM Deal Pipeline Mapping */}
        <Card className="rounded-xl border border-slate-200/80 bg-white shadow-xs">
          <CardHeader className="p-4 sm:p-5 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-agile-red" />
              <CardTitle className="text-sm sm:text-base font-bold text-header">
                HubSpot CRM &amp; Pipeline Synchronization
              </CardTitle>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Bidirectional sync rules between Retell calls, deal stages, and SDR notes.
            </p>
          </CardHeader>
          <CardContent className="p-4 sm:p-5 space-y-3">
            {[
              { rule: "Auto-advance deal to 'Qualified' on meeting booking", status: "Active" },
              { rule: "Record call audio recording in HubSpot timeline", status: "Active" },
              { rule: "Webhook retry policy: 3 attempts with exponential backoff", status: "Active" },
            ].map((r) => (
              <div
                key={r.rule}
                className="flex items-center justify-between p-3 rounded-lg border border-slate-100 bg-slate-50/50 text-xs"
              >
                <span className="font-medium text-slate-700">{r.rule}</span>
                <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                  {r.status}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
