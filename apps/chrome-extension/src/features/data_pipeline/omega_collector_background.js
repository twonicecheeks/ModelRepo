/* OMEGA owns forecasts; this worker collects sources using the user's site session. */
'use strict';
const OMEGA_HOME='http://127.0.0.1:8741';
let omegaCaptureBusy=false;
async function omegaCollectorStatus(){
  const s=await chrome.storage.local.get(['omega_collector_pair','omega_collector_queue','omega_collector_last']);
  return {paired:!!s.omega_collector_pair?.token,extensionId:chrome.runtime.id,
    queued:(s.omega_collector_queue||[]).length,last:s.omega_collector_last||null,appUrl:OMEGA_HOME};
}
async function omegaDeliver(capture){
  const s=await chrome.storage.local.get('omega_collector_pair');
  if(!s.omega_collector_pair?.token)throw Error('Connect this collector from the OMEGA app first.');
  const ac=new AbortController(),timer=setTimeout(()=>ac.abort(),20000);
  try{
    const r=await fetch(OMEGA_HOME+'/api/collector/capture',{method:'POST',credentials:'omit',cache:'no-store',
      signal:ac.signal,headers:{'Content-Type':'application/json','X-Omega-Collector-Token':s.omega_collector_pair.token},
      body:JSON.stringify({capture})});
    const data=await r.json();if(!r.ok)throw Error(data.error||`OMEGA HTTP ${r.status}`);
    return data;
  }finally{clearTimeout(timer);}
}
async function omegaFlush(){
  const s=await chrome.storage.local.get('omega_collector_queue');let queue=s.omega_collector_queue||[];
  while(queue.length){await omegaDeliver(queue[0]);queue=queue.slice(1);await chrome.storage.local.set({omega_collector_queue:queue});}
  return {ok:true,queued:0};
}
async function omegaCollect(league='mlb'){
  if(!['mlb','nfl'].includes(league))throw Error('Choose MLB or NFL.');
  if(omegaCaptureBusy)throw Error('A capture is already running.');
  const paired=await omegaCollectorStatus();if(!paired.paired)throw Error('Connect the collector to OMEGA first.');
  omegaCaptureBusy=true;let tab,created=false;
  try{
    await omegaFlush();
    const patterns=league==='mlb'?['https://propsmadness.com/mlb/props/*','https://www.propsmadness.com/mlb/props/*']:
      ['https://propsmadness.com/nfl*','https://www.propsmadness.com/nfl*'];
    const found=await chrome.tabs.query({url:patterns});
    tab=found[0]||await chrome.tabs.create({url:league==='mlb'?'https://propsmadness.com/mlb/props/player-strikeouts':'https://propsmadness.com/nfl',active:false});
    created=!found[0];await waitForComplete(tab.id);
    if(league==='mlb')await chrome.scripting.executeScript({target:{tabId:tab.id},world:'MAIN',
      files:['providers/propsmadness/table_core.js','providers/propsmadness/table_main.js']});
    const r=await chrome.scripting.executeScript({target:{tabId:tab.id},world:'MAIN',
      func:league==='mlb'?async()=>await window.__MODEL_PM_TABLE_RUN__():pageCapture});
    const capture=r?.[0]?.result;
    if(!capture)throw Error('The source page returned no capture.');
    if(league==='nfl'){capture.leagueCode='nfl';capture.capturedAt=capture.exportedAt;}
    // Preserve original observation times when a stopped app delays delivery.
    const state=await chrome.storage.local.get('omega_collector_queue');const queue=state.omega_collector_queue||[];
    if(queue.length>=3||JSON.stringify([...queue,capture]).length>16000000)throw Error('OMEGA capture queue is full; open the app and retry delivery.');
    await chrome.storage.local.set({omega_collector_queue:[...queue,capture]});
    const result=await omegaDeliver(capture);
    await chrome.storage.local.set({omega_collector_queue:queue,omega_collector_last:{ok:true,at:new Date().toISOString(),league,...result}});
    return {ok:true,...result};
  }catch(e){await chrome.storage.local.set({omega_collector_last:{ok:false,at:new Date().toISOString(),league,error:String(e.message||e)}});throw e;}
  finally{omegaCaptureBusy=false;if(created&&tab?.id){try{await chrome.tabs.remove(tab.id);}catch{}}}
}
async function omegaHandle(m){
  if(m.type==='OMEGA_COLLECTOR_STATUS')return omegaCollectorStatus();
  if(m.type==='OMEGA_COLLECTOR_OPEN'){await chrome.tabs.create({url:OMEGA_HOME+'/?collector='+chrome.runtime.id+'#collector'});return {ok:true};}
  if(m.type==='OMEGA_COLLECTOR_FLUSH'){if(omegaCaptureBusy)throw Error('Capture is running.');return omegaFlush();}
  if(m.type==='OMEGA_COLLECTOR_CAPTURE')return omegaCollect(m.league||'mlb');
  if(m.type==='OMEGA_COLLECTOR_ARCHIVE'){
    const keys=['model_pm_table_snapshot_current','model_mlb_official_starter_board_current',
      'model_mlb_k_projection_board_current','model_mlb_ml_projection_board_current',
      'model_mlb_slate_radar_current','model_mlb_lineup_transition_baselines','model_data_pipeline_audit_current',
      'model_mlb_public_research_current','modelV2LastEdgeBoard','modelV2PreviousEdgeBoard',
      'model_nfl_matchup_research_current','model_nfl_omega_matchup_current'];
    const artifacts=await chrome.storage.local.get(keys);
    return omegaDeliver({leagueCode:'legacy',schemaVersion:'OMEGA_CHROME_LEGACY_ARCHIVE_V1',
      archivedAt:new Date().toISOString(),artifacts});
  }
  throw Error('Unknown collector action.');
}
chrome.runtime.onMessage.addListener((m,_sender,reply)=>{
  if(!String(m?.type||'').startsWith('OMEGA_COLLECTOR_'))return;
  omegaHandle(m).then(reply,e=>reply({ok:false,error:String(e.message||e)}));return true;
});
chrome.runtime.onMessageExternal.addListener((m,sender,reply)=>{
  let u;try{u=new URL(sender.url);}catch{return;}
  if(u.origin!==OMEGA_HOME)return;
  if(m?.type==='OMEGA_COLLECTOR_PAIR'){
    if(typeof m.token!=='string'||m.token.length<32){reply({ok:false,error:'Invalid collector key.'});return;}
    chrome.storage.local.set({omega_collector_pair:{token:m.token,pairedAt:new Date().toISOString()}}).then(()=>reply({ok:true}));return true;
  }
  if(['OMEGA_COLLECTOR_STATUS','OMEGA_COLLECTOR_CAPTURE','OMEGA_COLLECTOR_FLUSH','OMEGA_COLLECTOR_ARCHIVE'].includes(m?.type)){
    omegaHandle(m).then(reply,e=>reply({ok:false,error:String(e.message||e)}));return true;
  }
});
