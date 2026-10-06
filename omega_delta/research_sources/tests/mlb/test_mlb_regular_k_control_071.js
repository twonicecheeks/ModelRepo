const assert=require('assert');
const path=require('path');

const ROOT=path.resolve(__dirname,'../..');
const m=require(path.join(ROOT,'scripts/mlb/build_mlb_regular_k_control_071.js'));

(function testReconstruction(){
  const full={
    playerId:'1',name:'Player',pa:100,strikeouts:25,walks:10,
    pitchCount:400,inZoneSwing:100,outZoneSwing:60,inZoneMiss:30,outZoneMiss:10,
    swingPct:40,whiffPct:25,swings:160,whiffs:40,kPct:25,bbPct:10
  };
  const future={pa:4,strikeouts:2,walks:1,pitches:18,swings:8,whiffs:3,games:2};
  const r=m.reconstructSkill(full,future);
  assert(r.row);
  assert.strictEqual(r.row.reconstructionCounts.pa,96);
  assert.strictEqual(r.row.reconstructionCounts.strikeouts,23);
  assert.strictEqual(r.row.reconstructionCounts.pitches,382);
  assert(Math.abs(r.row.K-(23/96*100))<1e-10);
  assert(Math.abs(r.row.Whiff-(37/152*100))<1e-10);
})();

(function testFutureFilter(){
  const rows=[
    {gamePk:'10',pitcher:'1',batter:'2',atBat:'1',description:'called_strike',event:''},
    {gamePk:'10',pitcher:'1',batter:'2',atBat:'1',description:'swinging_strike',event:'strikeout'},
    {gamePk:'11',pitcher:'1',batter:'3',atBat:'2',description:'hit_into_play',event:'field_out'},
    {gamePk:'9',pitcher:'1',batter:'4',atBat:'3',description:'swinging_strike',event:'strikeout'}
  ];
  const starts=new Map([['9',900],['10',1000],['11',1100]]);
  const x=m.futureContribution(rows,'1','pitcher',1000,starts);
  assert.strictEqual(x.pitches,3);
  assert.strictEqual(x.pa,2);
  assert.strictEqual(x.strikeouts,1);
  assert.strictEqual(x.swings,2);
  assert.strictEqual(x.whiffs,1);
  assert.strictEqual(x.games,2);
})();

(function testSkillChoice(){
  const cur={row:{playerId:'1',pa:50,K:24,BB:8,Whiff:27,Swing:48,SwStr:12.96,Contact:73},warnings:[]};
  const prev={playerId:'1',pa:500,K:22,BB:7,Whiff:25,Swing:46,SwStr:11.5,Contact:75,
    kPct:22,bbPct:7,whiffPct:25,swingPct:46};
  const x=m.chooseSkill(cur,prev,{minCurrent:30,minPrevious:60});
  assert.strictEqual(x.sourceSeason,'current');
  assert.strictEqual(x.sampleCurrent,50);
  assert.strictEqual(x.previousK,22);
})();

(function testRuleset(){
  assert.strictEqual(m.rulesetForSeason(2019),'PRE_UNIVERSAL_DH');
  assert.strictEqual(m.rulesetForSeason(2020),'UNIVERSAL_DH');
  assert.strictEqual(m.rulesetForSeason(2021),'PRE_UNIVERSAL_DH');
  assert.strictEqual(m.rulesetForSeason(2022),'UNIVERSAL_DH');
})();

console.log('PASS MLB late regular K control replay 0.7.1');

