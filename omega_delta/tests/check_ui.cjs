// Deterministic UI template checks. This is not a browser/layout test.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path'),os=require('node:os'),cp=require('node:child_process');
const root=path.resolve(__dirname,'..'),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'omega-ui-'));
try{
  if(!process.env.OMEGA_UI_STATE) cp.execFileSync(process.env.OMEGA_PYTHON||'python3',[path.join(root,'tools/build_preview.py'),
    '--output',path.join(tmp,'preview.html'),'--state-output',path.join(tmp,'state.json')]);
  const data=JSON.parse(fs.readFileSync(process.env.OMEGA_UI_STATE||path.join(tmp,'state.json'),'utf8'));
  const nodes=new Map();
  function node(id){if(!nodes.has(id))nodes.set(id,{innerHTML:'',textContent:'',open:false,
    classList:{toggle(){},remove(){}},insertAdjacentHTML(where,html){this.innerHTML=html+this.innerHTML},
    addEventListener(){},showModal(){this.open=true},close(){this.open=false}});return nodes.get(id);}
  const ctx={console,URL,URLSearchParams,Date,Intl,Set,Map,Math,Number,String,JSON,Array,Object,Promise,
    FormData:function(){},setTimeout(){},clearTimeout(){},setInterval(){},location:{hash:''},
    document:{querySelector:node,querySelectorAll(){return []},addEventListener(){},getElementById:node},
    window:{OMEGA_PREVIEW:data,addEventListener(){},scrollTo(){}}};
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(root,'web/app.js'),'utf8'),ctx);
  // Supply state directly: async load() at script end is harmless for these pure renders.
  ctx.fixtureState=data;vm.runInContext('S=fixtureState',ctx);
  for(const page of ['collector','delta','deltatest','mlb','mlbtest','forecasts','lab','review','markets','bets','poly','validation','system']){
    vm.runInContext(`tab='${page}';render()`,ctx);
    const html=node('#screen').innerHTML;
    assert(html.length>1000,page+' rendered');
    for(const invalid of ['NaN','[object Object]','undefined'])assert(!html.includes(invalid),page+' has no '+invalid);
    console.log('PASS view template:',page);
  }
  vm.runInContext("F.q='Roquan';tab='forecasts';render()",ctx);
  assert(node('#screen').innerHTML.includes('Roquan Smith'));
  assert(!node('#screen').innerHTML.includes('Carson Schwesinger'));
  vm.runInContext("F.reviewLane='MATCHED';tab='review';render()",ctx);
  assert(node('#screen').innerHTML.includes('+0.081'));
  vm.runInContext("playerModal(S.forecasts.find(r=>r.player_name==='Roquan Smith').player_id,'2026_03_BAL_DAL')",ctx);
  assert(node('#modal-content').innerHTML.includes('Where the expected tackles come from'));
  vm.runInContext('newBet()',ctx);
  assert(node('#modal-content').innerHTML.includes('Record a bet you placed'));
  assert.equal(vm.runInContext("fmt('')",ctx),'—');
  assert.equal(vm.runInContext("money(null)",ctx),'—');
  vm.runInContext("tab='delta';deltaLine=5;render()",ctx);
  assert(node('#screen').innerHTML.includes('Historical replay example'));
  assert(node('#screen').innerHTML.includes('Stuff+/PitchingBot'));
  assert(node('#screen').innerHTML.includes('Integer pushes return the stake'));
  assert(node('#screen').innerHTML.includes('Public pitch-data preparation'));
  assert(node('#screen').innerHTML.includes('/api/delta/data-sources.md'));
  vm.runInContext("tab='deltatest';render()",ctx);
  assert(node('#screen').innerHTML.includes('does not beat V2'));
  assert(node('#screen').innerHTML.includes('775'));
  assert(node('#screen').innerHTML.includes('Proposed fixed postseason adjustments'));
  assert(node('#screen').innerHTML.includes('455 of 775 actual starters'));
  assert(node('#screen').innerHTML.includes('Historical market benchmark'));
  assert(node('#screen').innerHTML.includes('/api/delta/market-template.csv'));
  assert.equal(vm.runInContext("deltaProbs([.1,.2,.3,.4],2).push",ctx),.3);
  vm.runInContext("S.scores.push({...S.scores[0],week:'3',game_id:'2026_03_TEST_TEST'});tab='review';render()",ctx);
  assert(node('#screen').innerHTML.includes('Week 3'));
  vm.runInContext("S.jobs=[{id:'fixture',kind:'validation',status:'RUNNING'}];tab='system';render()",ctx);
  assert(node('#screen').innerHTML.includes('Running: validation'));
  const injected="<img src=x onerror=alert(1)>";
  ctx.injected=injected;vm.runInContext("S.forecasts[0].player_name=injected;F.q='';tab='forecasts';render()",ctx);
  assert(!node('#screen').innerHTML.includes(injected));
  console.log('PASS search, cohorts, player detail, ticket form, missing displays, future weeks, jobs, and text escaping.');
  console.log('UI templates verified; full visual browser execution is a separate gate.');
}finally{fs.rmSync(tmp,{recursive:true,force:true});}
