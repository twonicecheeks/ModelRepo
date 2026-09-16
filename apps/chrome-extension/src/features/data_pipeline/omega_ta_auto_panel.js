(() => {
  'use strict';
  function fmt(v){if(!v)return '—';try{return new Date(v).toLocaleString()}catch{return String(v)}}
  async function msg(payload){return chrome.runtime.sendMessage(payload)}
  async function render(){
    const host=document.getElementById('modelDataPipelineHost')||document.body;
    let p=document.getElementById('omegaTaAutoPanel');
    if(!p){p=document.createElement('section');p.id='omegaTaAutoPanel';p.style.cssText='margin:10px 0;padding:10px;border:1px solid rgba(125,211,252,.25);border-radius:10px;background:#121923;color:#e8f2fa;font:12px system-ui';host.appendChild(p)}
    let s;try{s=await msg({type:'OMEGA_TA_AUTO_STATUS'})}catch(e){p.textContent='OMEGA T+A AUTO · background worker unavailable';return}
    const last=s?.last||{};
    p.innerHTML=`<div style="display:flex;justify-content:space-between;gap:10px;align-items:center"><b>OMEGA T+A AUTO</b><span>${s.enabled?'ON':'OFF'}</span></div><div style="font-size:10px;opacity:.75;margin:5px 0">Next: ${fmt(s.nextAt)} · Week 2 stop: ${fmt(s.stopAt)}<br>Last: ${last.ok===true?'PASS':last.ok===false?'FAIL':'—'} ${last.at?fmt(last.at):''}${last.offers?` · ${last.offers} offers`:''}${last.error?` · ${String(last.error).slice(0,120)}`:''}</div><div style="display:flex;gap:6px"><button id="omegaTaNow" style="flex:1">CAPTURE NOW</button><button id="omegaTaToggle" style="flex:1">${s.enabled?'TURN AUTO OFF':'TURN AUTO ON'}</button></div>`;
    p.querySelector('#omegaTaNow')?.addEventListener('click',async e=>{e.currentTarget.disabled=true;e.currentTarget.textContent='CAPTURING…';await msg({type:'OMEGA_TA_CAPTURE_NOW'});await render()});
    p.querySelector('#omegaTaToggle')?.addEventListener('click',async()=>{await msg({type:'OMEGA_TA_SET_ENABLED',enabled:!s.enabled});await render()});
  }
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',render):render();
  setInterval(render,60000);
})();
