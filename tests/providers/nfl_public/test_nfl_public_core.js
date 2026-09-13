const assert=require('assert');
const core=require('../../../packages/providers/nfl_public/src/nfl_public_core.js');
assert.equal(core.VERSION,'0.4.0');
const payload={season:{year:2026,type:2},week:{number:2},events:[{id:'g1',date:'2026-09-13T17:00:00Z',status:{type:{name:'STATUS_SCHEDULED',shortDetail:'9/13 - 1:00 PM EDT'}},competitions:[{venue:{fullName:'Test Field',address:{city:'Charlotte',state:'NC'}},broadcasts:[{names:['FOX']}],odds:[{provider:{name:'ESPN BET'},details:'CHI -2.5',spread:-2.5,overUnder:43.5}],competitors:[{homeAway:'away',team:{id:'3',abbreviation:'CHI',displayName:'Chicago Bears',shortDisplayName:'Bears',name:'Bears',location:'Chicago'},records:[{type:'total',summary:'1-0'}]},{homeAway:'home',team:{id:'29',abbreviation:'CAR',displayName:'Carolina Panthers',shortDisplayName:'Panthers',name:'Panthers',location:'Carolina'},records:[{type:'total',summary:'0-1'}]}]}]}]};
const schedule=core.parseScoreboard(payload);assert.equal(schedule.status,'PASS');assert.equal(schedule.week,2);assert.equal(schedule.games.length,1);assert.equal(schedule.games[0].away.abbr,'CHI');assert.equal(schedule.games[0].away.id,'3');assert.equal(schedule.games[0].market.overUnder,43.5);
assert(core.summaryUrl('g1').includes('event=g1'));assert(core.depthChartUrl('3').includes('/teams/3/depthcharts'));
const summary=core.parseSummary({
  injuries:[{team:{abbreviation:'CHI'},injuries:[{athlete:{id:'10',displayName:'Caleb Test',position:{abbreviation:'QB'}},status:'Questionable',type:{abbreviation:'Q'},details:{detail:'ankle'}}]},{team:{abbreviation:'CAR'},injuries:[{athlete:{id:'20',displayName:'Receiver Example',position:{abbreviation:'WR'}},status:'Out',type:{abbreviation:'O'},details:{detail:'hamstring'}}]}],
  boxscore:{teams:[{team:{abbreviation:'CHI'},statistics:[{name:'totalYards',displayValue:'367'},{name:'turnovers',displayValue:'1'}]},{team:{abbreviation:'CAR'},statistics:[{name:'totalYards',displayValue:'301'}]}]},
  pickcenter:[{provider:{name:'ESPN BET'},details:'CHI -3.0',spread:-3,overUnder:42.5}],
  gameInfo:{venue:{fullName:'Test Field'},weather:{displayValue:'68 degrees, wind 8 mph'}},
  predictor:{awayTeam:{gameProjection:'56.0'},homeTeam:{gameProjection:'44.0'}}
},{game:schedule.games[0]});
assert.equal(summary.injuries.length,2);assert.equal(summary.teamStats.CHI.totalYards,'367');assert.equal(summary.market.overUnder,42.5);assert.equal(summary.predictor.away,.56);

const chiDepth=core.parseDepthChart({depthCharts:[{name:'Offense',positions:{quarterback:{position:{abbreviation:'QB'},athletes:[{rank:1,athlete:{id:'10',displayName:'Caleb Test'}}]},wideReceiver:{position:{abbreviation:'WR'},athletes:[{rank:1,athlete:{id:'30',displayName:'Starter WR'}}]}}}]},{teamId:'3',teamAbbr:'CHI'});
const carDepth=core.parseDepthChart({depthCharts:[{name:'Offense',positions:{wideReceiver:{position:{abbreviation:'WR'},athletes:[{rank:1,athlete:{id:'20',displayName:'Receiver Example'}}]}}}]},{teamId:'29',teamAbbr:'CAR'});
assert.equal(chiDepth.status,'PASS');assert.equal(chiDepth.rows.find(x=>x.athleteId==='10').role,'STARTER');

const now=Date.parse('2026-09-12T22:00:00Z');
const rss=`<rss><channel><item><title><![CDATA[Chicago Bears rule starting receiver out vs Carolina Panthers]]></title><link>https://news.google.com/a</link><pubDate>Sat, 12 Sep 2026 20:00:00 GMT</pubDate><source>Example Sports</source></item><item><title><![CDATA[Bears Panthers betting odds and picks]]></title><link>https://news.google.com/b</link><pubDate>Sat, 12 Sep 2026 19:00:00 GMT</pubDate><source>Example Sports</source></item></channel></rss>`;
const articles=core.parseGoogleNewsRss(rss,{game:schedule.games[0],nowMs:now});assert.equal(articles.length,2);assert.equal(articles[0].relevance,'DIRECTLY_MATERIAL');assert.equal(articles[0].freshness,'FRESH');
assert.equal(core.classifyTitle('No surprise in weekly injury roundup',{away:{abbr:'NO',name:'New Orleans Saints',aliases:['Saints','New Orleans']},home:{abbr:'TB',name:'Tampa Bay Buccaneers',aliases:['Buccaneers','Tampa Bay']}}).teamMention,false);
assert.equal(core.classifyTitle('Saints rule receiver out Sunday',{away:{abbr:'NO',name:'New Orleans Saints',aliases:['Saints','New Orleans']},home:{abbr:'TB',name:'Tampa Bay Buccaneers',aliases:['Buccaneers','Tampa Bay']}}).relevance,'DIRECTLY_MATERIAL');
assert.equal(core.classifyTitle('Bears Panthers betting odds and spread',schedule.games[0]).relevance,'BACKGROUND');
const board=core.buildBoard(schedule,{newsResults:[{gameId:'g1',articles}],summaryResults:[{gameId:'g1',summary}],depthChartResults:[{depthChart:chiDepth},{depthChart:carDepth}],updatedAt:'2026-09-12T22:00:00Z'});assert.equal(board.gameCount,1);assert.equal(board.games[0].research.status,'REVIEW');assert.equal(board.games[0].research.injuries.find(x=>x.player==='Receiver Example').depthRole,'STARTER');assert(board.games[0].research.personnel.depthChartConnected);assert(board.games[0].research.keySubjects[0].includes('Caleb Test'));assert.equal(board.games[0].detail.teamStats.CHI.totalYards,'367');assert.equal(board.probabilityMutation,false);
assert.equal(core.injurySeverity({position:'WR',status:'Injured Reserve'}).level,'BACKGROUND');
assert.equal(core.injurySeverity({position:'DE',status:'Doubtful'}).level,'POSSIBLE');assert.equal(core.injurySeverity({position:'WR',status:'Out',depthRank:1,depthRole:'STARTER'}).level,'DIRECT');
assert.equal(core.injurySeverity({position:'QB',status:'Questionable'}).level,'DIRECT');
const neutralIr=core.summarizeGameResearch(schedule.games[0],[],{injuries:[{team:'CHI',player:'IR Player',position:'WR',status:'Injured Reserve'}]});assert.equal(neutralIr.status,'NEUTRAL');assert.equal(neutralIr.backgroundCount,1);
const watchOut=core.summarizeGameResearch(schedule.games[0],[],{injuries:[{team:'CHI',player:'Edge Player',position:'DE',status:'Doubtful'}]});assert.equal(watchOut.status,'WATCH');assert(watchOut.impactLabel.includes('Edge Player'));
const cluster=core.summarizeGameResearch(schedule.games[0],[],{injuries:[{team:'CHI',player:'Left Tackle',position:'LT',status:'Out'},{team:'CHI',player:'Right Guard',position:'RG',status:'Doubtful'}]});assert.equal(cluster.status,'REVIEW');assert(cluster.findings.some(x=>x.includes('OL availability concerns')));
console.log('PASS NFL Public Research 0.4.0: severity-weighted availability, long-term IR suppression, cluster escalation, freshness-aware news, non-mutating boundary');
