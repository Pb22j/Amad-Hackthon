import { cn } from "@/lib/utils";
import type { Bank } from "@/lib/nafiData";

/**
 * Renders a bank's official full-colour logo from `bank.logo` on a neutral tile.
 * Drop the real asset into /public/logos/ (see README) — no code change needed.
 */
export function BankLogo({
  bank,
  size = 40,
  className,
}: {
  bank: Bank;
  size?: number;
  className?: string;
}) {
  return (
    <span
      className={cn("grid shrink-0 place-items-center overflow-hidden rounded-xl ring-1 ring-black/5", className)}
      style={{ width: size, height: size, backgroundColor: bank.tile }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={bank.logo}
        alt={`${bank.name} logo`}
        className="h-full w-full object-contain p-1.5"
        loading="lazy"
        decoding="async"
      />
    </span>
  );
}
