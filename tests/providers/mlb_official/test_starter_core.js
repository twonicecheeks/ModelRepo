const assert=require('assert');
const core=require('../../../packages/providers/mlb_official/src/starter_core.js');
const awayPlayers=Array.from({length:9},(_,i)=>({id:100+i,fullName:`Away Hitter ${i+1}`,primaryPosition:{abbreviation:'OF'}}));
const homePlayers=Array.from({length:9},(_,i)=>({id:200+i,fullName:`Home Hitter ${i+1}`,primaryPosition:{abbreviation:'IF'}}));
const schedule=core.parseSchedule({dates:[{games:[{gamePk:1,gameDate:'2026-09-06T20:00:00Z',status:{abstractGameState:'Preview',detailedState:'Scheduled'},venue:{id:2680,name:'Petco Park'},lineups:{awayPlayers,homePlayers},teams:{away:{team:{id:147,name:'New York Yankees'},probablePitcher:{id:10,fullName:'Away Ace'}},home:{team:{id:135,name:'San Diego Padres'},probablePitcher:{id:20,fullName:'Home Ace'}}}}]}]},Date.parse('2026-09-06T19:50:00Z'));
assert.equal(core.VERSION,'1.5');assert.equal(schedule[0].awayTeamId,'147');assert.equal(schedule[0].homeTeamId,'135');assert.equal(schedule[0].venueId,'2680');assert.equal(schedule[0].venueName,'Petco Park');assert.equal(schedule[0].lineups.away.state,'OFFICIAL');assert.equal(schedule[0].lineups.away.hitters[0].mlbId,'100');
function cand(matchId,id,name,teamId,hand='right'){const markets={};for(const slug of core.MARKET_SLUGS)markets[slug]={observedAt:'2026-09-06T19:50:00Z',statistics:{overall:{l30:[1,2],season:{average:5}}},offers:[{sportsbook:{name:'Book',slug:'book'},line:5.5,odds:{over:-110,under:-110}}]};return{key:`${matchId}:${id}`,matchId:String(matchId),playerId:String(id),player:{name,position:'SP',teamId:String(teamId),throwingHand:hand},markets,marketCount:5};}
const rankings={'22':{strikeoutPercentageVsRightAllowed:4,whiffPercentageVsRightAllowed:7,contactPercentageVsRightAllowed:25}};
const board=core.buildStarterBoard(schedule,[cand(100,1,'Away Ace',11),cand(999,2,'Away Ace',11),cand(100,3,'Home Ace',22)],'2026-09-06T19:50:00Z',rankings);
assert.equal(board.games[0].state,'VERIFIED');assert.equal(board.games[0].propsMatchId,'100');assert.equal(board.verifiedStarterSlots,2);
assert.equal(board.games[0].starters.away.opponentRankContext.kRank,4);assert.equal(board.games[0].starters.away.opponentRankContext.semantics.includes('ordinal'),true);
assert.equal(board.games[0].starters.away.markets['player-strikeouts'].offers.length,1);assert.equal(board.games[0].starters.away.markets['player-strikeouts'].offers[0].sportsbook.slug,'book');
// Boxscore fallback parser must recover a 9-man official order.
const players={};const battingOrder=[];for(let i=0;i<9;i++){const id=300+i;battingOrder.push(id);players['ID'+id]={person:{id,fullName:`B${i+1}`},position:{abbreviation:'IF'},battingOrder:String((i+1)*100)};}
const box={teams:{away:{players,battingOrder},home:{players,battingOrder}}};
const recovered=core.resolveLineup({state:'PENDING',hitters:[]},box,'away');assert.equal(recovered.state,'OFFICIAL');assert.equal(recovered.hitters.length,9);
const started=core.parseSchedule({dates:[{games:[{gamePk:2,gameDate:'2026-09-06T19:40:00Z',status:{abstractGameState:'Preview',detailedState:'Scheduled'},teams:{away:{team:{name:'New York Yankees'}},home:{team:{name:'San Diego Padres'}}}}]}]},Date.parse('2026-09-06T19:50:00Z'));assert.equal(started[0].pregame,false);
console.log('PASS test_starter_core');
