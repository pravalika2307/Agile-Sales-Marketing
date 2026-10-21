"use client";

import * as React from "react";

export type AccessLevel = "sales" | "marketing" | "both";
export type AppMode = "sales" | "marketing";

export interface AppModeContextValue {
  mode: AppMode;
  accessLevel: AccessLevel;
  canToggle: boolean;
  setMode: (mode: AppMode) => void;
  toggleMode: () => void;
  isLoading: boolean;
}

const AppModeContext = React.createContext<AppModeContextValue | undefined>(undefined);

const STORAGE_KEY = "agile_app_mode";

function parseAccessLevel(val?: string | null): AccessLevel {
  if (!val) return "both";
  const clean = val.toLowerCase().trim();
  if (clean === "sales") return "sales";
  if (clean === "marketing") return "marketing";
  return "both";
}

export const AppModeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [accessLevel, setAccessLevel] = React.useState<AccessLevel>("both");
  const [mode, setModeState] = React.useState<AppMode>("sales");
  const [isLoading, setIsLoading] = React.useState(true);

  // Load access level from session and reconcile active mode
  React.useEffect(() => {
    let resolvedAccess: AccessLevel = "both";

    // 1. Try reading agile_user cookie
    try {
      const match = document.cookie.match(/(?:^|;\s*)agile_user=([^;]+)/);
      if (match && match[1]) {
        const parsed = JSON.parse(decodeURIComponent(match[1]));
        if (parsed.access_level) {
          resolvedAccess = parseAccessLevel(parsed.access_level);
        }
      }
    } catch {}

    setAccessLevel(resolvedAccess);

    // Reconcile initial mode
    if (resolvedAccess === "sales") {
      setModeState("sales");
    } else if (resolvedAccess === "marketing") {
      setModeState("marketing");
    } else {
      // User has "both" access: check URL parameter, path, or stored preference
      try {
        const params = new URLSearchParams(window.location.search);
        const queryMode = params.get("mode") as AppMode | null;
        if (queryMode === "marketing" || queryMode === "sales") {
          setModeState(queryMode);
          localStorage.setItem(STORAGE_KEY, queryMode);
        } else {
          const isMarketingPath =
            window.location.pathname.startsWith("/social-media") ||
            window.location.pathname.startsWith("/content-calendar") ||
            window.location.pathname.startsWith("/automation");

          if (isMarketingPath) {
            setModeState("marketing");
          } else {
            const saved = localStorage.getItem(STORAGE_KEY) as AppMode | null;
            if (saved === "marketing" || saved === "sales") {
              setModeState(saved);
            } else {
              setModeState("marketing");
            }
          }
        }
      } catch {
        setModeState("marketing");
      }
    }

    // 2. Background verify with /api/auth/me to stay in sync
    async function verifyUser() {
      try {
        const resp = await fetch("/api/auth/me");
        if (resp.ok) {
          const data = await resp.json();
          if (data && data.access_level) {
            const apiAccess = parseAccessLevel(data.access_level);
            setAccessLevel(apiAccess);
            if (apiAccess === "sales") {
              setModeState("sales");
            } else if (apiAccess === "marketing") {
              setModeState("marketing");
            }
          }
        }
      } catch {
        // Fallback to cookie / initial state
      } finally {
        setIsLoading(false);
      }
    }

    verifyUser();
  }, []);

  const canToggle = accessLevel === "both";

  const setMode = React.useCallback(
    (newMode: AppMode) => {
      if (!canToggle) return; // Locked to assigned view
      setModeState(newMode);
      try {
        localStorage.setItem(STORAGE_KEY, newMode);
      } catch {}
    },
    [canToggle]
  );

  const toggleMode = React.useCallback(() => {
    if (!canToggle) return;
    const nextMode: AppMode = mode === "sales" ? "marketing" : "sales";
    setMode(nextMode);
  }, [canToggle, mode, setMode]);

  const value = React.useMemo<AppModeContextValue>(
    () => ({
      mode,
      accessLevel,
      canToggle,
      setMode,
      toggleMode,
      isLoading,
    }),
    [mode, accessLevel, canToggle, setMode, toggleMode, isLoading]
  );

  return <AppModeContext.Provider value={value}>{children}</AppModeContext.Provider>;
};

export function useAppMode(): AppModeContextValue {
  const context = React.useContext(AppModeContext);
  if (!context) {
    throw new Error("useAppMode must be used within an AppModeProvider");
  }
  return context;
}
