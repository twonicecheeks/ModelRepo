const assert=require('assert');
const core=require('../../../../packages/models/mlb/k/structured_k_core.js');
const now=Date.parse('2026-09-06T19:50:00Z');
function market(label,line,o,u,avg,recent,state='PRICED'){return{label,state,observedAt:'2026-09-06T19:49:30Z',representative:{line,overOdds:o,underOdds:u,capturedAt:'2026-09-06T19:49:30Z'},statistics:{overall:{l30:recent,season:{average:avg},pitcherGrade:25}}};}
function clone(x){return JSON.parse(JSON.stringify(x));}
const st={identityState:'VERIFIED',officialName:'Gerrit Cole',officialMlbId:'10',team:'NYY',opponent:'SD',marketStates:{PRICED:5},opponentRankContext:{kRank:28,whiffRank:24},markets:{
 'player-strikeouts':market('K',5.5,-110,-110,6.0,[5,7,6,8,4,7,6,5,8,7,6,7]),
 'player-pitcher-outs':market('OUTS',17.5,-110,-110,17,[18,17,18,16,19,18,17,18,16,18,17,18]),
 'player-earned-runs':market('ER',2.5,-105,-125,2.4,[2,3,1,2,4,2,2,3,1,2,2,3]),
 'player-hits-allowed':market('HA',4.5,-115,-115,4.7,[5,4,5,6,3,5,4,4,5,6,4,5]),
 'player-walks':market('BB',1.5,-110,-120,1.8,[2,1,2,3,1,2,1,2,2,1,3,1])}};
const p={pa:500,K:30,Whiff:31,SwStr:15,Contact:69};
const lineup=Array.from({length:9},(_,i)=>({pa:300-i*10,K:20+i*.5,Whiff:23+i*.4,SwStr:10.5+i*.2,Contact:77-i*.4,order:i+1}));
const proj=core.projection({...st,gamePk:'1'},lineup,p,now);assert(proj);assert(proj.expectedK>5&&proj.expectedK<8);assert.equal(proj.modelVersion,'mlb-k-v0.8.4-projection-integrity-2026-09-13');assert.equal(proj.targetKMarketExcludedFromExpectedK,true);assert.equal(proj.components.targetKMarketWeight,0);assert.equal(proj.confidence,'High');assert.equal(proj.freshnessWarning,null);assert.equal(proj.opponentRankContext.kRank,28);assert.equal(proj.components.pitcherGrade,25);assert.equal(proj.components.recentKValues.length,10);assert.equal(proj.components.recentOutsValues.length,10);assert(Number.isFinite(proj.components.expectedBF));assert(Number.isFinite(proj.components.expectedOuts));

// Critical invariant: changing the target K line or price cannot move expected K.
const stMoved=clone(st);stMoved.markets['player-strikeouts'].representative.line=8.5;stMoved.markets['player-strikeouts'].representative.overOdds=250;stMoved.markets['player-strikeouts'].representative.underOdds=-400;
const moved=core.projection({...stMoved,gamePk:'1'},lineup,p,now);assert(Math.abs(moved.expectedK-proj.expectedK)<1e-12,'target K market contaminated expected K');assert.notEqual(moved.overProb,proj.overProb,'evaluation probability should change when evaluation line changes');

// Evaluate the same independent distribution at arbitrary downstream test lines.
const eval55=core.evaluateAtLine(proj,5.5,{evaluationSource:'arbitrary-test-line'});const eval65=core.evaluateAtLine(proj,6.5,{evaluationSource:'arbitrary-test-line'});assert(eval55.overProb>eval65.overProb);assert(Math.abs(eval55.expectedK-eval65.expectedK)<1e-12);assert.equal(eval65.line,6.5);

// Missing current K line does not block distribution construction when workload/history remain valid.
const stNoKLine=clone(st);stNoKLine.markets['player-strikeouts'].representative.line=null;stNoKLine.markets['player-strikeouts'].representative.overOdds=null;stNoKLine.markets['player-strikeouts'].representative.underOdds=null;stNoKLine.markets['player-strikeouts'].state='UNPRICED';
const noKLine=core.projection({...stNoKLine,gamePk:'1'},lineup,p,now);assert(noKLine);assert.equal(noKLine.line,null);assert(Math.abs(noKLine.expectedK-proj.expectedK)<1e-12);

const pcur={providerVersion:'1.1',current:{byId:new Map([['10',{playerId:'10',pa:500,kPct:30,whiffPct:31,swingPct:48.3870967742,contactPct:69,swStrPct:15}]])},previous:{byId:new Map()}};
const bcur=new Map();const hitters=[];for(let i=1;i<=9;i++){bcur.set(String(i),{playerId:String(i),pa:300,kPct:20+i*.5,whiffPct:23+i*.4,swingPct:45,contactPct:77-i*.4,swStrPct:10.5+i*.2});hitters.push({mlbId:String(i),name:`H${i}`,order:i});}
const starterBoard={games:[{pregame:true,state:'VERIFIED',gamePk:'1',away:'NYY',home:'SD',startAt:'x',starters:{away:st,home:{...st,officialName:'Other',officialMlbId:'20',team:'SD',opponent:'NYY'}}}]};
const kboard=core.buildBoard({starterBoard,lineupsByPk:new Map([['1',{away:{state:'OFFICIAL',source:'schedule',hitters},home:{state:'OFFICIAL',source:'schedule',hitters}}]]),pitcherSavant:pcur,batterSavant:{current:{byId:bcur},previous:{byId:new Map()}},nowMs:now});assert.equal(kboard.readyCount,1);assert.equal(kboard.blockedCount,1);assert(kboard.games[0].starters.find(x=>x.side==='home').reasons.some(x=>x.includes('Savant')));assert.equal(kboard.marketSeparation,'TARGET_K_MARKET_EXCLUDED_FROM_EXPECTED_K');

// Partial local K pricing remains WATCH, not hard-blocked.
const stPartial=clone(st);stPartial.markets['player-strikeouts'].state='PARTIAL';stPartial.markets['player-strikeouts'].representative.underOdds=null;
const sb2={games:[{pregame:true,state:'VERIFIED',gamePk:'2',away:'NYY',home:'SD',startAt:'x',starters:{away:stPartial,home:{...stPartial,officialName:'Other',officialMlbId:'20'}}}]};
const kb2=core.buildBoard({starterBoard:sb2,lineupsByPk:new Map([['2',{away:{state:'OFFICIAL',hitters},home:{state:'OFFICIAL',hitters}}]]),pitcherSavant:pcur,batterSavant:{current:{byId:bcur},previous:{byId:new Map()}},nowMs:now});assert.equal(kb2.games[0].starters[0].status,'WATCH');

// No local PropsMadness K line remains model-usable but cannot become an actionable market edge.
const sb3={games:[{pregame:true,state:'VERIFIED',gamePk:'3',away:'NYY',home:'SD',startAt:'x',starters:{away:stNoKLine,home:{...stNoKLine,officialName:'Other',officialMlbId:'20'}}}]};
const kb3=core.buildBoard({starterBoard:sb3,lineupsByPk:new Map([['3',{away:{state:'OFFICIAL',hitters},home:{state:'OFFICIAL',hitters}}]]),pitcherSavant:pcur,batterSavant:{current:{byId:bcur},previous:{byId:new Map()}},nowMs:now});assert.equal(kb3.games[0].starters[0].status,'WATCH');assert(kb3.games[0].starters[0].projection.expectedK>0);

// Missing baserunner context (Hudson-like HA + BB absent) still fails closed.
const thin=clone(stNoKLine);delete thin.markets['player-hits-allowed'];delete thin.markets['player-walks'];
const sb4={games:[{pregame:true,state:'VERIFIED',gamePk:'4',away:'NYY',home:'SD',startAt:'x',starters:{away:thin,home:{...thin,officialName:'Other',officialMlbId:'20'}}}]};
const kb4=core.buildBoard({starterBoard:sb4,lineupsByPk:new Map([['4',{away:{state:'OFFICIAL',hitters},home:{state:'OFFICIAL',hitters}}]]),pitcherSavant:pcur,batterSavant:{current:{byId:bcur},previous:{byId:new Map()}},nowMs:now});assert.equal(kb4.games[0].starters[0].status,'BLOCKED');assert(kb4.games[0].starters[0].reasons.some(x=>x.includes('Hits Allowed')));assert(kb4.games[0].starters[0].reasons.some(x=>x.includes('Pitcher Walks')));

console.log('PASS test_k_core independent mean',proj.expectedK.toFixed(6),'P>5.5',eval55.overProb.toFixed(6),'P>6.5',eval65.overProb.toFixed(6));
