import type * as React from "react";

import { cn } from "@/lib/utils";

/** Rounded bento surface — soft navy fill, hairline border, layered depth. */
export function BentoCard({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-white/[0.06] bg-card p-5 sm:p-6",
        "shadow-[inset_0_1px_0_0_rgb(255_255_255/0.04),0_18px_40px_-24px_rgb(0_0_0/0.8)]",
        className
      )}
      {...props}
    />
  );
}

/** Card heading — single language (title already localized by the caller). */
export function CardTitle({
  title,
  tag,
  action,
}: {
  title: string;
  tag?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
        {title}
        {tag && (
          <span className="rounded-md bg-white/5 px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground" dir="ltr">
            {tag}
          </span>
        )}
      </h2>
      {action}
    </div>
  );
}
