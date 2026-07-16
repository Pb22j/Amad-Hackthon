import type * as React from "react";

import { AuthProvider } from "@/lib/auth";
import { LanguageProvider } from "@/lib/i18n";

/**
 * App-wide providers. Wraps every route (login, chat, dashboard) so the
 * bilingual EN/AR context and `dir`, plus auth state, are available on all
 * screens.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <LanguageProvider>
      <AuthProvider>{children}</AuthProvider>
    </LanguageProvider>
  );
}
