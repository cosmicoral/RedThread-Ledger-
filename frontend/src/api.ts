/** Same-origin API prefix. Production builds must not hard-code a local host. */
export const API_BASE = "/api";

export function apiUrl(path: string): string {
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${suffix}`;
}
