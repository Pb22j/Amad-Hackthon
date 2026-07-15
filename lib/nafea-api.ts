const configuredBaseUrl = process.env.NEXT_PUBLIC_NAFEA_API_URL?.trim();

/**
 * The exported Next.js app cannot use server-side rewrites, so its browser API
 * target is selected at build time. Local development defaults to the voice
 * interaction service on port 8000.
 */
export const NAFEA_API_BASE_URL = (
  configuredBaseUrl || "http://localhost:8000"
).replace(/\/$/, "");

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
  return `${NAFEA_API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export function nafeaWebSocketUrl(path: string): string {
  const url = new URL(endpoint(path));
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
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
