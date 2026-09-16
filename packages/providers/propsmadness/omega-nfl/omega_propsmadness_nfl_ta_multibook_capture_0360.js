(() => {
  "use strict";

  const VERSION = "OMEGA_PM_NFL_TA_MULTIBOOK_CAPTURE_0.36.0";
  const MARKET_SLUG = "player-tackles-assists";
  const DISCOVERY_ENDPOINT = `/api/offer/nfl/explore/${MARKET_SLUG}`;
  const MATCHES_ENDPOINT = "/api/offer/nfl/matches";
  const CONCURRENCY = 4;

  const out = {
    schemaVersion: VERSION,
    capturedAt: new Date().toISOString(),
    pageUrl: location.href,
    marketSlug: MARKET_SLUG,
    discoveryEndpoint: DISCOVERY_ENDPOINT,
    matchesEndpoint: MATCHES_ENDPOINT,
    concurrency: CONCURRENCY,
    credentialFieldsCaptured: 0,
    requests: {},
    playerMarketRequests: []
  };

  if (!/(^|\.)propsmadness\.com$/i.test(location.hostname) || !location.pathname.startsWith("/nfl")) {
    console.error("OMEGA 0.36 FAIL: open https://propsmadness.com/nfl before running this capture.");
    return;
  }

  async function fetchJson(path) {
    const started = performance.now();
    try {
      const response = await fetch(path, {
        method: "GET",
        credentials: "include",
        cache: "no-store",
        headers: { accept: "application/json" }
      });
      const contentType = response.headers.get("content-type") || "";
      let data = null, text = null;
      if (contentType.includes("application/json")) {
        try { data = await response.json(); }
        catch (e) { text = `JSON_PARSE_ERROR: ${String(e)}`; }
      } else {
        try { text = (await response.text()).slice(0, 250000); } catch (_) {}
      }
      return {
        ok: response.ok,
        status: response.status,
        contentType,
        durationMs: Math.round(performance.now() - started),
        observedAt: new Date().toISOString(),
        data,
        text
      };
    } catch (e) {
      return {
        ok: false,
        status: null,
        contentType: null,
        durationMs: Math.round(performance.now() - started),
        observedAt: new Date().toISOString(),
        error: String(e && e.stack || e)
      };
    }
  }

  function rootOffer(x) {
    return x && typeof x === "object" && x.offer && typeof x.offer === "object" ? x.offer : x;
  }

  function playerName(p) {
    if (!p || typeof p !== "object") return "";
    return p.name || p.fullName || [p.firstName, p.lastName].filter(Boolean).join(" ");
  }

  function discoverPairs(payload) {
    const offers = payload && Array.isArray(payload.offers) ? payload.offers : [];
    const map = new Map();
    for (const entry of offers) {
      const root = rootOffer(entry) || {};
      const p = root.player && typeof root.player === "object" ? root.player : {};
      const playerId = p.id ?? root.playerId;
      const matchId = root.matchId ?? root.match_id;
      if (playerId == null || matchId == null) continue;
      const key = `${playerId}:${matchId}`;
      if (!map.has(key)) {
        map.set(key, {
          playerId,
          matchId,
          playerName: playerName(p),
          teamId: p.teamId ?? p.team_id ?? root.teamId ?? null
        });
      }
    }
    return [...map.values()];
  }

  async function runPool(items, worker, concurrency) {
    let next = 0;
    async function runner() {
      while (true) {
        const i = next++;
        if (i >= items.length) return;
        await worker(items[i], i);
      }
    }
    await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, () => runner()));
  }

  function download() {
    out.exportedAt = new Date().toISOString();
    const json = JSON.stringify(out, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    const stamp = new Date().toISOString().replace(/[-:.]/g, "");
    a.download = `OMEGA_0360_PROPSMADNESS_NFL_TA_MULTIBOOK_${stamp}.json`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
  }

  (async () => {
    console.log("OMEGA 0.36: discovering NFL T+A player/match pairs...");
    const [discovery, matches] = await Promise.all([
      fetchJson(DISCOVERY_ENDPOINT),
      fetchJson(MATCHES_ENDPOINT)
    ]);
    out.requests.discovery = discovery;
    out.requests.matches = matches;

    if (!discovery.ok || !discovery.data || !Array.isArray(discovery.data.offers)) {
      throw new Error(`discovery endpoint failed or offers[] missing (HTTP ${discovery.status})`);
    }
    if (!matches.ok) {
      throw new Error(`matches endpoint failed (HTTP ${matches.status})`);
    }

    const pairs = discoverPairs(discovery.data);
    if (!pairs.length) throw new Error("no player/match pairs discovered");
    out.validation = {
      discoveryHttpOk: !!discovery.ok,
      matchesHttpOk: !!matches.ok,
      discoveryOfferCount: discovery.data.offers.length,
      uniquePlayerMatchPairs: pairs.length,
      observedMarketSlug: discovery.data.market && discovery.data.market.slug || null,
      expectedMarketSlug: MARKET_SLUG
    };

    console.log(`OMEGA 0.36: capturing ${pairs.length} player main-line multibook markets at concurrency ${CONCURRENCY}...`);
    let done = 0;
    await runPool(pairs, async (pair) => {
      const path = `/api/players/${encodeURIComponent(pair.playerId)}/match/${encodeURIComponent(pair.matchId)}/bet-offers/${MARKET_SLUG}`;
      const response = await fetchJson(path);
      out.playerMarketRequests.push({ ...pair, endpoint: path, response });
      done += 1;
      if (done % 20 === 0 || done === pairs.length) {
        console.log(`OMEGA 0.36: ${done}/${pairs.length} player markets captured`);
      }
    }, CONCURRENCY);

    out.playerMarketRequests.sort((a, b) => {
      const am = Number(a.matchId), bm = Number(b.matchId);
      if (am !== bm) return am - bm;
      return Number(a.playerId) - Number(b.playerId);
    });

    const ok = out.playerMarketRequests.filter(x => x.response && x.response.ok).length;
    const bets = out.playerMarketRequests.reduce((n, x) => n + (x.response && x.response.data && Array.isArray(x.response.data.bets) ? x.response.data.bets.length : 0), 0);
    out.validation.playerMarketHttpOk = ok;
    out.validation.playerMarketHttpFailed = pairs.length - ok;
    out.validation.rawBookQuoteRows = bets;
    console.log("OMEGA 0.36 multibook capture complete", out.validation);
    download();
  })().catch(e => {
    out.fatalError = String(e && e.stack || e);
    console.error("OMEGA 0.36 capture failed", e);
    download();
  });
})();