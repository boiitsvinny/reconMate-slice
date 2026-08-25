const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "");
const API_TIMEOUT_MS = 30_000;

export const apiBaseUrl = configuredApiUrl;

export function apiUrl(path: string): string {
  if (!configuredApiUrl) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured.");
  }

  return `${configuredApiUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function apiFetch(path: string, init: RequestInit = {}, timeoutMs = API_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  let timedOut = false;
  const timeout = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const callerSignal = init.signal;
  const abortFromCaller = () => controller.abort(callerSignal?.reason);
  if (callerSignal?.aborted) abortFromCaller();
  else callerSignal?.addEventListener("abort", abortFromCaller, { once: true });

  try {
    return await fetch(apiUrl(path), { ...init, signal: controller.signal });
  } catch (error) {
    if (timedOut) throw new Error(`ReconMate API did not respond within ${Math.round(timeoutMs / 1000)} seconds. The backend may still be starting; try again.`);
    if (callerSignal?.aborted) throw error;
    throw new Error("Unable to reach the ReconMate API. The backend may be starting or temporarily unavailable.");
  } finally {
    window.clearTimeout(timeout);
    callerSignal?.removeEventListener("abort", abortFromCaller);
  }
}
