const OMEGA_ALARM='omega-ta-auto-capture';
const OMEGA_STOP_AT='2026-09-22T00:15:00Z';
const PM_URL='https://propsmadness.com/nfl';

async function storageGet(keys){return chrome.storage.local.get(keys)}
async function storageSet(obj){return chrome.storage.local.set(obj)}

function futureKickoffs(matchesPayload){
  const now=Date.now(); const out=[];
  for(const x of (matchesPayload?.matches||[])){
    const m=x?.match||x||{}; let v=m.startDateTimestamp??m.startTimestamp??m.startTime??m.startDate;
    if(v==null) continue; let ms=Number(v); if(Number.isFinite(ms)){ if(ms<1e12) ms*=1000; }
    else { ms=Date.parse(String(v)); }
    if(Number.isFinite(ms)&&ms>now) out.push(ms);
  }
  return out.sort((a,b)=>a-b);
}
function nextDelayMinutes(matchesPayload){
  const ks=futureKickoffs(matchesPayload); if(!ks.length) return 180;
  const h=(ks[0]-Date.now())/3600000;
  return h<=3?30:h<=12?60:180;
}
async function scheduleNext(minutes){
  await chrome.alarms.clear(OMEGA_ALARM);
  const s=await storageGet(['omega_ta_auto_enabled']);
  if(s.omega_ta_auto_enabled===false||Date.now()>=Date.parse(OMEGA_STOP_AT)) return;
  chrome.alarms.create(OMEGA_ALARM,{delayInMinutes:Math.max(1,minutes)});
}
async function waitForComplete(tabId,timeoutMs=30000){
  const t0=Date.now();
  while(Date.now()-t0<timeoutMs){ const t=await chrome.tabs.get(tabId); if(t.status==='complete') return; await new Promise(r=>setTimeout(r,500)); }
  throw new Error('PropsMadness tab load timeout');
}

async function pageCapture(){
  const VERSION='OMEGA_PM_NFL_TA_DIRECT_CAPTURE_0.17.6';
  const MARKET_SLUG='player-tackles-assists';
  const MARKET_ENDPOINT=`/api/offer/nfl/explore/${MARKET_SLUG}`;
  const MATCHES_ENDPOINT='/api/offer/nfl/matches';
  const out={schemaVersion:VERSION,capturedAt:new Date().toISOString(),pageUrl:location.href,marketSlug:MARKET_SLUG,marketEndpoint:MARKET_ENDPOINT,matchesEndpoint:MATCHES_ENDPOINT,requests:{},credentialFieldsCaptured:0};
  async function fetchJson(path){
    const started=performance.now();
    try{
      const response=await fetch(path,{method:'GET',credentials:'include',cache:'no-store',headers:{accept:'application/json'}});
      const contentType=response.headers.get('content-type')||''; let data=null,text=null;
      if(contentType.includes('application/json')){try{data=await response.json()}catch(e){text=`JSON_PARSE_ERROR: ${String(e)}`}}
      else {try{text=(await response.text()).slice(0,250000)}catch(_){}}
      return {ok:response.ok,status:response.status,contentType,durationMs:Math.round(performance.now()-started),observedAt:new Date().toISOString(),data,text};
    }catch(e){return {ok:false,status:null,contentType:null,durationMs:Math.round(performance.now()-started),observedAt:new Date().toISOString(),error:String(e&&e.stack||e)}}
  }
  const [market,matches]=await Promise.all([fetchJson(MARKET_ENDPOINT),fetchJson(MATCHES_ENDPOINT)]);
  out.requests.market=market; out.requests.matches=matches;
  const payload=market?.data; const offers=Array.isArray(payload?.offers)?payload.offers:null; const observedSlug=payload?.market?.slug;
  out.validation={marketHttpOk:!!market.ok,marketOffersArray:Array.isArray(offers),marketOfferCount:Array.isArray(offers)?offers.length:null,observedMarketSlug:observedSlug||null,expectedMarketSlug:MARKET_SLUG,marketSlugMatches:!observedSlug||observedSlug===MARKET_SLUG,matchesHttpOk:!!matches.ok};
  out.exportedAt=new Date().toISOString(); return out;
}

async function captureNow(reason='alarm'){
  const st=await storageGet(['omega_ta_auto_enabled']);
  if(st.omega_ta_auto_enabled===false&&reason!=='manual') return {ok:false,skipped:'disabled'};
  if(Date.now()>=Date.parse(OMEGA_STOP_AT)){await scheduleNext(999999);return {ok:false,skipped:'week2_complete'}}
  let tab=null,created=false;
  try{
    const tabs=await chrome.tabs.query({url:['https://propsmadness.com/nfl*','https://www.propsmadness.com/nfl*']});
    tab=tabs[0]||await chrome.tabs.create({url:PM_URL,active:false}); created=!tabs[0];
    await waitForComplete(tab.id);
    const r=await chrome.scripting.executeScript({target:{tabId:tab.id},world:'MAIN',func:pageCapture});
    const cap=r?.[0]?.result;
    if(!cap?.validation?.marketHttpOk||!cap?.validation?.matchesHttpOk||!(cap?.validation?.marketOfferCount>0)) throw new Error('PropsMadness capture validation failed');
    const json=JSON.stringify(cap,null,2); const stamp=new Date().toISOString().replace(/[-:.]/g,'');
    const filename=`OMEGA_0176_PROPSMADNESS_NFL_TA_DIRECT_CAPTURE_${stamp}.json`;
    const url='data:application/json;charset=utf-8,'+encodeURIComponent(json);
    await chrome.downloads.download({url,filename,saveAs:false,conflictAction:'uniquify'});
    const delay=nextDelayMinutes(cap.requests?.matches?.data);
    await storageSet({omega_ta_auto_last:{ok:true,reason,at:new Date().toISOString(),filename,offers:cap.validation.marketOfferCount,nextDelayMinutes:delay}});
    await scheduleNext(delay); return {ok:true,filename,offers:cap.validation.marketOfferCount,nextDelayMinutes:delay};
  }catch(e){
    const msg=String(e&&e.stack||e); await storageSet({omega_ta_auto_last:{ok:false,reason,at:new Date().toISOString(),error:msg}}); await scheduleNext(30); return {ok:false,error:msg};
  }finally{if(created&&tab?.id){try{await chrome.tabs.remove(tab.id)}catch(_){}}}
}

async function init(){
  const s=await storageGet(['omega_ta_auto_enabled']); if(typeof s.omega_ta_auto_enabled!=='boolean') await storageSet({omega_ta_auto_enabled:true});
  await scheduleNext(1);
}
chrome.runtime.onInstalled.addListener(init); chrome.runtime.onStartup.addListener(init);
chrome.alarms.onAlarm.addListener(a=>{if(a.name===OMEGA_ALARM) captureNow('alarm')});
chrome.runtime.onMessage.addListener((m,_sender,sendResponse)=>{
  if(m?.type==='OMEGA_TA_AUTO_STATUS'){Promise.all([storageGet(['omega_ta_auto_enabled','omega_ta_auto_last']),chrome.alarms.get(OMEGA_ALARM)]).then(([s,a])=>sendResponse({enabled:s.omega_ta_auto_enabled!==false,last:s.omega_ta_auto_last||null,nextAt:a?.scheduledTime?new Date(a.scheduledTime).toISOString():null,stopAt:OMEGA_STOP_AT}));return true}
  if(m?.type==='OMEGA_TA_CAPTURE_NOW'){captureNow('manual').then(sendResponse);return true}
  if(m?.type==='OMEGA_TA_SET_ENABLED'){storageSet({omega_ta_auto_enabled:!!m.enabled}).then(()=>m.enabled?scheduleNext(1):chrome.alarms.clear(OMEGA_ALARM)).then(()=>sendResponse({ok:true,enabled:!!m.enabled}));return true}
});
init();

importScripts('features/data_pipeline/omega_collector_background.js');
