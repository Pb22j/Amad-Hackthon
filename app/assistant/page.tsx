"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { AssistantScreen } from "@/components/assistant-screen";

export default function AssistantPage() {
  return <AppShell><Suspense><AssistantRoute /></Suspense></AppShell>;
}

function AssistantRoute() {
  const params = useSearchParams();
  return <AssistantScreen initialPrompt={params.get("q") ?? ""} />;
}
