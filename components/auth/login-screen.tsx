"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Lock, Mail, User } from "lucide-react";

import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { useLang } from "@/lib/i18n";
import { BrandLogo } from "@/components/nafi/brand-logo";
import { LanguageToggle } from "@/components/i18n/language-toggle";

type Mode = "signin" | "register";

/**
 * Login / registration gate. This is a front-end mock — it does NOT
 * authenticate or store any real credentials. As an Open Banking product there
 * is no anonymous entry: signing in or registering are the only ways through.
 */
export function LoginScreen() {
  const { t, dir } = useLang();
  const { signIn } = useAuth();
  const router = useRouter();
  const [mode, setMode] = React.useState<Mode>("signin");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    signIn();
    router.push("/chat");
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
          {/* Mode tabs */}
          <div className="mb-5 flex rounded-full border border-white/10 bg-white/[0.03] p-0.5 text-sm font-medium">
            {(["signin", "register"] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                aria-pressed={mode === m}
                className={cn(
                  "flex-1 rounded-full px-3 py-1.5 transition-colors",
                  mode === m ? "bg-white/10 text-foreground" : "text-muted-foreground hover:text-foreground"
                )}
              >
                {m === "signin" ? t("signIn") : t("register")}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-3">
            {mode === "register" && (
              <Field icon={User} label={t("fullName")}>
                <input
                  type="text"
                  autoComplete="name"
                  required
                  placeholder={t("fullName")}
                  className="w-full bg-transparent text-sm outline-none placeholder:text-faint"
                />
              </Field>
            )}

            <Field icon={Mail} label={t("email")}>
              <input
                type="email"
                autoComplete="email"
                required
                dir="ltr"
                placeholder={t("emailPlaceholder")}
                className="w-full bg-transparent text-sm outline-none placeholder:text-faint text-start"
              />
            </Field>

            <Field icon={Lock} label={t("password")}>
              <input
                type="password"
                autoComplete={mode === "signin" ? "current-password" : "new-password"}
                required
                dir="ltr"
                placeholder="••••••••"
                className="w-full bg-transparent text-sm outline-none placeholder:text-faint text-start"
              />
            </Field>

            <button
              type="submit"
              className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-br from-primary to-purple py-2.5 text-sm font-semibold text-white shadow-[0_10px_24px_-10px_rgba(111,141,255,0.7)] transition-transform hover:scale-[1.01] active:scale-[0.99]"
            >
              {mode === "signin" ? t("signIn") : t("register")}
              <ArrowRight className={cn("size-4", dir === "rtl" && "-scale-x-100")} aria-hidden />
            </button>
          </form>
        </div>

        <p className="mt-5 text-center text-[11px] leading-relaxed text-faint">{t("demoNote")}</p>
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
