import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Frosted bento surface — the shared material for every card on the dashboard.
 *
 * Translucent rather than filled: `.glass` blurs and saturates the ambient
 * colour fields painted on <body>, so each card picks up the light behind it.
 * The `before:` layer is a top-edge sheen (light catching a bevel); the inset
 * ring keeps the hairline crisp against the blur.
 */
export function BentoCard({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "group/card relative isolate overflow-hidden rounded-[1.375rem]",
        "glass border border-white/[0.075]",
        "p-5 sm:p-6",
        "shadow-[inset_0_1px_0_0_rgb(255_255_255/0.07),0_28px_70px_-30px_rgb(0_0_0/0.95)]",
        // Top-edge sheen — a soft highlight along the first few pixels.
        "before:pointer-events-none before:absolute before:inset-x-0 before:top-0 before:h-px",
        "before:bg-gradient-to-r before:from-transparent before:via-white/25 before:to-transparent",
        "transition-[border-color,box-shadow,transform] duration-500 ease-out",
        "hover:border-white/[0.11]",
        "hover:shadow-[inset_0_1px_0_0_rgb(255_255_255/0.09),0_34px_80px_-28px_rgb(0_0_0/0.98)]",
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
    <div className="mb-5 flex items-start justify-between gap-3">
      <h2 className="flex items-center gap-2 text-[0.9375rem] font-semibold tracking-[-0.01em] text-foreground/90">
        {title}
        {tag && (
          <span
            className="rounded-md bg-white/[0.06] px-1.5 py-0.5 font-mono text-[10px] tracking-tight text-faint"
            dir="ltr"
          >
            {tag}
          </span>
        )}
      </h2>
      {action}
    </div>
  );
}
