(() => {
  'use strict';

  const VERSION='1.2';
  const BASE='https://baseballsavant.mlb.com/leaderboard/custom';
  const SELECTIONS=['pa','k_percent','bb_percent','batting_avg','xba','xslg','xwoba','isolated_power','hard_hit_percent','barrel_batted_rate','whiff_percent','swing_percent'];

  function buildUrl(year,type){
    const u=new URL(BASE);
    const q={year:String(year),type,filter:'',min:'1',selections:SELECTIONS.join(','),chart:'false',x:'pa',y:'pa',r:'no',chartType:'beeswarm',sort:'pa',sortDir:'desc',csv:'true'};
    for(const [k,v] of Object.entries(q))u.searchParams.set(k,v);
    return u.toString();
  }

  function parseCsv(text){
    text=String(text||'').replace(/^\uFEFF/,'');
    const rows=[];let row=[],field='',quoted=false;
    for(let i=0;i<text.length;i++){
      const c=text[i];
      if(quoted){
        if(c==='"'&&text[i+1]==='"'){field+='"';i++;}
        else if(c==='"')quoted=false;
        else field+=c;
      }else{
        if(c==='"')quoted=true;
        else if(c===','){row.push(field);field='';}
        else if(c==='\n'){row.push(field.replace(/\r$/,''));rows.push(row);row=[];field='';}
        else field+=c;
      }
    }
    if(field.length||row.length){row.push(field.replace(/\r$/,''));rows.push(row);}
    return rows.filter(r=>r.some(x=>String(x).trim()!==''));
  }

  const normHeader=s=>String(s||'').replace(/^\uFEFF/,'').trim().toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'');
  const number=v=>{if(v===null||v===undefined)return null;const raw=String(v).replace(/%/g,'').trim();if(!raw)return null;const n=Number(raw);return Number.isFinite(n)?n:null;};
  const inRange=(v,a,b)=>Number.isFinite(v)&&v>=a&&v<=b;

  function rowValue(obj,names){for(const n of names){if(Object.prototype.hasOwnProperty.call(obj,n))return obj[n];}return null;}

  function parseLeaderboard(csv,type,year){
    const rows=parseCsv(csv);
    if(rows.length<2)throw new Error(`Baseball Savant ${type}: CSV has no data rows`);
    const headers=rows[0].map(normHeader);
    const requiredGroups=[['player_id','playerid'],['year'],['pa','b_total_pa','p_total_pa','bf','batters_faced'],['k_percent'],['whiff_percent'],['swing_percent']];
    for(const group of requiredGroups){if(!group.some(x=>headers.includes(x)))throw new Error(`Baseball Savant ${type}: required column missing (${group[0]})`);}
    const out=[];const rejected=[];
    for(let i=1;i<rows.length;i++){
      const vals=rows[i], o={}; headers.forEach((h,j)=>{o[h]=vals[j]??'';});
      const id=String(rowValue(o,['player_id','playerid'])||'').trim();
      const yr=number(rowValue(o,['year']));
      const pa=number(rowValue(o,['pa','b_total_pa','p_total_pa','bf','batters_faced']));
      const k=number(rowValue(o,['k_percent']));
      const bb=number(rowValue(o,['bb_percent']));
      const ba=number(rowValue(o,['batting_avg','ba','avg']));
      const xba=number(rowValue(o,['xba']));
      const xslg=number(rowValue(o,['xslg']));
      const xwoba=number(rowValue(o,['xwoba']));
      const iso=number(rowValue(o,['isolated_power','iso']));
      const hardHit=number(rowValue(o,['hard_hit_percent']));
      const barrel=number(rowValue(o,['barrel_batted_rate','barrel_percent']));
      const whiff=number(rowValue(o,['whiff_percent']));
      const swing=number(rowValue(o,['swing_percent']));
      const name=String(rowValue(o,['last_name_first_name','player_name','name'])||'').trim()||null;
      const valid=id&&Number(yr)===Number(year)&&inRange(pa,0,2000)&&inRange(k,0,70)&&inRange(whiff,0,75)&&inRange(swing,0,80);
      if(!valid){rejected.push({row:i+1,id:id||null,year:yr,pa,kPct:k,whiffPct:whiff,swingPct:swing});continue;}
      const contact=100-whiff;
      const swstr=swing*whiff/100;
      out.push({playerId:id,name,year:yr,pa,kPct:k,bbPct:inRange(bb,0,50)?bb:null,ba:inRange(ba,0,1)?ba:null,xba:inRange(xba,0,1)?xba:null,xslg:inRange(xslg,0,1.5)?xslg:null,xwoba:inRange(xwoba,0,1)?xwoba:null,iso:inRange(iso,0,1)?iso:null,hardHitPct:inRange(hardHit,0,100)?hardHit:null,barrelPct:inRange(barrel,0,100)?barrel:null,whiffPct:whiff,swingPct:swing,contactPct:contact,swStrPct:swstr,wrcPlus:null});
    }
    const byId=new Map();
    for(const r of out){
      const prev=byId.get(r.playerId);
      if(!prev||r.pa>prev.pa)byId.set(r.playerId,r);
    }
    return {provider:'baseball-savant-custom-leaderboard',providerVersion:VERSION,type,year:Number(year),capturedAt:new Date().toISOString(),rowCount:out.length,uniquePlayerCount:byId.size,rejectedCount:rejected.length,rows:out,byId,rejected:rejected.slice(0,20)};
  }

  function compact(parsed){
    return {provider:parsed.provider,providerVersion:parsed.providerVersion,type:parsed.type,year:parsed.year,capturedAt:parsed.capturedAt,rowCount:parsed.rowCount,uniquePlayerCount:parsed.uniquePlayerCount,rejectedCount:parsed.rejectedCount};
  }

  function seasonBundle(current, previous=null){
    return {provider:'baseball-savant-custom-leaderboard',providerVersion:VERSION,type:current?.type||previous?.type||null,currentYear:current?.year??null,previousYear:previous?.year??null,current,previous};
  }

  function getRow(bundle, playerId, {minCurrent=30,minPrevious=60}={}){
    const id=String(playerId||'');
    if(!id)return null;
    const cur=bundle?.current?.byId?.get?.(id)||null;
    const prev=bundle?.previous?.byId?.get?.(id)||null;
    if(cur && Number(cur.pa)>=Number(minCurrent)) return {...cur,sourceSeason:'current',sampleCurrent:Number(cur.pa),samplePrevious:prev?.pa??0};
    if(prev && Number(prev.pa)>=Number(minPrevious)) return {...prev,sourceSeason:'previous',sampleCurrent:cur?.pa??0,samplePrevious:Number(prev.pa)};
    if(cur) return {...cur,sourceSeason:'current-small',sampleCurrent:Number(cur.pa)||0,samplePrevious:prev?.pa??0};
    if(prev) return {...prev,sourceSeason:'previous-small',sampleCurrent:0,samplePrevious:Number(prev.pa)||0};
    return null;
  }

  function compactBundle(bundle){
    return {provider:bundle?.provider,providerVersion:bundle?.providerVersion,type:bundle?.type,current:bundle?.current?compact(bundle.current):null,previous:bundle?.previous?compact(bundle.previous):null};
  }

  const api={VERSION,BASE,SELECTIONS,buildUrl,parseCsv,parseLeaderboard,compact,seasonBundle,getRow,compactBundle};
  if(typeof window!=='undefined')window.MODEL_SAVANT_CORE=api;
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})();
