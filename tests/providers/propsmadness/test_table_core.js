const assert=require('assert');
const core=require('../../../packages/providers/propsmadness/src/table_core.js');
const cfg=core.MARKET_CONFIG[0];
const payload={leagueCode:'mlb',market:{id:68,name:'Player Strikeouts',slug:'player-strikeouts'},offers:[
 {offer:{matchId:123,player:{id:456,name:'Test Pitcher',position:'SP',teamId:9},bet:{line:5.5,market:{id:68,slug:'player-strikeouts'},sportsbook:{name:'FanDuel',slug:'fanduel'},odds:{over:-110,under:-110}}},statistics:{overall:{l30:[3,5,7],season:{average:5.2,hit:8,total:15},pitcherGrade:24},vsLeft:{l30:[1]},vsRight:{l30:[2]}}}
]};
const m=core.normalizeMarketPayload(payload,cfg,'2026-09-06T19:00:00Z');
assert.equal(m.offerCount,1);assert.equal(m.offers[0].statistics.overall.l30.length,3);assert.equal(m.offers[0].statistics.overall.season.average,5.2);
const board=core.buildPitcherBoard({'player-strikeouts':m});
assert.equal(board.length,1);assert.deepEqual(board[0].markets['player-strikeouts'].statistics.overall.l30,[3,5,7]);assert.equal(board[0].markets['player-strikeouts'].observedAt,'2026-09-06T19:00:00Z');
const summary=core.marketSummary(m);assert(!('offers' in summary));assert.equal(summary.offerCount,1);
console.log('PASS test_props_core');
