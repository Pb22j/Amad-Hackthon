"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, AtSign, Loader2, Lock, Mail, Phone, UserRound } from "lucide-react";

import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { useLang } from "@/lib/i18n";
import { NafeaApiError } from "@/lib/nafea-api";
import { BrandLogo } from "@/components/nafi/brand-logo";
import { LanguageToggle } from "@/components/i18n/language-toggle";

/**
 * Banking login gate. Credentials are verified by the interaction backend and
 * never stored by the frontend.
 */
export function LoginScreen() {
  const { t, dir, lang } = useLang();
  const { isAuthenticated, ready, signIn, signUp } = useAuth();
  const router = useRouter();
  const [mode, setMode] = React.useState<"login" | "register">("login");
  const [identifier, setIdentifier] = React.useState("");
  const [fullName, setFullName] = React.useState("");
  const [username, setUsername] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [phone, setPhone] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirmPassword, setConfirmPassword] = React.useState("");
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

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (
      mode === "register" &&
      (password.length < 8 || !/\p{L}/u.test(password) || !/\d/u.test(password))
    ) {
      setErrorMessage(t("passwordRequirements"));
      return;
    }
    if (mode === "register" && password !== confirmPassword) {
      setErrorMessage(t("passwordsDoNotMatch"));
      return;
    }
    setSubmitting(true);
    setErrorMessage("");
    try {
      if (mode === "register") {
        await signUp({
          full_name: fullName,
          username,
          email,
          phone_e164: phone,
          password,
          language: lang,
        });
      } else {
        await signIn(identifier, password, lang);
      }
      router.push("/chat");
    } catch (error) {
      if (mode === "login") {
        setErrorMessage(
          error instanceof NafeaApiError && error.status === 401
            ? t("invalidCredentials")
            : t("sessionError")
        );
      } else if (error instanceof NafeaApiError && error.status === 409) {
        const conflictMessages: Record<string, string> = {
          username_taken: t("usernameTaken"),
          email_taken: t("emailTaken"),
          phone_taken: t("phoneTaken"),
        };
        setErrorMessage(conflictMessages[error.message] || t("registrationError"));
      } else {
        setErrorMessage(t("registrationError"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  function switchMode() {
    setMode((current) => (current === "login" ? "register" : "login"));
    setPassword("");
    setConfirmPassword("");
    setErrorMessage("");
  }

  return (
    <div className="relative flex min-h-dvh flex-col items-center justify-center px-5 py-10">
      {/* Language toggle — pinned to the top-end corner */}
      <div className="absolute top-5 end-5">
        <LanguageToggle />
      </div>

      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="flex flex-col items-center text-center">
          <span className="grid size-14 place-items-center rounded-2xl bg-gradient-to-br from-primary to-purple shadow-[0_12px_30px_-10px_rgba(111,141,255,0.7)]">
            <BrandLogo className="h-6 w-9 text-white" />
          </span>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight">{t("welcome")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("welcomeSub")}</p>
        </div>

        {/* Card */}
        <div className="mt-7 rounded-2xl border border-white/[0.06] bg-card p-5 shadow-[inset_0_1px_0_0_rgb(255_255_255/0.04),0_18px_40px_-24px_rgb(0_0_0/0.8)] sm:p-6">
          <form onSubmit={submit} className="space-y-3">
            {mode === "register" ? (
              <>
                <Field icon={UserRound} label={t("fullName")}>
                  <input
                    type="text"
                    autoComplete="name"
                    required
                    minLength={2}
                    maxLength={200}
                    value={fullName}
                    onChange={(event) => setFullName(event.target.value)}
                    placeholder={t("fullName")}
                    className="w-full bg-transparent text-sm outline-none placeholder:text-faint text-start"
                  />
                </Field>
                <Field icon={AtSign} label={t("username")}>
                  <input
                    type="text"
                    autoComplete="username"
                    required
                    minLength={3}
                    maxLength={32}
                    pattern="[A-Za-z0-9][A-Za-z0-9._-]+"
                    dir="ltr"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    placeholder={t("username")}
                    className="w-full bg-transparent text-sm outline-none placeholder:text-faint text-start"
                  />
                </Field>
                <Field icon={Mail} label={t("email")}>
                  <input
                    type="email"
                    autoComplete="email"
                    required
                    dir="ltr"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder={t("emailPlaceholder")}
                    className="w-full bg-transparent text-sm outline-none placeholder:text-faint text-start"
                  />
                </Field>
                <Field icon={Phone} label={t("phone")}>
                  <input
                    type="tel"
                    autoComplete="tel"
                    required
                    pattern="\+[1-9][0-9]{7,14}"
                    dir="ltr"
                    value={phone}
                    onChange={(event) => setPhone(event.target.value)}
                    placeholder="+9665XXXXXXXX"
                    className="w-full bg-transparent text-sm outline-none placeholder:text-faint text-start"
                  />
                </Field>
              </>
            ) : (
              <Field icon={UserRound} label={t("usernameOrEmail")}>
                <input
                  type="text"
                  autoComplete="username"
                  required
                  dir="ltr"
                  value={identifier}
                  onChange={(event) => setIdentifier(event.target.value)}
                  placeholder={t("usernameOrEmail")}
                  className="w-full bg-transparent text-sm outline-none placeholder:text-faint text-start"
                />
              </Field>
            )}

            <Field icon={Lock} label={t("password")}>
              <input
                type="password"
                autoComplete={mode === "register" ? "new-password" : "current-password"}
                required
                minLength={mode === "register" ? 8 : 1}
                dir="ltr"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="••••••••"
                className="w-full bg-transparent text-sm outline-none placeholder:text-faint text-start"
              />
            </Field>

            {mode === "register" ? (
              <>
                <Field icon={Lock} label={t("confirmPassword")}>
                  <input
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={8}
                    dir="ltr"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    placeholder={t("confirmPassword")}
                    className="w-full bg-transparent text-sm outline-none placeholder:text-faint text-start"
                  />
                </Field>
                <p className="px-1 text-[11px] text-faint">{t("passwordRequirements")}</p>
              </>
            ) : null}

            <button
              type="submit"
              disabled={submitting}
              className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-br from-primary to-purple py-2.5 text-sm font-semibold text-white shadow-[0_10px_24px_-10px_rgba(111,141,255,0.7)] transition-transform hover:scale-[1.01] active:scale-[0.99] disabled:cursor-wait disabled:opacity-70"
            >
              {submitting ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
              {submitting
                ? mode === "register"
                  ? t("creatingAccount")
                  : t("connecting")
                : mode === "register"
                  ? t("register")
                  : t("signIn")}
              {!submitting ? (
                <ArrowRight className={cn("size-4", dir === "rtl" && "-scale-x-100")} aria-hidden />
              ) : null}
            </button>
            {errorMessage ? (
              <p role="alert" className="text-center text-xs text-negative">
                {errorMessage}
              </p>
            ) : null}
          </form>

          <div className="mt-4 border-t border-white/[0.06] pt-4 text-center text-xs text-muted-foreground">
            {mode === "register" ? t("haveAccount") : t("noAccount")} {" "}
            <button
              type="button"
              onClick={switchMode}
              disabled={submitting}
              className="font-semibold text-primary hover:underline disabled:opacity-50"
            >
              {mode === "register" ? t("signIn") : t("register")}
            </button>
          </div>
        </div>

        <p className="mt-5 text-center text-[11px] leading-relaxed text-faint">
          {mode === "register" ? t("createAccountHelp") : t("bankCredentials")}
        </p>
      </div>
    </div>
  );
}

/** A labelled input shell with a leading icon. */
function Field({
  icon: Icon,
  label,
  children,
}: {
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
