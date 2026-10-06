(() => {
  'use strict';

  const VERSION='1.4';
  const MODEL_VERSION='mlb-k-v0.8.4-projection-integrity-2026-09-13';
  const CALIBRATION_STATUS='PROSPECTIVE_INPUT_MIGRATION';
  const SLUG={K:'player-strikeouts',OUTS:'player-pitcher-outs',ER:'player-earned-runs',HA:'player-hits-allowed',BB:'player-walks'};
  const LABEL={K:'Strikeouts',OUTS:'Pitcher Outs',ER:'Earned Runs',HA:'Hits Allowed',BB:'Pitcher Walks'};
  const RANGES={K:[0,60],Whiff:[0,65],SwStr:[0,35],Contact:[35,100]};
  const TARGET_K_MARKET_WEIGHT=0;
  const SMALL_SAMPLE_BF=180;
  const SKILL_NEUTRAL={K:22.5,Whiff:25,SwStr:11.5,Contact:75};

  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const finite=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v));
  const num=(v,f=null)=>finite(v)?Number(v):f;
  function americanImplied(odds){const o=num(odds);if(o===null||o===0)return null;return o<0?(-o)/((-o)+100):100/(o+100);}
  function fairAmerican(p){p=num(p);if(p===null||p<=0||p>=1)return null;return p>=.5?Math.round(-100*p/(1-p)):Math.round(100*(1-p)/p);}
  function profitMultiple(odds){const o=num(odds);if(o===null||o===0)return null;return o>0?o/100:100/Math.abs(o);}
  function evAmerican(p,odds){const b=profitMultiple(odds);return b===null?null:p*b-(1-p);}
  function noVigOver(m){const o=americanImplied(m?.representative?.overOdds),u=americanImplied(m?.representative?.underOdds);return finite(o)&&finite(u)&&o+u>0?o/(o+u):null;}
  function poissonCdf(k,lambda){if(!finite(lambda)||lambda<=0)return k>=0?1:0;if(k<0)return 0;let term=Math.exp(-lambda),sum=term;for(let i=1;i<=k;i++){term*=lambda/i;sum+=term;}return clamp(sum,0,1);}
  function poissonOver(line,lambda){if(!finite(line)||!finite(lambda))return null;const threshold=Math.floor(Number(line))+1;return clamp(1-poissonCdf(threshold-1,lambda),0,1);}
  function overdispersedPoissonOver(line,lambda,uncertaintyMultiplier=1){if(!finite(line)||!finite(lambda))return null;const u=clamp(num(uncertaintyMultiplier,1),1,1.7),d=.18*u;const m=[1-d,1-d/2,1,1+d/2,1+d],w=[.08,.22,.40,.22,.08];return w.reduce((s,x,i)=>s+x*poissonOver(line,Math.max(.05,lambda*m[i])),0);}
  function solvePoissonMeanForOver(line,target){if(!finite(line)||!finite(target))return null;const p=clamp(Number(target),.03,.97);let lo=.05,hi=Math.max(12,Number(line)*2.4+6);for(let i=0;i<55;i++){const mid=(lo+hi)/2;if(poissonOver(line,mid)<p)lo=mid;else hi=mid;}return(lo+hi)/2;}
  function recentMean(values=[],maxN=12){const xs=(values||[]).map(Number).filter(Number.isFinite).slice(-maxN);if(!xs.length)return null;let sw=0,sx=0;xs.forEach((x,i)=>{const age=xs.length-1-i,w=Math.pow(.90,age);sx+=x*w;sw+=w;});return sw?sx/sw:null;}
  function weightedStd(values=[],mean=null,maxN=12){const xs=(values||[]).map(Number).filter(Number.isFinite).slice(-maxN);if(xs.length<2)return null;const mu=finite(mean)?Number(mean):recentMean(xs,maxN);let sw=0,ss=0;xs.forEach((x,i)=>{const age=xs.length-1-i,w=Math.pow(.90,age);ss+=w*Math.pow(x-mu,2);sw+=w;});return sw?Math.sqrt(ss/sw):null;}
  const logit=p=>{p=clamp(p,.001,.999);return Math.log(p/(1-p));};
  const logistic=x=>1/(1+Math.exp(-x));

  function shrinkSmallSample(current,currentBF,previous,previousBF,neutral){
    const cur=num(current),n=Math.max(0,num(currentBF,0));
    if(cur===null)return num(previous,neutral);
    if(n>=SMALL_SAMPLE_BF)return cur;
    const prior=(finite(previous)&&num(previousBF,0)>=60)?Number(previous):Number(neutral);
    const w=clamp(n/SMALL_SAMPLE_BF,0,1);
    return w*cur+(1-w)*prior;
  }
  function adjustedPitcherSkill(row){
    if(!row)return null;
    const n=num(row.sampleCurrent,row.pa)||0,prevN=num(row.samplePrevious,0)||0;
    const currentSource=/^current/.test(String(row.sourceSeason||''));
    if(!currentSource)return {...row,rawK:row.K,rawWhiff:row.Whiff,rawSwStr:row.SwStr,rawContact:row.Contact,sampleAdjusted:false,sampleAdjustmentWeight:1};
    const w=clamp(n/SMALL_SAMPLE_BF,0,1);
    return {...row,
      rawK:row.K,rawWhiff:row.Whiff,rawSwStr:row.SwStr,rawContact:row.Contact,
      K:shrinkSmallSample(row.K,n,row.previousK,prevN,SKILL_NEUTRAL.K),
      Whiff:shrinkSmallSample(row.Whiff,n,row.previousWhiff,prevN,SKILL_NEUTRAL.Whiff),
      SwStr:shrinkSmallSample(row.SwStr,n,row.previousSwStr,prevN,SKILL_NEUTRAL.SwStr),
      Contact:shrinkSmallSample(row.Contact,n,row.previousContact,prevN,SKILL_NEUTRAL.Contact),
      sampleAdjusted:n<SMALL_SAMPLE_BF,sampleAdjustmentWeight:w};
  }
  function workloadStateFromOuts(outs){
    const line=num(outs?.representative?.line),season=marketSeasonAverage(outs);
    if(line===null)return{state:'UNANCHORED',line:null,seasonAverage:season,limited:false};
    if(line<=7.5)return{state:'OPENER_LIKE',line,seasonAverage:season,limited:true};
    if(line<=14.5)return{state:'LIMITED',line,seasonAverage:season,limited:true};
    return{state:'NORMAL',line,seasonAverage:season,limited:false};
  }
  function confidenceFromSamples(row,lowPa,workload){
    const cur=num(row?.sampleCurrent,row?.pa)||0,prev=num(row?.samplePrevious,0)||0;
    let level=(cur>=250&&lowPa<=1)?'High':((cur>=100||prev>=180)&&lowPa<=2?'Medium':'Low');
    if(workload?.limited)level=level==='High'?'Medium':'Low';
    return level;
  }

  function projectionIntegrity({
    expectedOuts=null,recentOuts=null,seasonOuts=null,
    pitcherK=null,opponentK=null,matchupK=null,
    structuralK=null,recentK=null,seasonK=null,
    workloadState='UNANCHORED'
  }={}){
    const reasons=[],warnings=[];
    const eo=num(expectedOuts),ro=num(recentOuts),so=num(seasonOuts);
    const pk=num(pitcherK),ok=num(opponentK),mk=num(matchupK);
    const sk=num(structuralK),rk=num(recentK),sek=num(seasonK);
    const hist=[rk,sek].filter(Number.isFinite);
    const historicalK=hist.length?hist.reduce((a,b)=>a+b,0)/hist.length:null;
    const expectedIP=eo===null?null:eo/3;

    if(pk!==null&&pk<3) reasons.push(`pitcher K% implausible (${pk.toFixed(2)}%); possible fraction/percent schema error`);
    if(ok!==null&&ok<8) reasons.push(`opponent K% implausible (${ok.toFixed(2)}%); possible lineup metric schema error`);
    if(mk!==null&&mk<8) reasons.push(`matchup K% implausible (${mk.toFixed(2)}%); extreme low-K state`);

    if(workloadState==='NORMAL'&&eo!==null&&eo<12)
      reasons.push(`normal starter expected workload only ${expectedIP.toFixed(1)} IP`);
    if(workloadState==='NORMAL'&&eo!==null&&ro!==null&&ro>=15&&eo<ro-4.5)
      reasons.push(`expected outs ${eo.toFixed(1)} conflict with recent starter outs ${ro.toFixed(1)}`);
    if(workloadState==='NORMAL'&&eo!==null&&so!==null&&so>=15&&eo<so-4.5)
      reasons.push(`expected outs ${eo.toFixed(1)} conflict with season starter outs ${so.toFixed(1)}`);

    if(workloadState==='NORMAL'&&sk!==null&&historicalK!==null&&historicalK>=3.5&&sk<historicalK*.50)
      reasons.push(`structural K ${sk.toFixed(2)} is less than 50% of recent/season K baseline ${historicalK.toFixed(2)}`);

    if(workloadState==='NORMAL'&&mk!==null&&pk!==null&&ok!==null){
      const floor=Math.max(8,Math.min(pk,ok)-10);
      if(mk<floor) warnings.push(`matchup K% ${mk.toFixed(1)} unusually far below pitcher/opponent K context`);
    }

    return {ok:reasons.length===0,state:reasons.length?'BLOCKED':'PASS',reasons,warnings,
      expectedIP,expectedOuts:eo,recentOuts:ro,seasonOuts:so,pitcherK:pk,opponentK:ok,matchupK:mk,
      structuralK:sk,recentK:rk,seasonK:sek,historicalK,workloadState};
  }

  function marketImpliedMean(m,fallbackLineOnly=true){const line=num(m?.representative?.line);if(line===null)return null;const q=noVigOver(m);if(finite(q)){const solved=solvePoissonMeanForOver(line,q);if(finite(solved))return solved;}return fallbackLineOnly?line:null;}
  function marketRecent(m){return Array.isArray(m?.statistics?.overall?.l30)?m.statistics.overall.l30:[];}
  function marketSeasonAverage(m){return num(m?.statistics?.overall?.season?.average);}
  function marketHasHistory(m){return recentMean(marketRecent(m))!==null||marketSeasonAverage(m)!==null;}
  function marketHasAnyData(m){return !!m&&(finite(m?.representative?.line)||marketHasHistory(m));}
  function blendedCountExpectation(m,neutral,recentWeight,marketWeight){
    const market=marketImpliedMean(m),recent=recentMean(marketRecent(m)),season=marketSeasonAverage(m);let sx=0,sw=0;
    if(finite(market)){sx+=market*marketWeight;sw+=marketWeight;}
    if(finite(recent)){sx+=recent*recentWeight;sw+=recentWeight;}
    if(finite(season)){sx+=season*.24;sw+=.24;}
    if(sw)return sx/sw;
    return finite(neutral)?Number(neutral):null;
  }

  function metric(row,key){const v=num(row?.[key]);const [lo,hi]=RANGES[key]||[-Infinity,Infinity];return v!==null&&v>=lo&&v<=hi?v:null;}
  function teamPrior(rows,key,neutral){let sx=0,sw=0;for(const r of rows||[]){const v=metric(r,key);if(v===null)continue;const pa=Math.max(1,num(r.pa,1));const w=Math.min(pa,450);sx+=v*w;sw+=w;}return sw?sx/sw:neutral;}
  function lineupWeightedMetric(rows,key,fallback){const orderWeights=[1.10,1.08,1.06,1.03,1,.98,.95,.92,.89];let sx=0,sw=0;(rows||[]).slice(0,9).forEach((r,i)=>{const v=metric(r,key);if(v===null)return;const pa=Math.max(0,num(r.pa,0));const rel=pa/(pa+120);const shrunk=finite(fallback)?rel*v+(1-rel)*fallback:v;const w=orderWeights[i]||.9;sx+=shrunk*w;sw+=w;});return sw?sx/sw:fallback;}

  function marketFreshness(starter,nowMs=Date.now(),keys=['OUTS','ER','HA','BB','K']){
    const rows=[];
    for(const key of keys){
      const m=starter?.markets?.[SLUG[key]];
      if(!m)continue;
      const capturedAt=m?.observedAt||m?.representative?.capturedAt||null;const t=Date.parse(capturedAt||'');
      rows.push({market:LABEL[key],capturedAt,ageMinutes:Number.isFinite(t)?Math.max(0,(nowMs-t)/60000):null});
    }
    const times=rows.map(x=>Date.parse(x.capturedAt||'')).filter(Number.isFinite);
    const ages=rows.map(x=>x.ageMinutes).filter(Number.isFinite);
    return {rows,oldest:ages.length?Math.max(...ages):null,skew:times.length>=2?(Math.max(...times)-Math.min(...times))/60000:times.length===1?0:null};
  }

  function independentBlend(structuralK,recentK,seasonK){
    let weighted=0,weight=0;const raw={structural:.55,recent:.15,season:.08};const used={structural:0,recent:0,season:0};
    const add=(name,v,w)=>{if(finite(v)){weighted+=Number(v)*w;weight+=w;used[name]=w;}};
    add('structural',structuralK,raw.structural);add('recent',recentK,raw.recent);add('season',seasonK,raw.season);
    const normalized={};for(const k of Object.keys(used))normalized[k]=weight?used[k]/weight:0;
    return {value:weight?weighted/weight:structuralK,rawWeights:raw,normalizedWeights:normalized,totalWeight:weight};
  }

  function buildDistribution(starter,lineupRows,pitcherRow,nowMs=Date.now()){
    pitcherRow=adjustedPitcherSkill(pitcherRow);
    const k=starter.markets?.[SLUG.K]||null,outs=starter.markets?.[SLUG.OUTS]||null,er=starter.markets?.[SLUG.ER]||null,ha=starter.markets?.[SLUG.HA]||null,bb=starter.markets?.[SLUG.BB]||null;
    const outsSeason=marketSeasonAverage(outs);
    const workloadState=workloadStateFromOuts(outs);
    const expectedER=blendedCountExpectation(er,2.6,.34,.66);
    const expectedHits=blendedCountExpectation(ha,5.0,.36,.64);
    const expectedWalks=blendedCountExpectation(bb,2.0,.36,.64);
    let expectedOuts=blendedCountExpectation(outs,16.5,.36,.64);
    const outsLine=num(outs?.representative?.line);
    const openerLike=workloadState.state==='OPENER_LIKE'||(finite(outsSeason)&&outsSeason<=10);
    const leash=clamp(.28*((expectedER??2.6)-2.6)+.08*((expectedHits??5)-5)+.15*((expectedWalks??2)-2),-.75,1.15);
    expectedOuts=clamp((expectedOuts??16.5)-leash,3,23.5);
    let expectedBF=expectedOuts+(expectedHits??5)+(expectedWalks??2)+.30;
    expectedBF=clamp(expectedBF,openerLike?3.5:10,openerLike?14:33);

    const pitcherK=metric(pitcherRow,'K'),pitcherWhiff=metric(pitcherRow,'Whiff'),pitcherSwStr=metric(pitcherRow,'SwStr'),pitcherContact=metric(pitcherRow,'Contact');
    const teamK=teamPrior(lineupRows,'K',22.5),teamWhiff=teamPrior(lineupRows,'Whiff',25),teamSwStr=teamPrior(lineupRows,'SwStr',11.5),teamContact=teamPrior(lineupRows,'Contact',75);
    const lineupK=lineupWeightedMetric(lineupRows,'K',teamK);
    const opponentK=.72*lineupK+.28*teamK;
    let matchupK=logistic(logit(pitcherK/100)+logit(opponentK/100)-logit(.225));
    const oppWhiff=lineupWeightedMetric(lineupRows,'Whiff',teamWhiff),oppSwStr=lineupWeightedMetric(lineupRows,'SwStr',teamSwStr),oppContact=lineupWeightedMetric(lineupRows,'Contact',teamContact);
    matchupK+=(pitcherWhiff-25)*.0012+(oppWhiff-25)*.0009;
    matchupK+=(pitcherSwStr-11.5)*.0018+(oppSwStr-11.5)*.0012;
    matchupK-=(pitcherContact-75)*.0006+(oppContact-75)*.0006;
    matchupK=clamp(matchupK,.06,.46);
    const structuralK=expectedBF*matchupK;
    const recentK=recentMean(marketRecent(k)),seasonK=marketSeasonAverage(k),recentSd=weightedStd(marketRecent(k),recentK);
    const recentOuts=recentMean(marketRecent(outs));
    const blend=independentBlend(structuralK,recentK,seasonK);
    const physicalCeiling=Math.max(.5,Math.min(18,expectedBF*.75));
    const expectedK=clamp(blend.value,.15,physicalCeiling);
    const integrity=projectionIntegrity({expectedOuts,recentOuts,seasonOuts:outsSeason,pitcherK,opponentK,
      matchupK:matchupK*100,structuralK,recentK,seasonK,workloadState:workloadState.state});

    const freshnessKeys=['OUTS','ER','HA','BB'];if(k)freshnessKeys.push('K');
    const fresh=marketFreshness(starter,nowMs,freshnessKeys);
    const freshnessWarning=fresh.rows.some(x=>!finite(x.ageMinutes))?'structured model-source timestamp missing':fresh.oldest===null?'structured model-source timestamps missing':fresh.oldest>20?`structured model package stale (${Math.round(fresh.oldest)}m)`:fresh.skew!==null&&fresh.skew>2?`structured market sync skew ${fresh.skew.toFixed(1)}m`:null;
    const lowPa=lineupRows.filter(x=>num(x.pa,0)<10).length;
    const confidence=confidenceFromSamples(pitcherRow,lowPa,workloadState);
    const sampleUncertainty=pitcherRow.sampleAdjusted?(1-clamp(num(pitcherRow.sampleAdjustmentWeight,1),0,1))*.35:0;
    const workloadUncertainty=workloadState.limited?.25:0;
    const uncertaintyMultiplier=clamp(1+sampleUncertainty+workloadUncertainty,1,1.7);
    const localLine=num(k?.representative?.line),localOverOdds=num(k?.representative?.overOdds),localUnderOdds=num(k?.representative?.underOdds),localBook=k?.representative?.sportsbook||null,localBookSlug=k?.representative?.sportsbookSlug||null,localCapturedAt=k?.observedAt||k?.representative?.capturedAt||null,localMarketState=k?.state||null;
    const base={
      modelVersion:MODEL_VERSION,calibrationStatus:CALIBRATION_STATUS,
      player:starter.officialName,team:starter.team,officialMlbId:starter.officialMlbId,gamePk:starter.gamePk||null,
      role:'SP',openerLike,workloadState:workloadState.state,workloadLimited:workloadState.limited,roleWarning:openerLike?'opener/bulk workload detected from structured Outs context':workloadState.limited?'limited current-game workload from Pitcher Outs market':null,
      expectedK,distributionMean:expectedK,targetKMarketExcludedFromExpectedK:true,targetKMarketWeight:TARGET_K_MARKET_WEIGHT,distributionIndependentOfTargetKLine:true,
      localKLine:localLine,localKOverOdds:localOverOdds,localKUnderOdds:localUnderOdds,localKBook:localBook,localKBookSlug:localBookSlug,localKCapturedAt:localCapturedAt,localKMarketState:localMarketState,kMarketOffers:Array.isArray(k?.offers)?k.offers.map(x=>({sportsbook:{name:x?.sportsbook?.name||null,slug:x?.sportsbook?.slug||null},line:num(x?.line),odds:{over:num(x?.odds?.over),under:num(x?.odds?.under)}})):[],
      confidence,uncertaintyMultiplier,projectionIntegrity:integrity,sampleAdjustment:{applied:!!pitcherRow.sampleAdjusted,currentBF:num(pitcherRow.sampleCurrent,pitcherRow.pa)||0,previousBF:num(pitcherRow.samplePrevious,0)||0,currentWeight:num(pitcherRow.sampleAdjustmentWeight,1),rawK:num(pitcherRow.rawK),adjustedK:num(pitcherRow.K)},marketFreshness:fresh.rows,oldestMarketAgeMinutes:fresh.oldest,captureSkewMinutes:fresh.skew,freshnessWarning,sourceFreshLimitMinutes:20,sourceMaxSkewMinutes:2,
      components:{expectedBF,expectedOuts,expectedHits,expectedWalks,expectedER,workloadState:workloadState.state,workloadLimited:workloadState.limited,uncertaintyMultiplier,pitcherK,opponentK,lineupK,matchupK:matchupK*100,structuralK,recentK,seasonK,recentSd,recentKValues:marketRecent(k).map(Number).filter(Number.isFinite).slice(-10),recentOuts,seasonOuts:outsSeason,projectionIntegrity:integrity,recentOutsValues:marketRecent(outs).map(Number).filter(Number.isFinite).slice(-10),pitcherWhiff,oppWhiff,pitcherSwStr,oppSwStr,pitcherContact,oppContact,pitcherGrade:num(k?.statistics?.overall?.pitcherGrade),targetKMarketWeight:TARGET_K_MARKET_WEIGHT,blendWeights:blend.normalizedWeights,physicalCeiling},
      opponentRankContext:starter.opponentRankContext||null,
      metricValidation:{ok:true,invalid:[],checked:4+lineupRows.length*4,valid:4+lineupRows.length*4,schemaIntegrityFailed:false,pitcherSchemaFailed:false,opponentSchemaFailed:false,pitcher:{ok:true,valid:4,checked:4,invalid:[],schemaFailed:false},opponent:{ok:true,valid:lineupRows.length*4,checked:lineupRows.length*4,invalid:[],schemaFailed:false}},
      sourceProvenance:{pitcherSkill:'Baseball Savant Custom Leaderboard (current season with prior-season fallback)',lineupSkill:'MLB official batting order + Baseball Savant player IDs',workloadMarkets:'PropsMadness table API (Outs + ER + Hits Allowed + Walks current/history)',kHistory:'PropsMadness K recent/season history when available; current K line/price excluded from expected-K mean',opponentRanks:'PropsMadness ordinal team-rank context only',targetMarketTruth:'PropsMadness sportsbook offers in Trust Layer; Pinnacle/Circa sharp reference when same-line two-sided quotes are available; OddsPapi reserved for supported game markets'}
    };
    if(localLine!==null)return evaluateAtLine(base,localLine,{overOdds:localOverOdds,underOdds:localUnderOdds,marketOverProb:noVigOver(k),evaluationSource:'PropsMadness local diagnostic'});
    return {...base,line:null,overOdds:null,underOdds:null,overProb:null,underProb:null,sides:null,bestPricedSide:null,side:null,probability:null,fair:null,listedOdds:null,breakEven:null,ev:null,edge:null,marketSideProb:null,evaluationSource:null};
  }

  function evaluateAtLine(distribution,line,{overOdds=null,underOdds=null,marketOverProb=null,evaluationSource='external market'}={}){
    if(!distribution||!finite(distribution.expectedK)||!finite(line))return null;
    const l=Number(line),overProb=overdispersedPoissonOver(l,distribution.expectedK,distribution.uncertaintyMultiplier||1),underProb=1-overProb;
    const quote=(side,p,odds,mp)=>({side,probability:p,fair:fairAmerican(p),listedOdds:finite(odds)?Number(odds):null,breakEven:americanImplied(odds),marketSideProb:finite(mp)?Number(mp):null,edge:finite(mp)?p-Number(mp):null,ev:finite(odds)?evAmerican(p,odds):null});
    const sides={over:quote('Over',overProb,overOdds,marketOverProb),under:quote('Under',underProb,underOdds,finite(marketOverProb)?1-Number(marketOverProb):null)};
    const bestPricedSide=[sides.over,sides.under].filter(x=>finite(x.ev)).sort((a,b)=>b.ev-a.ev)[0]||null;
    const selected=overProb>=underProb?sides.over:sides.under;
    return {...distribution,line:l,overOdds:finite(overOdds)?Number(overOdds):null,underOdds:finite(underOdds)?Number(underOdds):null,overProb,underProb,sides,bestPricedSide,side:selected.side,probability:selected.probability,fair:selected.fair,listedOdds:selected.listedOdds,breakEven:selected.breakEven,ev:selected.ev,edge:selected.edge,marketSideProb:selected.marketSideProb,evaluationSource};
  }

  function projection(starter,lineupRows,pitcherRow,nowMs=Date.now()){return buildDistribution(starter,lineupRows,pitcherRow,nowMs);}
  function prepareSavantRow(r){if(!r)return null;return{mlbId:String(r.playerId),name:r.name||null,pa:num(r.pa,0),K:num(r.kPct),Whiff:num(r.whiffPct),SwStr:num(r.swStrPct),Contact:num(r.contactPct),BB:num(r.bbPct),sourceSeason:r.sourceSeason||null,sampleCurrent:num(r.sampleCurrent,0),samplePrevious:num(r.samplePrevious,0),previousK:num(r.previousK),previousWhiff:num(r.previousWhiff),previousSwStr:num(r.previousSwStr),previousContact:num(r.previousContact)};}
  function validSkillRow(r){return r&&metric(r,'K')!==null&&metric(r,'Whiff')!==null&&metric(r,'SwStr')!==null&&metric(r,'Contact')!==null;}
  function savantRow(bundle,id,{minCurrent=30,minPrevious=60}={}){
    const key=String(id||'');if(!key)return null;
    const current=bundle?.current?.byId?.get?.(key)||bundle?.byId?.get?.(key)||null;
    const previous=bundle?.previous?.byId?.get?.(key)||null;
    const prevFields=previous?{previousK:num(previous.kPct),previousWhiff:num(previous.whiffPct),previousSwStr:num(previous.swStrPct),previousContact:num(previous.contactPct)}:{};
    if(current&&num(current.pa,0)>=minCurrent)return {...current,...prevFields,sourceSeason:'current',sampleCurrent:num(current.pa,0),samplePrevious:num(previous?.pa,0)};
    if(previous&&num(previous.pa,0)>=minPrevious)return {...previous,sourceSeason:'previous',sampleCurrent:num(current?.pa,0),samplePrevious:num(previous.pa,0)};
    if(current)return {...current,...prevFields,sourceSeason:'current-small',sampleCurrent:num(current.pa,0),samplePrevious:num(previous?.pa,0)};
    if(previous)return {...previous,sourceSeason:'previous-small',sampleCurrent:0,samplePrevious:num(previous.pa,0)};
    return null;
  }
  function usableMarketLine(m){return finite(m?.representative?.line);}

  function buildBoard({starterBoard,lineupsByPk,pitcherSavant,batterSavant,nowMs=Date.now()}){
    const games=[];let ready=0,blocked=0,watch=0;
    const getLineups=pk=>lineupsByPk instanceof Map?lineupsByPk.get(String(pk)):lineupsByPk?.[String(pk)];
    for(const g of starterBoard?.games||[]){
      if(!g.pregame)continue;
      const game={gamePk:g.gamePk,matchup:`${g.away} @ ${g.home}`,away:g.away,home:g.home,startAt:g.startAt,sourceState:g.state,starters:[]};
      const lu=getLineups(g.gamePk)||{};
      for(const side of ['away','home']){
        const st=g.starters?.[side]||{};const hard=[];const warnings=[];
        const oppSide=side==='away'?'home':'away';const oppLineup=lu?.[oppSide]||{state:'PENDING',hitters:[],reason:'official lineup unavailable'};
        if(g.state!=='VERIFIED'||st.identityState!=='VERIFIED')hard.push('official starter/event identity not verified');
        const outs=st.markets?.[SLUG.OUTS],er=st.markets?.[SLUG.ER],ha=st.markets?.[SLUG.HA],bb=st.markets?.[SLUG.BB],k=st.markets?.[SLUG.K];
        if(!usableMarketLine(outs))hard.push('current Pitcher Outs line missing; workload anchor unavailable');
        for(const [key,m] of [['ER',er],['HA',ha],['BB',bb]]){
          if(!marketHasAnyData(m))hard.push(`${LABEL[key]} structured line/history unavailable`);
          else if(!usableMarketLine(m))warnings.push(`${LABEL[key]} current line unavailable; using structured recent/season history`);
        }
        if(!marketHasAnyData(k))warnings.push('PropsMadness K history/line unavailable; expected K is structural-only beyond Savant skill and workload');
        else if(!usableMarketLine(k))warnings.push('PropsMadness current K line unavailable; independent distribution is retained but Trust has no actionable K market');
        const partialCount=Object.values(SLUG).filter(slug=>usableMarketLine(st.markets?.[slug])&&st.markets?.[slug]?.state==='PARTIAL').length;
        if(partialCount)warnings.push(`${partialCount} PropsMadness market(s) have partial local pricing; line remains usable but local no-vig context is incomplete`);
        if(oppLineup.state!=='OFFICIAL'||oppLineup.hitters?.length!==9)hard.push(oppLineup.reason||`opponent lineup ${oppLineup.state||'unknown'}`);

        const pRaw=savantRow(pitcherSavant,st.officialMlbId,{minCurrent:30,minPrevious:60});const p=prepareSavantRow(pRaw);
        if(!p||!validSkillRow(p))hard.push('starter missing required Baseball Savant K/Whiff/Swing skill row');
        else if(/small/.test(p.sourceSeason||''))warnings.push(`starter Savant sample is small (${Math.round(p.pa)} BF)`);
        else if(p.sourceSeason==='previous')warnings.push(`starter uses prior-season Savant skill fallback (current ${Math.round(p.sampleCurrent||0)} BF)`);

        const hitters=[];const missing=[];const hitterWarnings=[];
        for(const h of oppLineup.hitters||[]){
          const raw=savantRow(batterSavant,h.mlbId,{minCurrent:20,minPrevious:80});const r=prepareSavantRow(raw);
          if(!r||!validSkillRow(r))missing.push(`${h.name||h.mlbId}`);
          else {hitters.push({...r,order:h.order,mlbId:String(h.mlbId),name:h.name||r.name});if(/small/.test(r.sourceSeason||''))hitterWarnings.push(h.name||h.mlbId);}
        }
        if(missing.length)hard.push(`Savant lineup metrics missing for ${missing.join(', ')}`);
        if(hitters.length!==9)hard.push(`structured lineup skill coverage ${hitters.length}/9`);
        if(hitterWarnings.length)warnings.push(`small-sample Savant hitter rows: ${hitterWarnings.join(', ')}`);

        let proj=null,status='BLOCKED';
        if(!hard.length){
          const stForProj={...st,gamePk:g.gamePk};proj=buildDistribution(stForProj,hitters,p,nowMs);
          if(!proj)hard.push('structured K distribution unavailable');
          else {
            if(proj.freshnessWarning)hard.push(proj.freshnessWarning);
            if(proj.projectionIntegrity?.ok===false)hard.push(...proj.projectionIntegrity.reasons.map(x=>`K projection integrity: ${x}`));
            if(proj.projectionIntegrity?.warnings?.length)warnings.push(...proj.projectionIntegrity.warnings.map(x=>`K projection integrity review: ${x}`));
            if(proj.openerLike)warnings.push(proj.roleWarning||'opener/bulk role');
            else if(proj.workloadLimited)warnings.push(proj.roleWarning||'limited current-game workload');
            if(proj.sampleAdjustment?.applied)warnings.push(`pitcher skill small-sample shrinkage applied (${Math.round(proj.sampleAdjustment.currentBF)} current BF, ${(proj.sampleAdjustment.currentWeight*100).toFixed(0)}% current weight)`);
            if(proj.confidence!=='High')warnings.push(`projection confidence ${proj.confidence}`);
            status=hard.length?'BLOCKED':warnings.length?'WATCH':'READY';
          }
        }
        if(status==='READY')ready++; else if(status==='WATCH')watch++; else blocked++;
        const reasons=[...hard,...warnings];
        game.starters.push({side,team:st.team,opponent:st.opponent,officialName:st.officialName,officialMlbId:st.officialMlbId||null,status,reasons,hardReasons:hard,watchReasons:warnings,lineupState:oppLineup.state,lineupSource:oppLineup.source||null,lineupCount:oppLineup.hitters?.length||0,savantLineupCount:hitters.length,pitcherSavantBF:p?.pa??null,pitcherSavantSource:p?.sourceSeason||null,opponentRankContext:st.opponentRankContext||null,projection:proj});
      }
      games.push(game);
    }
    return {schemaVersion:3,engineVersion:VERSION,modelVersion:MODEL_VERSION,calibrationStatus:CALIBRATION_STATUS,marketSeparation:'TARGET_K_MARKET_EXCLUDED_FROM_EXPECTED_K',builtAt:new Date(nowMs).toISOString(),pregameGameCount:games.length,starterCount:games.length*2,readyCount:ready,watchCount:watch,blockedCount:blocked,games};
  }

  function audit(board){return{engineVersion:VERSION,modelVersion:board?.modelVersion,calibrationStatus:board?.calibrationStatus,marketSeparation:board?.marketSeparation,builtAt:board?.builtAt,pregameGameCount:board?.pregameGameCount||0,starterCount:board?.starterCount||0,readyCount:board?.readyCount||0,watchCount:board?.watchCount||0,blockedCount:board?.blockedCount||0,games:(board?.games||[]).map(g=>({gamePk:g.gamePk,matchup:g.matchup,startAt:g.startAt,starters:(g.starters||[]).map(s=>({side:s.side,team:s.team,player:s.officialName,mlbId:s.officialMlbId,status:s.status,reasons:s.reasons,lineupState:s.lineupState,lineupSource:s.lineupSource,lineupCount:s.lineupCount,savantLineupCount:s.savantLineupCount,pitcherSavantBF:s.pitcherSavantBF,pitcherSavantSource:s.pitcherSavantSource,opponentRankContext:s.opponentRankContext||null,...(s.projection?{expectedK:s.projection.expectedK,localLine:s.projection.localKLine,localOverOdds:s.projection.localKOverOdds,localUnderOdds:s.projection.localKUnderOdds,localBook:s.projection.localKBook,localMarketState:s.projection.localKMarketState,localOverProb:s.projection.localKLine!==null?s.projection.overProb:null,localUnderProb:s.projection.localKLine!==null?s.projection.underProb:null,targetKMarketExcludedFromExpectedK:s.projection.targetKMarketExcludedFromExpectedK,distributionIndependentOfTargetKLine:s.projection.distributionIndependentOfTargetKLine,confidence:s.projection.confidence,projectionIntegrity:s.projection.projectionIntegrity,workloadState:s.projection.workloadState,workloadLimited:s.projection.workloadLimited,uncertaintyMultiplier:s.projection.uncertaintyMultiplier,sampleAdjustment:s.projection.sampleAdjustment,components:s.projection.components}: {})}))}))};}

  const api={VERSION,MODEL_VERSION,CALIBRATION_STATUS,TARGET_K_MARKET_WEIGHT,SLUG,LABEL,americanImplied,fairAmerican,noVigOver,poissonOver,overdispersedPoissonOver,solvePoissonMeanForOver,recentMean,weightedStd,marketImpliedMean,marketHasHistory,marketHasAnyData,blendedCountExpectation,teamPrior,lineupWeightedMetric,marketFreshness,independentBlend,shrinkSmallSample,adjustedPitcherSkill,workloadStateFromOuts,confidenceFromSamples,projectionIntegrity,buildDistribution,evaluateAtLine,projection,savantRow,usableMarketLine,buildBoard,audit};
  if(typeof window!=='undefined')window.MODEL_STRUCTURED_K_CORE=api;
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})();
