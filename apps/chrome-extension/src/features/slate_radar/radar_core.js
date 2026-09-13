(() => {
  'use strict';
  const VERSION='1.7';
  const MODE='PRELINEUP_ACTIVE_ROSTER_PROXY';
  const RESEARCH_VERSION='RCE-0.5';
  const MIN_PROXY_HITTERS=7;
  const ML_TARGET_EDGE=0.03;
  const num=(v,f=null)=>{if(v===null||v===undefined||v==='')return f;const n=Number(v);return Number.isFinite(n)?n:f;};
  const clamp=(x,lo,hi)=>Math.max(lo,Math.min(hi,x));
  const mean=a=>{const xs=(a||[]).map(Number).filter(Number.isFinite);return xs.length?xs.reduce((s,x)=>s+x,0)/xs.length:null;};
  const get=(m,k)=>m instanceof Map?m.get(String(k)):m?.[String(k)];
  const americanFromProb=p=>{p=clamp(Number(p),.01,.99);return p>=.5?-Math.round(100*p/(1-p)):Math.round(100*(1-p)/p);};
  const oddsText=n=>Number.isFinite(Number(n))?(Number(n)>0?`+${Math.round(Number(n))}`:`${Math.round(Number(n))}`):null;
  const isPitcher=e=>{const p=e?.position||e?.person?.primaryPosition||{};return /pitcher/i.test(String(p?.type||p?.name||''))||String(p?.abbreviation||'').toUpperCase()==='P';};
  const neutralMlRow=i=>({mlbId:`proxy-neutral-${i}`,name:'League-average proxy',PA:0,metrics:{'K%':22.5,'BB%':8.5,'Whiff%':25,'Contact%':75,'SwStr%':11.5,'BA':.245,'xBA':.245,'xSLG':.400,'xwOBA':.320,'ISO':.170,'HardHit%':39,'Barrel%':8,'wRC+':100},sourceSeason:'neutral-proxy',proxyNeutral:true});
  const asKRow=r=>({mlbId:r.mlbId,name:r.name,pa:num(r.PA,0),K:num(r.metrics?.['K%'],22.5),Whiff:num(r.metrics?.['Whiff%'],25),SwStr:num(r.metrics?.['SwStr%'],11.5),Contact:num(r.metrics?.['Contact%'],75),BB:num(r.metrics?.['BB%'],8.5),sourceSeason:r.sourceSeason||null,proxyNeutral:!!r.proxyNeutral});

  function enrichHitter(id,name,batterSavant,savantCore,wrcBundle,wrcCore,mlCore){
    const r=mlCore?.structuredSavantRow?.(batterSavant,id,savantCore,{minCurrent:20,minPrevious:80});
    if(!r)return null;
    const wr=wrcCore?.getForSavantRow?.(wrcBundle,id,r)||null;
    const metrics={...(r.metrics||{}),'wRC+':Number.isFinite(num(wr?.wrcPlus,null))?Number(wr.wrcPlus):100};
    return {...r,name:name||r.name,metrics,'wRC+':metrics['wRC+'],wrcProxyFallback:!Number.isFinite(num(wr?.wrcPlus,null))};
  }

  function rosterProfile(rosterPayload,{batterSavant,savantCore,wrcBundle,wrcCore,mlCore}={}){
    const entries=(rosterPayload?.roster||[]).filter(e=>!isPitcher(e));
    const resolved=[];
    for(const e of entries){const id=String(e?.person?.id||'');if(!id)continue;const r=enrichHitter(id,e?.person?.fullName||null,batterSavant,savantCore,wrcBundle,wrcCore,mlCore);if(r)resolved.push(r);}
    resolved.sort((a,b)=>num(b.PA,0)-num(a.PA,0));
    const raw=resolved.slice(0,9),usable=raw.length,rows=[...raw];
    if(usable>=MIN_PROXY_HITTERS)while(rows.length<9)rows.push(neutralMlRow(rows.length+1));
    return {status:usable>=MIN_PROXY_HITTERS?'USABLE':'INSUFFICIENT',source:'MLB active roster + Savant/FanGraphs PA-weighted regular proxy',rosterHitterCount:entries.length,resolvedHitterCount:resolved.length,usableTopNine:usable,coverage:clamp(usable/9,0,1),rows:usable>=MIN_PROXY_HITTERS?rows:raw,wrcFallbackCount:raw.filter(x=>x.wrcProxyFallback).length};
  }

  function officialProfile(lineup,{batterSavant,savantCore,wrcBundle,wrcCore,mlCore}={}){
    if(lineup?.state!=='OFFICIAL'||lineup?.hitters?.length!==9)return null;
    const rows=[];
    for(const h of lineup.hitters){const r=enrichHitter(String(h.mlbId||''),h.name||null,batterSavant,savantCore,wrcBundle,wrcCore,mlCore);if(!r)return null;rows.push({...r,order:h.order});}
    return {status:'USABLE',source:'MLB official batting order',rosterHitterCount:9,resolvedHitterCount:9,usableTopNine:9,coverage:1,rows,wrcFallbackCount:rows.filter(x=>x.wrcProxyFallback).length,official:true};
  }

  function teamProfile(teamId,teamSide,lineups,rostersByTeam,ctx){return officialProfile(lineups?.[teamSide],ctx)||rosterProfile(get(rostersByTeam,teamId),ctx);}
  function profileSnapshot(p){return{source:p?.source||null,official:!!p?.official,coverage:num(p?.coverage,0),players:(p?.rows||[]).slice(0,9).map((r,i)=>({mlbId:String(r?.playerId||r?.mlbId||''),name:r?.name||null,order:num(r?.order,i+1),pa:num(r?.PA??r?.pa,0),wrcPlus:num(r?.metrics?.['wRC+']??r?.['wRC+'],100),kPct:num(r?.metrics?.['K%']??r?.K,null)}))};}
  function stageForMl(prodGame,lineups){if(prodGame?.status==='READY'&&prodGame?.projectionEligible)return 'READY_FOR_MARKET';const n=['away','home'].filter(s=>lineups?.[s]?.state==='OFFICIAL').length;return n===1?'FINALIZING':'RADAR';}
  function stageForK(prodRow,oppLineup){if(prodRow?.projection&&['READY','WATCH'].includes(prodRow?.status))return 'READY_FOR_K_TRUST';return oppLineup?.state==='OFFICIAL'?'FINALIZING':'RADAR';}
  function tier(p){const x=Math.max(Number(p)||.5,1-(Number(p)||.5));return x>=.62?'PRIME':x>=.58?'STRONG':x>=.55?'WATCH':x>=.53?'LEAN':'LOW';}
  function preliminaryWatchPrice(p){if(!Number.isFinite(Number(p)))return null;const q=clamp(Number(p)-ML_TARGET_EDGE,.50,.90),a=americanFromProb(q);return{minimumModelEdgePP:ML_TARGET_EDGE*100,maxImpliedProbability:q,american:a,text:oddsText(a)};}

  function recentResultsProfile(teamId,payload,maxGames=10){
    const id=String(teamId||'');if(!id||!payload)return{status:'UNAVAILABLE',label:'UNKNOWN',direction:'→',games:0,wins:0,losses:0,winPct:null,runDiff:null,runDiffPerGame:null};
    const rows=[];
    for(const d of payload?.dates||[])for(const g of d?.games||[]){
      if(String(g?.status?.abstractGameState||'').toLowerCase()!=='final')continue;
      const away=String(g?.teams?.away?.team?.id||''),home=String(g?.teams?.home?.team?.id||'');if(id!==away&&id!==home)continue;
      const own=id===away?num(g?.teams?.away?.score,null):num(g?.teams?.home?.score,null),opp=id===away?num(g?.teams?.home?.score,null):num(g?.teams?.away?.score,null);if(own===null||opp===null)continue;
      rows.push({date:g?.officialDate||d?.date||null,win:own>opp,own,opp,diff:own-opp});
    }
    rows.sort((a,b)=>String(a.date||'').localeCompare(String(b.date||'')));const xs=rows.slice(-maxGames),games=xs.length,wins=xs.filter(x=>x.win).length,losses=games-wins,runDiff=xs.reduce((s,x)=>s+x.diff,0),winPct=games?wins/games:null,rdpg=games?runDiff/games:null;
    if(games<3)return{status:'INSUFFICIENT',label:'UNKNOWN',direction:'→',games,wins,losses,winPct,runDiff,runDiffPerGame:rdpg};
    const score=(winPct-.5)*2+clamp((rdpg||0)/3,-1,1)*.35;const label=score>=.22?'HOT':score<=-.22?'COLD':'AVERAGE';return{status:'READY',label,direction:label==='HOT'?'↑':label==='COLD'?'↓':'→',games,wins,losses,winPct,runDiff,runDiffPerGame:rdpg,score,results:xs};
  }

  function kRecentForm(c={}){
    const values=(c.recentKValues||[]).map(Number).filter(Number.isFinite).slice(-10),recent=num(c.recentK,null),season=num(c.seasonK,null),sd=Math.max(1,num(c.recentSd,1.5));
    if(recent===null&&values.length<3)return{label:'UNKNOWN',direction:'→',score:null,recentAverage:recent,seasonAverage:season,last3Average:null};
    const last3=mean(values.slice(-3)),prior3=mean(values.slice(-6,-3));let score=0,weight=0;
    if(recent!==null&&season!==null){score+=((recent-season)/sd)*.7;weight+=.7;}
    if(last3!==null&&prior3!==null){score+=((last3-prior3)/sd)*.3;weight+=.3;}
    score=weight?score/weight:0;const label=score>=.38?'HOT':score<=-.38?'COLD':'AVERAGE';return{label,direction:label==='HOT'?'↑':label==='COLD'?'↓':'→',score,recentAverage:recent,seasonAverage:season,last3Average:last3,values};
  }

  function hitRate(values,line,side,n){const xs=(values||[]).map(Number).filter(Number.isFinite).slice(-n);if(!xs.length||!Number.isFinite(Number(line)))return{hits:0,decisions:0,rate:null};let hits=0,decisions=0;for(const x of xs){if(x===Number(line))continue;decisions++;if(String(side).toLowerCase()==='over'?x>Number(line):x<Number(line))hits++;}return{hits,decisions,rate:decisions?hits/decisions:null};}

  function kResearch(projection,side,line,opponentProfile){
    const c=projection?.components||{},form=kRecentForm(c),last10=hitRate(c.recentKValues,line,side,10),last5=hitRate(c.recentKValues,line,side,5),oppK=num(c.opponentK,null),expectedOuts=num(c.expectedOuts,null),expectedIP=expectedOuts===null?null:expectedOuts/3;
    const over=String(side||'').toLowerCase()==='over';let opponentBand='NEUTRAL';if(oppK!==null)opponentBand=oppK>=24?'HIGH_K':oppK<=21?'LOW_K':'NEUTRAL';
    const opponentFit=oppK===null?'UNKNOWN':over?(oppK>=24?'FAVORABLE':oppK<=21?'UNFAVORABLE':'NEUTRAL'):(oppK<=21?'FAVORABLE':oppK>=24?'UNFAVORABLE':'NEUTRAL');
    const signals=[];if(last10.rate!==null)signals.push({name:'recent distribution',value:last10.rate>=.7?1:last10.rate<=.3?-1:0,detail:`${last10.hits}/${last10.decisions} last-10 decisions on ${side} ${line}`});
    signals.push({name:'opponent K profile',value:opponentFit==='FAVORABLE'?1:opponentFit==='UNFAVORABLE'?-1:0,detail:oppK===null?'opponent K unavailable':`${oppK.toFixed(1)}% matchup K`});
    const formFit=form.label==='UNKNOWN'?0:(over?(form.label==='HOT'?1:form.label==='COLD'?-1:0):(form.label==='COLD'?1:form.label==='HOT'?-1:0));signals.push({name:'recent form',value:formFit,detail:`${form.label} ${form.direction}`});
    const workloadFit=projection?.workloadLimited?(over?-1:1):0;signals.push({name:'workload',value:workloadFit,detail:`${projection?.workloadState||'UNKNOWN'}${expectedIP!==null?` · ${expectedIP.toFixed(1)} expected IP`:''}`});
    const vals=signals.map(x=>x.value),support=vals.filter(x=>x>0).length,conflict=vals.filter(x=>x<0).length,totalKnown=signals.filter(x=>!/UNKNOWN|unavailable/i.test(x.detail)).length;
    const recent=num(c.recentK,null),sd=Math.max(1,num(c.recentSd,1.5)),modelGap=recent===null?null:Math.abs(Number(projection?.expectedK)-recent),anomaly=modelGap!==null&&modelGap>Math.max(2.25,1.6*sd)&&last10.rate!==null&&last10.rate<.5;
    let verdict='MIXED';if(anomaly)verdict='ANOMALY';else if(conflict>=2&&support===0)verdict='CONFLICT';else if(support>=3&&conflict===0)verdict='STRONGLY_CONFIRMED';else if(support>=2&&conflict<=1)verdict='CONFIRMED';else if(totalKnown<2)verdict='INSUFFICIENT_DATA';
    const confidence=Math.round(clamp(50+support*11-conflict*14+(last10.decisions>=8?7:0)+(opponentProfile?.official?5:0),10,95));
    return{version:RESEARCH_VERSION,probabilityMutation:false,verdict,confidence,recentForm:form,last10,last5,opponentKProfile:{raw:opponentBand,fit:opponentFit,kPct:oppK},workload:{state:projection?.workloadState||'UNKNOWN',limited:!!projection?.workloadLimited,expectedOuts,expectedIP},recentKAverage:num(c.recentK,null),seasonKAverage:num(c.seasonK,null),signals,externalProjections:{status:'NOT_CONNECTED'},news:{starterConfirmed:true,officialOpponentLineup:!!opponentProfile?.official,workloadRestriction:projection?.workloadLimited?'MODEL_DETECTED_LIMITED':'NONE_DETECTED_IN_STRUCTURED_INPUTS'}};
  }

  function mlResearch(g,projection,side,recentSchedule){
    const sideKey=side===g.away?'away':'home',oppKey=sideKey==='away'?'home':'away',teamId=sideKey==='away'?g.awayTeamId:g.homeTeamId,oppId=oppKey==='away'?g.awayTeamId:g.homeTeamId,teamForm=recentResultsProfile(teamId,recentSchedule),oppForm=recentResultsProfile(oppId,recentSchedule);
    const sideRuns=sideKey==='away'?num(projection?.awayRuns,null):num(projection?.homeRuns,null),oppRuns=oppKey==='away'?num(projection?.awayRuns,null):num(projection?.homeRuns,null),sideOff=sideKey==='away'?num(projection?.awayOffenseRating,null):num(projection?.homeOffenseRating,null),oppOff=oppKey==='away'?num(projection?.awayOffenseRating,null):num(projection?.homeOffenseRating,null);
    const signals=[];let formValue=0;if(teamForm.label==='HOT'&&oppForm.label!=='HOT')formValue=1;else if(teamForm.label==='COLD'&&oppForm.label!=='COLD')formValue=-1;signals.push({name:'team recent form',value:formValue,detail:`${side} ${teamForm.label} ${teamForm.wins}-${teamForm.losses} vs opponent ${oppForm.label} ${oppForm.wins}-${oppForm.losses}`});
    const runEdge=sideRuns!==null&&oppRuns!==null?sideRuns-oppRuns:null;signals.push({name:'projected run edge',value:runEdge===null?0:runEdge>=.65?1:runEdge<=.20?-1:0,detail:runEdge===null?'run edge unavailable':`${runEdge>=0?'+':''}${runEdge.toFixed(2)} runs`});
    const offEdge=sideOff!==null&&oppOff!==null?sideOff-oppOff:null;signals.push({name:'offense rating',value:offEdge===null?0:offEdge>=3?1:offEdge<=-3?-1:0,detail:offEdge===null?'offense edge unavailable':`${offEdge>=0?'+':''}${offEdge.toFixed(1)} rating points`});
    const support=signals.filter(x=>x.value>0).length,conflict=signals.filter(x=>x.value<0).length;let verdict='MIXED';if(support===3&&conflict===0)verdict='STRONGLY_CONFIRMED';else if(support>=2&&conflict===0)verdict='CONFIRMED';else if(conflict>=2)verdict='CONFLICT';else if(teamForm.status!=='READY'&&oppForm.status!=='READY')verdict='INSUFFICIENT_DATA';const confidence=Math.round(clamp(48+support*12-conflict*15+(teamForm.games>=8&&oppForm.games>=8?8:0),15,92));
    return{version:RESEARCH_VERSION,probabilityMutation:false,verdict,confidence,recentForm:{team:teamForm,opponent:oppForm},signals,externalProjections:{status:'NOT_CONNECTED'},news:{startersConfirmed:g.state==='VERIFIED',officialLineups:null}};
  }

  function attachPublicResearch(row,research,bundle,publicResearchCore){
    if(!research)return research;
    if(!bundle||!publicResearchCore?.contextFor)return{...research,publicResearch:{status:'NOT_CONNECTED',reviewRequired:false,sources:[],probabilityMutation:false}};
    const context=publicResearchCore.contextFor(row,bundle),baseVerdict=research.baseVerdict||research.verdict,hold=row?.kind==='K'&&context?.reviewRequired;let verdict=baseVerdict,signals=(research.signals||[]).filter(x=>x.name!=='external projection');const ext=context?.externalProjection||{status:'NOT_CONNECTED'};
    if(row?.kind==='ML'&&ext.status==='CONNECTED'){const gap=Number.isFinite(Number(ext.selectedSideProbability))&&Number.isFinite(Number(row.probability))?Math.abs(Number(row.probability)-Number(ext.selectedSideProbability)):null,value=ext.agreement==='DISAGREE'?-1:(gap!==null&&gap<=.08?1:0),detail=`${ext.provider} · ${ext.agreement}${Number.isFinite(Number(ext.selectedSideProbability))?` · ${row.side} ${Math.round(Number(ext.selectedSideProbability)*1000)/10}%`:''}${gap!==null?` · gap ${(gap*100).toFixed(1)}pp`:''}`;signals.push({name:'external projection',value,detail});const support=signals.filter(x=>x.value>0).length,conflict=signals.filter(x=>x.value<0).length;if(conflict>=2)verdict='CONFLICT';else if(support>=3&&conflict===0)verdict='STRONGLY_CONFIRMED';else if(support>=2&&conflict<=1)verdict='CONFIRMED';else if(conflict>=1&&support>=1)verdict='MIXED';if(ext.agreement==='DISAGREE'){if(gap!==null&&gap>=.12)verdict='CONFLICT';else if(verdict!=='CONFLICT')verdict='MIXED';}}
    if(hold)verdict='NEWS_HOLD';return{...research,signals,baseVerdict,verdict,publicResearch:context,news:{...(research.news||{}),sourcedStatus:context?.news?.status||'NOT_REQUESTED',sourcedArticleCount:context?.news?.articles?.length||0,transactionCount:context?.transactions?.items?.length||0,reviewRequired:!!context?.reviewRequired},researchSources:context?.sources||[],externalProjections:ext};
  }

  function applyResearchBundle(board,bundle,publicResearchCore){
    if(!board)return board;
    const enrich=r=>({...r,research:attachPublicResearch(r,r.research,bundle,publicResearchCore)});
    return{...board,researchVersion:RESEARCH_VERSION,publicResearchVersion:bundle?.version||publicResearchCore?.VERSION||null,publicResearchStatus:bundle?.status||'NOT_CONNECTED',researchUpdatedAt:bundle?.updatedAt||null,probabilityMutationFromResearch:false,ml:(board.ml||[]).map(enrich),k:(board.k||[]).map(enrich)};
  }

  function mlPreviewForGame(g,ctx){
    const {lineupsByPk,rostersByTeam,pitcherSavant,savantCore,bullpensByTeam,parkBundle,parkCore,mlCore,mlBoard,recentSchedule}=ctx;
    const lu=get(lineupsByPk,g.gamePk)||{},prod=(mlBoard?.games||[]).find(x=>String(x.gamePk)===String(g.gamePk))||null;
    const base={kind:'ML',gamePk:String(g.gamePk),away:g.away,home:g.home,awayTeamId:g.awayTeamId||null,homeTeamId:g.homeTeamId||null,startAt:g.startAt,stage:stageForMl(prod,lu),preliminary:true,actionable:false,mode:MODE,officialLineups:['away','home'].filter(s=>lu?.[s]?.state==='OFFICIAL').length,productionStatus:prod?.status||'BLOCKED',productionReasons:prod?.reasons||[]};
    if(g.state!=='VERIFIED'||['away','home'].some(s=>g.starters?.[s]?.identityState!=='VERIFIED'))return{...base,status:'WAITING_STARTER',reasons:['both official/probable starter identities are required before an ML radar probability is allowed']};
    const park=parkCore?.getForVenue?.(parkBundle,g.venueName)||null;if(!park)return{...base,status:'WAITING_DATA',reasons:['structured park factor unavailable']};
    const profiles={away:teamProfile(g.awayTeamId,'away',lu,rostersByTeam,ctx),home:teamProfile(g.homeTeamId,'home',lu,rostersByTeam,ctx)};
    if(profiles.away.status!=='USABLE'||profiles.home.status!=='USABLE')return{...base,status:'WAITING_DATA',reasons:[`active-roster offense proxy insufficient: ${g.away} ${profiles.away.usableTopNine}/9, ${g.home} ${profiles.home.usableTopNine}/9`]};
    const parkConditions=parkCore.conditionLines(park),game={gamePk:g.gamePk,away:g.away,home:g.home,starters:{}};
    for(const side of ['away','home']){
      const st=g.starters?.[side]||{},team=g[side],opp=side==='away'?'home':'away';
      const p=mlCore.structuredSavantRow(pitcherSavant,st.officialMlbId,savantCore,{minCurrent:30,minPrevious:60});if(!p)return{...base,status:'WAITING_DATA',reasons:[`${side} starter Savant row unavailable`]};
      const bp=get(bullpensByTeam,`${g.gamePk}:${side}`),bpValid=bp?.validation?.status==='validated'&&Array.isArray(bp.rows)&&bp.rows.length>=4;if(!bpValid)return{...base,status:'WAITING_DATA',reasons:[`${side} structured bullpen unavailable`]};
      const workload=mlCore.workloadFromStarter(st);if(!Number.isFinite(num(workload?.IP,null)))return{...base,status:'WAITING_DATA',reasons:[`${side} pitcher workload anchor unavailable`]};
      const oppRows=profiles[opp].rows,avg=(key,f)=>{const xs=oppRows.map(x=>num(x.metrics?.[key],null)).filter(Number.isFinite);return xs.length?xs.reduce((a,b)=>a+b,0)/xs.length:f;};
      game.starters[team]={side,team,teamId:side==='away'?g.awayTeamId:g.homeTeamId,officialName:st.officialName,officialMlbId:st.officialMlbId,pitcherMetrics:p.metrics||{},opponentTeamMetrics:{'xwOBA':avg('xwOBA',.320),'BA':avg('BA',.245),'xSLG':avg('xSLG',.400),'HardHit%':avg('HardHit%',39),'Barrel%':avg('Barrel%',8),'K%':avg('K%',22.5),'BB%':avg('BB%',8.5),'Contact%':avg('Contact%',75)},lineupStatus:profiles[opp].official?'Official':'Projected roster proxy',lineup:oppRows,workload,bullpen:bp.rows,bullpenValidation:bp.validation,gameConditions:[...parkConditions]};
    }
    const projection=mlCore.projectGame(game);if(!projection?.complete)return{...base,status:'WAITING_DATA',reasons:[projection?.reason||'preliminary projection unavailable']};
    const side=projection.awayWin>=projection.homeWin?g.away:g.home,p=side===g.away?projection.awayWin:projection.homeWin,minCoverage=Math.min(profiles.away.coverage,profiles.home.coverage),proxySides=[profiles.away,profiles.home].filter(x=>!x.official).length,uncertaintyPP=2+proxySides*1.25+(1-minCoverage)*4;
    const research=mlResearch(g,projection,side,recentSchedule);research.news.officialLineups=base.officialLineups;
    return{...base,status:'CANDIDATE',side,probability:p,fairAmerican:americanFromProb(p),watchPrice:preliminaryWatchPrice(p),tier:tier(p),score:Math.max(0,(p-.5)*100-uncertaintyPP),uncertaintyPP,projection:{awayWin:projection.awayWin,homeWin:projection.homeWin,awayRuns:projection.awayRuns,homeRuns:projection.homeRuns,awayOffenseRating:projection.awayOffenseRating,homeOffenseRating:projection.homeOffenseRating,awayRunComponents:projection.awayRunComponents||null,homeRunComponents:projection.homeRunComponents||null},modelComponents:{runModel:{away:projection.awayRunComponents||null,home:projection.homeRunComponents||null},offenseRating:{away:projection.awayOffenseRating,home:projection.homeOffenseRating},winTransform:{runDiff:projection.homeRuns-projection.awayRuns,logisticScale:1.60}},research,lineupSnapshot:{away:profileSnapshot(profiles.away),home:profileSnapshot(profiles.home)},offenseProxy:{away:{source:profiles.away.source,coverage:profiles.away.coverage,usable:profiles.away.usableTopNine,official:!!profiles.away.official},home:{source:profiles.home.source,coverage:profiles.home.coverage,usable:profiles.home.usableTopNine,official:!!profiles.home.official}},reasons:['PRELIMINARY ONLY — active-roster offense proxy is replaced by the official batting order before production Trust']};
  }

  function kPreviewsForGame(g,ctx){
    const {lineupsByPk,rostersByTeam,pitcherSavant,kCore,kBoard}=ctx,lu=get(lineupsByPk,g.gamePk)||{},prodGame=(kBoard?.games||[]).find(x=>String(x.gamePk)===String(g.gamePk)),out=[];
    for(const side of ['away','home']){
      const st=g.starters?.[side]||{},opp=side==='away'?'home':'away',prodRow=prodGame?.starters?.find?.(x=>x.side===side)||null,base={kind:'K',gamePk:String(g.gamePk),away:g.away,home:g.home,startAt:g.startAt,team:st.team||g[side],player:st.officialName||null,officialMlbId:st.officialMlbId||null,stage:stageForK(prodRow,lu?.[opp]),preliminary:true,actionable:false,mode:MODE,productionStatus:prodRow?.status||'BLOCKED',productionReasons:prodRow?.reasons||[]};
      if(g.state!=='VERIFIED'||st.identityState!=='VERIFIED'){out.push({...base,status:'WAITING_STARTER',reasons:['verified starter/event identity required']});continue;}
      const profile=teamProfile(side==='away'?g.homeTeamId:g.awayTeamId,opp,lu,rostersByTeam,ctx);if(profile.status!=='USABLE'){out.push({...base,status:'WAITING_DATA',reasons:[`opponent active-roster K proxy only ${profile.usableTopNine}/9 usable hitters`]});continue;}
      const pRaw=kCore.savantRow(pitcherSavant,st.officialMlbId,{minCurrent:30,minPrevious:60}),pitcher=pRaw?{mlbId:String(pRaw.playerId),name:pRaw.name||st.officialName,pa:num(pRaw.pa,0),K:num(pRaw.kPct),Whiff:num(pRaw.whiffPct),SwStr:num(pRaw.swStrPct),Contact:num(pRaw.contactPct),BB:num(pRaw.bbPct),sourceSeason:pRaw.sourceSeason||null}:null;
      if(!pitcher||![pitcher.K,pitcher.Whiff,pitcher.SwStr,pitcher.Contact].every(Number.isFinite)){out.push({...base,status:'WAITING_DATA',reasons:['starter Savant K/Whiff/SwStr/Contact row unavailable']});continue;}
      let projection=null;try{projection=kCore.projection({...st,gamePk:g.gamePk},profile.rows.map(asKRow),pitcher,ctx.nowMs);}catch(e){out.push({...base,status:'WAITING_DATA',reasons:[e?.message||String(e)]});continue;}if(!projection){out.push({...base,status:'WAITING_DATA',reasons:['preliminary K distribution unavailable']});continue;}
      const best=projection.bestPricedSide||null,line=num(projection.localKLine,null),rawP=best?.probability??projection.probability??null,rawOdds=best?.listedOdds??projection.listedOdds??null,listedOdds=num(rawOdds,null),hasLine=line!==null,hasPrice=listedOdds!==null,p=hasLine?num(rawP,null):null,ev=hasPrice?num(best?.ev??projection.ev??null,null):null,edge=hasLine?num(best?.edge??projection.edge??null,null):null,sideName=hasLine?(best?.side||projection.side||null):null,marketState=!hasLine?'NO_MARKET':(!hasPrice?'NO_PRICE':'PRICED'),strength=p!==null?Math.abs(p-.5)*100:0,score=(marketState==='PRICED'?0:-40)+strength+(ev!==null?Math.max(-5,ev*100)*.35:0)-(1-profile.coverage)*4;
      const candidate=marketState==='PRICED'&&p!==null,research=kResearch(projection,sideName,line,profile);
      out.push({...base,status:candidate?'CANDIDATE':'DISTRIBUTION_ONLY',marketState,side:sideName,probability:p,line,listedOdds,ev,edge,expectedK:projection.expectedK,fair:hasLine?(best?.fair??projection.fair??null):null,tier:p!==null?tier(p):'LOW',score,modelComponents:projection.components||null,research,opponentProfile:{source:profile.source,coverage:profile.coverage,usable:profile.usableTopNine,official:!!profile.official},reasons:[candidate?'PRELIMINARY ONLY — opponent active-roster proxy is replaced by the official batting order before production K Trust':marketState==='NO_MARKET'?'NO CURRENT K MARKET — distribution available but no betting line/EV may be inferred':'NO CURRENT K PRICE — distribution available but EV unavailable']});
    }
    return out;
  }

  function buildBoard(args={}){const nowMs=args.nowMs??Date.now(),ctx={...args,nowMs},ml=[],k=[];for(const g of args.starterBoard?.games||[]){if(!g.pregame)continue;ml.push(mlPreviewForGame(g,ctx));k.push(...kPreviewsForGame(g,ctx));}const sorter=(a,b)=>(Number(b.score)||-999)-(Number(a.score)||-999)||String(a.startAt||'').localeCompare(String(b.startAt||''));ml.sort(sorter);k.sort(sorter);const base={schemaVersion:3,version:VERSION,researchVersion:RESEARCH_VERSION,mode:MODE,builtAt:new Date(nowMs).toISOString(),actionable:false,probabilityMutationFromResearch:false,oddsPapiRequests:0,policy:'PRELIMINARY_ONLY_NEVER_TRUST_INPUT',mlCount:ml.length,mlCandidateCount:ml.filter(x=>x.status==='CANDIDATE').length,kCount:k.length,kCandidateCount:k.filter(x=>x.status==='CANDIDATE').length,ml,k};return applyResearchBundle(base,args.researchBundle,args.publicResearchCore);}

  const api={VERSION,RESEARCH_VERSION,MODE,MIN_PROXY_HITTERS,ML_TARGET_EDGE,americanFromProb,rosterProfile,officialProfile,recentResultsProfile,kRecentForm,kResearch,mlResearch,attachPublicResearch,applyResearchBundle,buildBoard};
  if(typeof window!=='undefined')window.MODEL_SLATE_RADAR_CORE=api;
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})();
