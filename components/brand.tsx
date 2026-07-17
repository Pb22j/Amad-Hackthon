import Image from "next/image";

import nafiWordmark from "@/assets/nafi-logo.jpg";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand-lockup ${compact ? "compact" : ""}`}>
      {compact ? (
        <span className="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 40 28" fill="none">
            <path d="M2 17h6l3-8 3 13 3-16 3 10h3.5" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M24 16 34 6m0 0h-5.5M34 6v5.5" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      ) : (
        <span className="brand-image-frame">
          <Image
            src={nafiWordmark}
            alt="Nafi - نافع"
            className="brand-image"
            priority
            unoptimized
            sizes="122px"
          />
        </span>
      )}
    </div>
  );
}
