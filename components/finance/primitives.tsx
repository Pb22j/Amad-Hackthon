import type * as React from "react";

import { cn } from "@/lib/utils";

/** Nafi brand mark — a waveform that rises into an up-right arrow. */
export function NafiLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 44 32" fill="none" className={className} aria-hidden>
      <defs>
        <linearGradient id="nafiStroke" x1="0" y1="32" x2="44" y2="0" gradientUnits="userSpaceOnUse">
          <stop stopColor="#8b8bf7" />
          <stop offset="1" stopColor="#c9a2f0" />
        </linearGradient>
      </defs>
      <path
        d="M2 22h6l4-13 5 19 4-11 4 6h4"
        stroke="url(#nafiStroke)"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M29 23 41 7"
        stroke="url(#nafiStroke)"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M34 7h7v7"
        stroke="url(#nafiStroke)"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Bento surface card. */
export function Card({ className, ...props }: React.ComponentProps<"section">) {
  return (
    <section
      className={cn(
        "rounded-2xl border border-border bg-surface p-5 shadow-[0_1px_0_0_rgba(255,255,255,0.04)_inset,0_20px_40px_-30px_rgba(0,0,0,0.9)]",
        className
      )}
      {...props}
    />
  );
}

/** Card heading with an optional Arabic subtitle and a [cite] tag. */
export function CardTitle({
  children,
  ar,
  cite,
  className,
}: {
  children: React.ReactNode;
  ar?: string;
  cite?: string;
  className?: string;
}) {
  return (
    <div className={cn("flex items-start justify-between gap-3", className)}>
      <div>
        <h2 className="text-[17px] font-semibold tracking-tight text-foreground">{children}</h2>
        {ar && <p className="mt-0.5 text-xs text-muted-2">{ar}</p>}
      </div>
      {cite && <Cite value={cite} />}
    </div>
  );
}

/** Small muted citation tag, e.g. [cite: 17]. */
export function Cite({ value, short = false }: { value: string; short?: boolean }) {
  return (
    <span className="shrink-0 rounded-md bg-white/5 px-1.5 py-0.5 font-mono text-[10px] leading-none text-muted-2">
      [{short ? "" : "cite: "}
      {value}]
    </span>
  );
}

/** Bank logo tile. */
export function BankBadge({
  initials,
  brand,
  size = "md",
}: {
  initials: string;
  brand: string;
  size?: "sm" | "md";
}) {
  return (
    <span
      className={cn(
        "grid shrink-0 place-items-center rounded-lg font-bold tracking-tight text-white ring-1 ring-inset ring-white/10",
        size === "md" ? "size-9 text-[11px]" : "size-8 text-[10px]"
      )}
      style={{ backgroundColor: `${brand}2e`, color: brand }}
    >
      {initials}
    </span>
  );
}
