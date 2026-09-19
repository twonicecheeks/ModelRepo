#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function parseArgs(argv) {
  const out = {root:'/Users/abbeyfelix/Developer/MODEL', input:null, output:null};
  for (let i=2;i<argv.length;i++) {
    const a = argv[i];
    if (a === '--root') out.root = argv[++i];
    else if (a === '--input') out.input = argv[++i];
    else if (a === '--output') out.output = argv[++i];
    else if (!out.input) out.input = a;
    else throw new Error(`unknown argument ${a}`);
  }
  if (!out.input) throw new Error('usage: replay_mlb_historical_inputs_020.js --input <snapshots.jsonl> [--output <ledger.jsonl>]');
  return out;
}

function sha256File(p) {
  const h = crypto.createHash('sha256');
  h.update(fs.readFileSync(p));
  return h.digest('hex');
}

function loadJsonl(p) {
  const rows = [];
  const lines = fs.readFileSync(p,'utf8').split(/\r?\n/);
  lines.forEach((line,i)=>{
    if (!line.trim()) return;
    try { rows.push(JSON.parse(line)); }
    catch (e) { throw new Error(`${p}:${i+1}: invalid JSON: ${e.message}`); }
  });
  if (!rows.length) throw new Error(`no replay rows in ${p}`);
  return rows;
}

function writeJsonl(p, rows) {
  fs.mkdirSync(path.dirname(p), {recursive:true});
  const tmp = path.join(path.dirname(p), '.'+path.basename(p)+'.tmp');
  fs.writeFileSync(tmp, rows.map(r=>JSON.stringify(r)).join('\n')+'\n','utf8');
  fs.renameSync(tmp,p);
}

function main() {
  const args = parseArgs(process.argv);
  const root = path.resolve(args.root);
  const input = path.resolve(args.input);
  const replayPath = path.join(root,'packages/models/mlb/evaluation/production_replay_adapter_020.js');
  const mlPath = path.join(root,'packages/models/mlb/moneyline/structured_ml_core.js');
  const kPath = path.join(root,'packages/models/mlb/k/structured_k_core.js');
  const replay = require(replayPath);

  const inputRows = loadJsonl(input);
  const outputs = [];
  const errors = [];
  inputRows.forEach((r,idx)=>{
    try { outputs.push(replay.replayRow(r)); }
    catch (e) {
      errors.push({
        row: idx+1,
        game_id: r.game_id || null,
        replay_type: r.replay_type || r.market_type || null,
        error: e.message,
      });
    }
  });

  const runId = new Date().toISOString().replace(/[-:.]/g,'').replace('T','T').replace('Z','Z') + '_' + crypto.randomBytes(4).toString('hex');
  const defaultDir = path.join(root,'data/models/mlb/production_replay_020',runId);
  const output = args.output ? path.resolve(args.output) : path.join(defaultDir,'MLB_PRODUCTION_REPLAY_LEDGER.jsonl');
  writeJsonl(output, outputs);

  const manifest = {
    version: replay.VERSION,
    lineage: replay.LINEAGE,
    run_id: runId,
    created_at: new Date().toISOString(),
    input_path: input,
    input_sha256: sha256File(input),
    input_rows: inputRows.length,
    output_path: output,
    output_sha256: sha256File(output),
    output_rows: outputs.length,
    error_rows: errors.length,
    errors,
    core_identity: replay.coreIdentity(),
    core_hashes: {
      structured_ml_core_sha256: sha256File(mlPath),
      structured_k_core_sha256: sha256File(kPath),
      replay_adapter_sha256: sha256File(replayPath),
    },
    production_model_mutation: false,
    model_refit_performed: false,
    oddsPapi_requests: 0,
    market_requests: 0,
  };
  const manifestPath = output.replace(/\.jsonl$/i,'') + '.manifest.json';
  fs.writeFileSync(manifestPath, JSON.stringify(manifest,null,2)+'\n','utf8');

  console.log('');
  console.log('MLB PRODUCTION REPLAY 0.2.0');
  console.log(`Input rows: ${inputRows.length}`);
  console.log(`Output rows: ${outputs.length}`);
  console.log(`Errors: ${errors.length}`);
  console.log(`ML: ${manifest.core_identity.ml.engineVersion} · ${manifest.core_identity.ml.modelVersion}`);
  console.log(`K:  ${manifest.core_identity.k.engineVersion} · ${manifest.core_identity.k.modelVersion}`);
  console.log('Production mutation: NO · refit: NO · OddsPapi: 0');
  console.log(`Ledger: ${output}`);
  console.log(`Manifest: ${manifestPath}`);
  if (errors.length) {
    errors.slice(0,20).forEach(e=>console.log(`ERROR row ${e.row} ${e.game_id||''} ${e.replay_type||''}: ${e.error}`));
    process.exitCode = 1;
  }
}

main();
