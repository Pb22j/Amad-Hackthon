import type { Metadata } from "next";
import { Sparkles } from "lucide-react";

import { PlaceholderPage } from "@/components/placeholder-page";

export const metadata: Metadata = {
  title: "AI Advisor",
};

export default function AdvisorPage() {
  return (
    <PlaceholderPage
      icon={Sparkles}
      title="AI Advisor"
      description="Ask Nafi anything about your money — spending patterns, portfolio performance, or what to do next. Tap the mic to start."
    />
  );
}
