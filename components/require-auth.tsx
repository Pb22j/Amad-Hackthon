"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { LoaderCircle } from "lucide-react";
import { useAuth } from "@/lib/auth";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { ready, isAuthenticated } = useAuth();
  const router = useRouter();

  React.useEffect(() => {
    if (ready && !isAuthenticated) router.replace("/");
  }, [isAuthenticated, ready, router]);

  if (!ready || !isAuthenticated) {
    return (
      <main className="center-state" role="status" aria-live="polite">
        <LoaderCircle className="spin" />
      </main>
    );
  }
  return <>{children}</>;
}
