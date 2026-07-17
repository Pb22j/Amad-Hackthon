"use client";

import { useRouter } from "next/navigation";
import { ArrowRightFromLine, Languages, MessageSquarePlus, ShieldCheck, UserRound } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useDashboard } from "@/components/dashboard-provider";
import { useAuth } from "@/lib/auth";
import { useLang } from "@/lib/i18n";
import { startNewNafeaChat } from "@/lib/nafea-api";

export default function SettingsPage() {
  return <AppShell><SettingsContent /></AppShell>;
}

function SettingsContent() {
  const { snapshot } = useDashboard();
  const { signOut } = useAuth();
  const { t, toggleLang, localize } = useLang();
  const router = useRouter();
  return <div className="page-stack settings-page">
    <header className="page-heading"><div><h1>{t("settings")}</h1><p>{t("secureAccessCopy")}</p></div></header>
    <section className="settings-list">
      <article className="settings-row"><span className="settings-icon"><UserRound size={20} /></span><div><strong>{t("profile")}</strong><small>{snapshot ? localize(snapshot.user.name, snapshot.user.name_ar) : "Nafi"}</small></div><span className="avatar">{snapshot?.user.initial || "N"}</span></article>
      <button type="button" className="settings-row" onClick={toggleLang}><span className="settings-icon"><Languages size={20} /></span><div><strong>{t("preferences")}</strong><small>{t("language")}</small></div></button>
      <article className="settings-row"><span className="settings-icon"><ShieldCheck size={20} /></span><div><strong>{t("security")}</strong><small>{t("securityCopy")}</small></div></article>
      <button type="button" className="settings-row" onClick={async () => { await startNewNafeaChat(); router.push("/assistant"); }}><span className="settings-icon"><MessageSquarePlus size={20} /></span><div><strong>{t("startFresh")}</strong><small>{t("freshChatCopy")}</small></div></button>
      <button type="button" className="settings-row danger" onClick={async () => { await signOut(); router.replace("/"); }}><span className="settings-icon"><ArrowRightFromLine size={20} /></span><div><strong>{t("signOut")}</strong></div></button>
    </section>
  </div>;
}
