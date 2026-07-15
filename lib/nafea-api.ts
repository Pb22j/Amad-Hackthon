const configuredBaseUrl = process.env.NEXT_PUBLIC_NAFEA_API_URL?.trim();
let sessionToken: string | undefined;

/**
 * The exported Next.js app cannot use server-side rewrites, so its browser API
 * target is selected at build time. Local development defaults to the voice
 * interaction service on port 8001.
 */
export const NAFEA_API_BASE_URL = (
  configuredBaseUrl || "http://localhost:8001"
).replace(/\/$/, "");

export function setNafeaSessionToken(token: string): void {
  sessionToken = token;
}

export class NafeaApiError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message);
    this.name = "NafeaApiError";
  }
}

function endpoint(path: string): string {
  let baseUrl = NAFEA_API_BASE_URL;
  if (typeof window !== "undefined") {
    const configured = new URL(baseUrl);
    const browserHost = window.location.hostname;
    const loopbackHosts = new Set(["localhost", "127.0.0.1", "::1"]);
    if (loopbackHosts.has(configured.hostname) && loopbackHosts.has(browserHost)) {
      // Keep the API on the same loopback site as the page. Otherwise a page
      // opened at 127.0.0.1 would call localhost and Strict session cookies
      // would correctly be withheld as cross-site.
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
    let message = "Nafi could not complete that request.";
    // Backend 5xx details are intentionally not surfaced to the user.
    if (response.status < 500) {
      try {
        const payload = (await response.json()) as { detail?: string };
        if (payload.detail) message = payload.detail;
      } catch {
        // Use the generic message when the response is not JSON.
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
