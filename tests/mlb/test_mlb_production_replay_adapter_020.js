const assert = require('assert');
const path = require('path');

const ROOT = path.resolve(__dirname, '../..');
const ml = require(path.join(ROOT, 'packages/models/mlb/moneyline/structured_ml_core.js'));
const k = require(path.join(ROOT, 'packages/models/mlb/k/structured_k_core.js'));
const replay = require(path.join(ROOT, 'packages/models/mlb/evaluation/production_replay_adapter_020.js'));

function lineupML(mult=1) {
  return Array.from({length:9}, (_,i)=>({
    PA: 250 + i*8,
    metrics: {
      'wRC+': 100*mult + (i-4),
      'ISO': .170*mult,
      'xSLG': .400*mult,
      'xwOBA': .320*mult,
      'BB%': 8.5,
      'K%': 22.5,
      'BA': .245,
      'HardHit%': 39,
      'Barrel%': 8,
      'Contact%': 75,
      'Whiff%': 25,
      'SwStr%': 11.5,
    }
  }));
}

function starterML({offMult=1, ip=5.5, era=4.1}) {
  const lineup = lineupML(offMult);
  return {
    pitcherMetrics: {
      'xwOBA': .315, 'BA': .240, 'xSLG': .390, 'HardHit%': 38,
      'Barrel%': 7.5, 'K%': 24, 'BB%': 7.5, 'Whiff%': 26
    },
    opponentTeamMetrics: {
      'xwOBA': .320*offMult, 'BA': .245, 'xSLG': .400*offMult,
      'HardHit%': 39, 'Barrel%': 8, 'K%': 22.5, 'BB%': 8.5, 'Contact%':75
    },
    lineupStatus: 'Official',
    lineup,
    workload: {IP:ip, expectedOuts:ip*3, state:'CURRENT_GAME', productionEligible:true},
    bullpen: Array.from({length:5}, ()=>({ERA:era, WHIP:1.25, K:24, BB:8, rest:'1'})),
    bullpenValidation: {status:'validated'},
    gameConditions: ['Runs +2%'],
  };
}

function market(line, overOdds, underOdds, avg, l30, capturedAt) {
  return {
    state:'COMPLETE',
    observedAt:capturedAt,
    representative:{line,overOdds,underOdds,capturedAt,sportsbook:'Test',sportsbookSlug:'test'},
    statistics:{overall:{season:{average:avg},l30}},
  };
}

function kInputs() {
  const t = '2025-10-08T19:00:00Z';
  const starter = {
    officialName:'Test Pitcher',
    officialMlbId:'999',
    team:'TST',
    gamePk:'gk1',
    markets:{
      'player-strikeouts': market(5.5,-105,-115,5.3,[4,6,7,5,6],t),
      'player-pitcher-outs': market(15.5,-110,-110,16.2,[18,15,17,16,15],t),
      'player-earned-runs': market(2.5,-110,-110,2.4,[2,3,1,4,2],t),
      'player-hits-allowed': market(5.5,-110,-110,5.1,[5,6,4,7,5],t),
      'player-walks': market(1.5,-110,-110,1.9,[2,1,3,2,1],t),
    }
  };
  const lineup = Array.from({length:9}, (_,i)=>({
    pa: 300+i*5, K: 24+(i%3), Whiff:26, SwStr:12.2, Contact:73.5
  }));
  const pitcher = {
    pa:400,K:27,Whiff:29,SwStr:13.5,Contact:71,
    sourceSeason:'current',sampleCurrent:400,samplePrevious:500,
    previousK:25,previousWhiff:27,previousSwStr:12.5,previousContact:72
  };
  return {starter,lineup,pitcher,t};
}

(function testML(){
  const game = {
    away:'AAA',
    home:'BBB',
    starters:{
      AAA: starterML({offMult:1.04, ip:5.7, era:4.0}),
      BBB: starterML({offMult:.97, ip:5.4, era:4.3}),
    }
  };
  const direct = ml.projectGame(game);
  assert(direct.complete);

  const out = replay.replayRow({
    replay_type:'ML',
    game_id:'g1',game_date:'2025-10-07',season:2025,season_type:'POST',
    snapshot_at:'2025-10-07T22:00:00Z',
    selection_team:'BBB',actual_home_win:1,
    production_input:game,
    replay_input_mode:'EXACT_PRODUCTION_SNAPSHOT',
  });
  assert.strictEqual(out.model_probability, direct.homeWin);
  assert.strictEqual(out.actual_win, 1);
  assert.strictEqual(out.production_model_version, ml.MODEL_VERSION);
  assert.strictEqual(out.season_type, 'POST');
})();

(function testK(){
  const {starter,lineup,pitcher,t} = kInputs();
  const now = Date.parse(t);
  const directDistribution = k.buildDistribution(starter,lineup,pitcher,now);
  const direct = k.evaluateAtLine(directDistribution,5.5,{
    overOdds:-105,underOdds:-115,evaluationSource:'test'
  });
  const out = replay.replayRow({
    replay_type:'K',
    game_id:'gk1',game_date:'2025-10-08',season:2025,season_type:'POST',
    snapshot_at:t,
    side:'OVER',line:5.5,actual_k:7,market_odds:-105,
    over_odds:-105,under_odds:-115,
    starter_input:starter,lineup_rows:lineup,pitcher_row:pitcher,
    replay_input_mode:'EXACT_PRODUCTION_SNAPSHOT',
  });
  assert(Math.abs(out.xk-direct.expectedK)<1e-12);
  assert(Math.abs(out.model_probability-direct.overProb)<1e-12);
  assert.strictEqual(out.production_model_version,k.MODEL_VERSION);
  assert.strictEqual(out.target_k_market_excluded_from_expected_k,true);
  assert.strictEqual(out.distribution_independent_of_target_k_line,true);
})();

(function testIdentity(){
  const id = replay.coreIdentity();
  assert.strictEqual(id.ml.modelVersion, ml.MODEL_VERSION);
  assert.strictEqual(id.k.modelVersion, k.MODEL_VERSION);
  assert.strictEqual(id.k.targetKMarketWeight, 0);
})();

console.log('PASS MLB exact production replay adapter 0.2.0');
