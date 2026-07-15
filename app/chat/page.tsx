import type { Metadata } from "next";

import { ChatScreen } from "@/components/chat/chat-screen";

export const metadata: Metadata = {
  title: "Chat",
};

/** Voice-first chat — the primary Nafi experience. */
export default function ChatPage() {
  return <ChatScreen />;
}
