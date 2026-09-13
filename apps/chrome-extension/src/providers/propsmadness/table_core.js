(() => {
  'use strict';

  const VERSION = '1.3';
  const MARKET_CONFIG = Object.freeze([
    { label: 'Strikeouts', slug: 'player-strikeouts', path: '/api/offer/mlb/explore/player-strikeouts' },
    { label: 'Pitcher Outs', slug: 'player-pitcher-outs', path: '/api/offer/mlb/explore/player-pitcher-outs' },
    { label: 'Earned Runs', slug: 'player-earned-runs', path: '/api/offer/mlb/explore/player-earned-runs' },
    { label: 'Hits Allowed', slug: 'player-hits-allowed', path: '/api/offer/mlb/explore/player-hits-allowed' },
    { label: 'Pitcher Walks', slug: 'player-walks', path: '/api/offer/mlb/explore/player-walks' }
  ]);

  const isObj = v => !!v && typeof v === 'object' && !Array.isArray(v);
  const first = (...xs) => xs.find(v => v !== undefined && v !== null);
  const obj = (...xs) => xs.find(isObj) || null;
  const str = v => v === undefined || v === null ? null : String(v);

  function numberish(v) {
    if (typeof v === 'number' && Number.isFinite(v)) return v;
    if (typeof v === 'string') {
      const m = v.replace(/,/g, '').match(/[+-]?\d+(?:\.\d+)?/);
      if (m) {
        const n = Number(m[0]);
        return Number.isFinite(n) ? n : null;
      }
    }
    return null;
  }

  function findNumber(value, preferred = []) {
    const direct = numberish(value);
    if (direct !== null) return direct;
    if (!isObj(value)) return null;
    const keys = [...preferred, 'american', 'americanOdds', 'price', 'odds', 'value', 'decimal', 'decimalOdds'];
    for (const k of keys) {
      if (!(k in value)) continue;
      const n = numberish(value[k]);
      if (n !== null) return n;
    }
    for (const v of Object.values(value)) {
      const n = numberish(v);
      if (n !== null) return n;
    }
    return null;
  }

  function normalizeOdds(raw) {
    if (!isObj(raw)) return { over: null, under: null };
    const overRaw = first(raw.over, raw.o, raw.Over, raw.OVER);
    const underRaw = first(raw.under, raw.u, raw.Under, raw.UNDER);
    return {
      over: findNumber(overRaw, ['american', 'price']),
      under: findNumber(underRaw, ['american', 'price'])
    };
  }

  function cleanSeries(values) {
    if (!Array.isArray(values)) return [];
    return values.map(numberish).filter(Number.isFinite).slice(-30);
  }

  function normalizeStatBlock(raw) {
    if (!isObj(raw)) return { l30: [], season: { average: null, hit: null, total: null }, pitcherGrade: null };
    const season = isObj(raw.season) ? raw.season : {};
    return {
      // PropsMadness uses this array to render the chronological recent-results graph.
      // We preserve provider order and make no DOM assumptions.
      l30: cleanSeries(raw.l30),
      season: {
        average: numberish(season.average),
        hit: numberish(season.hit),
        total: numberish(season.total)
      },
      pitcherGrade: numberish(raw.pitcherGrade)
    };
  }

  function normalizeStatistics(raw) {
    raw = isObj(raw) ? raw : {};
    return {
      overall: normalizeStatBlock(raw.overall),
      vsLeft: normalizeStatBlock(raw.vsLeft),
      vsRight: normalizeStatBlock(raw.vsRight)
    };
  }

  function statisticsScore(s) {
    if (!s) return 0;
    const o = s.overall || {};
    return (o.l30?.length || 0) + (Number.isFinite(o.season?.average) ? 5 : 0) + (Number.isFinite(o.pitcherGrade) ? 1 : 0);
  }

  function normalizeOffer(entry, payloadMarket, rawIndex = 0) {
    const root = obj(entry?.offer, entry) || {};
    const bet = obj(root.bet, entry?.bet) || {};
    const player = obj(root.player, entry?.player, bet.player) || {};
    const market = obj(bet.market, root.market, entry?.market, payloadMarket) || {};
    const sportsbook = obj(bet.sportsbook, root.sportsbook, entry?.sportsbook) || {};
    const odds = normalizeOdds(first(bet.odds, root.odds, entry?.odds));
    const firstName = first(player.firstName, player.first_name, player.givenName);
    const lastName = first(player.lastName, player.last_name, player.familyName);
    const displayName = first(player.name, player.fullName, [firstName, lastName].filter(Boolean).join(' ').trim()) || null;
    const matchId = first(root.matchId, entry?.matchId, bet.matchId, root.match?.id, entry?.match?.id);
    const playerId = first(player.id, root.playerId, entry?.playerId);
    const teamId = first(player.teamId, player.team_id, root.teamId, entry?.teamId);
    const line = findNumber(first(bet.line, root.line, entry?.line));
    return {
      rawIndex,
      matchId: matchId == null ? null : String(matchId),
      playerId: playerId == null ? null : String(playerId),
      player: {
        name: displayName,
        position: str(first(player.position, root.position)),
        teamId: teamId == null ? null : String(teamId),
        throwingHand: str(first(player.throwingHand, player.throwing_hand)),
        battingHand: str(first(player.battingHand, player.batting_hand))
      },
      market: {
        id: first(market.id, payloadMarket?.id) ?? null,
        name: str(first(market.name, payloadMarket?.name)),
        slug: str(first(market.slug, payloadMarket?.slug)),
        code: str(first(market.code, payloadMarket?.code)),
        marketType: str(first(market.marketType, market.type, payloadMarket?.marketType))
      },
      sportsbook: {
        id: sportsbook.id ?? null,
        name: str(sportsbook.name),
        slug: str(sportsbook.slug)
      },
      line,
      odds,
      statistics: normalizeStatistics(entry?.statistics)
    };
  }

  function normalizeMarketPayload(payload, expected, observedAt = null) {
    if (!isObj(payload)) throw new Error(`${expected.label}: payload is not an object`);
    if (!Array.isArray(payload.offers)) throw new Error(`${expected.label}: offers[] missing`);
    const market = obj(payload.market) || {};
    const observedSlug = str(market.slug);
    if (observedSlug && observedSlug !== expected.slug) {
      throw new Error(`${expected.label}: market slug mismatch (${observedSlug} != ${expected.slug})`);
    }
    const offers = payload.offers.map((x, i) => normalizeOffer(x, market, i));
    const validIdentity = offers.filter(x => x.matchId && x.playerId && x.player?.name).length;
    return {
      label: expected.label,
      slug: expected.slug,
      endpoint: expected.path,
      observedAt,
      market: {
        id: market.id ?? null,
        name: str(market.name),
        slug: observedSlug || expected.slug,
        code: str(market.code),
        marketType: str(market.marketType || market.type)
      },
      offerCount: offers.length,
      validIdentityCount: validIdentity,
      offers
    };
  }

  function buildPitcherBoard(markets) {
    const map = new Map();
    for (const market of Object.values(markets || {})) {
      for (const offer of market.offers || []) {
        if (!offer.playerId || !offer.matchId || !offer.player?.name) continue;
        const key = `${offer.matchId}:${offer.playerId}`;
        let p = map.get(key);
        if (!p) {
          p = {
            key,
            matchId: offer.matchId,
            playerId: offer.playerId,
            player: { ...offer.player },
            markets: {}
          };
          map.set(key, p);
        }
        const slug = market.slug;
        if (!p.markets[slug]) {
          p.markets[slug] = {
            label: market.label,
            slug,
            observedAt: market.observedAt || null,
            statistics: null,
            offers: []
          };
        }
        p.markets[slug].offers.push({ sportsbook: offer.sportsbook, line: offer.line, odds: offer.odds });
        if (statisticsScore(offer.statistics) > statisticsScore(p.markets[slug].statistics)) {
          p.markets[slug].statistics = offer.statistics;
        }
      }
    }
    const pitchers = [...map.values()].map(p => {
      for (const m of Object.values(p.markets)) m.offerCount = m.offers.length;
      p.marketCount = Object.keys(p.markets).length;
      return p;
    });
    pitchers.sort((a,b) => (a.matchId || '').localeCompare(b.matchId || '') || (a.player?.name || '').localeCompare(b.player?.name || ''));
    return pitchers;
  }

  function marketSummary(m) {
    return {
      label: m.label,
      slug: m.slug,
      endpoint: m.endpoint,
      observedAt: m.observedAt || null,
      market: m.market,
      offerCount: m.offerCount,
      validIdentityCount: m.validIdentityCount
    };
  }

  function validateCapture(capture) {
    const errors = [];
    if (!capture || capture.leagueCode !== 'mlb') errors.push('leagueCode is not mlb');
    if (!Array.isArray(capture.matches?.matches)) errors.push('matches payload missing matches[]');
    if (!isObj(capture.rankings?.rankings)) errors.push('team rankings payload missing rankings{}');
    if (!Array.isArray(capture.pitcherBoard)) errors.push('pitcherBoard missing');
    for (const cfg of MARKET_CONFIG) {
      const m = capture.markets?.[cfg.slug];
      if (!m) errors.push(`${cfg.label}: missing market summary`);
      else if (!Number.isFinite(Number(m.offerCount)) || m.offerCount <= 0) errors.push(`${cfg.label}: zero offers`);
      else if (m.validIdentityCount !== m.offerCount) errors.push(`${cfg.label}: ${m.offerCount - m.validIdentityCount} offer identity rows invalid`);
    }
    return { ok: !errors.length, errors };
  }

  const api = {
    VERSION, MARKET_CONFIG, numberish, normalizeStatistics, normalizeOffer, normalizeMarketPayload,
    buildPitcherBoard, marketSummary, validateCapture
  };
  if (typeof window !== 'undefined') window.MODEL_PM_TABLE_CORE = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
