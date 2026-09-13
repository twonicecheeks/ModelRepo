const assert=require('assert');
const core=require('../../../packages/providers/mlb_official/src/bullpen_core.js');
assert.equal(core.VERSION,'1.1');
assert(core.buildRosterUrl(147,2026,'2026-09-07').includes('/teams/147/roster'));assert(core.buildStatsUrl(147,2026).includes('/stats?')&&core.buildStatsUrl(147,2026).includes('teamId=147'));
function pitcher(id,name,{g=50,gs=0,bf=200,so=50,bb=16,era='3.60',whip='1.20',ip='45.1'}={}){
  return {position:{type:'Pitcher',abbreviation:'P'},person:{id,fullName:name,stats:[{group:{displayName:'pitching'},type:{displayName:'season'},splits:[{season:'2026',stat:{gamesPitched:g,gamesStarted:gs,battersFaced:bf,strikeOuts:so,baseOnBalls:bb,era,whip,inningsPitched:ip}}]}]}};
}
const roster={roster:[
  pitcher(1,'Reliever 1'),pitcher(2,'Reliever 2',{era:'4.10',whip:'1.31'}),pitcher(3,'Reliever 3',{so:60}),pitcher(4,'Reliever 4',{bb:20}),pitcher(5,'Starter',{g:25,gs:25}),pitcher(55,'Starter With One Relief',{g:25,gs:24}),pitcher(6,'Current Starter',{g:28,gs:28}),
]};
const statSplits=roster.roster.map(e=>({season:'2026',player:{id:e.person.id,fullName:e.person.fullName},stat:e.person.stats[0].splits[0].stat}));const statMap=core.parseTeamPitchingStats({stats:[{splits:statSplits}]},2026);const stripped={roster:roster.roster.map(e=>({...e,person:{id:e.person.id,fullName:e.person.fullName}}))};const parsed=core.parseRoster(stripped,{teamId:147,teamCode:'NYY',year:2026,starterId:6,usedYesterday:new Set(['2']),usageKnown:true,pitchingStatsById:statMap});
assert.equal(parsed.validation.status,'validated'); assert.equal(parsed.rows.length,4); assert(!parsed.rows.some(r=>['6','5','55'].includes(r.playerId)));
assert.equal(parsed.rows.find(r=>r.playerId==='2').rest,'0'); assert.equal(parsed.rows.find(r=>r.playerId==='1').rest,'1+');
assert(Math.abs(parsed.rows.find(r=>r.playerId==='1').K-25)<1e-12); assert(Math.abs(parsed.rows.find(r=>r.playerId==='1').BB-8)<1e-12);
const sched={dates:[{games:[{gamePk:10,teams:{away:{team:{id:147}},home:{team:{id:135}}}}]}]};
const boxes=new Map([['10',{teams:{away:{pitchers:[2,7]},home:{pitchers:[8]}}}]]);
const usage=core.parseYesterdayUsage(sched,boxes,[147,135,121]);
assert(usage.knownTeams.has('147')&&usage.knownTeams.has('135')&&usage.knownTeams.has('121')); assert(usage.usedByTeam.get('147').has('2')); assert.equal(usage.usedByTeam.get('121').size,0);
const unresolved=core.parseYesterdayUsage(sched,new Map(),[147]); assert(!unresolved.knownTeams.has('147'));
console.log('PASS MLB bullpen: active relievers + season metrics + prior-day usage fail closed');
