"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  BadgeCheck,
  Eye,
  EyeOff,
  Languages,
  LoaderCircle,
  LockKeyhole,
  MessageCircleMore,
  ShieldCheck,
  WalletCards,
} from "lucide-react";
import { Brand } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { useAuth } from "@/lib/auth";
import { useLang } from "@/lib/i18n";
import { NafeaApiError } from "@/lib/nafea-api";

export function LoginScreen() {
  const { ready, isAuthenticated, signIn, signUp } = useAuth();
  const { t, lang, dir, toggleLang } = useLang();
  const router = useRouter();
  const [mode, setMode] = React.useState<"login" | "register">("login");
  const [identifier, setIdentifier] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [nameEn, setNameEn] = React.useState("");
  const [nameAr, setNameAr] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (ready && isAuthenticated) router.replace("/dashboard");
  }, [isAuthenticated, ready, router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      if (mode === "register") {
        await signUp({
          username: identifier,
          full_name_en: nameEn,
          full_name_ar: nameAr,
          password,
          language: lang,
        });
      } else {
        await signIn(identifier, password, lang);
      }
      router.push("/dashboard");
    } catch (requestError) {
      setError(
        requestError instanceof NafeaApiError && requestError.status === 401
          ? t("invalidCredentials")
          : requestError instanceof NafeaApiError && requestError.status === 409
            ? t("usernameTaken")
            : t("authError")
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (!ready || isAuthenticated) {
    return <main className="center-state"><LoaderCircle className="spin" /></main>;
  }

  return (
    <main className="login-page">
      <section className="login-story">
        <div className="login-story-inner">
          <Brand />
          <div className="login-headline">
            <p className="eyebrow"><BadgeCheck size={15} /> {t("secureAccess")}</p>
            <h1>{t("welcome")}</h1>
            <p>{t("welcomeSub")}</p>
          </div>
          <div className="login-capabilities">
            <div><span><WalletCards size={20} /></span><p>{t("capabilityOne")}</p></div>
            <div><span><ShieldCheck size={20} /></span><p>{t("capabilityTwo")}</p></div>
            <div><span><MessageCircleMore size={20} /></span><p>{t("capabilityThree")}</p></div>
          </div>
          <div className="login-preview-card" aria-hidden="true">
            <div className="preview-card-top"><span>Nafi wallet</span><span>••• 4821</span></div>
            <strong>SAR 12,450.00</strong>
            <div className="preview-card-line"><i /><i /><i /><i /></div>
            <small>Clear balances. Safe actions. Natural conversations.</small>
          </div>
        </div>
      </section>

      <section className="login-panel">
        <div className="login-controls">
          <button type="button" className="login-language" onClick={toggleLang}>
            <Languages size={17} /> {t("language")}
          </button>
          <ThemeToggle className="login-theme-button" />
        </div>
        <div className="login-form-wrap">
          <div className="login-mobile-brand"><Brand /></div>
          <div className="auth-tabs" role="tablist">
            <button type="button" className={mode === "login" ? "active" : ""}
              onClick={() => { setMode("login"); setError(""); }}>
              {t("signIn")}
            </button>
            <button type="button" className={mode === "register" ? "active" : ""}
              onClick={() => { setMode("register"); setError(""); }}>
              {t("createAccount")}
            </button>
          </div>
          <div className="auth-heading">
            <h2>{mode === "login" ? t("signIn") : t("createAccount")}</h2>
            <p>{mode === "login" ? t("secureAccessCopy") : t("welcomeSub")}</p>
          </div>
          <form onSubmit={submit} className="auth-form">
            {mode === "register" ? (
              <div className="field-row">
                <label className="field">
                  <span>{t("fullNameEn")}</span>
                  <input required minLength={2} dir="ltr" value={nameEn}
                    onChange={(event) => setNameEn(event.target.value)} />
                </label>
                <label className="field">
                  <span>{t("fullNameAr")}</span>
                  <input required minLength={2} dir="rtl" value={nameAr}
                    onChange={(event) => setNameAr(event.target.value)} />
                </label>
              </div>
            ) : null}
            <label className="field">
              <span>{t("username")}</span>
              <input required minLength={mode === "register" ? 3 : 1} maxLength={32}
                pattern={mode === "register" ? "[A-Za-z0-9][A-Za-z0-9._-]+" : undefined}
                autoComplete="username" dir="ltr" value={identifier}
                onChange={(event) => setIdentifier(event.target.value)} />
            </label>
            <label className="field">
              <span>{t("password")}</span>
              <div className="password-field">
                <LockKeyhole size={17} />
                <input required minLength={mode === "register" ? 8 : 1}
                  pattern={mode === "register" ? "(?=.*[A-Za-z])(?=.*[0-9]).{8,}" : undefined}
                  type={showPassword ? "text" : "password"}
                  autoComplete={mode === "register" ? "new-password" : "current-password"}
                  dir="ltr" value={password}
                  onChange={(event) => setPassword(event.target.value)} />
                <button type="button" onClick={() => setShowPassword((shown) => !shown)}
                  aria-label={showPassword ? "Hide password" : "Show password"}>
                  {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
              {mode === "register" ? <small>{t("passwordHint")}</small> : null}
            </label>
            {error ? <p className="form-error" role="alert">{error}</p> : null}
            <button type="submit" className="primary-button auth-submit" disabled={submitting}>
              {submitting ? <LoaderCircle className="spin" size={18} /> : null}
              <span>{submitting ? (mode === "register" ? t("creating") : t("signingIn")) : t("continue")}</span>
              {!submitting ? <ArrowRight size={18} className={dir === "rtl" ? "flip" : ""} /> : null}
            </button>
          </form>
          <p className="auth-switch">
            {mode === "login" ? t("noAccount") : t("haveAccount")} {" "}
            <button type="button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
              {mode === "login" ? t("createAccount") : t("signIn")}
            </button>
          </p>
        </div>
      </section>
    </main>
  );
}
