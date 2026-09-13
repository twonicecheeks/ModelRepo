const assert=require('assert');
const core=require('../../../packages/providers/fangraphs/src/wrc_core.js');
assert.equal(core.VERSION,'1.0');
const url=core.buildUrl(2026); assert(url.includes('season=2026')&&url.includes('stats=bat')&&url.includes('type=8'));
const current=core.parseLeaderboard({data:[
  {xMLBAMID:111,playerid:'fg1',PlayerName:'Exact Current','PA':500,'wRC+':132},
  {xMLBAMID:222,playerid:'fg2',PlayerName:'Other','PA':240,'wRC+':94},
  {xMLBAMID:'',PlayerName:'No MLB id','PA':400,'wRC+':120},
  {xMLBAMID:333,PlayerName:'Missing wrc','PA':400,'wRC+':null},
]},2026);
const previous=core.parseLeaderboard({data:[
  {xMLBAMID:111,playerid:'fg1',PlayerName:'Exact Previous','PA':610,'wRC+':118},
  {xMLBAMID:444,playerid:'fg4',PlayerName:'Previous Only','PA':300,'wRC+':105},
]},2025);
assert.equal(current.byId.get('111').wrcPlus,132); assert.equal(current.rejectedCount,2);
const bundle=core.seasonBundle(current,previous);
const cur=core.getForSavantRow(bundle,111,{sourceSeason:'current'}); assert.equal(cur.wrcPlus,132); assert.equal(cur.sourceSeason,'current'); assert.equal(cur.seasonFallback,false);
const prev=core.getForSavantRow(bundle,111,{sourceSeason:'previous'}); assert.equal(prev.wrcPlus,118); assert.equal(prev.sourceSeason,'previous'); assert.equal(prev.seasonFallback,false);
const fallback=core.getForSavantRow(bundle,444,{sourceSeason:'current'}); assert.equal(fallback.wrcPlus,105); assert.equal(fallback.seasonFallback,true);
assert.equal(core.getForSavantRow(bundle,999,{sourceSeason:'current'}),null);
assert.equal(typeof core.getByName,'undefined');
console.log('PASS FanGraphs wRC+: exact MLBAM join + season selection + fail closed');
