"use client";

import * as React from "react";
import { useAppMode } from "@/contexts/AppModeContext";
import MarketingSettingsPage from "@/app/marketing/settings/page";
import SalesSettingsPage from "@/app/sales/settings/page";

export default function SettingsRouterPage() {
  const { mode } = useAppMode();
  const isMarketing = mode === "marketing";

  if (isMarketing) {
    return <MarketingSettingsPage />;
  }

  return <SalesSettingsPage />;
}
