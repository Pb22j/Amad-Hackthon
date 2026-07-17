"use client";

import * as React from "react";
import {
  authenticateNafea,
  getNafeaSession,
  logoutNafea,
  registerNafea,
  type NafeaLanguage,
  type NafeaRegistration,
} from "@/lib/nafea-api";

type AuthContextValue = {
  isAuthenticated: boolean;
  ready: boolean;
  signIn: (identifier: string, password: string, language: NafeaLanguage) => Promise<void>;
  signUp: (registration: NafeaRegistration) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = React.useState(false);
  const [ready, setReady] = React.useState(false);

  React.useEffect(() => {
    let disposed = false;
    const unauthorized = () => setIsAuthenticated(false);
    window.addEventListener("nafea:unauthorized", unauthorized);
    void getNafeaSession()
      .then(() => !disposed && setIsAuthenticated(true))
      .catch(() => !disposed && setIsAuthenticated(false))
      .finally(() => !disposed && setReady(true));
    return () => {
      disposed = true;
      window.removeEventListener("nafea:unauthorized", unauthorized);
    };
  }, []);

  const value = React.useMemo<AuthContextValue>(
    () => ({
      isAuthenticated,
      ready,
      signIn: async (identifier, password, language) => {
        await authenticateNafea(identifier, password, language);
        setIsAuthenticated(true);
      },
      signUp: async (registration) => {
        await registerNafea(registration);
        setIsAuthenticated(true);
      },
      signOut: async () => {
        await logoutNafea();
        setIsAuthenticated(false);
      },
    }),
    [isAuthenticated, ready]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = React.useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
