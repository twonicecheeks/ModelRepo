const assert=require('assert');
const path=require('path');

const ROOT=path.resolve(__dirname,'../..');
const m=require(path.join(ROOT,'scripts/mlb/build_mlb_postseason_replay_050.js'));

(function testIp(){
  assert.strictEqual(m.ipToOuts('5.2'),17);
  assert.strictEqual(m.ipToOuts('6.0'),18);
  assert.strictEqual(m.ipToOuts('3.1'),10);
  assert.strictEqual(m.ipToOuts('2.3'),null);
})();

(function testGameLog(){
  const payload={stats:[{splits:[
    {date:'2024-04-01',game:{gamePk:1},stat:{gamesStarted:1,inningsPitched:'5.2',earnedRuns:2,hits:5,baseOnBalls:1,strikeOuts:7,battersFaced:23,numberOfPitches:92}},
    {date:'2024-04-07',game:{gamePk:2},stat:{gamesStarted:1,inningsPitched:'6.0',earnedRuns:1,hits:4,baseOnBalls:2,strikeOuts:8,battersFaced:24,numberOfPitches:96}},
    {date:'2024-04-10',game:{gamePk:3},stat:{gamesStarted:0,inningsPitched:'1.0',earnedRuns:0,hits:0,baseOnBalls:0,strikeOuts:1,battersFaced:3,numberOfPitches:12}}
  ]}]};
  const rows=m.parseStarterGameLog(payload);
  assert.strictEqual(rows.length,2);
  assert.deepStrictEqual(rows.map(x=>x.outs),[17,18]);
  const mk=m.workloadMarkets(rows,'2024-10-01T20:00:00Z');
  assert.strictEqual(mk['player-pitcher-outs'].representative,null);
  assert.strictEqual(mk['player-pitcher-outs'].statistics.overall.season.average,17.5);
  assert.deepStrictEqual(mk['player-strikeouts'].statistics.overall.l30,[7,8]);
})();

(function testNoFutureHistory(){
  const rows=[
    {date:'2024-09-20',outs:18,er:1,hits:4,bb:1,k:8},
    {date:'2024-10-05',outs:12,er:4,hits:7,bb:3,k:3}
  ];
  const mk=m.workloadMarkets(rows,'2024-10-01T20:00:00Z');
  assert.deepStrictEqual(mk['player-pitcher-outs'].statistics.overall.l30,[18]);
  assert.deepStrictEqual(mk['player-strikeouts'].statistics.overall.l30,[8]);
})();

(function testLegacyTeamCode(){
  const fakeCore={teamCode:n=>n==='Cleveland Guardians'?'CLE':null};
  assert.strictEqual(m.teamCode(fakeCore,{team_id:114,name:'Cleveland Indians'}),'CLE');
  assert.strictEqual(m.teamCode(fakeCore,{team_id:147,name:'New York Yankees'}),'NYY');
})();

(function testPriorDate(){
  assert.strictEqual(m.priorDate('2024-10-01'),'2024-09-30');
  assert.strictEqual(m.priorDate('2025-01-01'),'2024-12-31');
})();

console.log('PASS MLB postseason history-proxy replay builder 0.5.0');
