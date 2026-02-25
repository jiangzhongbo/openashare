/**
 * A股选股工具 Cloudflare Worker
 * 统一数据网关：POST 写入（鉴权）+ GET 读取（公开）
 */

export interface Env {
  DB: D1Database;
  WORKER_WRITE_TOKEN?: string;
  ENVIRONMENT?: string;
}

// CORS 响应头
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

// JSON 响应辅助函数
function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...corsHeaders,
    },
  });
}

// 错误响应辅助函数
function errorResponse(message: string, status = 400): Response {
  return jsonResponse({ error: message }, status);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // 处理 CORS 预检请求
    if (method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    try {
      // GET /api/combinations - 获取所有组合的元数据（从 DB 读取，fallback 到硬编码）
      if (method === 'GET' && path === '/api/combinations') {
        try {
          const dbResult = await env.DB.prepare('SELECT * FROM combinations ORDER BY id').all();
          if (dbResult.results && dbResult.results.length > 0) {
            const combinations = dbResult.results.map((row: any) => ({
              id: row.id,
              label: row.label,
              description: row.description,
              entry_rule: row.entry_rule,
              exit_rule: row.exit_rule,
              factors: JSON.parse(row.factors || '[]'),
            }));
            return jsonResponse({ combinations });
          }
        } catch {
          // combinations 表可能不存在，fallback 到硬编码
        }

        // Fallback：表为空或不存在时使用硬编码
        const combinations = [
          {
            id: 'ma60_bounce_uptrend',
            label: 'MA60支撑反弹+趋势向上',
            description: '跌破MA60后强力反弹+趋势向上+信号质量过滤',
            entry_rule: '信号日出现阴线时买入（5天入场窗口）。条件：跌破MA60后反弹涨幅≥5%、量比5d≥1.5、换手率5~12%、跌破天数≤5天、MA60近10日持续上升',
            exit_rule: '止盈：涨幅达10%卖出 | 最大持仓：15个交易日强制卖出',
            factors: ['ma60_bounce_volume', 'ma60_recent_uptrend', 'signal_quality_filter'],
          },
        ];
        return jsonResponse({ combinations });
      }

      // GET /api/screening/latest - 获取最新筛选结果
      if (method === 'GET' && path === '/api/screening/latest') {
        const combination = url.searchParams.get('combination');
        
        let query = 'SELECT * FROM screening_results WHERE run_date = (SELECT MAX(run_date) FROM screening_results)';
        const params: string[] = [];
        
        if (combination) {
          query += ' AND combination = ?';
          params.push(combination);
        }
        
        query += ' ORDER BY code ASC';
        
        const results = await env.DB.prepare(query).bind(...params).all();
        return jsonResponse({ data: results.results || [] });
      }

      // GET /api/screening/history - 历史运行日志
      if (method === 'GET' && path === '/api/screening/history') {
        const results = await env.DB.prepare(
          'SELECT * FROM run_logs ORDER BY run_date DESC LIMIT 30'
        ).all();
        return jsonResponse({ data: results.results || [] });
      }

      // GET /api/screening/by-date?date=YYYY-MM-DD&combination=xxx - 获取指定日期的筛选结果
      if (method === 'GET' && path === '/api/screening/by-date') {
        const date = url.searchParams.get('date');
        const combination = url.searchParams.get('combination');

        if (!date) {
          return errorResponse('Missing date parameter', 400);
        }

        let query = 'SELECT * FROM screening_results WHERE run_date = ?';
        const params: string[] = [date];

        if (combination) {
          query += ' AND combination = ?';
          params.push(combination);
        }

        query += ' ORDER BY code ASC';

        const results = await env.DB.prepare(query).bind(...params).all();
        return jsonResponse({ data: results.results || [] });
      }

      // GET /api/stocks/:code - 单股历史记录
      if (method === 'GET' && path.startsWith('/api/stocks/')) {
        const code = path.replace('/api/stocks/', '');
        if (!code) {
          return errorResponse('Missing stock code', 400);
        }
        
        const results = await env.DB.prepare(
          'SELECT * FROM screening_results WHERE code = ? ORDER BY run_date DESC LIMIT 100'
        ).bind(code).all();
        return jsonResponse({ data: results.results || [] });
      }

      // POST /api/ingest - 写入数据（需要鉴权）
      if (method === 'POST' && path === '/api/ingest') {
        // 验证 Authorization token
        const authHeader = request.headers.get('Authorization');
        const token = authHeader?.replace('Bearer ', '');

        if (!token || token !== env.WORKER_WRITE_TOKEN) {
          return errorResponse('Unauthorized', 403);
        }

        const body = await request.json() as {
          run_date?: string;
          results?: unknown[];
          run_log?: unknown;
          combinations?: unknown[];
        };

        const runDate = body.run_date;
        let insertedCount = 0;

        // 写入筛选结果（匹配 Python to_ingest_payload 格式）
        if (body.results && Array.isArray(body.results)) {
          // 先删除当天同组合的旧数据（去重）
          if (runDate && body.results.length > 0) {
            const combinations = new Set(body.results.map((r: any) => r.combination).filter(Boolean));
            for (const combination of combinations) {
              await env.DB.prepare(
                'DELETE FROM screening_results WHERE run_date = ? AND combination = ?'
              ).bind(runDate, combination).run();
            }
          }

          for (const result of body.results) {
            const r = result as Record<string, unknown>;
            // D1 不支持 undefined，需要转为 null
            const n = (v: unknown) => (v === undefined ? null : v);

            await env.DB.prepare(`
              INSERT INTO screening_results (
                run_date, combination, code, name, latest_price,
                ma60_change_pct, ma60_angle, ma20_change_pct, ma_distance,
                macd_days_ago, rsi, turnover_avg, n_day_return,
                passed_factors, factor_config_snapshot, created_at
              ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            `).bind(
              n(runDate || r.run_date),
              n(r.combination),
              n(r.code),
              n(r.name),
              n(r.latest_price),
              n(r.factor_ma60_bounce_volume ?? r.ma60_change_pct),
              n(r.factor_ma60_recent_uptrend ?? r.ma60_angle),
              n(r.factor_signal_quality_filter ?? r.ma20_change_pct),
              n(r.factor_ma_distance ?? r.ma_distance),
              n(r.factor_macd_golden_cross ?? r.macd_days_ago),
              n(r.factor_rsi ?? r.rsi),
              n(r.factor_turnover ?? r.turnover_avg),
              n(r.factor_n_day_return ?? r.n_day_return),
              JSON.stringify(r.passed_factors || []),
              JSON.stringify(r.factor_config_snapshot || {}),
              new Date().toISOString()
            ).run();
            insertedCount++;
          }
        }

        // 写入组合元数据
        if (body.combinations && Array.isArray(body.combinations)) {
          for (const combo of body.combinations) {
            const c = combo as Record<string, unknown>;
            const n = (v: unknown) => (v === undefined ? null : v);
            await env.DB.prepare(`
              INSERT OR REPLACE INTO combinations (id, label, description, entry_rule, exit_rule, factors, updated_at)
              VALUES (?, ?, ?, ?, ?, ?, ?)
            `).bind(
              n(c.id),
              n(c.label),
              n(c.description),
              n(c.entry_rule),
              n(c.exit_rule),
              JSON.stringify(c.factors || []),
              new Date().toISOString()
            ).run();
          }
        }

        // 写入运行日志
        if (body.run_log) {
          const log = body.run_log as Record<string, unknown>;
          const n = (v: unknown) => (v === undefined ? null : v);
          await env.DB.prepare(`
            INSERT INTO run_logs (run_date, total_stocks, passed_stocks, duration_seconds, status, error_msg, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
          `).bind(
            n(log.run_date), n(log.total_stocks), n(log.passed_stocks),
            n(log.duration_seconds), n(log.status), n(log.error_msg),
            new Date().toISOString()
          ).run();
        }

        return jsonResponse({ success: true, inserted: insertedCount });
      }

      // 404 - 未知路由
      return errorResponse('Not found', 404);

    } catch (err) {
      console.error('Worker error:', err);
      return errorResponse('Internal server error', 500);
    }
  },
};

