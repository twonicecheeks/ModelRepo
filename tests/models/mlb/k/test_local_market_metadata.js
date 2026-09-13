const fs=require('fs');
const p='packages/models/mlb/k/structured_k_core.js';
const s=fs.readFileSync(p,'utf8');
for(const marker of ["const VERSION='1.4'",'TARGET_K_MARKET_WEIGHT=0','localKBook:localBook','localKCapturedAt:localCapturedAt',"targetMarketTruth:'PropsMadness sportsbook offers"]){
  if(!s.includes(marker)) throw new Error('missing '+marker);
}
if(s.includes("targetMarketTruth:'OddsPapi")) throw new Error('OddsPapi still owns K market truth');
console.log('PASS Structured K target market remains weight 0 and exports local market metadata');
