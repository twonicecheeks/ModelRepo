const assert=require('assert');
const core=require('../../../../packages/models/mlb/k/structured_k_core.js');

const good=core.projectionIntegrity({expectedOuts:17.8,recentOuts:18.1,seasonOuts:17.4,pitcherK:18.5,opponentK:20.2,matchupK:16.8,structuralK:4.15,recentK:4.9,seasonK:4.5,workloadState:'NORMAL'});
assert.equal(good.ok,true);

const fractional=core.projectionIntegrity({expectedOuts:17.5,recentOuts:18,seasonOuts:17.5,pitcherK:.185,opponentK:20,matchupK:6,structuralK:1.4,recentK:5,seasonK:4.6,workloadState:'NORMAL'});
assert.equal(fractional.ok,false);assert(fractional.reasons.some(x=>/fraction\/percent/i.test(x)));

const workload=core.projectionIntegrity({expectedOuts:10.5,recentOuts:18,seasonOuts:17.5,pitcherK:18,opponentK:20,matchupK:17,structuralK:2.8,recentK:4.8,seasonK:4.5,workloadState:'NORMAL'});
assert.equal(workload.ok,false);assert(workload.reasons.some(x=>/workload|expected outs/i.test(x)));

const structural=core.projectionIntegrity({expectedOuts:18,recentOuts:18,seasonOuts:17.5,pitcherK:18,opponentK:20,matchupK:8.5,structuralK:1.7,recentK:5.1,seasonK:4.7,workloadState:'NORMAL'});
assert.equal(structural.ok,false);assert(structural.reasons.some(x=>/less than 50%/i.test(x)));

const limited=core.projectionIntegrity({expectedOuts:11,recentOuts:11.5,seasonOuts:12,pitcherK:18,opponentK:20,matchupK:17,structuralK:3.2,recentK:3.4,seasonK:3.5,workloadState:'LIMITED'});
assert.equal(limited.reasons.some(x=>/normal starter expected workload/i.test(x)),false);
console.log('PASS K projection integrity guards');
