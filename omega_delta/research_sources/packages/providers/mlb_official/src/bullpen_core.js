(() => {
  'use strict';
  const VERSION='1.1';
  const BASE='https://statsapi.mlb.com/api/v1';
  const num=(v,f=null)=>{if(v===null||v===undefined||v==='')return f;const n=Number(v);return Number.isFinite(n)?n:f;};
  const ipNum=v=>{if(v===null||v===undefined||v==='')return null;const s=String(v),m=s.match(/^(\d+)(?:\.(\d))?$/);if(!m)return num(v,null);const whole=Number(m[1]),outs=m[2]==null?0:Number(m[2]);if(outs>2)return null;return whole+outs/3;};
  function buildRosterUrl(teamId,year,dateIso){const u=new URL(`${BASE}/teams/${encodeURIComponent(teamId)}/roster`);u.searchParams.set('rosterType','active');u.searchParams.set('season',String(year));if(dateIso)u.searchParams.set('date',dateIso);u.searchParams.set('hydrate','person');return u.toString();}
  function buildStatsUrl(teamId,year){const u=new URL(`${BASE}/stats`);for(const [k,v] of Object.entries({stats:'season',group:'pitching',season:String(year),teamId:String(teamId),playerPool:'All',gameType:'R',limit:'100',hydrate:'person'}))u.searchParams.set(k,v);return u.toString();}
  function parseTeamPitchingStats(payload,year){
    const byId=new Map();
    for(const group of payload?.stats||[]){for(const split of group?.splits||[]){if(split?.season!=null&&String(split.season)!==String(year))continue;const id=String(split?.player?.id??split?.person?.id??'');if(!id||!split?.stat)continue;byId.set(id,{stat:split.stat,name:split?.player?.fullName||split?.person?.fullName||null});}}
    return byId;
  }
  function nestedSeasonStat(person,year){for(const group of person?.stats||[]){const splits=Array.isArray(group?.splits)?group.splits:[];const exact=splits.find(s=>String(s?.season||'')===String(year))||splits[0];if(exact?.stat)return exact.stat;}return null;}
  function parseRoster(rosterPayload,{teamId,teamCode,year,starterId=null,usedYesterday=new Set(),usageKnown=true,pitchingStatsById=new Map()}={}){
    const roster=Array.isArray(rosterPayload?.roster)?rosterPayload.roster:[];const candidates=[],rows=[],rejected=[];
    for(const entry of roster){
      const pos=entry?.position||entry?.person?.primaryPosition||{};if(!/pitcher/i.test(String(pos?.type||pos?.name||''))&&String(pos?.abbreviation||'').toUpperCase()!=='P')continue;
      const id=String(entry?.person?.id??'');if(!id||id===String(starterId||''))continue;
      const ext=pitchingStatsById instanceof Map?pitchingStatsById.get(id):pitchingStatsById?.[id];const st=ext?.stat||nestedSeasonStat(entry?.person,year);
      if(!st){rejected.push({playerId:id,name:entry?.person?.fullName||ext?.name||null,reason:'season pitching stats missing'});continue;}
      const gp=num(st.gamesPitched??st.gamesPlayed,null),gs=num(st.gamesStarted,0),bf=num(st.battersFaced,null),so=num(st.strikeOuts,null),bb=num(st.baseOnBalls,null),era=num(st.era,null),whip=num(st.whip,null),ip=ipNum(st.inningsPitched),reliefApps=Number.isFinite(gp)&&Number.isFinite(gs)?Math.max(0,gp-gs):null;
      if(!(Number.isFinite(reliefApps)&&Number.isFinite(gp)&&reliefApps>=3&&reliefApps>=gs))continue;candidates.push(id);
      const kPct=Number.isFinite(so)&&Number.isFinite(bf)&&bf>0?so/bf*100:null,bbPct=Number.isFinite(bb)&&Number.isFinite(bf)&&bf>0?bb/bf*100:null;
      const valid=[era,whip,kPct,bbPct].every(Number.isFinite)&&era>=0&&era<=20&&whip>=0&&whip<=4&&kPct>=0&&kPct<=60&&bbPct>=0&&bbPct<=40;
      if(!valid){rejected.push({playerId:id,name:entry?.person?.fullName||ext?.name||null,reason:'core bullpen metrics incomplete',era,whip,kPct,bbPct,bf});continue;}
      rows.push({playerId:id,name:entry?.person?.fullName||ext?.name||null,ERA:era,WHIP:whip,K:kPct,BB:bbPct,IP:ip,gamesPitched:gp,gamesStarted:gs,reliefAppearances:reliefApps,rest:usageKnown?(usedYesterday.has(id)?'0':'1+'):'UNKNOWN'});
    }
    const coverage=candidates.length?rows.length/candidates.length:0;let status='missing_structured',reason='no validated active reliever rows';
    if(rows.length>=4&&coverage>=0.60&&usageKnown){status='validated';reason=null;}else if(rows.length){status=usageKnown?'partial':'usage_unresolved';reason=!usageKnown?'prior-day bullpen usage unresolved':`only ${rows.length} validated reliever rows (${Math.round(coverage*100)}% coverage)`;}
    return {provider:'mlb-official-active-bullpen',providerVersion:VERSION,teamId:String(teamId||''),teamCode:teamCode||null,season:Number(year),capturedAt:new Date().toISOString(),starterId:starterId==null?null:String(starterId),candidateRelieverCount:candidates.length,rowCount:rows.length,coverage,rows,rejected:rejected.slice(0,20),validation:{status,source:'MLB StatsAPI active roster + team-filtered player season pitching stats + prior-day boxscore usage',usageKnown,reason}};
  }
  function parseYesterdayUsage(schedulePayload,boxscoresByPk,currentTeamIds=[]){
    const wanted=new Set((currentTeamIds||[]).map(String)),usedByTeam=new Map(),knownTeams=new Set(),scheduledCount=new Map(),resolvedCount=new Map();const games=Array.isArray(schedulePayload?.dates)?schedulePayload.dates.flatMap(d=>d?.games||[]):[];
    for(const g of games){const pk=String(g?.gamePk||'');if(!pk)continue;const box=boxscoresByPk instanceof Map?boxscoresByPk.get(pk):boxscoresByPk?.[pk];for(const side of ['away','home']){const tid=String(g?.teams?.[side]?.team?.id||'');if(!tid||!wanted.has(tid))continue;scheduledCount.set(tid,(scheduledCount.get(tid)||0)+1);if(!box)continue;resolvedCount.set(tid,(resolvedCount.get(tid)||0)+1);if(!usedByTeam.has(tid))usedByTeam.set(tid,new Set());for(const pid of box?.teams?.[side]?.pitchers||[])usedByTeam.get(tid).add(String(pid));}}
    for(const tid of wanted){const scheduled=scheduledCount.get(tid)||0,resolved=resolvedCount.get(tid)||0;if(scheduled===0||resolved===scheduled)knownTeams.add(tid);if(!usedByTeam.has(tid))usedByTeam.set(tid,new Set());}return{usedByTeam,knownTeams,scheduledCount,resolvedCount};
  }
  function compactMap(map){const out=[];for(const [team,v] of map instanceof Map?map.entries():Object.entries(map||{}))out.push({team,teamId:v?.teamId||null,status:v?.validation?.status||'missing',rowCount:v?.rowCount||0,coverage:v?.coverage??0,usageKnown:!!v?.validation?.usageKnown});return out;}
  const api={VERSION,BASE,buildRosterUrl,buildStatsUrl,parseTeamPitchingStats,parseRoster,parseYesterdayUsage,compactMap};if(typeof window!=='undefined')window.MODEL_MLB_BULLPEN_CORE=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})();

