(() => {
  'use strict';

  const mlCore = require('../moneyline/structured_ml_core.js');
  const kCore = require('../k/structured_k_core.js');

  const VERSION = '0.2.1';
  const LINEAGE = 'mlb-production-replay-adapter-v0.2.1-xk-only-2026-09-19';

  const finite = v => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));
  const clean = v => v == null ? '' : String(v).trim();

  function seasonType(v) {
    const x = clean(v).toUpperCase();
    if (['POST','POSTSEASON','PLAYOFFS'].includes(x)) return 'POST';
    if (['REG','REGULAR','REGULAR_SEASON'].includes(x)) return 'REG';
    throw new Error(`season_type must be REG or POST; got ${v}`);
  }

  function timestampMs(row) {
    const raw = row.snapshot_at || row.snapshotAt || row.game_start_at || row.gameStartAt;
    const ms = Date.parse(raw || '');
    if (!Number.isFinite(ms)) {
      throw new Error('replay row requires parseable snapshot_at or game_start_at');
    }
    return ms;
  }

  function common(row, marketType) {
    for (const key of ['game_id','game_date','season','season_type']) {
      if (row[key] === null || row[key] === undefined || row[key] === '') {
        throw new Error(`missing required replay field ${key}`);
      }
    }
    return {
      game_id: clean(row.game_id),
      game_date: clean(row.game_date),
      season: Number(row.season),
      season_type: seasonType(row.season_type),
      market_type: marketType,
      model_variant: clean(row.model_variant) || 'PRODUCTION_BASE',
      stage: clean(row.stage) || null,
      thesis: clean(row.thesis) || null,
      trust: clean(row.trust) || null,
      research_confidence: finite(row.research_confidence) ? Number(row.research_confidence) : null,
      snapshot_at: clean(row.snapshot_at || row.snapshotAt || row.game_start_at || row.gameStartAt),
      replay_input_mode: clean(row.replay_input_mode) || 'UNSPECIFIED',
      replay_adapter_version: VERSION,
      replay_adapter_lineage: LINEAGE,
    };
  }

  function attachMarketFields(out, row) {
    for (const key of [
      'market_probability','market_odds','closing_odds','closing_line',
      'opening_odds','opening_line','book','closing_book'
    ]) {
      if (row[key] !== undefined) out[key] = row[key];
    }
    return out;
  }

  function replayML(row) {
    const game = row.production_input || row.game_input || row.game;
    if (!game || typeof game !== 'object') {
      throw new Error('ML replay requires production_input/game_input');
    }
    const projection = mlCore.projectGame(game);
    if (!projection || !projection.complete) {
      throw new Error(`ML production replay incomplete: ${projection?.reason || 'unknown reason'}`);
    }

    const away = clean(game.away);
    const home = clean(game.home);
    if (!away || !home) throw new Error('ML production input requires away/home team codes');

    const actualHomeWin = Number(row.actual_home_win);
    if (![0,1].includes(actualHomeWin)) {
      throw new Error('ML replay requires actual_home_win 0/1');
    }

    const selection = clean(row.selection_team) || home;
    if (![away,home].includes(selection)) {
      throw new Error(`ML selection_team ${selection} is not ${away} or ${home}`);
    }

    const isHome = selection === home;
    const p = isHome ? projection.homeWin : projection.awayWin;
    const actualWin = isHome ? actualHomeWin : 1 - actualHomeWin;

    const out = {
      ...common(row, 'ML'),
      selection_team: selection,
      opponent_team: isHome ? away : home,
      actual_win: actualWin,
      model_probability: p,
      fair_odds: isHome ? projection.homeFair : projection.awayFair,
      projected_away_runs: projection.awayRuns,
      projected_home_runs: projection.homeRuns,
      favorite: projection.favorite,
      favorite_probability: projection.favoriteProbability,
      production_engine_version: projection.engineVersion || mlCore.VERSION,
      production_model_version: projection.modelVersion || mlCore.MODEL_VERSION,
      calibration_status: projection.calibrationStatus || mlCore.CALIBRATION_STATUS,
      production_projection_complete: true,
      ml_projection: projection,
    };
    return attachMarketFields(out, row);
  }

  function kSideProbability(evaluated, side) {
    const s = clean(side).toUpperCase();
    if (s === 'OVER') return {side:'OVER', probability:evaluated.overProb, fair:evaluated.sides?.over?.fair};
    if (s === 'UNDER') return {side:'UNDER', probability:evaluated.underProb, fair:evaluated.sides?.under?.fair};
    throw new Error(`K replay side must be OVER or UNDER; got ${side}`);
  }

  function replayKDistributionOnly(row) {
    const starter = row.starter_input || row.starter;
    const lineup = row.lineup_rows || row.lineup;
    const pitcher = row.pitcher_row || row.pitcher_skill;
    if (!starter || !Array.isArray(lineup) || !pitcher) {
      throw new Error('K xK-only replay requires starter_input, lineup_rows[], and pitcher_row');
    }
    if (lineup.length !== 9) {
      throw new Error(`K xK-only replay requires 9 lineup rows; got ${lineup.length}`);
    }
    const actualK = Number(row.actual_k);
    if (!Number.isFinite(actualK) || actualK < 0) throw new Error('K xK-only replay requires nonnegative actual_k');

    const nowMs = timestampMs(row);
    const distribution = kCore.buildDistribution(starter, lineup, pitcher, nowMs);
    if (!distribution || !Number.isFinite(Number(distribution.expectedK))) {
      throw new Error('K xK-only production replay failed to build distribution');
    }

    return {
      ...common(row, 'K'),
      evaluation_mode: 'XK_ONLY',
      pitcher: clean(row.pitcher || starter.officialName || distribution.player),
      team: clean(row.team || starter.team || distribution.team),
      xk: distribution.expectedK,
      actual_k: actualK,
      workload_state: distribution.workloadState,
      workload_limited: !!distribution.workloadLimited,
      uncertainty_multiplier: distribution.uncertaintyMultiplier,
      expected_batters_faced: distribution.components?.expectedBF ?? null,
      expected_outs: distribution.components?.expectedOuts ?? null,
      structural_k: distribution.components?.structuralK ?? null,
      pitcher_k_rate: distribution.components?.pitcherK ?? null,
      opponent_k_rate: distribution.components?.opponentK ?? null,
      production_engine_version: kCore.VERSION,
      production_model_version: kCore.MODEL_VERSION,
      calibration_status: kCore.CALIBRATION_STATUS,
      target_k_market_excluded_from_expected_k: distribution.targetKMarketExcludedFromExpectedK,
      distribution_independent_of_target_k_line: distribution.distributionIndependentOfTargetKLine,
      k_projection: distribution,
    };
  }

  function replayK(row) {
    const starter = row.starter_input || row.starter;
    const lineup = row.lineup_rows || row.lineup;
    const pitcher = row.pitcher_row || row.pitcher_skill;
    if (!starter || !Array.isArray(lineup) || !pitcher) {
      throw new Error('K replay requires starter_input, lineup_rows[], and pitcher_row');
    }
    if (lineup.length !== 9) {
      throw new Error(`K replay requires 9 lineup rows; got ${lineup.length}`);
    }
    const line = Number(row.line ?? row.evaluation_line);
    if (!Number.isFinite(line)) throw new Error('K replay requires numeric line/evaluation_line');
    const actualK = Number(row.actual_k);
    if (!Number.isFinite(actualK) || actualK < 0) throw new Error('K replay requires nonnegative actual_k');

    const nowMs = timestampMs(row);
    const distribution = kCore.buildDistribution(starter, lineup, pitcher, nowMs);
    if (!distribution || !Number.isFinite(Number(distribution.expectedK))) {
      throw new Error('K production replay failed to build distribution');
    }

    const overOdds = finite(row.over_odds) ? Number(row.over_odds) : (clean(row.side).toUpperCase() === 'OVER' && finite(row.market_odds) ? Number(row.market_odds) : null);
    const underOdds = finite(row.under_odds) ? Number(row.under_odds) : (clean(row.side).toUpperCase() === 'UNDER' && finite(row.market_odds) ? Number(row.market_odds) : null);
    const marketOverProb = finite(row.market_over_probability) ? Number(row.market_over_probability) : null;

    const evaluated = kCore.evaluateAtLine(distribution, line, {
      overOdds,
      underOdds,
      marketOverProb,
      evaluationSource: 'historical production replay',
    });
    if (!evaluated) throw new Error('K production replay line evaluation failed');

    const selected = kSideProbability(evaluated, row.side);
    const out = {
      ...common(row, 'K'),
      pitcher: clean(row.pitcher || starter.officialName || distribution.player),
      team: clean(row.team || starter.team || distribution.team),
      side: selected.side,
      line,
      xk: evaluated.expectedK,
      actual_k: actualK,
      model_probability: selected.probability,
      fair_odds: selected.fair,
      workload_state: evaluated.workloadState,
      workload_limited: !!evaluated.workloadLimited,
      uncertainty_multiplier: evaluated.uncertaintyMultiplier,
      expected_batters_faced: evaluated.components?.expectedBF ?? null,
      expected_outs: evaluated.components?.expectedOuts ?? null,
      structural_k: evaluated.components?.structuralK ?? null,
      pitcher_k_rate: evaluated.components?.pitcherK ?? null,
      opponent_k_rate: evaluated.components?.opponentK ?? null,
      production_engine_version: kCore.VERSION,
      production_model_version: kCore.MODEL_VERSION,
      calibration_status: kCore.CALIBRATION_STATUS,
      target_k_market_excluded_from_expected_k: evaluated.targetKMarketExcludedFromExpectedK,
      distribution_independent_of_target_k_line: evaluated.distributionIndependentOfTargetKLine,
      k_projection: evaluated,
    };
    return attachMarketFields(out, row);
  }

  function replayRow(row) {
    const type = clean(row.replay_type || row.market_type).toUpperCase();
    if (type === 'ML') return replayML(row);
    if (type === 'K' && clean(row.evaluation_mode).toUpperCase() === 'XK_ONLY') return replayKDistributionOnly(row);
    if (type === 'K') return replayK(row);
    throw new Error(`replay_type/market_type must be ML or K; got ${type}`);
  }

  function coreIdentity() {
    return {
      replayAdapterVersion: VERSION,
      replayAdapterLineage: LINEAGE,
      ml: {
        engineVersion: mlCore.VERSION,
        modelVersion: mlCore.MODEL_VERSION,
        calibrationStatus: mlCore.CALIBRATION_STATUS,
      },
      k: {
        engineVersion: kCore.VERSION,
        modelVersion: kCore.MODEL_VERSION,
        calibrationStatus: kCore.CALIBRATION_STATUS,
        targetKMarketWeight: kCore.TARGET_K_MARKET_WEIGHT,
      },
    };
  }

  const api = {VERSION,LINEAGE,replayML,replayK,replayKDistributionOnly,replayRow,coreIdentity};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();

