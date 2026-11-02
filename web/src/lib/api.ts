// Thin client for the FinAdvisor API. The frontend never computes money; it only displays what the API returns.

const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "http://localhost:8000";

let tokenGetter: () => Promise<string | null> = async () => null;
let onUnauthorized: () => void = () => {};

export function configureApi(getToken: () => Promise<string | null>, unauthorized: () => void) {
  tokenGetter = getToken;
  onUnauthorized = unauthorized;
}

/** Current access token, for the rare request that cannot go through `api` (multipart uploads). */
export function getToken(): Promise<string | null> {
  return tokenGetter();
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function headers(json = true): Promise<HeadersInit> {
  const h: Record<string, string> = {};
  if (json) h["Content-Type"] = "application/json";
  const t = await tokenGetter();
  if (t) h.Authorization = `Bearer ${t}`;
  return h;
}

async function handle<T>(r: Response): Promise<T> {
  if (r.status === 401) onUnauthorized();
  if (!r.ok) {
    let msg = `Request failed (${r.status})`;
    try {
      const body = await r.json();
      msg = typeof body.detail === "string" ? body.detail : msg;
    } catch {
      /* not json */
    }
    throw new ApiError(r.status, msg);
  }
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

export const api = {
  base: BASE,
  async get<T>(path: string): Promise<T> {
    return handle<T>(await fetch(BASE + path, { headers: await headers(false) }));
  },
  async post<T>(path: string, body?: unknown): Promise<T> {
    return handle<T>(await fetch(BASE + path, { method: "POST", headers: await headers(), body: JSON.stringify(body ?? {}) }));
  },
  async put<T>(path: string, body: unknown): Promise<T> {
    return handle<T>(await fetch(BASE + path, { method: "PUT", headers: await headers(), body: JSON.stringify(body) }));
  },
  async patch<T>(path: string, body: unknown): Promise<T> {
    return handle<T>(await fetch(BASE + path, { method: "PATCH", headers: await headers(), body: JSON.stringify(body) }));
  },
  async del(path: string): Promise<void> {
    return handle<void>(await fetch(BASE + path, { method: "DELETE", headers: await headers(false) }));
  },
  async download(path: string, filename: string): Promise<void> {
    const r = await fetch(BASE + path, { headers: await headers(false) });
    if (!r.ok) throw new ApiError(r.status, "Download failed");
    const url = URL.createObjectURL(await r.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: filename });
    a.click();
    URL.revokeObjectURL(url);
  },
  /** POST that answers with Server-Sent Events. Calls onEvent for each event until the stream ends or is aborted. */
  async stream(path: string, body: unknown, onEvent: (event: string, data: any) => void, signal?: AbortSignal) {
    const r = await fetch(BASE + path, { method: "POST", headers: await headers(), body: JSON.stringify(body ?? {}), signal });
    if (!r.ok || !r.body) return handle(r);
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i: number;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, i);
        buf = buf.slice(i + 2);
        let ev = "message";
        let data = "";
        for (const line of block.split("\n")) {
          if (line.startsWith("event: ")) ev = line.slice(7);
          else if (line.startsWith("data: ")) data += line.slice(6);
        }
        if (data) onEvent(ev, JSON.parse(data));
      }
    }
  },
};
