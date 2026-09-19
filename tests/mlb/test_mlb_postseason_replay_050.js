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
  const rows=m.parsePitchingGameLog(payload);
  assert.strictEqual(rows.length,3);
  const selected=m.selectWorkloadHistory(rows,'2024-10-01T20:00:00Z');
  assert.strictEqual(selected.mode,'REGULAR_SEASON_STARTS');
  assert.deepStrictEqual(selected.rows.map(x=>x.outs),[17,18]);
  const wk=m.workloadMarkets(rows,'2024-10-01T20:00:00Z');
  const mk=wk.markets;
  assert.strictEqual(wk.mode,'REGULAR_SEASON_STARTS');
  assert.strictEqual(mk['player-pitcher-outs'].representative,null);
  assert.strictEqual(mk['player-pitcher-outs'].statistics.overall.season.average,17.5);
  assert.deepStrictEqual(mk['player-strikeouts'].statistics.overall.l30,[7,8]);
})();

(function testNoFutureHistory(){
  const rows=[
    {date:'2024-09-20',gamesStarted:1,outs:18,er:1,hits:4,bb:1,k:8},
    {date:'2024-10-05',gamesStarted:1,outs:12,er:4,hits:7,bb:3,k:3}
  ];
  const mk=m.workloadMarkets(rows,'2024-10-01T20:00:00Z').markets;
  assert.deepStrictEqual(mk['player-pitcher-outs'].statistics.overall.l30,[18]);
  assert.deepStrictEqual(mk['player-strikeouts'].statistics.overall.l30,[8]);
})();


(function testOpenerFallback(){
  const rows=[
    {date:'2024-09-20',gamesStarted:0,outs:6,er:0,hits:1,bb:0,k:2},
    {date:'2024-09-25',gamesStarted:0,outs:9,er:1,hits:2,bb:1,k:3}
  ];
  const selected=m.selectWorkloadHistory(rows,'2024-10-01T20:00:00Z');
  assert.strictEqual(selected.mode,'REGULAR_SEASON_APPEARANCES_OPENER_FALLBACK');
  assert.deepStrictEqual(selected.rows.map(x=>x.outs),[6,9]);
})();

(function testHistoricalStartingLineupExcludesSubs(){
  const players={};
  for(let i=1;i<=9;i++){
    players['ID'+i]={person:{id:i,fullName:'Starter '+i},battingOrder:String(i*100),position:{abbreviation:'X'}};
  }
  players.ID99={person:{id:99,fullName:'Relief Pitcher'},battingOrder:'901',position:{abbreviation:'P'}};
  const lu=m.historicalStartingLineup({teams:{away:{players}}},'away');
  assert.strictEqual(lu.state,'OFFICIAL');
  assert.strictEqual(lu.hitters.length,9);
  assert(!lu.hitters.some(x=>x.mlbId==='99'));
})();

(function testParkAliasesAndTeamFallback(){
  const bundle={rows:[
    {team:'Dodgers',venue:'UNIQLO Field at Dodger Stadium'},
    {team:'Astros',venue:'Daikin Park'}
  ]};
  const fakeCore={
    getForVenue:(b,name)=>b.rows.find(r=>r.venue===name)||null
  };
  const lad=m.resolvePark(fakeCore,bundle,'Dodger Stadium','LAD');
  assert.strictEqual(lad.method,'HISTORICAL_VENUE_ALIAS');
  assert.strictEqual(lad.row.team,'Dodgers');
  const hou=m.resolvePark(fakeCore,bundle,'Minute Maid Park','HOU');
  assert.strictEqual(hou.method,'HISTORICAL_VENUE_ALIAS');
  assert.strictEqual(hou.row.team,'Astros');

  const noAliasCore={getForVenue:()=>null};
  const fallback=m.resolvePark(noAliasCore,{rows:[{team:'Dodgers',venue:'some dodger stadium label'}]},'Unknown','LAD');
  assert.strictEqual(fallback.method,'HOME_TEAM_IDENTITY');
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

console.log('PASS MLB postseason history-proxy replay builder 0.5.4');
