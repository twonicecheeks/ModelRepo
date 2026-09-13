const assert=require('assert');
const research=require('../../../packages/providers/public_research/src/public_research_core.js');
const radar=require('../../../packages/core/src/slate_radar/radar_core.js');
assert.equal(research.VERSION,'0.5.0');
const close=(a,b,t=1e-9)=>assert(Math.abs(Number(a)-Number(b))<t,`${a} != ${b}`);

const nfHtml=`<html><body>
<h3>Colorado Rockies at Detroit Tigers</h3><h4>numberFire Prediction</h4><li>Tigers Win Probability: 64.49%</li><li>Rockies Win Probability: 35.51%</li>
<h3>Texas Rangers at Arizona Diamondbacks</h3><h4>numberFire Prediction</h4><li>Rangers Win Probability: 53.85%</li><li>Diamondbacks Win Probability: 46.15%</li>
</body></html>`;
const nf=research.parseNumberFireHtml(nfHtml,{dateIso:'2026-09-12',url:'https://www.fanduel.com/research/mlb-betting-odds-09-12-2026'});
assert.equal(nf.status,'PASS');
close(nf.byTeam.DET,0.6449);
close(nf.byTeam.COL,0.3551);
close(nf.byTeam.TEX,0.5385);
close(nf.byTeam.ARI,0.4615);
assert(research.numberFireUrlCandidates('2026-09-12')[0].includes('09-12-2026'));

const now=Date.parse('2026-09-12T16:00:00Z');
assert.equal(research.freshnessBand(20),'FRESH');
assert.equal(research.freshnessBand(60),'CURRENT');
assert.equal(research.freshnessBand(90),'STALE');
const dupRss=`<?xml version="1.0"?><rss><channel>
<item><title><![CDATA[Gerrit Cole working with pitch limit after return]]></title><link>https://news.google.com/articles/d1</link><pubDate>Sat, 12 Sep 2026 14:00:00 GMT</pubDate><source>Source A</source></item>
<item><title><![CDATA[Pitch limit after return: Gerrit Cole working]]></title><link>https://news.google.com/articles/d2</link><pubDate>Sat, 12 Sep 2026 13:00:00 GMT</pubDate><source>Source B</source></item>
</channel></rss>`;
const dups=research.parseGoogleNewsRss(dupRss,{target:{kind:'K',player:'Gerrit Cole'},nowMs:now});
assert.equal(dups.length,1);
assert(dups[0].evidenceId&&dups[0].sourceClass==='NEWS');
const staleRss=`<?xml version="1.0"?><rss><channel><item><title><![CDATA[Gerrit Cole working with a pitch limit after return]]></title><link>https://news.google.com/articles/stale</link><pubDate>Mon, 07 Sep 2026 14:00:00 GMT</pubDate><source>Old Sports</source></item></channel></rss>`;
const staleArticles=research.parseGoogleNewsRss(staleRss,{target:{kind:'K',player:'Gerrit Cole'},nowMs:now,maxAgeHours:240});
assert.equal(staleArticles[0].freshness,'STALE');

const rss=`<?xml version="1.0"?><rss><channel><item><title><![CDATA[Gerrit Cole working with a pitch limit after return]]></title><link>https://news.google.com/articles/abc</link><pubDate>Sat, 12 Sep 2026 14:00:00 GMT</pubDate><source url="https://example.com">Example Sports</source></item></channel></rss>`;
const articles=research.parseGoogleNewsRss(rss,{target:{kind:'K',player:'Gerrit Cole'},nowMs:now});
assert.equal(articles.length,1);
assert.equal(articles[0].reviewRequired,true);
assert.equal(articles[0].relevance,'DIRECTLY_MATERIAL');
assert(articles[0].flags.includes('WORKLOAD'));

const genericRss=`<?xml version="1.0"?><rss><channel><item><title><![CDATA[White Sox and Cardinals final score and recap]]></title><link>https://news.google.com/articles/generic</link><pubDate>Sat, 12 Sep 2026 14:00:00 GMT</pubDate><source url="https://example.com">Example Sports</source></item></channel></rss>`;
const generic=research.parseGoogleNewsRss(genericRss,{target:{kind:'ML',teams:['CWS','STL']},nowMs:now});
assert.equal(generic[0].relevance,'BACKGROUND');
assert.equal(generic[0].reviewRequired,false);

const txPayload={transactions:[{id:1,person:{id:543037,fullName:'Gerrit Cole'},toTeam:{id:147,name:'New York Yankees'},date:'2026-09-10',effectiveDate:'2026-09-10',typeDesc:'Reinstated',description:'New York Yankees reinstated RHP Gerrit Cole from the 15-day injured list.'}]};
const targets=[{key:'K:99:543037',kind:'K',player:'Gerrit Cole',officialMlbId:'543037',query:'"Gerrit Cole" MLB'}];
const bundle=research.buildBundle({dateIso:'2026-09-12',targets,newsResults:[{key:'K:99:543037',query:'"Gerrit Cole" MLB',articles}],transactionsPayload:txPayload,numberFireResult:nf,nowMs:now});
assert.equal(bundle.status,'PASS');
assert.equal(bundle.transactions.count,1);
assert.equal(bundle.externalProjections.status,'PASS');
const krow={kind:'K',gamePk:'99',officialMlbId:'543037',player:'Gerrit Cole',team:'NYY',away:'NYM',home:'NYY',side:'Under',probability:.56};
const kctx=research.contextFor(krow,bundle);
assert.equal(kctx.reviewRequired,true);
assert.equal(kctx.news.articles.length,1);
assert.equal(kctx.transactions.items.length,1);
assert.equal(kctx.externalProjection.status,'NOT_AVAILABLE_FOR_K');
assert.equal(kctx.materialSummary.status,'REVIEW');
assert(kctx.materialSummary.directCount>=1);
assert(kctx.materialSummary.findings.some(x=>/workload|pitch-count|innings-limit/i.test(x)));
assert(kctx.materialSummary.evidence.length>=1);
assert(kctx.materialSummary.evidence.every(e=>e.sourceClass&&e.relevance&&e.freshness));
const staleBundle=research.buildBundle({dateIso:'2026-09-12',targets,newsResults:[{key:'K:99:543037',query:'"Gerrit Cole" MLB',articles:staleArticles}],transactionsPayload:{transactions:[]},numberFireResult:nf,nowMs:now});
const staleCtx=research.contextFor(krow,staleBundle);
assert.equal(staleCtx.reviewRequired,false);
assert.equal(staleCtx.materialSummary.staleDirectCount,1);


const mlrow={kind:'ML',gamePk:'1',away:'COL',home:'DET',awayTeamId:'115',homeTeamId:'116',side:'DET',probability:.681};
const mlctx=research.contextFor(mlrow,bundle);
assert.equal(mlctx.externalProjection.status,'CONNECTED');
assert.equal(mlctx.externalProjection.agreement,'AGREE');
close(mlctx.externalProjection.selectedSideProbability,.6449);
close(mlctx.externalProjection.modelDeltaPP,3.61,1e-6);
assert.equal(mlctx.externalProjection.assessment,'AGREE_CLOSE');
const arizona={kind:'ML',gamePk:'2',away:'TEX',home:'ARI',side:'ARI',probability:.675};
const azctx=research.contextFor(arizona,bundle);
assert.equal(azctx.externalProjection.agreement,'DISAGREE');
assert.equal(azctx.externalProjection.assessment,'MAJOR_CONFLICT');
assert(azctx.externalProjection.modelDeltaPP>20);

const baseKResearch={verdict:'CONFIRMED',confidence:80,signals:[{name:'recent form',value:1,detail:'COLD'}],externalProjections:{status:'NOT_CONNECTED'},news:{starterConfirmed:true}};
const held=radar.attachPublicResearch(krow,baseKResearch,bundle,research);
assert.equal(held.verdict,'NEWS_HOLD');
assert.equal(held.baseVerdict,'CONFIRMED');
assert.equal(held.probabilityMutation,undefined); // base object shape preserved; board owns the mutation contract

const baseMlResearch={verdict:'CONFIRMED',confidence:82,signals:[{name:'team recent form',value:1,detail:'HOT'},{name:'projected run edge',value:1,detail:'+1.0 runs'}],externalProjections:{status:'NOT_CONNECTED'},news:{startersConfirmed:true}};
const azEnriched=radar.attachPublicResearch(arizona,baseMlResearch,bundle,research);
assert.equal(azEnriched.externalProjections.status,'CONNECTED');
assert.equal(azEnriched.externalProjections.agreement,'DISAGREE');
assert(azEnriched.signals.some(x=>x.name==='external projection'&&x.value===-1));
assert.equal(azEnriched.verdict,'CONFLICT'); // opposite-side external forecast with a 12pp+ probability gap is a research conflict, not a probability mutation

const board={version:'1.6',researchVersion:'RCE-0.5',probabilityMutationFromResearch:false,ml:[arizona],k:[{...krow,expectedK:5.35}],builtAt:'2026-09-12T15:00:00Z'};
const updated=radar.applyResearchBundle(board,bundle,research);
assert.equal(updated.ml[0].probability,.675);
assert.equal(updated.k[0].probability,.56);
assert.equal(updated.k[0].expectedK,5.35);
assert.equal(updated.probabilityMutationFromResearch,false);
console.log('PASS Public Research 0.5: Google News parsing, MLB transactions, numberFire ML projections, NEWS HOLD, and strict non-mutation');
