(() => {
  'use strict';
  const VERSION='1.0';
  const BASE='https://www.fangraphs.com/api/leaders/major-league/data';

  const finite=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v));
  const num=(v,f=null)=>finite(v)?Number(v):f;
  function buildUrl(year){
    const u=new URL(BASE);
    const q={age:'',pos:'all',stats:'bat',lg:'all',qual:'0',season:String(year),season1:String(year),startdate:'',enddate:'',month:'0',hand:'',team:'0',pageitems:'2000',pagenum:'1',ind:'0',rost:'0',players:'0',type:'8',postseason:'',sortdir:'default',sortstat:'WAR'};
    for(const [k,v] of Object.entries(q))u.searchParams.set(k,v);
    return u.toString();
  }
  function first(o,keys){for(const k of keys){if(Object.prototype.hasOwnProperty.call(o||{},k)&&o[k]!==null&&o[k]!==undefined&&o[k]!=='')return o[k];}return null;}
  function parseLeaderboard(payload,year){
    const data=Array.isArray(payload?.data)?payload.data:[];
    if(!data.length)throw new Error(`FanGraphs wRC+: leaderboard returned no data for ${year}`);
    const rows=[],rejected=[];
    for(let i=0;i<data.length;i++){
      const r=data[i]||{};
      const id=String(first(r,['xMLBAMID','MLBAMID','mlbamid','mlbId'])||'').trim();
      const pa=num(first(r,['PA','pa']),null);
      const wrc=num(first(r,['wRC+','wRCPlus','wrc_plus','wrcPlus']),null);
      const name=String(first(r,['PlayerName','Name','playerName'])||'').trim()||null;
      const fgId=String(first(r,['playerid','PlayerId','playerId'])||'').trim()||null;
      if(!id||!Number.isFinite(pa)||pa<0||pa>1000||!Number.isFinite(wrc)||wrc<-100||wrc>300){rejected.push({row:i+1,id:id||null,name,pa,wrcPlus:wrc});continue;}
      rows.push({playerId:id,fanGraphsId:fgId,name,year:Number(year),pa,wrcPlus:wrc});
    }
    const byId=new Map();
    for(const r of rows){const p=byId.get(r.playerId);if(!p||r.pa>p.pa)byId.set(r.playerId,r);}
    if(!byId.size)throw new Error(`FanGraphs wRC+: no MLBAM-ID rows survived validation for ${year}`);
    return {provider:'fangraphs-major-league-leaderboard',providerVersion:VERSION,year:Number(year),capturedAt:new Date().toISOString(),rowCount:rows.length,uniquePlayerCount:byId.size,rejectedCount:rejected.length,rows,byId,rejected:rejected.slice(0,20)};
  }
  function seasonBundle(current,previous=null){return{provider:'fangraphs-major-league-leaderboard',providerVersion:VERSION,currentYear:current?.year??null,previousYear:previous?.year??null,current,previous};}
  function getForSavantRow(bundle,playerId,savantRow){
    const id=String(playerId||'');if(!id)return null;
    const preferPrevious=/^previous/.test(String(savantRow?.sourceSeason||''));
    const preferred=preferPrevious?bundle?.previous?.byId?.get?.(id):bundle?.current?.byId?.get?.(id);
    const fallback=preferPrevious?bundle?.current?.byId?.get?.(id):bundle?.previous?.byId?.get?.(id);
    const r=preferred||fallback||null;if(!r)return null;
    return {...r,sourceSeason:r.year===bundle?.currentYear?'current':'previous',seasonFallback:!preferred};
  }
  function compact(bundle){return{provider:bundle?.provider,providerVersion:bundle?.providerVersion,current:bundle?.current?{year:bundle.current.year,rowCount:bundle.current.rowCount,uniquePlayerCount:bundle.current.uniquePlayerCount,rejectedCount:bundle.current.rejectedCount}:null,previous:bundle?.previous?{year:bundle.previous.year,rowCount:bundle.previous.rowCount,uniquePlayerCount:bundle.previous.uniquePlayerCount,rejectedCount:bundle.previous.rejectedCount}:null};}
  const api={VERSION,BASE,buildUrl,parseLeaderboard,seasonBundle,getForSavantRow,compact};
  if(typeof window!=='undefined')window.MODEL_FANGRAPHS_WRC_CORE=api;
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})();
