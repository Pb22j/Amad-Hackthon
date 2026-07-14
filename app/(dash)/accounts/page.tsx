import type { Metadata } from "next";
import { Landmark } from "lucide-react";

import { PlaceholderPage } from "@/components/placeholder-page";

export const metadata: Metadata = {
  title: "My Accounts",
};

export default function AccountsPage() {
  return (
    <PlaceholderPage
      icon={Landmark}
      title="My Accounts"
      description="Link and manage your institutions via Open Banking. Balances refresh automatically and stay read-only."
    />
  );
}
