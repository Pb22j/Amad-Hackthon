"use client";

import { AlertCircle, LoaderCircle, RefreshCw } from "lucide-react";
import { useDashboard } from "@/components/dashboard-provider";
import { useLang } from "@/lib/i18n";

export function DashboardState({ children }: { children: React.ReactNode }) {
  const { snapshot, status, error, refresh } = useDashboard();
  const { t } = useLang();
  if ((status === "loading" || status === "refreshing") && !snapshot) {
    return <div className="content-state"><LoaderCircle className="spin" /><p>{t("dashboardLoading")}</p></div>;
  }
  if (!snapshot) {
    return <div className="content-state error"><AlertCircle /><p>{error || t("dashboardError")}</p>
      <button type="button" className="secondary-button" onClick={() => void refresh()}>
        <RefreshCw size={16} /> {t("tryAgain")}
      </button>
    </div>;
  }
  return <>{children}</>;
}
