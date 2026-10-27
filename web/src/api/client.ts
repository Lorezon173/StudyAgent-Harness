import { AuthTicket, workspaceStore } from "../store/workspace";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string, public code: string | null = null, public detail: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function extractApiError(status: number, body: unknown): ApiError {
  const object = body && typeof body === "object" ? body as Record<string, unknown> : {};
  const detail = object.detail ?? body;
  const source = detail && typeof detail === "object" && !Array.isArray(detail) ? detail as Record<string, unknown> : object;
  const code = typeof source.code === "string" ? source.code : typeof source.error_code === "string" ? source.error_code : null;
  let message = typeof detail === "string" ? detail : typeof source.message === "string" ? source.message : code ?? `请求失败（${status}）`;
  if (Array.isArray(detail)) message = detail.map(item => {
    if (!item || typeof item !== "object") return "参数无效";
    const value = item as { loc?: unknown; msg?: unknown };
    return `${Array.isArray(value.loc) ? value.loc.join(".") + ": " : ""}${typeof value.msg === "string" ? value.msg : "参数无效"}`;
  }).join("；");
  if (/Traceback\s*\(most recent call last\)/i.test(message)) message = `请求失败（${status}）`;
  return new ApiError(status, message, code, detail);
}
const invalidationListeners = new Set<(ticket: AuthTicket) => void>();
export function registerAuthInvalidation(listener: (ticket: AuthTicket) => void) {
  invalidationListeners.add(listener);
  return () => { invalidationListeners.delete(listener); };
}

const TIMEOUT_MS = 120_000;   // 对话是长耗时操作（协作环多次 LLM），见 spec §3.1

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem("studyagent_token");
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

async function request<T>(url: string, init: RequestInit): Promise<T> {
  const ticket = workspaceStore.captureTicket();
  const storedToken = localStorage.getItem("studyagent_token");
  const storedId = localStorage.getItem("studyagent_user_id");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let resp: Response;
  try {
    resp = await fetch(url, {
      ...init,
      headers: { ...getAuthHeaders(), ...init.headers },
      signal: controller.signal,
    });
  } catch (e) {
    clearTimeout(timer);
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new ApiError(0, "响应超时，教学协作环可能较慢");
    }
    throw new ApiError(0, "连接失败");
  }
  clearTimeout(timer);

  // 凭证端点的 401 是本次登录失败，不使当前 Login.submit 的票据失效。
  const credentialRequest = url === "/api/auth/login" || url === "/api/auth/register";
  if (resp.status === 401 && !credentialRequest && workspaceStore.isCurrent(ticket) && storedToken === localStorage.getItem("studyagent_token") && storedId === localStorage.getItem("studyagent_user_id")) {
    if (invalidationListeners.size) invalidationListeners.forEach(listener => listener(ticket));
    else {
      workspaceStore.clearAccount();
      ["studyagent_token", "studyagent_user_id", "studyagent_username"].forEach(key => localStorage.removeItem(key));
    }
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
  }

  if (resp.status === 204 && resp.ok) return undefined as T;
  let body: unknown = null;
  try {
    body = await resp.json();
  } catch {
    if (resp.ok) throw new ApiError(resp.status, "服务器返回了无法读取的数据", "invalid_json");
    body = null;
  }
  if (!resp.ok) {
    throw extractApiError(resp.status, body);
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
export function apiPatch<T>(url: string, payload: unknown): Promise<T> {
  return request<T>(url, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}
export function apiPostForm<T>(url: string, form: FormData): Promise<T> {
  return request<T>(url, { method: "POST", body: form });
}
