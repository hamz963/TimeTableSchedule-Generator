import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, authHeaders, getToken, saveSession, clearSession } from "@/lib/api";

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("api()", () => {
  it("sends the bearer token from the stored session", async () => {
    saveSession("token-123", "admin", "admin");
    expect(getToken()).toBe("token-123");
    expect(authHeaders()).toEqual({ Authorization: "Bearer token-123" });

    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api("/health")).resolves.toEqual({ ok: true });
    const init = fetchMock.mock.calls[0][1];
    expect(init.headers.Authorization).toBe("Bearer token-123");
  });

  it("returns null for 204 responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(api("/timetable/1", { method: "DELETE" })).resolves.toBeNull();
  });

  it("maps FastAPI validation errors to a field map", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(422, {
          detail: [
            { loc: ["body", "day_start"], msg: "must be HH:MM" },
            { loc: ["body", "courses", 0, "credit_hours"], msg: "must be >= 1" },
          ],
        }),
      ),
    );
    const err = await api("/schedule/generate-simple", { method: "POST" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.fields).toEqual({
      day_start: "must be HH:MM",
      credit_hours: "must be >= 1",
    });
  });

  it("clears the session on 401", async () => {
    saveSession("token-123", "admin", "admin");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(401, { detail: "expired" })));
    const err = await api("/schedule/1").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(401);
    expect(getToken()).toBeNull();
    clearSession();
  });

  it("surfaces a timeout as a 408", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener("abort", () => {
              const abort = new Error("aborted");
              abort.name = "AbortError";
              reject(abort);
            });
          }),
      ),
    );
    const pending = api("/slow").catch((e) => e);
    await vi.advanceTimersByTimeAsync(30001);
    const err = await pending;
    vi.useRealTimers();
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(408);
    expect(err.message).toMatch(/timed out/i);
  });
});
