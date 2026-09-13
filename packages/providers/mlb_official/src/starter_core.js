(() => {
  'use strict';

  const VERSION = '1.5';
  const MARKET_SLUGS = Object.freeze([
    'player-strikeouts','player-pitcher-outs','player-earned-runs','player-hits-allowed','player-walks'
  ]);
  const MARKET_LABELS = Object.freeze({
    'player-strikeouts':'K','player-pitcher-outs':'OUTS','player-earned-runs':'ER','player-hits-allowed':'HA','player-walks':'BB'
  });

  function normalizeName(name) {
    return String(name || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'')
      .replace(/[^a-z0-9 ]+/g,' ').replace(/\s+/g,' ').trim();
  }

  function teamCode(name) {
    const u = String(name || '').trim().toUpperCase();
    const map = {
      'ARIZONA DIAMONDBACKS':'ARI','ATLANTA BRAVES':'ATL','BALTIMORE ORIOLES':'BAL','BOSTON RED SOX':'BOS',
      'CHICAGO CUBS':'CHC','CHICAGO WHITE SOX':'CWS','CINCINNATI REDS':'CIN','CLEVELAND GUARDIANS':'CLE',
      'COLORADO ROCKIES':'COL','DETROIT TIGERS':'DET','HOUSTON ASTROS':'HOU','KANSAS CITY ROYALS':'KC',
      'LOS ANGELES ANGELS':'LAA','LOS ANGELES DODGERS':'LAD','MIAMI MARLINS':'MIA','MILWAUKEE BREWERS':'MIL',
      'MINNESOTA TWINS':'MIN','NEW YORK METS':'NYM','NEW YORK YANKEES':'NYY','ATHLETICS':'OAK','OAKLAND ATHLETICS':'OAK',
      'PHILADELPHIA PHILLIES':'PHI','PITTSBURGH PIRATES':'PIT','SAN DIEGO PADRES':'SD','SAN FRANCISCO GIANTS':'SF',
      'SEATTLE MARINERS':'SEA','ST. LOUIS CARDINALS':'STL','ST LOUIS CARDINALS':'STL','TAMPA BAY RAYS':'TB',
      'TEXAS RANGERS':'TEX','TORONTO BLUE JAYS':'TOR','WASHINGTON NATIONALS':'WSH'
    };
    return map[u] || ({ATH:'OAK',CHW:'CWS',KCR:'KC',SDP:'SD',SFG:'SF',TBR:'TB',WSN:'WSH',AZ:'ARI',NYA:'NYY',NYN:'NYM'})[u] || (u.match(/^[A-Z]{2,4}$/)?.[0] || null);
  }

  function parseHydratedLineup(game, side) {
    const key=side==='away'?'awayPlayers':'homePlayers';
    const alt=game?.lineups?.[side];
    const candidates=[
      game?.lineups?.[key],
      alt?.players,
      alt?.battingOrder,
      game?.teams?.[side]?.lineup,
      game?.teams?.[side]?.batters
    ];
    const rows=candidates.find(Array.isArray)||[];
    const hitters=rows.slice(0,9).map((raw,i)=>{
      const p=raw?.person||raw||{};
      const id=p?.id??raw?.id??raw?.personId??null;
      const name=p?.fullName||raw?.fullName||[p?.useName||p?.firstName, p?.lastName].filter(Boolean).join(' ').trim()||null;
      return {mlbId:id==null?null:String(id),name,order:i+1,position:p?.primaryPosition?.abbreviation||raw?.position?.abbreviation||null};
    }).filter(x=>x.mlbId&&x.name);
    if(rows.length>=9&&hitters.length===9&&new Set(hitters.map(x=>x.mlbId)).size===9) return {state:'OFFICIAL',count:9,hitters,reason:null,source:'MLB schedule hydrate=lineups'};
    if(!rows.length) return {state:'PENDING',count:0,hitters:[],reason:'official batting order not present in MLB schedule hydration',source:'MLB schedule hydrate=lineups'};
    return {state:'INCOMPLETE',count:hitters.length,hitters,reason:`MLB hydrated lineup contains ${hitters.length}/9 valid hitters`,source:'MLB schedule hydrate=lineups'};
  }


  function parseSchedule(data, nowMs=Date.now()) {
    const games = Array.isArray(data?.dates) ? data.dates.flatMap(d => Array.isArray(d?.games) ? d.games : []) : [];
    return games.map(g => {
      const away = teamCode(g?.teams?.away?.team?.name);
      const home = teamCode(g?.teams?.home?.team?.name);
      const abstractState = String(g?.status?.abstractGameState || '');
      const detailedState = String(g?.status?.detailedState || '');
      const pregameDetailed = /scheduled|pre-?game|warmup|preview|delayed start/i.test(detailedState);
      const finalState = /final/i.test(abstractState) || /game over|final|completed early/i.test(detailedState);
      const activePlay = /in progress|manager challenge|review|suspended/i.test(detailedState);
      const startMs=Date.parse(g?.gameDate||'');
      // Fail closed at scheduled first pitch if status lags, except MLB's explicit Delayed Start state.
      const beforeScheduledStart=Number.isFinite(startMs)?startMs>Number(nowMs):false;
      const delayedStart=/delayed start/i.test(detailedState);
      const pregame = !finalState && !activePlay && (beforeScheduledStart||delayedStart) && (/preview/i.test(abstractState) || pregameDetailed);
      const ap = g?.teams?.away?.probablePitcher || null;
      const hp = g?.teams?.home?.probablePitcher || null;
      return {
        gamePk: g?.gamePk == null ? null : String(g.gamePk),
        away, home,
        awayTeamId:g?.teams?.away?.team?.id==null?null:String(g.teams.away.team.id),
        homeTeamId:g?.teams?.home?.team?.id==null?null:String(g.teams.home.team.id),
        venueId:g?.venue?.id==null?null:String(g.venue.id),
        venueName:g?.venue?.name||null,
        startAt: g?.gameDate || null,
        abstractState, detailedState, pregame,
        awayProbable: ap?.fullName || null,
        awayProbableId: ap?.id == null ? null : String(ap.id),
        homeProbable: hp?.fullName || null,
        homeProbableId: hp?.id == null ? null : String(hp.id),
        lineups: { away:parseHydratedLineup(g,'away'), home:parseHydratedLineup(g,'home') }
      };
    }).filter(x => x.gamePk && x.away && x.home);
  }

  function finite(v){ return v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v)); }

  function classifyMarket(record) {
    if (!record) return { state:'MISSING', representative:null, offerCount:0, statistics:null, observedAt:null };
    const offers = Array.isArray(record.offers) ? record.offers : [];
    if (!offers.length) return { state:'UNPRICED', representative:null, offerCount:0, statistics:record.statistics||null, observedAt:record.observedAt||null };
    const scored = offers.map((o,i) => {
      const lineOk = finite(o?.line), overOk = finite(o?.odds?.over), underOk = finite(o?.odds?.under), bookOk = !!o?.sportsbook?.name;
      const score = (lineOk?5:0) + (overOk?2:0) + (underOk?2:0) + (bookOk?1:0);
      return { o, i, lineOk, overOk, underOk, bookOk, score };
    }).sort((a,b)=>b.score-a.score || a.i-b.i);
    const best = scored[0];
    let state = 'UNPRICED';
    if (best.lineOk && best.overOk && best.underOk && best.bookOk) state = 'PRICED';
    else if (best.lineOk || best.overOk || best.underOk || best.bookOk) state = 'PARTIAL';
    return {
      state, offerCount: offers.length, statistics:record.statistics||null, observedAt:record.observedAt||null,
      offers: offers.map(o=>({sportsbook:{name:o?.sportsbook?.name||null,slug:o?.sportsbook?.slug||null},line:finite(o?.line)?Number(o.line):null,odds:{over:finite(o?.odds?.over)?Number(o.odds.over):null,under:finite(o?.odds?.under)?Number(o.odds.under):null}})),
      representative: best ? {
        sportsbook: best.o?.sportsbook?.name || null,
        sportsbookSlug: best.o?.sportsbook?.slug || null,
        line: finite(best.o?.line) ? Number(best.o.line) : null,
        overOdds: finite(best.o?.odds?.over) ? Number(best.o.odds.over) : null,
        underOdds: finite(best.o?.odds?.under) ? Number(best.o.odds.under) : null,
        capturedAt: record.observedAt || null
      } : null
    };
  }

  function emptyStarter(side, game, officialName, officialMlbId, state, reason) {
    return {
      side, officialName:officialName||null, officialMlbId:officialMlbId||null,
      team:side==='away'?game.away:game.home, opponent:side==='away'?game.home:game.away,
      identityState:state, reasons:reason?[reason]:[], marketStates:null, markets:{}
    };
  }

  function opponentRankContext(rankings, teamId, throwingHand) {
    const raw=rankings?.[String(teamId)]||rankings?.[Number(teamId)]||null;
    if(!raw)return null;
    const hand=String(throwingHand||'').toLowerCase().startsWith('l')?'Left':'Right';
    const pick=(base)=>{
      const hk=`${base}Vs${hand}Allowed`;
      const all=`${base}Allowed`;
      const v=raw?.[hk]??raw?.[all]??null;
      return Number.isFinite(Number(v))?Number(v):null;
    };
    return {
      source:'PropsMadness team rankings',
      semantics:'ordinal rank 1-30; context only, never converted into a fake percentage',
      teamId:String(teamId),pitcherHand:hand,
      kRank:pick('strikeoutPercentage'),whiffRank:pick('whiffPercentage'),chaseRank:pick('chasePercentage'),
      contactRank:pick('contactPercentage'),pitchesPerPaRank:pick('pitchesPerPlateAppearance'),bbRank:pick('walkPercentage'),
      xwobaRank:pick('expectedWoba'),hardHitRank:pick('hardHitRate')
    };
  }

  function starterFromCandidate(side, game, officialName, officialMlbId, candidate, opponentCandidate, rankings) {
    if (!officialName || !officialMlbId) return emptyStarter(side,game,officialName,officialMlbId,'MISSING_OFFICIAL','MLB schedule has no complete probable-pitcher identity');
    if (!candidate) return emptyStarter(side,game,officialName,officialMlbId,'NOT_FOUND','official starter not found in a unique PropsMadness event pair');
    const markets = {};
    const counts = { PRICED:0, PARTIAL:0, UNPRICED:0, MISSING:0 };
    for (const slug of MARKET_SLUGS) {
      const q = classifyMarket(candidate.markets?.[slug]);
      markets[slug] = { label:MARKET_LABELS[slug], ...q };
      counts[q.state] = (counts[q.state] || 0) + 1;
    }
    return {
      side, officialName, officialMlbId:String(officialMlbId),
      team:side==='away'?game.away:game.home, opponent:side==='away'?game.home:game.away,
      identityState:'VERIFIED', reasons:[], propsName:candidate.player?.name || null, propsPlayerId:candidate.playerId || null,
      propsMatchId:candidate.matchId || null, propsPosition:candidate.player?.position || null, propsTeamId:candidate.player?.teamId||null, throwingHand:candidate.player?.throwingHand || null,
      opponentPropsTeamId:opponentCandidate?.player?.teamId||null, opponentRankContext:opponentRankContext(rankings,opponentCandidate?.player?.teamId,candidate.player?.throwingHand),
      marketCount:candidate.marketCount || Object.keys(candidate.markets||{}).length, marketStates:counts, markets
    };
  }

  function candidatePairForGame(game, byName) {
    const awayAll = game.awayProbable ? (byName.get(normalizeName(game.awayProbable)) || []) : [];
    const homeAll = game.homeProbable ? (byName.get(normalizeName(game.homeProbable)) || []) : [];
    const awayByMatch = new Map(); for (const c of awayAll) { if (!awayByMatch.has(c.matchId)) awayByMatch.set(c.matchId,[]); awayByMatch.get(c.matchId).push(c); }
    const homeByMatch = new Map(); for (const c of homeAll) { if (!homeByMatch.has(c.matchId)) homeByMatch.set(c.matchId,[]); homeByMatch.get(c.matchId).push(c); }
    const common = [...awayByMatch.keys()].filter(k => k && homeByMatch.has(k));
    const valid = common.filter(k => awayByMatch.get(k).length===1 && homeByMatch.get(k).length===1);
    if (valid.length === 1) return { matchId:valid[0], away:awayByMatch.get(valid[0])[0], home:homeByMatch.get(valid[0])[0], reason:null };
    if (!game.awayProbable || !game.homeProbable) return { matchId:null, away:null, home:null, reason:'MLB probable-pitcher identity incomplete' };
    if (!valid.length) {
      return { matchId:null, away:null, home:null, reason:`no unique PropsMadness event contains both official starters (${awayAll.length} away-name row(s), ${homeAll.length} home-name row(s))` };
    }
    return { matchId:null, away:null, home:null, reason:`multiple PropsMadness events contain both official starter names (${valid.join(', ')})` };
  }

  function buildStarterBoard(scheduleRows, pitcherBoard, capturedAt, rankings={}) {
    const byName = new Map();
    for (const p of pitcherBoard || []) {
      const n = normalizeName(p?.player?.name);
      if (!n) continue;
      if (!byName.has(n)) byName.set(n, []);
      byName.get(n).push(p);
    }
    const usedCandidate = new Map();
    const propsMatchOwners = new Map();
    const games = [];

    for (const g of scheduleRows || []) {
      const reasons = [];
      const pair = candidatePairForGame(g,byName);
      let awayStarter, homeStarter, state='VERIFIED';
      if (!pair.away || !pair.home) {
        awayStarter = emptyStarter('away',g,g.awayProbable,g.awayProbableId,'NOT_FOUND',pair.reason);
        homeStarter = emptyStarter('home',g,g.homeProbable,g.homeProbableId,'NOT_FOUND',pair.reason);
        state='BLOCKED'; reasons.push(pair.reason || 'official starters were not uniquely reconciled');
      } else {
        awayStarter=starterFromCandidate('away',g,g.awayProbable,g.awayProbableId,pair.away,pair.home,rankings);
        homeStarter=starterFromCandidate('home',g,g.homeProbable,g.homeProbableId,pair.home,pair.away,rankings);
        for (const [side, st, c] of [['away',awayStarter,pair.away],['home',homeStarter,pair.home]]) {
          const ownerKey=`${g.gamePk}:${side}`, ckey=c.key||`${c.matchId}:${c.playerId}`;
          if (usedCandidate.has(ckey) && usedCandidate.get(ckey)!==ownerKey) {
            st.identityState='REUSED_IDENTITY'; st.reasons=['PropsMadness player/match identity already mapped to another official starter']; state='BLOCKED'; reasons.push(`${side} starter identity reused`);
          } else usedCandidate.set(ckey,ownerKey);
        }
        const prior=propsMatchOwners.get(pair.matchId);
        if (prior && prior!==g.gamePk) { state='BLOCKED'; reasons.push(`PropsMadness match ${pair.matchId} already mapped to MLB gamePk ${prior}`); }
        else propsMatchOwners.set(pair.matchId,g.gamePk);
      }
      if (!g.pregame && state==='VERIFIED') state='NOT_PREGAME';
      const fullyPriced = [awayStarter,homeStarter].every(s => s.identityState==='VERIFIED' && s.marketStates?.PRICED===5);
      games.push({ ...g, state, reasons, propsMatchId:pair.matchId||null, fullyPriced5x2:fullyPriced, starters:{away:awayStarter,home:homeStarter} });
    }

    const starterSlots = games.length*2;
    const verifiedSlots = games.flatMap(g=>[g.starters.away,g.starters.home]).filter(s=>s.identityState==='VERIFIED').length;
    const pregameGames = games.filter(g=>g.pregame).length;
    const verifiedPregameGames = games.filter(g=>g.pregame && g.state==='VERIFIED').length;
    const blockedPregameGames = games.filter(g=>g.pregame && g.state==='BLOCKED').length;
    return {
      schemaVersion:2, boardVersion:VERSION, builtAt:new Date().toISOString(), sourceCapturedAt:capturedAt || null,
      officialGameCount:games.length, pregameGameCount:pregameGames, officialStarterSlots:starterSlots,
      verifiedStarterSlots:verifiedSlots, verifiedPregameGames, blockedPregameGames,
      rawPropsPitcherRows:(pitcherBoard||[]).length, games
    };
  }

  function playerEntry(team, id) {
    if (!team || id == null) return null;
    return team.players?.[`ID${id}`] || Object.values(team.players||{}).find(p=>String(p?.person?.id||'')===String(id)) || null;
  }

  function parseBoxscoreLineup(boxscore, side) {
    const team=boxscore?.teams?.[side];
    if (!team) return { state:'ERROR', count:0, hitters:[], reason:`boxscore missing teams.${side}` };
    let ids=Array.isArray(team.battingOrder)?team.battingOrder.map(String):[];
    if (!ids.length) {
      ids=Object.values(team.players||{}).filter(p=>/^\d00$/.test(String(p?.battingOrder||'')))
        .sort((a,b)=>Number(a.battingOrder)-Number(b.battingOrder)).map(p=>String(p.person?.id||'')).filter(Boolean);
    }
    ids=[...new Set(ids)].slice(0,9);
    const hitters=ids.map((id,i)=>{
      const p=playerEntry(team,id)||{};
      return {
        mlbId:String(id), name:p?.person?.fullName||null, order:i+1,
        battingOrder:p?.battingOrder||String((i+1)*100), position:p?.position?.abbreviation||null
      };
    });
    if (hitters.length===9 && hitters.every(x=>x.mlbId&&x.name)) return { state:'OFFICIAL', count:9, hitters, reason:null };
    if (!hitters.length) return { state:'PENDING', count:0, hitters:[], reason:'official batting order not posted in MLB boxscore yet' };
    return { state:'INCOMPLETE', count:hitters.length, hitters, reason:`MLB boxscore contains ${hitters.length}/9 batting-order hitters` };
  }

  function resolveLineup(hydrated, boxscore, side) {
    if(hydrated?.state==='OFFICIAL'&&hydrated?.hitters?.length===9)return hydrated;
    const b=parseBoxscoreLineup(boxscore,side);
    return b?.state==='OFFICIAL'?{...b,source:'MLB /game/{gamePk}/boxscore fallback'}:(hydrated||b||{state:'PENDING',count:0,hitters:[],reason:'lineup unavailable'});
  }

  function audit(board) {
    const gameRows = (board?.games || []).map(g => ({
      gamePk:g.gamePk, matchup:`${g.away} @ ${g.home}`, awayTeamId:g.awayTeamId||null, homeTeamId:g.homeTeamId||null, venueId:g.venueId||null, venueName:g.venueName||null, startAt:g.startAt, pregame:g.pregame, state:g.state,
      propsMatchId:g.propsMatchId, reasons:g.reasons,
      starters:['away','home'].map(side => {
        const s=g.starters?.[side]||{};
        return { side, team:s.team, officialName:s.officialName, officialMlbId:s.officialMlbId||null, identityState:s.identityState, propsName:s.propsName||null, propsPlayerId:s.propsPlayerId||null, propsMatchId:s.propsMatchId||null, marketStates:s.marketStates||null, opponentRankContext:s.opponentRankContext||null,
          markets:Object.fromEntries(Object.entries(s.markets||{}).map(([slug,m])=>[m.label||slug,{state:m.state,...(m.representative||{}),recentCount:m.statistics?.overall?.l30?.length||0,seasonAverage:m.statistics?.overall?.season?.average??null}])) };
      })
    }));
    return {
      boardVersion:VERSION, builtAt:board?.builtAt, sourceCapturedAt:board?.sourceCapturedAt,
      officialGameCount:board?.officialGameCount||0, pregameGameCount:board?.pregameGameCount||0,
      officialStarterSlots:board?.officialStarterSlots||0, verifiedStarterSlots:board?.verifiedStarterSlots||0,
      verifiedPregameGames:board?.verifiedPregameGames||0, blockedPregameGames:board?.blockedPregameGames||0,
      rawPropsPitcherRows:board?.rawPropsPitcherRows||0, games:gameRows
    };
  }

  const api={VERSION,MARKET_SLUGS,MARKET_LABELS,normalizeName,teamCode,parseHydratedLineup,parseSchedule,classifyMarket,candidatePairForGame,buildStarterBoard,parseBoxscoreLineup,resolveLineup,opponentRankContext,audit};
  if(typeof window!=='undefined') window.MODEL_MLB_STARTER_CORE=api;
  if(typeof module!=='undefined'&&module.exports) module.exports=api;
})();
