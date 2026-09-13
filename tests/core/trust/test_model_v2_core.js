const core=require('../../../packages/core/src/trust/model_v2_core.js');
if(core.VERSION!=='3.0.0') throw new Error('wrong core version '+core.VERSION);
const now=new Date().toISOString();
const base={
  player:'Bailey Ober',team:'MIN',gamePk:'824552',line:3.5,localKLine:3.5,
  localKOverOdds:-110,localKUnderOdds:-110,localKBook:'FanDuel',localKCapturedAt:now,
  overProb:0.58,underProb:0.42,confidence:'High',oldestMarketAgeMinutes:1,captureSkewMinutes:0.1,
  freshnessWarning:null,openerLike:false,roleWarning:false,metricValidation:{schemaIntegrityFailed:false},
  calibrationStatus:'PROSPECTIVE_INPUT_MIGRATION'
};
const market=core.localStarterKMarket({projection:base,row:{officialName:'Bailey Ober'},game:{gamePk:'824552',away:'MIN',home:'CWS'}});
if(!market||market.marketSource!=='PropsMadness') throw new Error('local market adapter failed');
if(market.marketReference?.kind!=='propsmadness_local_no_vig') throw new Error('local no-vig reference missing');
if(Math.abs(market.marketReference.overNoVig-0.5)>1e-9) throw new Error('devig failed');
const t=core.trustStarterK({projection:base,market,config:{trust:{marketFreshSeconds:180,marketBlockSeconds:300,anomalyEdgePP:12,verifiedMinEdgePP:2.5,verifiedMinEV:0.02,propModelFreshMinutes:30,propModelMaxSkewMinutes:10}}});
if(t.state!=='WATCH') throw new Error('two-sided local source should WATCH when valuable '+JSON.stringify(t));
if(!(t.reasons||[]).some(x=>x.includes('single-source PropsMadness'))) throw new Error('single-source reason missing');
if(t.side?.side!=='over') throw new Error('expected over side');

const one={...base,localKOverOdds:+120,localKUnderOdds:null,overProb:0.58,underProb:0.42};
const oneMarket=core.localStarterKMarket({projection:one,row:{officialName:'Bailey Ober'},game:{gamePk:'824552',away:'MIN',home:'CWS'}});
if(oneMarket.marketReference!==null) throw new Error('one-sided market must not invent no-vig probability');
const t1=core.trustStarterK({projection:one,market:oneMarket,config:{trust:{marketFreshSeconds:180,marketBlockSeconds:300,anomalyEdgePP:12,verifiedMinEdgePP:2.5,verifiedMinEV:0.02,propModelFreshMinutes:30,propModelMaxSkewMinutes:10}}});
if(t1.state!=='WATCH') throw new Error('positive-EV one-sided price should WATCH '+JSON.stringify(t1));
if(t1.side?.market!==null||t1.side?.edge!==null) throw new Error('one-sided price invented market probability/edge');
if(!(t1.reasons||[]).some(x=>x.includes('one-sided PropsMadness'))) throw new Error('one-sided reason missing');


const sharpBase={...base,kMarketOffers:[
  {sportsbook:{name:'Pinnacle',slug:'pinnacle'},line:3.5,odds:{over:+100,under:-120}},
  {sportsbook:{name:'Circa',slug:'circa'},line:3.5,odds:{over:-102,under:-118}},
  {sportsbook:{name:'FanDuel',slug:'fanduel'},line:3.5,odds:{over:-110,under:-110}}
]};
const sharpMarket=core.localStarterKMarket({projection:sharpBase,row:{officialName:'Bailey Ober'},game:{gamePk:'824552',away:'MIN',home:'CWS'}});
if(sharpMarket.marketReference?.kind!=='propsmadness_sharp_consensus') throw new Error('Pinnacle/Circa sharp consensus missing '+JSON.stringify(sharpMarket.marketReference));
if(sharpMarket.marketReference.books.length!==2) throw new Error('expected two sharp books');
const ts=core.trustStarterK({projection:sharpBase,market:sharpMarket,config:{trust:{marketFreshSeconds:180,marketBlockSeconds:300,anomalyEdgePP:12,verifiedMinEdgePP:2.5,verifiedMinEV:0.02,propModelFreshMinutes:30,propModelMaxSkewMinutes:10}}});
if(!['VERIFIED','WATCH'].includes(ts.state)) throw new Error('sharp K reference should be usable '+JSON.stringify(ts));
if(ts.side?.marketReferenceKind!=='propsmadness_sharp_consensus') throw new Error('sharp reference kind not propagated');

const noLine=core.localStarterKMarket({projection:{...base,localKLine:null,line:null},row:{},game:{}});
if(noLine!==null) throw new Error('missing line should not create market');
console.log('PASS local PropsMadness K reference, two-sided no-vig, and one-sided EV-only fallback');

const watchEdge={kind:'K',projection:{confidence:'High'},market:{},trust:{state:'WATCH',side:{ev:.10,edge:.08,marketReferenceKind:'propsmadness_single_sharp'},reasons:['single sharp-book PropsMadness K reference']}};
const anomalyEdge={kind:'K',projection:{confidence:'High'},market:{},trust:{state:'ANOMALY',side:{ev:.40,edge:.24,marketReferenceKind:'propsmadness_local_no_vig'},reasons:['model-local-market disagreement 24.0pp exceeds anomaly gate']}};
const verifiedEdge={kind:'ML',projection:{dataQuality:'High'},market:{sharp:{books:['Pinnacle','Circa']}},trust:{state:'VERIFIED',side:{ev:.03,edge:.03},reasons:[]}};
const passEdge={kind:'K',projection:{confidence:'High'},market:{},trust:{state:'PASS',side:{ev:.50,edge:.20},reasons:['edge below verified threshold']}};
const ordered=core.sortEdgesByOpportunity([anomalyEdge,passEdge,watchEdge,verifiedEdge]);
if(ordered[0]!==verifiedEdge||ordered[1]!==watchEdge) throw new Error('decision hierarchy failed: VERIFIED/WATCH must outrank anomaly/pass');
if(core.opportunityScore(watchEdge)<=core.opportunityScore(anomalyEdge)) throw new Error('huge anomaly EV must not outrank clean WATCH');
if(core.opportunityLabel(watchEdge)!=='WATCH — NOT VERIFIED') throw new Error('WATCH label must explicitly say not verified');
if(core.opportunityLabel(anomalyEdge)!=='RESEARCH — ANOMALY') throw new Error('ANOMALY must be research-only');
const mediumWatch=JSON.parse(JSON.stringify(watchEdge));mediumWatch.projection.confidence='Medium';mediumWatch.trust.reasons.push('K model confidence Medium');
if(core.opportunityScore(mediumWatch)>=core.opportunityScore(watchEdge)) throw new Error('Medium confidence should rank below same High-confidence WATCH');
console.log('PASS opportunity integrity: VERIFIED/WATCH hierarchy, anomaly quarantine, confidence penalty');

