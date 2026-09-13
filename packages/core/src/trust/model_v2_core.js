(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports) module.exports=api;
  else root.MODELV2Core=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';

  const VERSION='3.0.0';

  function num(v){ if(v===null||v===undefined||v==='') return null; const n=Number(v); return Number.isFinite(n)?n:null; }
  function impliedAmerican(odds){
    const o=num(odds); if(o===null||o===0) return null;
    return o>0 ? 100/(o+100) : (-o)/((-o)+100);
  }
  function decimalFromAmerican(odds){
    const o=num(odds); if(o===null||o===0) return null;
    return o>0 ? 1+o/100 : 1+100/(-o);
  }
  function fairAmerican(p){
    p=num(p); if(p===null||p<=0||p>=1) return null;
    return p>=0.5 ? Math.round(-100*p/(1-p)) : Math.round(100*(1-p)/p);
  }
  function evAmerican(p,odds){
    p=num(p); const d=decimalFromAmerican(odds);
    if(p===null||d===null) return null;
    return p*d-1;
  }
  function ageSeconds(iso, nowMs=Date.now()){
    const t=Date.parse(iso||'');
    return Number.isFinite(t)?Math.max(0,(nowMs-t)/1000):Infinity;
  }
  function sideEdge(modelProb,marketProb){
    const a=num(modelProb),b=num(marketProb); return a===null||b===null?null:a-b;
  }
  function chooseMoneylineSide(proj,market){
    if(!proj||!market?.sharp) return null;
    const away={side:'away',team:market.away,model:num(proj.awayWin),market:num(market.sharp.awayNoVig)};
    const home={side:'home',team:market.home,model:num(proj.homeWin),market:num(market.sharp.homeNoVig)};
    for(const x of [away,home]) x.edge=(x.model===null||x.market===null)?null:x.model-x.market;
    const chosen=[away,home].filter(x=>x.edge!==null).sort((a,b)=>b.edge-a.edge)[0]||null;
    if(!chosen) return null;
    const best=market.bestAvailable?.[chosen.side]||null;
    chosen.best=best;
    chosen.ev=best?.american!=null?evAmerican(chosen.model,best.american):null;
    chosen.fair=fairAmerican(chosen.model);
    return chosen;
  }
  function trustMoneyline({projection,market,config,nowMs=Date.now()}){
    const trust=config?.trust||config||{};
    const fresh=Number(trust.marketFreshSeconds??180);
    const block=Number(trust.marketBlockSeconds??300);
    const anomaly=Number(trust.anomalyEdgePP??12)/100;
    const minEdge=Number(trust.verifiedMinEdgePP??2.5)/100;
    const minEV=Number(trust.verifiedMinEV??0.02);
    const modelHard=Number(trust.mlbModelFreshMinutes??90);
    const modelWatch=Number(trust.mlbModelWatchMinutes??45);
    const modelSkewMax=Number(trust.mlbModelMaxSkewMinutes??30);
    const reasons=[];

    if(!projection?.complete) return {state:'BLOCKED',reasons:[projection?.reason||'model projection incomplete']};
    if(!market) return {state:'BLOCKED',reasons:['no OddsPapi market joined to this game']};
    if(market.identityStatus!=='VERIFIED') return {state:'BLOCKED',reasons:['canonical event identity not verified']};
    const age=ageSeconds(market.observedAt,nowMs);
    if(age>block) return {state:'BLOCKED',reasons:[`market snapshot stale (${Math.round(age)}s)`],marketAgeSeconds:age};
    if(!market.sharp) return {state:'BLOCKED',reasons:['no sharp market reference']};
    const side=chooseMoneylineSide(projection,market);
    if(!side) return {state:'BLOCKED',reasons:['model/market probability comparison unavailable']};
    if((side.edge??-1)>anomaly) return {state:'ANOMALY',side,reasons:[`model-market disagreement ${(side.edge*100).toFixed(1)}pp exceeds anomaly gate`],marketAgeSeconds:age};
    if(projection.dataQuality==='Low') return {state:'BLOCKED',side,reasons:['model Data Quality is Low'],marketAgeSeconds:age};
    const modelAge=num(projection.modelInputAgeMinutes), modelSkew=num(projection.modelCaptureSkewMinutes);
    if(modelAge===null) return {state:'BLOCKED',side,reasons:['moneyline model input freshness unknown'],marketAgeSeconds:age};
    if(modelAge>modelHard) return {state:'BLOCKED',side,reasons:[`moneyline model inputs stale (${Math.round(modelAge)}m)`],marketAgeSeconds:age};
    if(modelSkew===null) return {state:'BLOCKED',side,reasons:['moneyline model capture skew unknown'],marketAgeSeconds:age};
    if(modelSkew>modelSkewMax) return {state:'BLOCKED',side,reasons:[`moneyline model package unsynchronized (${Math.round(modelSkew)}m skew)`],marketAgeSeconds:age};
    const sharpCount=market.sharp?.books?.length||0;
    const gap=num(market.sharp?.bookGapPP);
    if(age>fresh) reasons.push(`market aging (${Math.round(age)}s)`);
    if(modelAge>modelWatch) reasons.push(`moneyline model inputs aging (${Math.round(modelAge)}m)`);
    if(sharpCount<2) reasons.push('only one sharp reference available');
    if(gap!==null&&gap>2) reasons.push(`sharp-book disagreement ${gap.toFixed(2)}pp`);
    if(projection.dataQuality!=='High') reasons.push(`model Data Quality ${projection.dataQuality||'unknown'}`);

    const edgeOk=(side.edge??-1)>=minEdge;
    const evOk=(side.ev??-1)>=minEV;
    if(!edgeOk||!evOk){
      return {state:'PASS',side,reasons:[!edgeOk?'edge below verified threshold':null,!evOk?'EV below verified threshold':null].filter(Boolean),marketAgeSeconds:age};
    }
    if(reasons.length) return {state:'WATCH',side,reasons,marketAgeSeconds:age};
    return {state:'VERIFIED',side,reasons:[],marketAgeSeconds:age};
  }

  function localKNoVig(overOdds,underOdds){
    const o=impliedAmerican(overOdds),u=impliedAmerican(underOdds);
    if(o===null||u===null||o+u<=0) return null;
    return {overNoVig:o/(o+u),underNoVig:u/(o+u)};
  }
  function normalizeBookSlug(v){return String(v||'').toLowerCase().replace(/[^a-z0-9]/g,'');}
  function kSharpReference(offers,line){
    const target=num(line);if(target===null)return null;
    const sharp=[];
    for(const o of offers||[]){const l=num(o?.line);if(l===null||Math.abs(l-target)>.001)continue;const slug=normalizeBookSlug(o?.sportsbook?.slug||o?.sportsbook?.name);if(!['pinnacle','circa','circasports'].includes(slug))continue;const pair=localKNoVig(o?.odds?.over,o?.odds?.under);if(!pair)continue;sharp.push({book:o?.sportsbook?.name||o?.sportsbook?.slug||slug,slug,overNoVig:pair.overNoVig,underNoVig:pair.underNoVig});}
    if(!sharp.length)return null;const over=sharp.reduce((a,x)=>a+x.overNoVig,0)/sharp.length,vals=sharp.map(x=>x.overNoVig),gap=(Math.max(...vals)-Math.min(...vals))*100;return{overNoVig:over,underNoVig:1-over,books:sharp.map(x=>x.book),bookGapPP:gap,kind:sharp.length>=2?'propsmadness_sharp_consensus':'propsmadness_single_sharp',source:'PropsMadness book-level offers',quoteCount:sharp.length};
  }
  function localStarterKMarket({projection,row,game}){
    if(!projection) return null;
    const line=num(projection.localKLine??projection.line);
    if(line===null) return null;
    const overOdds=num(projection.localKOverOdds??projection.overOdds);
    const underOdds=num(projection.localKUnderOdds??projection.underOdds);
    const book=projection.localKBook||projection.localKBookSlug||'PropsMadness';
    const pair=localKNoVig(overOdds,underOdds);
    const sharpRef=kSharpReference(projection.kMarketOffers||[],line);
    const localRef=pair?{
      ...pair,
      books:[book],
      bookGapPP:null,
      kind:'propsmadness_local_no_vig',
      source:'PropsMadness'
    }:null;
    const ref=sharpRef||localRef;
    const freshnessRow=(projection.marketFreshness||[]).find(x=>String(x?.market||'').toLowerCase()==='strikeouts');
    const observedAt=projection.localKCapturedAt||freshnessRow?.capturedAt||null;
    return {
      gamePk:String(game?.gamePk||projection.gamePk||''),
      away:game?.away||'?', home:game?.home||'?',
      player:projection.player||row?.officialName||'?',
      line,
      identityStatus:'VERIFIED',
      playerIdentityStatus:'VERIFIED_OFFICIAL_STARTER',
      observedAt,
      marketSource:'PropsMadness',
      referenceType:ref?ref.kind:'propsmadness_one_sided',
      marketReference:ref,
      bestAvailable:{
        over:overOdds===null?null:{book,american:overOdds},
        under:underOdds===null?null:{book,american:underOdds}
      },
      localMarketState:projection.localKMarketState||null
    };
  }
  function kMarketReference(market){
    if(!market) return null;
    return market.marketReference||market.consensus||market.retailConsensus||market.sharp||null;
  }
  function chooseStarterKSide(proj,market){
    if(!proj||!market) return null;
    const ref=kMarketReference(market);
    const over={side:'over',label:'Over',player:market.player,team:proj.team||null,model:num(proj.overProb),market:num(ref?.overNoVig)};
    const under={side:'under',label:'Under',player:market.player,team:proj.team||null,model:num(proj.underProb),market:num(ref?.underNoVig)};
    for(const x of [over,under]){
      x.edge=(x.model===null||x.market===null)?null:x.model-x.market;
      x.best=market.bestAvailable?.[x.side]||null;
      x.ev=x.best?.american!=null?evAmerican(x.model,x.best.american):null;
      x.fair=fairAmerican(x.model);
      x.marketReferenceKind=ref?.kind||market.referenceType||'propsmadness_local_price';
      x.marketReferenceBooks=Array.isArray(ref?.books)?ref.books.slice():[];
    }
    const priced=[over,under].filter(x=>x.model!==null&&x.ev!==null).sort((a,b)=>b.ev-a.ev);
    if(priced.length) return priced[0];
    const edged=[over,under].filter(x=>x.edge!==null).sort((a,b)=>b.edge-a.edge);
    return edged[0]||null;
  }
  function trustStarterK({projection,market,config,nowMs=Date.now()}){
    const trust=config?.trust||config||{};
    const fresh=Number(trust.marketFreshSeconds??180);
    const block=Number(trust.marketBlockSeconds??300);
    const anomaly=Number(trust.anomalyEdgePP??12)/100;
    const minEdge=Number(trust.verifiedMinEdgePP??2.5)/100;
    const minEV=Number(trust.verifiedMinEV??0.02);
    const modelFresh=Number(trust.propModelFreshMinutes??30);
    const modelSkew=Number(trust.propModelMaxSkewMinutes??10);
    const reasons=[];
    if(!projection) return {state:'BLOCKED',reasons:['K model projection unavailable']};
    if(!market) return {state:'BLOCKED',reasons:['no PropsMadness K line available for this official starter']};
    if(market.identityStatus!=='VERIFIED'||market.playerIdentityStatus!=='VERIFIED_OFFICIAL_STARTER') return {state:'BLOCKED',reasons:['official event/player identity not verified']};
    if(Math.abs(Number(projection.line)-Number(market.line))>0.001) return {state:'BLOCKED',reasons:['independent K distribution was not evaluated at the current PropsMadness K line']};
    if(projection.metricValidation?.schemaIntegrityFailed) return {state:'BLOCKED',reasons:['K model schema integrity failed']};
    if(projection.freshnessWarning) return {state:'BLOCKED',reasons:[String(projection.freshnessWarning)]};
    if(projection.openerLike||projection.roleWarning) return {state:'BLOCKED',reasons:['starter workload/role unresolved']};
    const modelAge=num(projection.oldestMarketAgeMinutes);
    const skew=num(projection.captureSkewMinutes);
    if(modelAge===null) return {state:'BLOCKED',reasons:['K model source freshness unknown']};
    if(modelAge>modelFresh) return {state:'BLOCKED',reasons:[`K model package stale (${Math.round(modelAge)}m)`]};
    if(skew===null) return {state:'BLOCKED',reasons:['K model capture skew unknown']};
    if(skew>modelSkew) return {state:'BLOCKED',reasons:[`K model package unsynchronized (${Math.round(skew)}m skew)`]};
    const age=ageSeconds(market.observedAt,nowMs);
    if(!Number.isFinite(age)) return {state:'BLOCKED',reasons:['PropsMadness K market timestamp missing']};
    if(age>block) return {state:'BLOCKED',reasons:[`PropsMadness K market stale (${Math.round(age)}s)`],marketAgeSeconds:age};
    const side=chooseStarterKSide(projection,market);
    if(!side) return {state:'BLOCKED',reasons:['no actionable PropsMadness K price available'],marketAgeSeconds:age};
    const ref=kMarketReference(market);
    if(ref&&side.edge!==null&&(side.edge??-1)>anomaly) return {state:'ANOMALY',side,reasons:[`model-local-market disagreement ${(side.edge*100).toFixed(1)}pp exceeds anomaly gate`],marketAgeSeconds:age,marketReferenceKind:side.marketReferenceKind};
    if(projection.confidence==='Low') return {state:'BLOCKED',side,reasons:['K model confidence Low'],marketAgeSeconds:age,marketReferenceKind:side.marketReferenceKind};
    if(age>fresh) reasons.push(`PropsMadness K market aging (${Math.round(age)}s)`);
    if(projection.confidence!=='High') reasons.push(`K model confidence ${projection.confidence||'unknown'}`);

    const evOk=(side.ev??-1)>=minEV;
    if(!ref){
      if(!evOk) return {state:'PASS',side,reasons:['EV below verified threshold','one-sided PropsMadness K price; no two-sided no-vig reference'],marketAgeSeconds:age,marketReferenceKind:side.marketReferenceKind};
      reasons.push('one-sided PropsMadness K price; no two-sided no-vig reference');
      return {state:'WATCH',side,reasons:[...new Set(reasons)],marketAgeSeconds:age,marketReferenceKind:side.marketReferenceKind};
    }

    const edgeOk=(side.edge??-1)>=minEdge;
    if(!edgeOk||!evOk) return {state:'PASS',side,reasons:[!edgeOk?'edge below verified threshold':null,!evOk?'EV below verified threshold':null].filter(Boolean),marketAgeSeconds:age,marketReferenceKind:side.marketReferenceKind};
    if(ref?.kind==='propsmadness_sharp_consensus'&&(ref.books||[]).length>=2){if(num(ref.bookGapPP,0)>2)reasons.push(`Pinnacle/Circa K disagreement ${Number(ref.bookGapPP).toFixed(1)}pp`);return{state:reasons.length?'WATCH':'VERIFIED',side,reasons:[...new Set(reasons)],marketAgeSeconds:age,marketReferenceKind:side.marketReferenceKind};}
    reasons.push(ref?.kind==='propsmadness_single_sharp'?'single sharp-book PropsMadness K reference':'single-source PropsMadness local K reference');
    return {state:'WATCH',side,reasons:[...new Set(reasons)],marketAgeSeconds:age,marketReferenceKind:side.marketReferenceKind};
  }

  function opportunityRiskPenalty(edge){
    const t=edge?.trust||{},p=edge?.projection||{},reasons=(t.reasons||[]).map(String);
    let penalty=0;
    if(p?.confidence==='Medium') penalty+=60;
    if(p?.confidence==='Low') penalty+=500;
    if(reasons.some(x=>/aging|stale/i.test(x))) penalty+=35;
    if(reasons.some(x=>/single sharp-book/i.test(x))) penalty+=35;
    if(reasons.some(x=>/single-source PropsMadness/i.test(x))) penalty+=55;
    if(reasons.some(x=>/one-sided PropsMadness/i.test(x))) penalty+=85;
    if(reasons.some(x=>/disagreement/i.test(x))) penalty+=75;
    if(reasons.some(x=>/prospective/i.test(x))) penalty+=20;
    if(reasons.some(x=>/workload|role unresolved/i.test(x))) penalty+=250;
    return penalty;
  }
  function opportunityScore(edge){
    const t=edge?.trust||{},s=t?.side||{};
    const base={VERIFIED:10000,WATCH:8000,PASS:2000,ANOMALY:1000,BLOCKED:0}[t.state]??0;
    const ev=num(s.ev),ed=num(s.edge);
    const evPts=ev===null?0:Math.max(-100,Math.min(100,ev*100))*8;
    const edgePts=ed===null?0:Math.max(-30,Math.min(30,ed*100))*4;
    let refBonus=0;
    if(s.marketReferenceKind==='propsmadness_sharp_consensus')refBonus=100;
    else if(s.marketReferenceKind==='propsmadness_single_sharp')refBonus=45;
    else if(s.marketReferenceKind==='propsmadness_local_no_vig')refBonus=15;
    if(edge?.kind==='ML'&&(edge?.market?.sharp?.books||[]).length>=2)refBonus=Math.max(refBonus,100);
    return base+evPts+edgePts+refBonus-opportunityRiskPenalty(edge);
  }
  function opportunityLabel(edge){
    const st=edge?.trust?.state||'BLOCKED';
    if(st==='VERIFIED')return 'VERIFIED';
    if(st==='WATCH')return 'WATCH — NOT VERIFIED';
    if(st==='ANOMALY')return 'RESEARCH — ANOMALY';
    return st;
  }
  function sortEdgesByOpportunity(edges){
    return [...(edges||[])].sort((a,b)=>opportunityScore(b)-opportunityScore(a)||String(a?.market?.away||'').localeCompare(String(b?.market?.away||'')));
  }

  return {VERSION,num,impliedAmerican,decimalFromAmerican,fairAmerican,evAmerican,ageSeconds,sideEdge,chooseMoneylineSide,trustMoneyline,localKNoVig,kSharpReference,localStarterKMarket,kMarketReference,chooseStarterKSide,trustStarterK,opportunityRiskPenalty,opportunityScore,opportunityLabel,sortEdgesByOpportunity};
});
