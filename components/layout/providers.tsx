import type * as React from "react";

import { LanguageProvider } from "@/lib/i18n";

/**
 * App-wide providers. Wraps every route (login, chat, dashboard) so the
 * bilingual EN/AR context and `dir` are available on all screens.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  return <LanguageProvider>{children}</LanguageProvider>;
}
