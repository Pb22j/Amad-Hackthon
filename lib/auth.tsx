"use client";

import * as React from "react";

/**
 * Front-end auth state for the demo. This is a MOCK — it does not verify or
 * store credentials. It only tracks whether the visitor has passed the login
 * gate in this browser session, so protected screens (chat) can be withheld.
 * Replace `signIn` with a real backend call when auth is wired up.
 */

const STORAGE_KEY = "nafi.auth";

/**
 * sessionStorage throws — not returns null — when storage is blocked (Safari
 * with cookies disabled, some private/sandboxed contexts). Reading it bare
 * would take the whole provider down and blank the app, so every access is
 * guarded and degrades to in-memory-only session state.
 */
function readSession(): boolean {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeSession(signedIn: boolean) {
  try {
    if (signedIn) window.sessionStorage.setItem(STORAGE_KEY, "1");
    else window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable — auth stays in React state for this page session.
  }
}

type Ctx = {
  isAuthenticated: boolean;
  /** False until the stored session has been read on the client. */
  ready: boolean;
  signIn: () => void;
  signOut: () => void;
};

const AuthContext = React.createContext<Ctx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = React.useState(false);
  const [ready, setReady] = React.useState(false);

  // The app is statically exported, so the session can only be read after
  // hydration. `ready` keeps guards from flashing before we know.
  React.useEffect(() => {
    setIsAuthenticated(readSession());
    setReady(true);
  }, []);

  const value = React.useMemo<Ctx>(
    () => ({
      isAuthenticated,
      ready,
      signIn: () => {
        writeSession(true);
        setIsAuthenticated(true);
      },
      signOut: () => {
        writeSession(false);
        setIsAuthenticated(false);
      },
    }),
    [isAuthenticated, ready]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
