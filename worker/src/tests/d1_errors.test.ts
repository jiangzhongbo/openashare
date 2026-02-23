/**
 * Layer 2 Worker 测试 - D1 错误处理
 * 测试数据库失败、非法 payload 等异常情况
 */
import { describe, it, expect, vi } from "vitest";
import worker, { Env } from "../index";

// 创建会抛出错误的 Mock D1
function createFailingD1(): D1Database {
  return {
    prepare: vi.fn().mockReturnValue({
      bind: vi.fn().mockReturnThis(),
      all: vi.fn().mockRejectedValue(new Error("D1 database error")),
      run: vi.fn().mockRejectedValue(new Error("D1 write error")),
      first: vi.fn().mockRejectedValue(new Error("D1 read error")),
    }),
    batch: vi.fn().mockRejectedValue(new Error("D1 batch error")),
    exec: vi.fn().mockRejectedValue(new Error("D1 exec error")),
    dump: vi.fn().mockRejectedValue(new Error("D1 dump error")),
  } as unknown as D1Database;
}

function createFailingEnv(): Env {
  return {
    DB: createFailingD1(),
    WORKER_WRITE_TOKEN: "test-token-local",
    ENVIRONMENT: "test",
  };
}

// 正常的 Mock D1
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

function createMockEnv(): Env {
  return {
    DB: createMockD1(),
    WORKER_WRITE_TOKEN: "test-token-local",
    ENVIRONMENT: "test",
  };
}

describe("D1 Error Handling", () => {
  describe("GET endpoints with D1 failure", () => {
    it("returns 500 when D1 fails on /api/screening/latest", async () => {
      const env = createFailingEnv();
      const request = new Request("http://localhost/api/screening/latest");
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(500);

      const data = (await response.json()) as { error: string };
      expect(data.error).toBe("Internal server error");
    });

    it("returns 500 when D1 fails on /api/screening/history", async () => {
      const env = createFailingEnv();
      const request = new Request("http://localhost/api/screening/history");
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(500);
    });

    it("returns 500 when D1 fails on /api/stocks/:code", async () => {
      const env = createFailingEnv();
      const request = new Request("http://localhost/api/stocks/sh.600001");
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(500);
    });
  });

  describe("POST /api/ingest with D1 failure", () => {
    it("returns 500 when D1 write fails", async () => {
      const env = createFailingEnv();
      const request = new Request("http://localhost/api/ingest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer test-token-local",
        },
        body: JSON.stringify({
          run_date: "2026-02-23",
          results: [{ code: "sh.600001", combination: "watch" }],
        }),
      });
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(500);
    });
  });

  describe("Invalid payload handling", () => {
    it("handles empty results array gracefully", async () => {
      const env = createMockEnv();
      const request = new Request("http://localhost/api/ingest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer test-token-local",
        },
        body: JSON.stringify({
          run_date: "2026-02-23",
          results: [],
        }),
      });
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(200);

      const data = (await response.json()) as { inserted: number };
      expect(data.inserted).toBe(0);
    });

    it("handles missing results field gracefully", async () => {
      const env = createMockEnv();
      const request = new Request("http://localhost/api/ingest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer test-token-local",
        },
        body: JSON.stringify({
          run_date: "2026-02-23",
        }),
      });
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(200);

      const data = (await response.json()) as { inserted: number };
      expect(data.inserted).toBe(0);
    });

    it("handles only run_log without results", async () => {
      const env = createMockEnv();
      const request = new Request("http://localhost/api/ingest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer test-token-local",
        },
        body: JSON.stringify({
          run_log: {
            run_date: "2026-02-23",
            total_stocks: 100,
            passed_stocks: 0,
            duration_seconds: 5,
            status: "success",
          },
        }),
      });
      const response = await worker.fetch(request, env);
      expect(response.status).toBe(200);
    });
  });
});

