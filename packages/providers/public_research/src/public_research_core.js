(() => {
  'use strict';
  const VERSION='0.5.0';
  const PROVIDER='PUBLIC_RESEARCH';
  const MAX_NEWS_AGE_HOURS=120;
  const TEAM_ALIASES={ARI:['diamondbacks'],ATL:['braves'],BAL:['orioles'],BOS:['red sox'],CHC:['cubs'],CWS:['white sox'],CIN:['reds'],CLE:['guardians'],COL:['rockies'],DET:['tigers'],HOU:['astros'],KC:['royals'],LAA:['angels'],LAD:['dodgers'],MIA:['marlins'],MIL:['brewers'],MIN:['twins'],NYM:['mets'],NYY:['yankees'],OAK:['athletics'],PHI:['phillies'],PIT:['pirates'],SD:['padres'],SEA:['mariners'],SF:['giants'],STL:['cardinals'],TB:['rays'],TEX:['rangers'],TOR:['blue jays'],WSH:['nationals']};
  const normalize=s=>String(s??'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  const freshnessBand=hours=>hours===null||hours===undefined||!Number.isFinite(Number(hours))?'UNKNOWN':Number(hours)<=24?'FRESH':Number(hours)<=72?'CURRENT':'STALE';
  const headlineFingerprint=title=>{const stop=new Set(['mlb','baseball','game','games','today','prediction','predictions','pick','picks','odds','preview','recap','final','score','vs','at','the','a','an','and','or','for','to','on','in','of','with']);return normalize(title).split(' ').filter(w=>w.length>2&&!stop.has(w)).slice(0,12).sort().join('|');};
  const uniq=a=>[...new Set((a||[]).filter(Boolean))];
  function decodeXml(s){return String(s??'').replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g,'$1').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;|&apos;/g,"'").replace(/&#(\d+);/g,(_,n)=>String.fromCharCode(Number(n))).trim();}
  function tag(block,name){const m=String(block||'').match(new RegExp(`<${name}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${name}>`,'i'));return m?decodeXml(m[1]):null;}
  function googleNewsUrl(query){const q=encodeURIComponent(String(query||'').trim());return `https://news.google.com/rss/search?q=${q}&hl=en-US&gl=US&ceid=US:en`;}
  function numberFireUrlCandidates(dateIso){const [y,m,d]=String(dateIso||'').split('-');if(!y||!m||!d)return[];const di=String(Number(d)),mi=String(Number(m));return uniq([`https://www.fanduel.com/research/mlb-betting-odds-${m}-${d}-${y}`,`https://www.fanduel.com/research/mlb-betting-odds-${m}-${di}-${y}`,`https://www.fanduel.com/research/mlb-betting-odds-${mi}-${di}-${y}`]);}
  function htmlText(html){return decodeXml(String(html||'').replace(/<script\b[\s\S]*?<\/script>/gi,' ').replace(/<style\b[\s\S]*?<\/style>/gi,' ').replace(/<br\s*\/?>/gi,'\n').replace(/<\/(?:p|li|h1|h2|h3|h4|div|section)>/gi,'\n').replace(/<[^>]+>/g,' ').replace(/[ \t]+/g,' ').replace(/\n[ \t]+/g,'\n'));}
  function teamCodeForLabel(label){const n=normalize(label);for(const [code,aliases] of Object.entries(TEAM_ALIASES))if(aliases.some(a=>n===a||n.endsWith(` ${a}`)||n.includes(a)))return code;return null;}
  function parseNumberFireHtml(html,{dateIso=null,url=null}={}){const text=htmlText(html),byTeam={},raw=[];const re=/([A-Za-z][A-Za-z .'-]{1,40}?)\s+Win Probability:\s*(\d{1,2}(?:\.\d+)?|100(?:\.0+)?)%/gi;let m;while((m=re.exec(text))){const label=m[1].trim(),code=teamCodeForLabel(label),p=Number(m[2])/100;if(!code||!Number.isFinite(p))continue;byTeam[code]=p;raw.push({label,team:code,probability:p});}const count=Object.keys(byTeam).length;return{provider:'numberFire via FanDuel Research',status:count>=2?'PASS':'ERROR',dateIso,url,teamProbabilityCount:count,byTeam,raw,probabilityMutation:false};}
  function researchKey(row){if(!row)return null;if(row.kind==='K')return `K:${row.gamePk}:${row.officialMlbId||normalize(row.player)}`;return `ML:${row.gamePk}`;}
  function buildTargets(board,{mlLimit=4,kLimit=6}={}){
    const ml=(board?.ml||[]).filter(r=>r.status==='CANDIDATE').slice(0,Math.max(0,mlLimit)).map(r=>({key:researchKey(r),kind:'ML',gamePk:String(r.gamePk),query:`\"${r.away}\" \"${r.home}\" MLB`,label:`${r.away} @ ${r.home}`,teams:[r.away,r.home],teamIds:[r.awayTeamId,r.homeTeamId].filter(Boolean)}));
    const k=(board?.k||[]).filter(r=>r.status==='CANDIDATE'&&r.player).slice(0,Math.max(0,kLimit)).map(r=>({key:researchKey(r),kind:'K',gamePk:String(r.gamePk),officialMlbId:r.officialMlbId?String(r.officialMlbId):null,player:r.player,team:r.team||null,query:`\"${r.player}\" MLB`,label:r.player,terms:uniq([r.player,r.team,r.away,r.home])}));
    return [...ml,...k];
  }
  const patterns={
    INJURY:/\b(injur(?:y|ed)|soreness|strain|sprain|pain|discomfort|shoulder|elbow|forearm|hamstring|back tightness|knee|ankle)\b/i,
    SCRATCH:/\b(scratched|scratch|late scratch|removed from (?:the )?lineup)\b/i,
    WORKLOAD:/\b(pitch count|pitch limit|innings limit|workload|short leash|limited to|restriction)\b/i,
    ROLE_CHANGE:/\b(opener|bullpen game|relief role|moved to bullpen|rotation change|spot start)\b/i,
    RETURN:/\b(activated|reinstated|return(?:s|ed|ing)?|back from (?:the )?il|cleared to)\b/i,
    TRANSACTION:/\b(optioned|recalled|designated for assignment|dfa|selected (?:the )?contract|placed on|injured list|\bil\b)\b/i,
    LINEUP:/\b(lineup|batting order|rest day|sitting|benched)\b/i,
    WEATHER:/\b(rain|weather|storm|wind|delay|postpon)\b/i,
    VELOCITY:/\b(velocity|velo|mph|fastball)\b/i
  };
  function classifyTitle(title,target={}){
    const text=String(title||''),flags=Object.entries(patterns).filter(([,re])=>re.test(text)).map(([k])=>k),norm=normalize(text),playerNorm=normalize(target.player||''),last=playerNorm.split(' ').filter(Boolean).slice(-1)[0]||'';
    const escaped=last.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    const playerMention=target.kind==='K'&&last?new RegExp(`\\b${escaped}\\b`,'i').test(norm):false;
    let relevance='BACKGROUND';
    if(target.kind==='K'&&playerMention){
      if(flags.some(x=>['INJURY','SCRATCH','WORKLOAD','ROLE_CHANGE'].includes(x)))relevance='DIRECTLY_MATERIAL';
      else if(flags.some(x=>['RETURN','TRANSACTION','LINEUP','VELOCITY'].includes(x)))relevance='POSSIBLY_MATERIAL';
    }else if(target.kind==='ML'){
      if(flags.includes('WEATHER'))relevance='DIRECTLY_MATERIAL';
      else if(flags.some(x=>['INJURY','SCRATCH','LINEUP','WORKLOAD','ROLE_CHANGE'].includes(x)))relevance='POSSIBLY_MATERIAL';
    }
    return{flags,playerMention,relevance,reviewRequired:relevance==='DIRECTLY_MATERIAL',risk:relevance==='DIRECTLY_MATERIAL'?'HIGH':relevance==='POSSIBLY_MATERIAL'?'MEDIUM':'LOW'};
  }
  function transactionRelevance(tx,row){
    if(!tx||!row)return'BACKGROUND';
    if(row.kind!=='K'||!row.officialMlbId||String(tx.personId||'')!==String(row.officialMlbId))return'BACKGROUND';
    const text=normalize(`${tx.typeDesc||''} ${tx.description||''}`),flags=tx.flags||[];
    if(/placed .* injured list|transferred .* injured list|60 day injured list|15 day injured list|10 day injured list/.test(text))return'DIRECTLY_MATERIAL';
    if(flags.some(x=>['INJURY','SCRATCH','WORKLOAD','ROLE_CHANGE'].includes(x)))return'DIRECTLY_MATERIAL';
    if(flags.some(x=>['RETURN','TRANSACTION'].includes(x))||/reinstated|activated|recalled|selected contract/.test(text))return'POSSIBLY_MATERIAL';
    return'BACKGROUND';
  }
  function parseGoogleNewsRss(xml,{target={},nowMs=Date.now(),maxAgeHours=MAX_NEWS_AGE_HOURS}={}){
    const out=[],itemRe=/<item\b[^>]*>([\s\S]*?)<\/item>/gi;let m;
    while((m=itemRe.exec(String(xml||'')))){
      const block=m[1],title=tag(block,'title'),link=tag(block,'link'),pubDate=tag(block,'pubDate'),sm=block.match(/<source(?:\s+url="([^"]+)")?[^>]*>([\s\S]*?)<\/source>/i),sourceName=sm?decodeXml(sm[2]):null,sourceUrl=sm?.[1]?decodeXml(sm[1]):null,t=Date.parse(pubDate||'');
      if(!title||!link)continue;const ageHours=Number.isFinite(t)?Math.max(0,(nowMs-t)/3600000):null;if(ageHours!==null&&ageHours>maxAgeHours)continue;
      const classification=classifyTitle(title,target),freshness=freshnessBand(ageHours),fingerprint=headlineFingerprint(title),evidenceId=`NEWS:${fingerprint||normalize(title).slice(0,80)}`;out.push({title,link,publishedAt:Number.isFinite(t)?new Date(t).toISOString():null,ageHours,freshness,sourceClass:'NEWS',sourceName,sourceUrl,fingerprint,evidenceId,...classification});
    }
    const seen=new Set();return out.filter(a=>{const k=a.fingerprint||normalize(a.title);if(seen.has(k))return false;seen.add(k);return true;}).slice(0,8);
  }
  function transactionFlags(tx){const text=`${tx?.typeDesc||''} ${tx?.description||''}`;return Object.entries(patterns).filter(([k,re])=>k!=='WEATHER'&&k!=='VELOCITY'&&re.test(text)).map(([k])=>k);}
  function normalizeTransactions(payload,nowMs=Date.now()){
    return (payload?.transactions||[]).map(tx=>{const t=Date.parse(tx?.effectiveDate||tx?.date||''),ageHours=Number.isFinite(t)?Math.max(0,(nowMs-t)/3600000):null,flags=transactionFlags(tx),id=tx?.id??null;return{id,personId:tx?.person?.id!=null?String(tx.person.id):null,personName:tx?.person?.fullName||null,fromTeamId:tx?.fromTeam?.id!=null?String(tx.fromTeam.id):null,fromTeam:tx?.fromTeam?.name||null,toTeamId:tx?.toTeam?.id!=null?String(tx.toTeam.id):null,toTeam:tx?.toTeam?.name||null,date:tx?.date||null,effectiveDate:tx?.effectiveDate||null,typeCode:tx?.typeCode||null,typeDesc:tx?.typeDesc||null,description:tx?.description||null,flags,ageHours,freshness:freshnessBand(ageHours),sourceClass:'OFFICIAL',sourceName:'MLB StatsAPI',evidenceId:`MLB_TX:${id??`${tx?.person?.id||'na'}:${tx?.effectiveDate||tx?.date||'na'}`}`};}).sort((a,b)=>String(b.effectiveDate||b.date||'').localeCompare(String(a.effectiveDate||a.date||'')));
  }
  function buildBundle({dateIso=null,targets=[],newsResults=[],transactionsPayload=null,transactionsError=null,numberFireResult=null,numberFireError=null,updatedAt=null,nowMs=Date.now()}={}){
    const newsByKey={};let queryErrors=0,articleCount=0;const sourceNames=[];
    for(const result of newsResults||[]){if(!result?.key)continue;if(result.error){queryErrors++;newsByKey[result.key]={status:'ERROR',error:result.error,articles:[]};continue;}const articles=(result.articles||[]);articleCount+=articles.length;sourceNames.push(...articles.map(x=>x.sourceName).filter(Boolean));newsByKey[result.key]={status:'PASS',query:result.query||null,articles};}
    const transactions=normalizeTransactions(transactionsPayload,nowMs);const txStatus=transactionsPayload?'PASS':transactionsError?'ERROR':'NOT_REQUESTED';
    const targetCount=(targets||[]).length,newsPass=Object.values(newsByKey).filter(x=>x.status==='PASS').length,baseStatus=(txStatus==='PASS'||newsPass>0)?(queryErrors||txStatus==='ERROR'?'PARTIAL':'PASS'):'ERROR';
    const ext=numberFireResult?.status==='PASS'?numberFireResult:{provider:'numberFire via FanDuel Research',status:numberFireError?'ERROR':'NOT_CONNECTED',error:numberFireError||numberFireResult?.error||null,dateIso,byTeam:{},teamProbabilityCount:0},status=ext.status==='ERROR'?(baseStatus==='ERROR'?'ERROR':'PARTIAL'):baseStatus;return{provider:PROVIDER,version:VERSION,status,dateIso,updatedAt:updatedAt||new Date(nowMs).toISOString(),targetCount,news:{provider:'Google News RSS',status:targetCount===0?'NO_TARGETS':newsPass===targetCount?'PASS':newsPass>0?'PARTIAL':'ERROR',queryCount:targetCount,passCount:newsPass,errorCount:queryErrors,articleCount,sourceCount:uniq(sourceNames).length,newsByKey},transactions:{provider:'MLB StatsAPI',status:txStatus,error:transactionsError||null,count:transactions.length,items:transactions},externalProjections:ext,probabilityMutation:false};
  }
  function materialSummary(row,articles=[],tx=[]){
    const articleRows=(articles||[]).map(a=>({...a,relevance:a.relevance||'BACKGROUND',freshness:a.freshness||freshnessBand(a.ageHours),sourceClass:a.sourceClass||'NEWS'}));
    const txRows=(tx||[]).map(x=>({...x,relevance:x.relevance||transactionRelevance(x,row),freshness:x.freshness||freshnessBand(x.ageHours),sourceClass:x.sourceClass||'OFFICIAL'}));
    const all=[...articleRows,...txRows],direct=all.filter(x=>x.relevance==='DIRECTLY_MATERIAL'&&x.freshness!=='STALE'),staleDirect=all.filter(x=>x.relevance==='DIRECTLY_MATERIAL'&&x.freshness==='STALE'),possible=all.filter(x=>x.relevance==='POSSIBLY_MATERIAL'&&x.freshness!=='STALE'),background=all.filter(x=>x.relevance==='BACKGROUND'||x.freshness==='STALE');
    const findings=[];
    const directFlags=uniq(direct.flatMap(x=>x.flags||[])),possibleFlags=uniq(possible.flatMap(x=>x.flags||[]));
    const add=(arr,flag,text)=>{if(arr.includes(flag)&&!findings.includes(text))findings.push(text);};
    add(directFlags,'INJURY','DIRECT: current player-specific sourced evidence flags injury/health context.');
    add(directFlags,'SCRATCH','DIRECT: current sourced evidence flags a scratch or lineup removal.');
    add(directFlags,'WORKLOAD','DIRECT: current player-specific evidence flags pitch-count, innings-limit, or workload context.');
    add(directFlags,'ROLE_CHANGE','DIRECT: current player-specific evidence flags a role/rotation change.');
    add(directFlags,'WEATHER','DIRECT: current sourced weather/delay context may affect this game.');
    add(directFlags,'TRANSACTION','DIRECT: a current player-specific MLB transaction may affect availability.');
    add(possibleFlags,'RETURN','POSSIBLE: recent return/activation context deserves awareness but does not trigger a hold by itself.');
    add(possibleFlags,'VELOCITY','POSSIBLE: recent velocity/fastball context may matter; verify before use.');
    add(possibleFlags,'LINEUP','POSSIBLE: recent lineup/rest context may matter; verify against the official lineup.');
    add(possibleFlags,'INJURY','POSSIBLE: team-level injury context was found but is not tied tightly enough to this row for a hold.');
    if(staleDirect.length)findings.push(`STALE: ${staleDirect.length} otherwise-direct item(s) are older than 72h and cannot create a hold.`);
    if(!findings.length){if(background.length)findings.push('BACKGROUND ONLY: reviewed sources contained no current directly material finding for this row.');else findings.push('No material sourced headline or transaction finding is available for this row.');}
    const evidence=all.map(x=>({evidenceId:x.evidenceId||null,relevance:x.relevance||'BACKGROUND',freshness:x.freshness||'UNKNOWN',sourceClass:x.sourceClass||'UNKNOWN',sourceName:x.sourceName||null,title:x.title||null,description:x.description||null,ageHours:x.ageHours??null,flags:x.flags||[]}));
    return{status:direct.length?'REVIEW':possible.length?'WATCH':'NEUTRAL',impact:direct.length?'DIRECTLY_MATERIAL':possible.length?'POSSIBLY_MATERIAL':'BACKGROUND_ONLY',findings:findings.slice(0,6),directCount:direct.length,possibleCount:possible.length,staleDirectCount:staleDirect.length,backgroundCount:background.length,articleCount:articleRows.length,transactionCount:txRows.length,evidence,oldestMaterialAgeHours:Math.max(...direct.concat(possible).map(x=>Number(x.ageHours)).filter(Number.isFinite),-1),probabilityMutation:false};
  }
  function contextFor(row,bundle){
    const key=researchKey(row),news=bundle?.news?.newsByKey?.[key]||{status:'NOT_REQUESTED',articles:[]};let tx=[];
    if(row?.kind==='K'&&row?.officialMlbId){const id=String(row.officialMlbId);tx=(bundle?.transactions?.items||[]).filter(x=>x.personId===id).slice(0,5);}else if(row?.kind==='ML'){const ids=new Set([row.awayTeamId,row.homeTeamId].filter(Boolean).map(String));tx=(bundle?.transactions?.items||[]).filter(x=>ids.has(String(x.toTeamId||''))||ids.has(String(x.fromTeamId||''))).slice(0,8);}
    const articles=(news.articles||[]).slice(0,5),txWithRelevance=tx.map(x=>({...x,relevance:transactionRelevance(x,row)})),material=materialSummary(row,articles,txWithRelevance);
    const reviewArticle=articles.some(a=>a.relevance==='DIRECTLY_MATERIAL'&&a.reviewRequired&&a.freshness!=='STALE'),reviewTx=txWithRelevance.some(x=>x.relevance==='DIRECTLY_MATERIAL'&&x.freshness!=='STALE');
    let externalProjection={status:'NOT_AVAILABLE_FOR_K'};if(row?.kind==='ML'){const ext=bundle?.externalProjections||{},away=ext?.byTeam?.[row.away],home=ext?.byTeam?.[row.home];if(Number.isFinite(Number(away))&&Number.isFinite(Number(home))){const favorite=Number(away)>=Number(home)?row.away:row.home,selected=String(row.side||'')===String(row.away)?Number(away):String(row.side||'')===String(row.home)?Number(home):null,model=Number.isFinite(Number(row.probability))?Number(row.probability):null,deltaPP=model!==null&&selected!==null?(model-selected)*100:null;externalProjection={status:'CONNECTED',provider:ext.provider||'numberFire via FanDuel Research',url:ext.url||null,awayTeam:row.away,awayProbability:Number(away),homeTeam:row.home,homeProbability:Number(home),favorite,selectedSide:row.side||null,selectedSideProbability:selected,modelProbability:model,modelDeltaPP:deltaPP,agreement:favorite===row.side?'AGREE':'DISAGREE',assessment:favorite!==row.side?(deltaPP!==null&&Math.abs(deltaPP)>=12?'MAJOR_CONFLICT':'DISAGREE'):(deltaPP!==null&&Math.abs(deltaPP)<=8?'AGREE_CLOSE':'AGREE_WIDE')};}else externalProjection={status:ext?.status==='ERROR'?'ERROR':'NOT_FOUND',provider:ext?.provider||'numberFire via FanDuel Research',url:ext?.url||null};}
    const sources=uniq([(bundle?.transactions?.status==='PASS'?'MLB StatsAPI':null),...(articles.map(x=>x.sourceName).filter(Boolean)),externalProjection.status==='CONNECTED'?'numberFire / FanDuel Research':null]);return{providerVersion:bundle?.version||VERSION,status:bundle?.status||'NOT_CONNECTED',updatedAt:bundle?.updatedAt||null,key,news:{status:news.status||'NOT_REQUESTED',articles,reviewRequired:reviewArticle},transactions:{status:bundle?.transactions?.status||'NOT_REQUESTED',items:txWithRelevance,reviewRequired:reviewTx},materialSummary:material,externalProjection,reviewRequired:reviewArticle||reviewTx||material.status==='REVIEW',sources,probabilityMutation:false};
  }
  function sourceSummary(context){const a=context?.news?.articles?.length||0,t=context?.transactions?.items?.length||0,s=context?.sources?.length||0;return{articleCount:a,transactionCount:t,sourceCount:s,evidenceCount:context?.materialSummary?.evidence?.length||0,staleDirectCount:context?.materialSummary?.staleDirectCount||0,externalProjectionStatus:context?.externalProjection?.status||'NOT_CONNECTED',reviewRequired:!!context?.reviewRequired,status:context?.status||'NOT_CONNECTED'};}
  const api={VERSION,PROVIDER,MAX_NEWS_AGE_HOURS,TEAM_ALIASES,freshnessBand,headlineFingerprint,googleNewsUrl,numberFireUrlCandidates,parseNumberFireHtml,researchKey,buildTargets,classifyTitle,transactionRelevance,parseGoogleNewsRss,normalizeTransactions,buildBundle,materialSummary,contextFor,sourceSummary};
  if(typeof window!=='undefined')window.MODEL_PUBLIC_RESEARCH_CORE=api;
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})();
