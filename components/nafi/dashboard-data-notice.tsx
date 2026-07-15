"use client";

import { Info } from "lucide-react";

import { useLang } from "@/lib/i18n";

export function DashboardDataNotice() {
  const { t } = useLang();

  return (
    <aside
      className="mb-4 flex items-start gap-2 rounded-xl border border-primary/20 bg-primary/10 px-3.5 py-3 text-xs text-muted-foreground"
      role="note"
    >
      <Info className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
      <p>{t("dashboardDataNotice")}</p>
    </aside>
  );
}
