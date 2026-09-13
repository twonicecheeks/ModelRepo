const assert=require('assert');
const core=require('../../../packages/providers/baseball_savant/src/park_factor_core.js');
assert.equal(core.VERSION,'1.1');
assert(core.buildUrl(2026).includes('rolling=3'));
assert(core.buildUrl(2026,2).includes('rolling=2'));
assert(core.buildUrl(2026,1).includes('rolling=1'));
assert(core.buildUrl(2026).includes('type=year'));
const header=['Rk.','Team','Venue','Year','Park Factor','wOBAcon','xwOBAcon','BACON','xBACON','HardHit','R','OBP','H','1B','2B','3B','HR','BB','SO','PA'];
const venues=[
  ['Rockies','Coors Field','2024-2026',112,112,101,112,102,101,125,110,117,115,123,209,108,98,90,'54,107'],
  ['Red Sox','Fenway Park','2024-2026',103,103,99,105,100,99,106,104,105,104,120,91,88,98,97,'53,887'],
  ...Array.from({length:20},(_,i)=>[`T${i}`,`Venue ${i}`,'2024-2026',100,100,100,100,100,100,100+i%3,100,100,100,100,100,100,100,100,10000+i])
];
const html='<table><thead><tr>'+header.map(x=>`<th>${x}</th>`).join('')+'</tr></thead><tbody>'+venues.map((r,i)=>'<tr><td>'+(i+1)+'</td>'+r.map(x=>`<td>${x}</td>`).join('')+'</tr>').join('')+'</tbody></table>';
const b=core.parseHtml(html,2026,3);
assert.equal(b.rowCount,22);
const coors=core.getForVenue(b,'Coors Field');
assert(coors);assert.equal(coors.runIndex,125);assert.equal(coors.runFactor,1.15);assert.deepEqual(core.conditionLines(coors),['Park: Coors Field','Runs +25%']);
const fenway=core.getForVenue(b,'Fenway Park');assert.equal(fenway.runFactor,1.06);assert.equal(fenway.fallbackWindowUsed,false);
assert.equal(core.getForVenue(b,'Unknown Park'),null);
assert.equal(core.canonicalVenue('Oriole Park at Camden Yards'),'oriole camden yards');

const jsonRows=[
  {team:'Rockies',venue_name:'Coors Field',year:'2024-2026',index_woba:113,index_runs:128,pa:48373},
  {team:'Orioles',venue_name:'Oriole Park at Camden Yards',year:'2024-2026',index_woba:103,index_runs:106,pa:48603},
  ...Array.from({length:20},(_,i)=>({team:`J${i}`,venue_name:`JSON Venue ${i}`,year:'2024-2026',index_woba:100,index_runs:95+(i%11),pa:40000+i}))
];
const inline='<html><script>const data = '+JSON.stringify(jsonRows)+';</script></html>';
const jb=core.parseHtml(inline,2026,3);
assert.equal(jb.rowCount,22);
assert.equal(core.getForVenue(jb,'Coors Field').runIndex,128);
assert.equal(core.getForVenue(jb,'Oriole Park at Camden Yards').runFactor,1.06);

// New-venue fallback: 3y bundle omits Sutter, 2y bundle supplies it. Merge must preserve
// the 3y row for mature venues and use the longest available shorter window only for Sutter.
const twoYearRows=[
  {team:'Athletics',venue_name:'Sutter Health Park',year:'2025-2026',index_woba:108,index_runs:117,pa:13794},
  {team:'Rockies',venue_name:'Coors Field',year:'2025-2026',index_woba:114,index_runs:130,pa:14912},
  ...Array.from({length:20},(_,i)=>({team:`K${i}`,venue_name:`Venue ${i}`,year:'2025-2026',index_woba:100,index_runs:96+(i%9),pa:20000+i}))
];
const two=core.parseHtml('<html><script>const data = '+JSON.stringify(twoYearRows)+';</script></html>',2026,2);
const merged=core.mergeBundles([b,two]);
assert(merged);
assert.equal(core.getForVenue(merged,'Fenway Park').rollingYears,3);
const sutter=core.getForVenue(merged,'Sutter Health Park');
assert(sutter);assert.equal(sutter.rollingYears,2);assert.equal(sutter.runIndex,117);assert.equal(sutter.runFactor,1.15);assert.equal(sutter.fallbackWindowUsed,true);
assert.deepEqual(core.conditionLines(sutter),['Park: Sutter Health Park','Runs +17% (2y fallback)']);
assert.equal(merged.fallbackRowCount,1);
assert.equal(merged.fallbackVenues[0].venue,'Sutter Health Park');
console.log('PASS Baseball Savant park-factor provider: preferred 3-year R index + explicit longest-available 2y/1y fallback');
