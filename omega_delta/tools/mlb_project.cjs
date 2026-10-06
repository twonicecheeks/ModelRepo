// Run the recovered, pinned structured engines against normalized inputs.
const fs=require('node:fs');
const ml=require('../models/mlb/moneyline/structured_ml_core.js');
const k=require('../models/mlb/k/structured_k_core.js');
const text=fs.readFileSync(0,'utf8');
const rows=JSON.parse(text);
const result=rows.map(r=>{
  if(r.replay_type==='ML'){
    const b=ml.projectGame(r.production_input);
    if(!b.complete)throw Error(b.reason||'Incomplete moneyline input');
    return {market_type:'ML',base:b};
  }
  if(r.replay_type==='K'){
    if(r.lineup_rows?.length!==9)throw Error('Nine confirmed lineup rows are required');
    return {market_type:'K',base:k.buildDistribution(r.starter_input,r.lineup_rows,r.pitcher_row,Date.parse(r.snapshot_at))};
  }
  throw Error('Unknown replay type');
});
process.stdout.write(JSON.stringify(result));
