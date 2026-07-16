"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2, Lock, UserRound } from "lucide-react";

import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { useLang } from "@/lib/i18n";
import { NafeaApiError } from "@/lib/nafea-api";
import { BrandLogo } from "@/components/nafi/brand-logo";
import { LanguageToggle } from "@/components/i18n/language-toggle";

export function LoginScreen() {
  const { t, dir, lang } = useLang();
  const { isAuthenticated, ready, signIn, signUp } = useAuth();
  const router = useRouter();
  const [identifier, setIdentifier] = React.useState("");
  const [mode, setMode] = React.useState<"login" | "register">("login");
  const [fullNameAr, setFullNameAr] = React.useState("");
  const [fullNameEn, setFullNameEn] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState("");

  React.useEffect(() => {
    if (ready && isAuthenticated) router.replace("/chat");
  }, [isAuthenticated, ready, router]);

  if (!ready || isAuthenticated) {
    return (
      <div className="grid min-h-dvh place-items-center" role="status">
        <Loader2 className="size-5 animate-spin text-primary" aria-hidden />
      </div>
    );
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setErrorMessage("");
    try {
      if (mode === "register") {
        await signUp({
          username: identifier,
          full_name_ar: fullNameAr,
          full_name_en: fullNameEn,
          password,
          language: lang,
        });
      } else {
        await signIn(identifier, password, lang);
      }
      router.push("/chat");
    } catch (error) {
      setErrorMessage(
        error instanceof NafeaApiError && error.status === 401
          ? t("invalidCredentials")
          : error instanceof NafeaApiError && error.status === 409
            ? t("usernameTaken")
            : t("sessionError")
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-h-dvh flex-col items-center justify-center px-5 py-10">
      <div className="absolute top-5 end-5"><LanguageToggle /></div>
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center text-center">
          <span className="grid size-14 place-items-center rounded-2xl bg-gradient-to-br from-primary to-purple shadow-[0_12px_30px_-10px_rgba(111,141,255,0.7)]">
            <BrandLogo className="h-6 w-9 text-white" />
          </span>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight">{t("welcome")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("welcomeSub")}</p>
        </div>

        <div className="mt-7 rounded-2xl border border-white/[0.06] bg-card p-5 shadow-[inset_0_1px_0_0_rgb(255_255_255/0.04),0_18px_40px_-24px_rgb(0_0_0/0.8)] sm:p-6">
          <form onSubmit={submit} className="space-y-3">
            {mode === "register" ? (
              <>
                <Field icon={UserRound} label={`${t("fullName")} (العربية)`}>
                  <input type="text" required dir="rtl" minLength={2} value={fullNameAr}
                    onChange={(event) => setFullNameAr(event.target.value)} placeholder={`${t("fullName")} (العربية)`}
                    className="w-full bg-transparent text-sm outline-none placeholder:text-faint text-start" />
                </Field>
                <Field icon={UserRound} label={`${t("fullName")} (English)`}>
                  <input type="text" required dir="ltr" minLength={2} value={fullNameEn}
                    onChange={(event) => setFullNameEn(event.target.value)} placeholder={`${t("fullName")} (English)`}
                    className="w-full bg-transparent text-sm outline-none placeholder:text-faint text-start" />
                </Field>
              </>
            ) : null}
            <Field icon={UserRound} label={t("username")}>
              <input type="text" autoComplete="username" required dir="ltr" value={identifier}
                onChange={(event) => setIdentifier(event.target.value)} placeholder={t("username")}
                className="w-full bg-transparent text-sm outline-none placeholder:text-faint text-start" />
            </Field>
            <Field icon={Lock} label={t("password")}>
              <input type="password" autoComplete={mode === "register" ? "new-password" : "current-password"}
                required minLength={mode === "register" ? 8 : 1} dir="ltr" value={password}
                onChange={(event) => setPassword(event.target.value)} placeholder="••••••••"
                className="w-full bg-transparent text-sm outline-none placeholder:text-faint text-start" />
            </Field>
            <button type="submit" disabled={submitting}
              className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-br from-primary to-purple py-2.5 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-70">
              {submitting ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
              {submitting ? (mode === "register" ? t("creatingAccount") : t("connecting")) : (mode === "register" ? t("register") : t("signIn"))}
              {!submitting ? <ArrowRight className={cn("size-4", dir === "rtl" && "-scale-x-100")} aria-hidden /> : null}
            </button>
            {errorMessage ? <p role="alert" className="text-center text-xs text-negative">{errorMessage}</p> : null}
          </form>
          <div className="mt-4 border-t border-white/[0.06] pt-4 text-center text-xs text-muted-foreground">
            {mode === "register" ? t("haveAccount") : t("noAccount")} {" "}
            <button type="button" className="font-semibold text-primary hover:underline"
              onClick={() => { setMode(mode === "login" ? "register" : "login"); setErrorMessage(""); }}>
              {mode === "register" ? t("signIn") : t("register")}
            </button>
          </div>
        </div>
        <p className="mt-5 text-center text-[11px] leading-relaxed text-faint">{t("bankCredentials")}</p>
      </div>
    </div>
  );
}

function Field({ icon: Icon, label, children }: {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex items-center gap-2.5 rounded-xl border border-white/[0.06] bg-card-2 px-3.5 py-2.5 focus-within:border-primary/50">
      <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      <span className="sr-only">{label}</span>
      {children}
    </label>
  );
}
