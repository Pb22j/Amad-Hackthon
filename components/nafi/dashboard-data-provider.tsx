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
  refresh: () => Promise<void>;
};

const DashboardContext = React.createContext<DashboardContextValue | null>(null);

export function DashboardDataProvider({ children }: { children: React.ReactNode }) {
  const { lang, t } = useLang();
  const [snapshot, setSnapshot] = React.useState<DashboardSnapshot | null>(null);
  const [status, setStatus] = React.useState<DashboardStatus>("loading");
  const [error, setError] = React.useState("");
  const requestSequence = React.useRef(0);

  const refresh = React.useCallback(async () => {
    const sequence = ++requestSequence.current;
    setStatus((current) => (current === "ready" || current === "refreshing" ? "refreshing" : "loading"));
    setError("");
    try {
      await ensureNafeaSession(lang);
      let next: DashboardSnapshot;
      try {
        next = await nafeaRequest<DashboardSnapshot>("/api/dashboard");
      } catch (requestError) {
        if (!(requestError instanceof NafeaApiError) || requestError.status !== 401) throw requestError;
        invalidateNafeaSession();
        await ensureNafeaSession(lang);
        next = await nafeaRequest<DashboardSnapshot>("/api/dashboard");
      }
      if (sequence !== requestSequence.current) return;
      setSnapshot(next);
      setStatus("ready");
    } catch {
      if (sequence !== requestSequence.current) return;
      setStatus("error");
      setError(t("dashboardError"));
    }
  }, [lang, t]);

  React.useEffect(() => {
    void refresh();
    return () => {
      requestSequence.current += 1;
    };
  }, [refresh]);

  const value = React.useMemo(
    () => ({ snapshot, status, error, refresh }),
    [snapshot, status, error, refresh]
  );

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboardData(): DashboardContextValue {
  const context = React.useContext(DashboardContext);
  if (!context) throw new Error("useDashboardData must be used within DashboardDataProvider");
  return context;
}
