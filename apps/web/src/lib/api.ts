const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "");

export const apiBaseUrl = configuredApiUrl;

export function apiUrl(path: string): string {
  if (!configuredApiUrl) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured.");
  }

  return `${configuredApiUrl}${path.startsWith("/") ? path : `/${path}`}`;
}
