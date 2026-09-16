(() => {
  "use strict";

  const VERSION = "OMEGA_PM_NFL_TA_ROUTE_PROBE_0.36.2";
  const MARKET_SLUG = "player-tackles-assists";
  const DISCOVERY = `/api/offer/nfl/explore/${MARKET_SLUG}`;
  const MAX_PER_MATCH = 2;
  const CONCURRENCY = 3;

  const out = {
    schemaVersion: VERSION,
    capturedAt: new Date().toISOString(),
    pageUrl: location.href,
    marketSlug: MARKET_SLUG,
    maxPerMatch: MAX_PER_MATCH,
    concurrency: CONCURRENCY,
    credentialFieldsCaptured: 0,
    discovery: null,
    probes: []
  };

  if (!/(^|\.)propsmadness\.com$/i.test(location.hostname) || !location.pathname.startsWith("/nfl")) {
    console.error("OMEGA 0.36.2 FAIL: open https://propsmadness.com/nfl before running this probe.");
    return;
  }

  async function fetchJson(path) {
    const started = performance.now();
    try {
      const response = await fetch(path, {method:"GET", credentials:"include", cache:"no-store", headers:{accept:"application/json"}});
      const contentType = response.headers.get("content-type") || "";
      let data = null, text = null;
      if (contentType.includes("application/json")) {
        try { data = await response.json(); } catch (e) { text = `JSON_PARSE_ERROR: ${String(e)}`; }
      } else {
        try { text = (await response.text()).slice(0, 100000); } catch (_) {}
      }
      return {ok:response.ok,status:response.status,contentType,durationMs:Math.round(performance.now()-started),observedAt:new Date().toISOString(),data,text};
    } catch (e) {
      return {ok:false,status:null,contentType:null,durationMs:Math.round(performance.now()-started),observedAt:new Date().toISOString(),error:String(e && e.stack || e)};
    }
  }

  function rootOffer(x) {
    return x && typeof x === "object" && x.offer && typeof x.offer === "object" ? x.offer : x;
  }
  function playerName(p) {
    return p && typeof p === "object" ? (p.name || p.fullName || [p.firstName,p.lastName].filter(Boolean).join(" ")) : "";
  }
  function hasReference(root) {
    const q = root && root.referenceBet;
    if (!q || typeof q !== "object") return false;
    const odds = q.odds && typeof q.odds === "object" ? q.odds : {};
    return q.line != null && (odds.over != null || odds.under != null);
  }
  function choosePairs(payload) {
    const offers = payload && Array.isArray(payload.offers) ? payload.offers : [];
    const perMatch = new Map();
    const seen = new Set();
    const chosen = [];
    for (const entry of offers) {
      const root = rootOffer(entry) || {};
      const p = root.player && typeof root.player === "object" ? root.player : {};
      const playerId = p.id ?? root.playerId;
      const matchId = root.matchId ?? root.match_id;
      if (playerId == null || matchId == null || !hasReference(root)) continue;
      const key = `${playerId}:${matchId}`;
      if (seen.has(key)) continue;
      const n = perMatch.get(String(matchId)) || 0;
      if (n >= MAX_PER_MATCH) continue;
      seen.add(key);
      perMatch.set(String(matchId), n+1);
      const rb = root.referenceBet || {};
      const sb = rb.sportsbook && typeof rb.sportsbook === "object" ? rb.sportsbook : {};
      chosen.push({
        playerId, matchId, playerName: playerName(p), teamId: p.teamId ?? p.team_id ?? root.teamId ?? null,
        discoveryReference: {book:sb.name || sb.slug || null,line:rb.line ?? null,odds:rb.odds || null}
      });
    }
    return chosen;
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
    await Promise.all(Array.from({length:Math.min(concurrency,items.length)},()=>runner()));
  }
  function download() {
    out.exportedAt = new Date().toISOString();
    const blob = new Blob([JSON.stringify(out,null,2)], {type:"application/json"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `OMEGA_0362_PROPSMADNESS_NFL_TA_ROUTE_PROBE_${new Date().toISOString().replace(/[-:.]/g,"")}.json`;
    document.body.appendChild(a); a.click();
    setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},2000);
  }

  (async()=>{
    console.log("OMEGA 0.36.2: probing alternate PropsMadness T+A routes...");
    const discovery = await fetchJson(DISCOVERY);
    out.discovery = discovery;
    if (!discovery.ok || !discovery.data || !Array.isArray(discovery.data.offers)) throw new Error(`discovery failed HTTP ${discovery.status}`);
    const pairs = choosePairs(discovery.data);
    if (!pairs.length) throw new Error("no populated-reference T+A player/match pairs available for route probe");
    console.log(`OMEGA 0.36.2: selected ${pairs.length} players across ${new Set(pairs.map(x=>x.matchId)).size} matches`);
    let done = 0;
    await runPool(pairs, async pair => {
      const genericPath = `/api/players/${encodeURIComponent(pair.playerId)}/match/${encodeURIComponent(pair.matchId)}/bet-offers`;
      const altPath = `/api/players/${encodeURIComponent(pair.playerId)}/match/${encodeURIComponent(pair.matchId)}/bet-offers/alt/${MARKET_SLUG}`;
      const [generic, alt] = await Promise.all([fetchJson(genericPath), fetchJson(altPath)]);
      out.probes.push({...pair,genericEndpoint:genericPath,altEndpoint:altPath,genericResponse:generic,altResponse:alt});
      done += 1;
      if (done % 8 === 0 || done === pairs.length) console.log(`OMEGA 0.36.2: ${done}/${pairs.length} players probed`);
    }, CONCURRENCY);
    out.probes.sort((a,b)=>Number(a.matchId)-Number(b.matchId)||Number(a.playerId)-Number(b.playerId));
    out.validation = {selectedPlayers:pairs.length,selectedMatches:new Set(pairs.map(x=>String(x.matchId))).size};
    console.log("OMEGA 0.36.2 route probe complete", out.validation);
    download();
  })().catch(e=>{
    out.fatalError=String(e && e.stack || e); console.error("OMEGA 0.36.2 probe failed",e); download();
  });
})();
