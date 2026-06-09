import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiGet, apiPost, ApiError } from "./client";

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("apiPost", () => {
  it("posts JSON and returns parsed body", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ reply: "hi", session_id: "s1" }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await apiPost("/api/chat", { message: "x", session_id: "s1", user_id: 1 });
    expect(result).toEqual({ reply: "hi", session_id: "s1" });
    const [url, opts] = mockFetch.mock.calls[0];
    expect(url).toBe("/api/chat");
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toEqual({ message: "x", session_id: "s1", user_id: 1 });
  });

  it("throws ApiError with status on non-ok response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false, status: 401,
      json: async () => ({ detail: "用户名或密码错误" }),
    }));
    await expect(apiPost("/api/auth/login", {})).rejects.toMatchObject({
      status: 401, message: "用户名或密码错误",
    });
  });
});

describe("apiGet", () => {
  it("returns parsed body on success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, status: 200, json: async () => [{ id: 1, name: "k", description: "" }],
    }));
    const result = await apiGet("/api/knowledge");
    expect(result).toEqual([{ id: 1, name: "k", description: "" }]);
  });

  it("throws ApiError on 500", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false, status: 500, json: async () => ({ detail: "server error" }),
    }));
    await expect(apiGet("/api/profile/1")).rejects.toBeInstanceOf(ApiError);
  });
});
