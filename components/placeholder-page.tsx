import type { LucideIcon } from "lucide-react";

export function PlaceholderPage({
  title,
  description,
  icon: Icon,
}: {
  title: string;
  description: string;
  icon: LucideIcon;
}) {
  return (
    <section
      aria-labelledby="placeholder-heading"
      className="flex min-h-[60vh] flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-card/40 p-10 text-center"
    >
      <span className="grid size-14 place-items-center rounded-2xl bg-primary/10 text-primary ring-1 ring-primary/25">
        <Icon className="size-7" aria-hidden />
      </span>
      <h1 id="placeholder-heading" className="mt-5 text-xl font-semibold tracking-tight">
        {title}
      </h1>
      <p className="mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground">
        {description}
      </p>
    </section>
  );
}
