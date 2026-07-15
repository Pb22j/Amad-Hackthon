import { cn } from "@/lib/utils";

/** Nafi wave-and-arrow mark. Uses currentColor unless `gradient` is set. */
export function BrandLogo({
  className,
  gradient = false,
}: {
  className?: string;
  gradient?: boolean;
}) {
  const stroke = gradient ? "url(#nafiGrad)" : "currentColor";
  return (
    <svg
      viewBox="0 0 40 28"
      fill="none"
      className={cn("h-6 w-8", className)}
      aria-hidden
    >
      {gradient && (
        <defs>
          <linearGradient id="nafiGrad" x1="0" y1="28" x2="40" y2="0">
            <stop offset="0%" stopColor="#6f8dff" />
            <stop offset="100%" stopColor="#a78bfa" />
          </linearGradient>
        </defs>
      )}
      <path
        d="M2 17h6l3-8 3 13 3-16 3 10h3.5"
        stroke={stroke}
        strokeWidth="2.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M24 16 L34 6 M34 6 L28.5 6 M34 6 L34 11.5"
        stroke={stroke}
        strokeWidth="2.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
