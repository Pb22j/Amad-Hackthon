import type { Metadata } from "next";
import { Settings } from "lucide-react";

import { PlaceholderPage } from "@/components/placeholder-page";

export const metadata: Metadata = {
  title: "Settings",
};

export default function SettingsPage() {
  return (
    <PlaceholderPage
      icon={Settings}
      title="Settings"
      description="Profile, security, connected institutions, and voice preferences for your Nafi assistant."
    />
  );
}
