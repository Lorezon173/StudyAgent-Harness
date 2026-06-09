export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const TIMEOUT_MS = 120_000;   // 对话是长耗时操作（协作环多次 LLM），见 spec §3.1

async function request<T>(url: string, init: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let resp: Response;
  try {
    resp = await fetch(url, { ...init, signal: controller.signal });
  } catch (e) {
    clearTimeout(timer);
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new ApiError(0, "响应超时，教学协作环可能较慢");
    }
    throw new ApiError(0, "连接失败");
  }
  clearTimeout(timer);
  let body: unknown = null;
  try {
    body = await resp.json();
  } catch {
    body = null;
  }
  if (!resp.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `请求失败（${resp.status}）`;
    throw new ApiError(resp.status, detail);
  }
  return body as T;
}

export function apiGet<T>(url: string): Promise<T> {
  return request<T>(url, { method: "GET" });
}

export function apiPost<T>(url: string, payload: unknown): Promise<T> {
  return request<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function apiDelete<T>(url: string): Promise<T> {
  return request<T>(url, { method: "DELETE" });
}
