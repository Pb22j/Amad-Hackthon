import type { Metadata } from "next";

import { RequireAuth } from "@/components/auth/require-auth";
import { ChatScreen } from "@/components/chat/chat-screen";

export const metadata: Metadata = {
  title: "Chat",
};

/** Voice-first chat — the primary Nafi experience. Signed-in users only. */
export default function ChatPage() {
  return (
    <RequireAuth>
      <ChatScreen />
    </RequireAuth>
  );
}
