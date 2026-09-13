const assert=require('assert');
const core=require('../../../packages/providers/baseball_savant/src/savant_core.js');
assert.equal(core.VERSION,'1.2');
const header='"last_name, first_name",player_id,year,pa,k_percent,bb_percent,batting_avg,xba,xslg,xwoba,isolated_power,hard_hit_percent,barrel_batted_rate,whiff_percent,swing_percent';
const csv26=header+'\n"Cole, Gerrit",543037,2026,20,31.2,7.5,.214,.220,.390,.305,.176,41.2,8.9,30.0,50.0\n"Current, Regular",2,2026,200,22,8,.271,.265,.455,.342,.184,44.5,10.1,24,45\n';
const csv25=header+'\n"Cole, Gerrit",543037,2025,600,29.0,7.0,.230,.235,.410,.315,.180,42.0,9.2,28.0,49.0\n';
const cur=core.parseLeaderboard(csv26,'pitcher',2026), prev=core.parseLeaderboard(csv25,'pitcher',2025);
const bundle=core.seasonBundle(cur,prev);
const r=core.getRow(bundle,'543037',{minCurrent:30,minPrevious:60});
assert.equal(r.sourceSeason,'previous');assert.equal(r.kPct,29);assert.equal(r.contactPct,72);assert(Math.abs(r.swStrPct-13.72)<1e-9);
assert.equal(r.ba,.230);assert.equal(r.xba,.235);assert.equal(r.xslg,.410);assert.equal(r.xwoba,.315);assert.equal(r.iso,.180);assert.equal(r.hardHitPct,42);assert.equal(r.barrelPct,9.2);assert.equal(r.wrcPlus,null);
const r2=core.getRow(bundle,'2',{minCurrent:30,minPrevious:60});assert.equal(r2.sourceSeason,'current');assert.equal(r2.xwoba,.342);
const url=core.buildUrl(2026,'pitcher');
for(const field of ['batting_avg','xba','xslg','xwoba','isolated_power','hard_hit_percent','barrel_batted_rate']) assert(url.includes(field),`URL missing ${field}`);
assert(url.includes('csv=true'));assert(url.includes('min=1'));assert(core.compactBundle(bundle).current.uniquePlayerCount===2);

const csvBf='"last_name, first_name",player_id,year,bf,k_percent,bb_percent,whiff_percent,swing_percent\n"Pitcher, BF",99,2026,77,24,8,26,47\n';
const bf=core.parseLeaderboard(csvBf,'pitcher',2026);const br=bf.byId.get('99');assert.equal(br.pa,77);
// Missing optional offense columns must remain null, never silently become numeric zero.
for(const key of ['ba','xba','xslg','xwoba','iso','hardHitPct','barrelPct']) assert.equal(br[key],null,`${key} should be null`);
console.log('PASS test_savant_core v1.2 expanded metrics + null-safe parsing');
