"use client";

import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";

import { useLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export function DashboardDataNotice({
  status,
  error,
  onRetry,
}: {
  status: "loading" | "ready" | "refreshing" | "error";
  error: string;
  onRetry: () => void;
}) {
  const { t } = useLang();
  const failed = status === "error";
  const busy = status === "loading" || status === "refreshing";
  const Icon = failed ? AlertTriangle : busy ? Loader2 : CheckCircle2;

  return (
    <aside
      className={cn(
        "mb-4 flex items-center gap-2 rounded-xl border px-3.5 py-3 text-xs",
        failed
          ? "border-negative/25 bg-negative/10 text-negative"
          : "border-primary/20 bg-primary/10 text-muted-foreground"
      )}
      role={failed ? "alert" : "status"}
    >
      <Icon
        className={cn("size-4 shrink-0", busy && "animate-spin", !failed && "text-primary")}
        aria-hidden
      />
      <p className="flex-1">
        {failed
          ? error
          : status === "loading"
            ? t("dashboardLoading")
            : status === "refreshing"
              ? t("dashboardRefreshing")
              : t("dashboardDataNotice")}
      </p>
      {failed ? (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-lg border border-negative/30 px-2.5 py-1 font-semibold transition-colors hover:bg-negative/10"
        >
          {t("retry")}
        </button>
      ) : null}
    </aside>
  );
}
