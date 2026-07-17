"use client";

import * as React from "react";
import type { DashboardSnapshot } from "@/lib/dashboard";
import { useLang } from "@/lib/i18n";
import {
  ensureNafeaSession,
  invalidateNafeaSession,
  NafeaApiError,
  nafeaRequest,
} from "@/lib/nafea-api";

type DashboardStatus = "loading" | "ready" | "refreshing" | "error";
type DashboardContextValue = {
  snapshot: DashboardSnapshot | null;
  status: DashboardStatus;
  error: string;
  refresh: (options?: { silent?: boolean }) => Promise<void>;
};

const DashboardContext = React.createContext<DashboardContextValue | null>(null);

export function DashboardProvider({ children }: { children: React.ReactNode }) {
  const { lang, t } = useLang();
  const [snapshot, setSnapshot] = React.useState<DashboardSnapshot | null>(null);
  const [status, setStatus] = React.useState<DashboardStatus>("loading");
  const [error, setError] = React.useState("");
  const sequence = React.useRef(0);
  const hasSnapshot = React.useRef(false);

  const refresh = React.useCallback(async (options?: { silent?: boolean }) => {
    const request = ++sequence.current;
    const isBackgroundRefresh = Boolean(options?.silent && hasSnapshot.current);
    if (!isBackgroundRefresh) {
      setStatus((current) => (current === "ready" ? "refreshing" : "loading"));
      setError("");
    }
    try {
      await ensureNafeaSession(lang);
      let next: DashboardSnapshot;
      try {
        next = await nafeaRequest<DashboardSnapshot>("/api/dashboard", { cache: "no-store" });
      } catch (requestError) {
        if (!(requestError instanceof NafeaApiError) || requestError.status !== 401) {
          throw requestError;
        }
        invalidateNafeaSession();
        await ensureNafeaSession(lang);
        next = await nafeaRequest<DashboardSnapshot>("/api/dashboard", { cache: "no-store" });
      }
      if (sequence.current !== request) return;
      hasSnapshot.current = true;
      setSnapshot(next);
      setStatus("ready");
    } catch {
      if (sequence.current !== request) return;
      if (isBackgroundRefresh) return;
      setStatus("error");
      setError(t("dashboardError"));
    }
  }, [lang, t]);

  React.useEffect(() => {
    void refresh();
    const update = () => void refresh();
    const updateWhenVisible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    window.addEventListener("nafea:financial-action", update);
    window.addEventListener("focus", update);
    document.addEventListener("visibilitychange", updateWhenVisible);
    return () => {
      sequence.current += 1;
      window.removeEventListener("nafea:financial-action", update);
      window.removeEventListener("focus", update);
      document.removeEventListener("visibilitychange", updateWhenVisible);
    };
  }, [refresh]);

  const value = React.useMemo(
    () => ({ snapshot, status, error, refresh }),
    [snapshot, status, error, refresh]
  );
  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboard() {
  const context = React.useContext(DashboardContext);
  if (!context) throw new Error("useDashboard must be used within DashboardProvider");
  return context;
}
