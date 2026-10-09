'use strict';
async function refreshCollector(){
  const s=await chrome.runtime.sendMessage({type:'OMEGA_COLLECTOR_STATUS'});
  document.querySelector('#collector-state').textContent=s.paired?'Paired with OMEGA':'Not connected yet';
  document.querySelector('#collector-detail').textContent=`${s.queued} captures waiting for delivery. `+
    (s.last?s.last.ok?`Last source saved: ${s.last.league?.toUpperCase()} · ${s.last.priced_quotes||0} research quotes.`:`Last error: ${s.last.error}`:'No capture sent yet.');
  document.querySelectorAll('[data-league],#retry').forEach(e=>e.disabled=!s.paired);
}
document.addEventListener('click',async e=>{
  const b=e.target.closest('button');if(!b)return;
  const message=b.id==='open'?{type:'OMEGA_COLLECTOR_OPEN'}:b.id==='retry'?{type:'OMEGA_COLLECTOR_FLUSH'}:
    b.dataset.league?{type:'OMEGA_COLLECTOR_CAPTURE',league:b.dataset.league}:null;
  if(!message)return;b.disabled=true;document.querySelector('#collector-detail').textContent='Working…';
  try{const r=await chrome.runtime.sendMessage(message);if(r?.ok===false)throw Error(r.error);await refreshCollector();}
  catch(err){document.querySelector('#collector-detail').textContent=err.message;}finally{b.disabled=false;}
});
refreshCollector().catch(e=>document.querySelector('#collector-detail').textContent=e.message);
