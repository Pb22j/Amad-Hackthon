"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth";
import { useLang } from "@/lib/i18n";

/**
 * Gate for authenticated-only screens. Children are never mounted unless the
 * visitor is signed in — unauthenticated visitors are bounced to the login
 * screen. Open Banking surfaces must not render for anonymous users.
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, ready } = useAuth();
  const { t } = useLang();
  const router = useRouter();

  React.useEffect(() => {
    if (ready && !isAuthenticated) router.replace("/");
  }, [ready, isAuthenticated, router]);

  if (!ready || !isAuthenticated) {
    return (
      <div className="grid min-h-dvh place-items-center px-5" role="status" aria-live="polite">
        <p className="text-sm text-muted-foreground">
          {ready ? t("redirectingSignIn") : t("checkingAccess")}
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
