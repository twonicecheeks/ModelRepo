(() => {
  "use strict";

  const VERSION = "OMEGA_PM_NFL_TA_DIRECT_CAPTURE_0.17.6";
  const MARKET_SLUG = "player-tackles-assists";
  const MARKET_ENDPOINT = `/api/offer/nfl/explore/${MARKET_SLUG}`;
  const MATCHES_ENDPOINT = "/api/offer/nfl/matches";

  const out = {
    schemaVersion: VERSION,
    capturedAt: new Date().toISOString(),
    pageUrl: location.href,
    marketSlug: MARKET_SLUG,
    marketEndpoint: MARKET_ENDPOINT,
    matchesEndpoint: MATCHES_ENDPOINT,
    requests: {},
    credentialFieldsCaptured: 0
  };

  if (!/(^|\.)propsmadness\.com$/i.test(location.hostname) || !location.pathname.startsWith("/nfl")) {
    console.error("OMEGA 0.17.6 FAIL: open https://propsmadness.com/nfl before running this adapter.");
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
        try { data = await response.json(); } catch (e) { text = `JSON_PARSE_ERROR: ${String(e)}`; }
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

  function download() {
    out.exportedAt = new Date().toISOString();
    const json = JSON.stringify(out, null, 2);
    const blob = new Blob([json], {type: "application/json"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    const stamp = new Date().toISOString().replace(/[-:.]/g, "");
    a.download = `OMEGA_0176_PROPSMADNESS_NFL_TA_DIRECT_CAPTURE_${stamp}.json`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
  }

  (async () => {
    const [market, matches] = await Promise.all([
      fetchJson(MARKET_ENDPOINT),
      fetchJson(MATCHES_ENDPOINT)
    ]);
    out.requests.market = market;
    out.requests.matches = matches;

    const payload = market && market.data;
    const offers = payload && Array.isArray(payload.offers) ? payload.offers : null;
    const observedSlug = payload && payload.market && payload.market.slug;

    out.validation = {
      marketHttpOk: !!market.ok,
      marketOffersArray: Array.isArray(offers),
      marketOfferCount: Array.isArray(offers) ? offers.length : null,
      observedMarketSlug: observedSlug || null,
      expectedMarketSlug: MARKET_SLUG,
      marketSlugMatches: !observedSlug || observedSlug === MARKET_SLUG,
      matchesHttpOk: !!matches.ok
    };

    console.log("OMEGA 0.17.6 direct NFL T+A capture", out.validation);
    download();
  })().catch(e => {
    out.fatalError = String(e && e.stack || e);
    download();
  });
})();