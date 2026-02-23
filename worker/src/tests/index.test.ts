/**
 * Layer 1 Worker 测试 - 路由/鉴权/过滤
 * 使用 Mock D1 进行单元测试
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import worker, { Env } from "../index";

// Mock D1Database
function createMockD1(): D1Database {
  const mockResults = { results: [] };
  return {
    prepare: vi.fn().mockReturnValue({
      bind: vi.fn().mockReturnThis(),
      all: vi.fn().mockResolvedValue(mockResults),
      run: vi.fn().mockResolvedValue({ success: true }),
      first: vi.fn().mockResolvedValue(null),
    }),
    batch: vi.fn().mockResolvedValue([]),
    exec: vi.fn().mockResolvedValue({ count: 0, duration: 0 }),
    dump: vi.fn().mockResolvedValue(new ArrayBuffer(0)),
  } as unknown as D1Database;
}

function createMockEnv(token: string = "test-token-local"): Env {
  return {
    DB: createMockD1(),
    WORKER_WRITE_TOKEN: token,
    ENVIRONMENT: "test",
  };
}

describe("Worker API Routes", () => {
  let env: Env;

  beforeEach(() => {
    env = createMockEnv();
  });

  describe("GET /api/screening/latest", () => {
    it("returns 200 with empty data", async () => {
      const request = new Request("http://localhost/api/screening/latest");
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(200);

      const data = (await response.json()) as { data: unknown[] };
      expect(data).toHaveProperty("data");
      expect(Array.isArray(data.data)).toBe(true);
    });

    it("accepts combination query parameter", async () => {
      const request = new Request("http://localhost/api/screening/latest?combination=watch");
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(200);

      const data = await response.json();
      expect(data).toHaveProperty("data");
    });
  });

  describe("GET /api/screening/history", () => {
    it("returns 200 with run logs", async () => {
      const request = new Request("http://localhost/api/screening/history");
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(200);

      const data = (await response.json()) as { data: unknown[] };
      expect(data).toHaveProperty("data");
      expect(Array.isArray(data.data)).toBe(true);
    });
  });

  describe("GET /api/stocks/:code", () => {
    it("returns 200 for valid stock code", async () => {
      const request = new Request("http://localhost/api/stocks/sh.600001");
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(200);

      const data = await response.json();
      expect(data).toHaveProperty("data");
    });

    it("returns 400 for missing stock code", async () => {
      const request = new Request("http://localhost/api/stocks/");
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(400);
    });
  });

  describe("POST /api/ingest", () => {
    it("returns 403 without authorization", async () => {
      const request = new Request("http://localhost/api/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ results: [] }),
      });
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(403);
    });

    it("returns 403 with wrong token", async () => {
      const request = new Request("http://localhost/api/ingest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer wrong-token",
        },
        body: JSON.stringify({ results: [] }),
      });
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(403);
    });

    it("returns 200 with valid token and payload", async () => {
      const request = new Request("http://localhost/api/ingest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer test-token-local",
        },
        body: JSON.stringify({
          run_date: "2026-02-23",
          results: [
            {
              code: "sh.600001",
              combination: "watch",
              factor_ma60_monotonic: 1.5,
            },
          ],
          run_log: {
            run_date: "2026-02-23",
            total_stocks: 100,
            passed_stocks: 1,
            duration_seconds: 10,
            status: "success",
          },
        }),
      });
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(200);

      const data = (await response.json()) as { success: boolean; inserted: number };
      expect(data.success).toBe(true);
      expect(data.inserted).toBe(1);
    });
  });

  describe("Unknown routes", () => {
    it("returns 404 for unknown GET", async () => {
      const request = new Request("http://localhost/api/unknown");
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(404);
    });

    it("returns 404 for unknown POST", async () => {
      const request = new Request("http://localhost/api/unknown", { method: "POST" });
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(404);
    });
  });

  describe("CORS", () => {
    it("handles OPTIONS preflight", async () => {
      const request = new Request("http://localhost/api/screening/latest", { method: "OPTIONS" });
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(204);
      expect(response.headers.get("Access-Control-Allow-Origin")).toBe("*");
    });

    it("includes CORS headers in response", async () => {
      const request = new Request("http://localhost/api/screening/latest");
      const response = await worker.fetch(request, env);
      expect(response.headers.get("Access-Control-Allow-Origin")).toBe("*");
    });
  });
});

