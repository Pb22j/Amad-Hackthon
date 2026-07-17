const configuredBaseUrl = process.env.NEXT_PUBLIC_NAFEA_API_URL?.trim();
const SESSION_TOKEN_KEY = "nafea.interaction-session-token";
let sessionToken: string | undefined = readStoredSessionToken();

export type NafeaLanguage = "en" | "ar";

export type NafeaSession = {
  session_id: string;
  session_token: string;
  language: NafeaLanguage;
  expires_at: number;
};

export type NafeaRegistration = {
  username: string;
  full_name_ar: string;
  full_name_en: string;
  password: string;
  language: NafeaLanguage;
};

let sessionBootstrap:
  | {
      language: NafeaLanguage;
      expiresAt: number;
      promise: Promise<NafeaSession>;
    }
  | undefined;

function readStoredSessionToken(): string | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    return window.sessionStorage.getItem(SESSION_TOKEN_KEY) || undefined;
  } catch {
    return undefined;
  }
}

export const NAFEA_API_BASE_URL = (
  configuredBaseUrl || "http://localhost:8001"
).replace(/\/$/, "");

export function setNafeaSessionToken(token: string): void {
  sessionToken = token;
  if (typeof window !== "undefined") {
    try {
      window.sessionStorage.setItem(SESSION_TOKEN_KEY, token);
    } catch {
      // In-memory authentication still works when browser storage is unavailable.
    }
  }
}

export function invalidateNafeaSession(): void {
  sessionBootstrap = undefined;
  sessionToken = undefined;
  if (typeof window !== "undefined") {
    try {
      window.sessionStorage.removeItem(SESSION_TOKEN_KEY);
    } catch {
      // The in-memory token has still been cleared.
    }
  }
}

export async function authenticateNafea(
  identifier: string,
  password: string,
  language: NafeaLanguage
): Promise<NafeaSession> {
  invalidateNafeaSession();
  const session = await nafeaPost<NafeaSession>("/api/auth/login", {
    identifier,
    password,
    language,
  });
  rememberSession(session);
  return session;
}

export async function registerNafea(
  registration: NafeaRegistration
): Promise<NafeaSession> {
  invalidateNafeaSession();
  const session = await nafeaPost<NafeaSession>("/api/auth/register", registration);
  rememberSession(session);
  return session;
}

export async function getNafeaSession(): Promise<NafeaSession> {
  const session = await nafeaRequest<NafeaSession>("/api/auth/session");
  rememberSession(session);
  return session;
}

export async function logoutNafea(): Promise<void> {
  try {
    await nafeaPost<void>("/api/auth/logout", {});
  } catch {
    // Local credentials must still be removed if the interaction service is unavailable.
  } finally {
    invalidateNafeaSession();
  }
}

export async function startNewNafeaChat(): Promise<NafeaSession> {
  const session = await nafeaPost<NafeaSession>("/api/new-chat", {});
  rememberSession(session);
  return session;
}

export function ensureNafeaSession(language: NafeaLanguage): Promise<NafeaSession> {
  const now = Date.now() / 1000;
  if (
    sessionBootstrap?.language === language &&
    (sessionBootstrap.expiresAt === 0 || sessionBootstrap.expiresAt > now + 30)
  ) {
    return sessionBootstrap.promise;
  }
  const record = {
    language,
    expiresAt: 0,
    promise: nafeaPost<NafeaSession>("/api/session", {
      language,
      reuse_existing: true,
    }),
  };
  sessionBootstrap = record;
  void record.promise
    .then((session) => {
      setNafeaSessionToken(session.session_token);
      record.expiresAt = session.expires_at;
    })
    .catch(() => {
      if (sessionBootstrap === record) sessionBootstrap = undefined;
    });
  return record.promise;
}

function rememberSession(session: NafeaSession) {
  setNafeaSessionToken(session.session_token);
  sessionBootstrap = {
    language: session.language,
    expiresAt: session.expires_at,
    promise: Promise.resolve(session),
  };
}

export class NafeaApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "NafeaApiError";
  }
}

function endpoint(path: string): string {
  let baseUrl = NAFEA_API_BASE_URL;
  if (typeof window !== "undefined") {
    const configured = new URL(baseUrl);
    const browserHost = window.location.hostname;
    const loopback = new Set(["localhost", "127.0.0.1", "::1"]);
    if (loopback.has(configured.hostname) && loopback.has(browserHost)) {
      configured.hostname = browserHost;
      baseUrl = configured.toString().replace(/\/$/, "");
    }
  }
  return `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

export function nafeaWebSocketUrl(path: string): string {
  const url = new URL(endpoint(path));
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  if (sessionToken) url.searchParams.set("session_token", sessionToken);
  return url.toString();
}

export async function nafeaRequest<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const response = await fetch(endpoint(path), {
    ...init,
    credentials: "include",
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(sessionToken ? { "X-Session-Token": sessionToken } : {}),
      ...init.headers,
    },
  });

  if (!response.ok) {
    if (
      response.status === 401 &&
      path !== "/api/auth/login" &&
      path !== "/api/auth/register" &&
      typeof window !== "undefined"
    ) {
      window.dispatchEvent(new Event("nafea:unauthorized"));
    }
    let message = "Nafi could not complete that request.";
    if (response.status < 500 || response.status === 504) {
      try {
        const payload = (await response.json()) as { detail?: string };
        if (payload.detail) message = payload.detail;
      } catch {
        // Keep the safe fallback message for non-JSON errors.
      }
    }
    throw new NafeaApiError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function nafeaPost<T>(path: string, body: unknown): Promise<T> {
  return nafeaRequest<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
