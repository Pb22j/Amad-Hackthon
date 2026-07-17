"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ArrowRightFromLine,
  Bot,
  Compass,
  House,
  Languages,
  Menu,
  Settings,
  Sparkles,
  TrendingUp,
  WalletCards,
  X,
} from "lucide-react";
import { Brand } from "@/components/brand";
import { DashboardProvider, useDashboard } from "@/components/dashboard-provider";
import { RequireAuth } from "@/components/require-auth";
import { ThemeToggle } from "@/components/theme-toggle";
import { useAuth } from "@/lib/auth";
import { useLang } from "@/lib/i18n";

const navigation = [
  { href: "/dashboard", label: "overview", icon: House },
  { href: "/investments", label: "invest", icon: TrendingUp },
  { href: "/activity", label: "activity", icon: WalletCards },
  { href: "/explore", label: "explore", icon: Compass },
  { href: "/assistant", label: "assistant", icon: Bot },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <DashboardProvider>
        <Shell>{children}</Shell>
      </DashboardProvider>
    </RequireAuth>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const { t, toggleLang, dir, localize } = useLang();
  const { signOut } = useAuth();
  const { snapshot } = useDashboard();
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = React.useState(false);

  async function logout() {
    await signOut();
    router.replace("/");
  }

  const userName = snapshot
    ? localize(snapshot.user.name, snapshot.user.name_ar)
    : t("profile");

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <Brand />
        <nav className="sidebar-nav">
          {navigation.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={`nav-link ${pathname === href ? "active" : ""}`}
            >
              <Icon size={20} strokeWidth={1.9} />
              <span>{t(label)}</span>
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <Link
            href="/settings"
            className={`nav-link ${pathname === "/settings" ? "active" : ""}`}
          >
            <Settings size={20} strokeWidth={1.9} />
            <span>{t("settings")}</span>
          </Link>
          <div className="sidebar-profile">
            <span className="avatar">{snapshot?.user.initial || "N"}</span>
            <span className="profile-copy">
              <strong>{userName}</strong>
              <small>{snapshot?.wallet.nafi_iban || "Nafi"}</small>
            </span>
            <button type="button" onClick={() => void logout()} aria-label={t("signOut")}>
              <ArrowRightFromLine size={18} className={dir === "rtl" ? "flip" : ""} />
            </button>
          </div>
        </div>
      </aside>

      <div className="app-main">
        <header className="topbar">
          <div className="mobile-brand"><Brand compact /></div>
          <div className="topbar-spacer" />
          <button type="button" className="language-button" onClick={toggleLang}>
            <Languages size={17} />
            <span>{t("language")}</span>
          </button>
          <ThemeToggle />
          <button
            type="button"
            className="profile-button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-expanded={menuOpen}
            aria-label={t("profile")}
          >
            <span className="avatar small">{snapshot?.user.initial || "N"}</span>
            <Menu size={18} />
          </button>
          {menuOpen ? (
            <div className="profile-menu">
              <div className="profile-menu-name">
                <span className="avatar">{snapshot?.user.initial || "N"}</span>
                <span><strong>{userName}</strong><small>{t("secureAccess")}</small></span>
                <button type="button" onClick={() => setMenuOpen(false)} aria-label="Close">
                  <X size={17} />
                </button>
              </div>
              <Link href="/settings" onClick={() => setMenuOpen(false)}>
                <Settings size={17} /> {t("settings")}
              </Link>
              <button type="button" onClick={() => void logout()}>
                <ArrowRightFromLine size={17} /> {t("signOut")}
              </button>
            </div>
          ) : null}
        </header>
        <main className="page-content">{children}</main>
      </div>

      <nav className="mobile-nav" aria-label="Mobile navigation">
        {navigation.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} className={pathname === href ? "active" : ""}>
            <Icon size={21} strokeWidth={pathname === href ? 2.4 : 1.8} />
            <span>{t(label)}</span>
          </Link>
        ))}
      </nav>

      <Link className="assistant-fab" href="/assistant" aria-label={t("assistant")}>
        <Sparkles size={20} />
      </Link>
    </div>
  );
}
