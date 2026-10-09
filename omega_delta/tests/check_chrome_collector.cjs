// Worker integration with mocked Chrome/site transport; no real account or provider requests.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../../apps/chrome-extension/src');
const storage={},messages=[],external=[];let offline=true,posts=[];
const capture={leagueCode:'mlb',capturedAt:'2026-10-09T01:00:00Z',status:'PASS',pitcherBoard:[]};
const context={console,URL,Date,JSON,Array,Object,String,Error,Promise,AbortController,setTimeout,clearTimeout,
  waitForComplete:async()=>{},pageCapture:async()=>{},
  chrome:{runtime:{id:'a'.repeat(32),onMessage:{addListener:f=>messages.push(f)},onMessageExternal:{addListener:f=>external.push(f)}},
    storage:{local:{get:async keys=>Object.fromEntries((Array.isArray(keys)?keys:[keys]).filter(k=>k in storage).map(k=>[k,storage[k]])),set:async obj=>Object.assign(storage,obj)}},
    tabs:{query:async()=>[{id:1}],create:async()=>({id:1}),remove:async()=>{}},
    scripting:{executeScript:async opts=>opts.func?[{result:structuredClone(capture)}]:[]}},
  fetch:async(url,options)=>{assert.equal(url,'http://127.0.0.1:8741/api/collector/capture');if(offline)throw Error('offline');
    posts.push(JSON.parse(options.body));return {ok:true,json:async()=>({snapshot_id:'source',priced_quotes:2})};}};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'features/data_pipeline/omega_collector_background.js'),'utf8'),context);
(async()=>{
  let answer;
  external[0]({type:'OMEGA_COLLECTOR_PAIR',token:'x'.repeat(40)},{url:'https://example.com'},r=>answer=r);
  assert.equal(answer,undefined);assert.equal(storage.omega_collector_pair,undefined);
  await new Promise(resolve=>external[0]({type:'OMEGA_COLLECTOR_PAIR',token:'x'.repeat(40)},{url:'http://127.0.0.1:8741/?collector=x#collector'},r=>{answer=r;resolve();}));
  assert.equal(answer.ok,true);
  await assert.rejects(vm.runInContext("omegaCollect('mlb')",context),/offline/);
  assert.equal(storage.omega_collector_queue.length,1);
  assert.equal(storage.omega_collector_queue[0].capturedAt,capture.capturedAt);
  offline=false;await vm.runInContext('omegaFlush()',context);
  assert.equal(storage.omega_collector_queue.length,0);assert.equal(posts[0].capture.capturedAt,capture.capturedAt);
  await vm.runInContext("omegaCollect('mlb')",context);
  assert.equal(storage.omega_collector_last.ok,true);
  storage.service_token='never-export';storage.model_mlb_k_projection_board_current={expectedK:6};
  await vm.runInContext("omegaHandle({type:'OMEGA_COLLECTOR_ARCHIVE'})",context);
  assert.equal(posts.at(-1).capture.artifacts.service_token,undefined);
  assert.equal(posts.at(-1).capture.artifacts.model_mlb_k_projection_board_current.expectedK,6);
  const manifest=JSON.parse(fs.readFileSync(path.join(root,'manifest.json')));
  assert(manifest.host_permissions.includes('http://127.0.0.1:8741/*'));
  assert(manifest.externally_connectable.matches.includes('http://127.0.0.1/*'));
  const popup=fs.readFileSync(path.join(root,'popup.html'),'utf8');
  assert(popup.includes('omega_collector_panel.js'));assert(!popup.includes('structured_k_core.js'));
  assert(fs.existsSync(path.join(root,'popup_legacy.html')));
  console.log('PASS worker: pairing scope, offline recovery, original timestamps, legacy allowlist, collector-only popup');
})().catch(e=>{console.error(e);process.exitCode=1;});
