import type * as React from "react";

import { TopHeader } from "@/components/nafi/top-header";
import { VoiceFAB } from "@/components/nafi/voice-fab";

/**
 * Dashboard chrome — a centred column with the brand header on top and the
 * bento grid below. The Nafi Voice affordance is a persistent floating action
 * button (VoiceFAB) that opens the chat. Shared by every /dashboard-area route.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-dvh">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:start-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-foreground"
      >
        Skip to main content
      </a>

      <div className="mx-auto flex min-h-dvh w-full max-w-[1180px] flex-col gap-5 px-4 py-5 sm:px-6 sm:py-7">
        <TopHeader />
        <main id="main-content" className="flex-1 pb-6">
          {children}
        </main>
      </div>

      <VoiceFAB />
    </div>
  );
}
