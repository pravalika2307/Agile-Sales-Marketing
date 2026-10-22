"use client";

import * as React from "react";
import { usePathname } from "next/navigation";

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
  const pathname = usePathname();

  const [accessLevel, setAccessLevel] = React.useState<AccessLevel>(() => {
    if (typeof document !== "undefined") {
      try {
        const match = document.cookie.match(/(?:^|;\s*)agile_user=([^;]+)/);
        if (match && match[1]) {
          const parsed = JSON.parse(decodeURIComponent(match[1]));
          if (parsed.access_level) {
            return parseAccessLevel(parsed.access_level);
          }
        }
      } catch {}
    }
    return "both";
  });

  const [modeState, setModeState] = React.useState<AppMode>(() => {
    if (typeof window !== "undefined") {
      try {
        if (window.location.pathname.startsWith("/marketing")) return "marketing";
        if (window.location.pathname.startsWith("/sales")) return "sales";
        const params = new URLSearchParams(window.location.search);
        const queryMode = params.get("mode") as AppMode | null;
        if (queryMode === "marketing" || queryMode === "sales") return queryMode;
        const saved = localStorage.getItem(STORAGE_KEY) as AppMode | null;
        if (saved === "marketing" || saved === "sales") return saved;
      } catch {}
    }
    return "marketing";
  });

  const isLoading = false;

  // Derived mode: when the route path explicitly starts with /marketing or /sales, it takes priority
  const mode: AppMode = React.useMemo(() => {
    if (pathname?.startsWith("/marketing")) return "marketing";
    if (pathname?.startsWith("/sales")) return "sales";
    return modeState;
  }, [pathname, modeState]);

  // Background verify with /api/auth/me to stay in sync
  React.useEffect(() => {
    let isMounted = true;
    async function verifyUser() {
      try {
        const resp = await fetch("/api/auth/me");
        if (resp.ok && isMounted) {
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
      }
    }

    verifyUser();
    return () => {
      isMounted = false;
    };
  }, []);

  const canToggle = accessLevel === "both";

  const setMode = React.useCallback(
    (newMode: AppMode) => {
      if (!canToggle) return;
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
  const ctx = React.useContext(AppModeContext);
  if (!ctx) {
    throw new Error("useAppMode must be used within an AppModeProvider");
  }
  return ctx;
}
