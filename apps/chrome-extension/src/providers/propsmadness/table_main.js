(() => {
  'use strict';

  const VERSION = '1.3';
  const MATCHES = '/api/offer/mlb/matches';
  const RANKINGS = '/api/team-rankings/mlb/season/current/all/by-season';

  function memoryMB() {
    if (!performance.memory) return null;
    return {
      usedJSHeapMB: Math.round(performance.memory.usedJSHeapSize / 1048576),
      totalJSHeapMB: Math.round(performance.memory.totalJSHeapSize / 1048576),
      heapLimitMB: Math.round(performance.memory.jsHeapSizeLimit / 1048576)
    };
  }

  async function fetchJson(path) {
    const started = performance.now();
    const response = await fetch(path, {
      method: 'GET', credentials: 'include', cache: 'no-store', headers: { accept: 'application/json' }
    });
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    const data = await response.json();
    return { data, durationMs: Math.round(performance.now() - started), observedAt: new Date().toISOString() };
  }

  async function run() {
    const core = window.MODEL_PM_TABLE_CORE;
    if (!core || core.VERSION !== VERSION) throw new Error(`PropsMadness table provider core ${VERSION} is not loaded.`);
    if (!/(^|\.)propsmadness\.com$/i.test(location.hostname) || !/^\/mlb\/props(?:\/|$)/i.test(location.pathname)) {
      throw new Error('Open a PropsMadness MLB props table before syncing.');
    }

    const t0 = performance.now();
    const memoryBefore = memoryMB();
    const jobs = [['matches', MATCHES], ['rankings', RANKINGS], ...core.MARKET_CONFIG.map(cfg => [cfg.slug, cfg.path])];
    const settled = await Promise.all(jobs.map(async ([key, path]) => {
      try { return { key, path, ok: true, ...(await fetchJson(path)) }; }
      catch (e) { return { key, path, ok: false, error: e?.message || String(e) }; }
    }));
    const failures = settled.filter(x => !x.ok);
    if (failures.length) throw new Error(`PropsMadness table sync failed: ${failures.map(x => `${x.key} (${x.error})`).join('; ')}`);

    const byKey = Object.fromEntries(settled.map(x => [x.key, x]));
    const fullMarkets = {};
    for (const cfg of core.MARKET_CONFIG) {
      const src = byKey[cfg.slug];
      fullMarkets[cfg.slug] = core.normalizeMarketPayload(src.data, cfg, src.observedAt);
    }
    const pitcherBoard = core.buildPitcherBoard(fullMarkets);
    // Production snapshot stores each offer only once, inside pitcherBoard. The old
    // schema-probe/sourceSchema duplication is deliberately gone.
    const markets = Object.fromEntries(Object.entries(fullMarkets).map(([slug,m]) => [slug, core.marketSummary(m)]));

    const snapshot = {
      schemaVersion: 3,
      provider: 'propsmadness-table-api',
      providerVersion: VERSION,
      leagueCode: 'mlb',
      capturedAt: new Date().toISOString(),
      pageUrl: location.href,
      durationMs: Math.round(performance.now() - t0),
      endpointTimings: Object.fromEntries(settled.map(x => [x.key, x.durationMs])),
      matches: byKey.matches.data,
      rankings: byKey.rankings.data,
      markets,
      pitcherBoard,
      memory: { before: memoryBefore, after: memoryMB() }
    };
    const validation = core.validateCapture(snapshot);
    snapshot.status = validation.ok ? 'PASS' : 'BLOCKED';
    snapshot.validationErrors = validation.errors;
    snapshot.serializedBytes = JSON.stringify(snapshot).length;
    if (!validation.ok) throw new Error(`Table provider BLOCKED: ${validation.errors.join('; ')}`);
    return snapshot;
  }

  window.__MODEL_PM_TABLE_RUN__ = run;
  window.__MODEL_PM_TABLE_PING__ = () => ({ ok: true, version: VERSION, core: window.MODEL_PM_TABLE_CORE?.VERSION === VERSION });
})();
