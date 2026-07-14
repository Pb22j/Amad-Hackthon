"use client";

import * as React from "react";
import Link from "next/link";
import { Mic, Send, Sparkles, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { useLang } from "@/lib/i18n";
import { respondTo } from "@/lib/chatDemo";
import { BrandLogo } from "@/components/nafi/brand-logo";
import { LanguageToggle } from "@/components/i18n/language-toggle";

type Msg = { id: number; role: "nafi" | "user"; text: string };

const EQ_BARS = [0.4, 0.8, 1, 0.6, 0.85];

/**
 * Nafi chat — the voice-first conversation. Text + a simulated voice mic.
 * Replies are scripted (see lib/chatDemo). The X closes to the dashboard.
 */
export function ChatScreen() {
  const { t, lang, dir } = useLang();
  const [messages, setMessages] = React.useState<Msg[]>([]);
  const [input, setInput] = React.useState("");
  const [listening, setListening] = React.useState(false);
  const idRef = React.useRef(0);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const micTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const nextId = () => ++idRef.current;

  // Seed the greeting (and re-seed if the language changes before any chat).
  React.useEffect(() => {
    setMessages((prev) =>
      prev.length === 0 || (prev.length === 1 && prev[0].role === "nafi")
        ? [{ id: nextId(), role: "nafi", text: t("chatGreeting") }]
        : prev
    );
  }, [t]);

  // Keep the latest message in view.
  React.useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, listening]);

  React.useEffect(() => {
    return () => {
      if (micTimer.current) clearTimeout(micTimer.current);
    };
  }, []);

  function send(text: string) {
    const body = text.trim();
    if (!body) return;
    const userMsg: Msg = { id: nextId(), role: "user", text: body };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    // Scripted reply, after a short "thinking" beat.
    setTimeout(() => {
      setMessages((m) => [...m, { id: nextId(), role: "nafi", text: respondTo(body, lang) }]);
    }, 550);
  }

  const suggestions = [t("sugNetWorth"), t("sugSpend"), t("sugTransfer")];

  // Simulate a voice capture: listen briefly, then "transcribe" a suggestion.
  function toggleMic() {
    if (listening) {
      setListening(false);
      micTimer.current && clearTimeout(micTimer.current);
      return;
    }
    setListening(true);
    const phrase = suggestions[idRef.current % suggestions.length];
    micTimer.current = setTimeout(() => {
      setListening(false);
      send(phrase);
    }, 1500);
  }

  return (
    <div className="mx-auto flex h-dvh w-full max-w-2xl flex-col">
      {/* Header */}
      <header className="flex items-center justify-between gap-3 border-b border-white/[0.06] px-4 py-3 sm:px-5">
        <div className="flex items-center gap-3">
          <span className="relative grid size-10 place-items-center rounded-full bg-gradient-to-br from-primary to-purple">
            <BrandLogo className="h-4 w-6 text-white" />
            <span className="absolute -bottom-0.5 -end-0.5 size-3 rounded-full border-2 border-background bg-positive" />
          </span>
          <div className="leading-tight">
            <p className="text-sm font-semibold">{lang === "ar" ? "نافع" : "Nafi"}</p>
            <p className="text-[11px] text-positive">{t("online")}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <LanguageToggle />
          <Link
            href="/dashboard"
            aria-label={t("skipToDashboard")}
            title={t("skipToDashboard")}
            className="grid size-9 place-items-center rounded-full border border-white/10 bg-white/[0.03] text-muted-foreground transition-colors hover:text-foreground"
          >
            <X className="size-4" aria-hidden />
          </Link>
        </div>
      </header>

      {/* Unlock banner */}
      <div className="flex items-center gap-2.5 border-b border-white/[0.06] bg-primary/[0.06] px-4 py-2.5 sm:px-5">
        <Sparkles className="size-4 shrink-0 text-primary" aria-hidden />
        <p className="min-w-0 flex-1 truncate text-[12px] text-muted-foreground">
          <span className="font-medium text-foreground">{t("unlockTitle")}</span> — {t("unlockDesc")}
        </p>
        <Link
          href="/"
          className="shrink-0 rounded-full bg-primary px-3 py-1 text-[11px] font-semibold text-primary-foreground transition-opacity hover:opacity-90"
        >
          {t("register")}
        </Link>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-5 sm:px-5">
        {messages.map((m) => (
          <div key={m.id} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
            <div
              className={cn(
                "max-w-[82%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed",
                m.role === "user"
                  ? "bg-gradient-to-br from-primary to-purple text-white"
                  : "border border-white/[0.06] bg-card-2 text-foreground"
              )}
            >
              {m.text}
            </div>
          </div>
        ))}

        {listening && (
          <div className="flex justify-end">
            <div className="flex items-center gap-3 rounded-2xl border border-primary/30 bg-primary/10 px-4 py-3">
              <span className="flex h-5 items-end gap-[3px]" aria-hidden>
                {EQ_BARS.map((h, i) => (
                  <span
                    key={i}
                    className="w-[3px] origin-bottom animate-eq rounded-full bg-primary"
                    style={{ height: `${h * 100}%`, animationDelay: `${i * 90}ms` }}
                  />
                ))}
              </span>
              <span className="text-[12px] font-medium text-primary">{t("listening")}</span>
            </div>
          </div>
        )}
      </div>

      {/* Suggestions (only before the user has spoken) */}
      {messages.filter((m) => m.role === "user").length === 0 && (
        <div className="flex flex-wrap gap-2 px-4 pb-2 sm:px-5">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => send(s)}
              className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-[12px] text-muted-foreground transition-colors hover:text-foreground"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="flex items-center gap-2 border-t border-white/[0.06] px-4 py-3 sm:px-5"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("chatPlaceholder")}
          className="min-w-0 flex-1 rounded-full border border-white/[0.06] bg-card-2 px-4 py-2.5 text-sm outline-none placeholder:text-faint focus:border-primary/50"
        />
        <button
          type="button"
          onClick={toggleMic}
          aria-pressed={listening}
          aria-label={t("askNafi")}
          className={cn(
            "grid size-11 shrink-0 place-items-center rounded-full transition-colors",
            listening
              ? "bg-primary text-white"
              : "border border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground"
          )}
        >
          <Mic className="size-4" aria-hidden />
        </button>
        <button
          type="submit"
          disabled={!input.trim()}
          aria-label={t("send")}
          className="grid size-11 shrink-0 place-items-center rounded-full bg-gradient-to-br from-primary to-purple text-white transition-opacity disabled:opacity-40"
        >
          <Send className={cn("size-4", dir === "rtl" && "-scale-x-100")} aria-hidden />
        </button>
      </form>
    </div>
  );
}
