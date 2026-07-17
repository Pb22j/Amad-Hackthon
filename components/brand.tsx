import { Sparkles } from "lucide-react";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="brand-lockup">
      <span className="brand-mark" aria-hidden="true">
        <span className="brand-mark-letter">N</span>
        <Sparkles size={12} strokeWidth={2.4} />
      </span>
      {!compact ? (
        <span className="brand-word">
          Nafi <small>نافع</small>
        </span>
      ) : null}
    </div>
  );
}
