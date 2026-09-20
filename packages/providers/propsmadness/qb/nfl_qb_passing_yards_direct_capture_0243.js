(() => {
  "use strict";

  const VERSION = "NFL_QB_PASSING_YARDS_DIRECT_CAPTURE_0.2.4.3";
  const MATCHES_ENDPOINT = "/api/offer/nfl/matches";
  const CANDIDATE_SLUGS = [
    "player-passing-yards",
    "passing-yards",
    "player-pass-yards"
  ];

  const out = {
    schemaVersion: VERSION,
    capturedAt: new Date().toISOString(),
    pageUrl: location.href,
    matchesEndpoint: MATCHES_ENDPOINT,
    attemptedMarketSlugs: CANDIDATE_SLUGS,
    credentialFieldsCaptured: 0,
    requests: {}
  };

  if (!/(^|\.)propsmadness\.com$/i.test(location.hostname) || !location.pathname.startsWith("/nfl")) {
    console.error("QB 0.2.4.3 FAIL: open https://propsmadness.com/nfl before running this adapter.");
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
        try { data = await response.json(); } catch (e) { text = "JSON_PARSE_ERROR: " + String(e); }
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

  function looksLikePassingYards(req) {
    const d = req && req.data;
    if (!req || !req.ok || !d || !Array.isArray(d.offers) || !d.offers.length) return false;
    const m = d.market || {};
    const txt = [m.code, m.name, m.slug].filter(Boolean).join(" ").toLowerCase();
    return txt.includes("pass") && txt.includes("yard");
  }

  function download() {
    out.exportedAt = new Date().toISOString();
    const blob = new Blob([JSON.stringify(out, null, 2)], {type: "application/json"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    const stamp = new Date().toISOString().replace(/[-:.]/g, "");
    a.download = `NFL_QB_PASSING_YARDS_DIRECT_CAPTURE_${stamp}.json`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
  }

  (async () => {
    const matches = await fetchJson(MATCHES_ENDPOINT);
    out.requests.matches = matches;

    let chosen = null;
    for (const slug of CANDIDATE_SLUGS) {
      const endpoint = `/api/offer/nfl/explore/${slug}`;
      const req = await fetchJson(endpoint);
      out.requests[slug] = req;
      if (!chosen && looksLikePassingYards(req)) {
        chosen = {slug, endpoint, req};
      }
    }

    if (chosen) {
      out.marketSlug = chosen.slug;
      out.marketEndpoint = chosen.endpoint;
      out.validation = {
        marketHttpOk: true,
        marketOfferCount: chosen.req.data.offers.length,
        observedMarket: chosen.req.data.market || null,
        matchesHttpOk: !!matches.ok
      };
      console.log("QB 0.2.4.3 passing-yards capture", out.validation);
    } else {
      out.validation = {
        marketHttpOk: false,
        marketOfferCount: 0,
        observedMarket: null,
        matchesHttpOk: !!matches.ok
      };
      console.error("QB 0.2.4.3 FAIL: no passing-yards Explore route resolved.", out.requests);
    }
    download();
  })().catch(e => {
    out.fatalError = String(e && e.stack || e);
    download();
  });
})();