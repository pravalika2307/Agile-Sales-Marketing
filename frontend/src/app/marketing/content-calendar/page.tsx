"use client";

import * as React from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { ContentCalendarKanban } from "@/components/marketing/content-calendar-kanban";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Share2 } from "lucide-react";

export default function MarketingContentCalendarPage() {
  return (
    <AppShell>
      <div className="space-y-6">
        {/* Breadcrumb / Top Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-200/80">
          <div>
            <div className="flex items-center gap-2">
              <Link
                href="/marketing"
                className="text-xs font-semibold text-slate-500 hover:text-slate-800 flex items-center gap-1 transition-colors"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Marketing</span>
              </Link>
              <span className="text-slate-300">/</span>
              <span className="text-xs font-semibold text-indigo-600">Content Calendar</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 mt-1">
              Content Calendar (Kanban)
            </h1>
            <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
              Plan, review, and schedule social media creatives across LinkedIn, Instagram, X, and Facebook.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <Link href="/marketing/social-media">
              <Button
                variant="outline"
                size="sm"
                className="text-xs font-semibold border-indigo-200 hover:bg-indigo-50 text-indigo-700 bg-white"
              >
                <Share2 className="w-3.5 h-3.5 mr-1.5 text-indigo-600" />
                <span>Social Media Hub</span>
              </Button>
            </Link>
          </div>
        </div>

        {/* Content Calendar Kanban Component */}
        <ContentCalendarKanban />
      </div>
    </AppShell>
  );
}
