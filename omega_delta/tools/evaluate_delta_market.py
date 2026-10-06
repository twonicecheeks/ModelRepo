"""Audit DELTA distributions against an operator-supplied historical K market file.

The market file is a join layer. It never enters DELTA fitting or inference.
Opening prices are used for the hypothetical decision and ROI; closing prices
are used for the market benchmark and CLV. Whole-number lines keep their push
probability. A line move makes price-only CLV unscorable rather than inventing
a conversion between runs.

This command is intentionally offline. It reads local JSONL/CSV files and
does not call OddsPapi, The Odds API, BettingPros, or a sportsbook.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def finite(value, name, lo=None, hi=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be numeric.") from None
    if not math.isfinite(number) or (lo is not None and number < lo) or (hi is not None and number > hi):
        raise ValueError(f"{name} is outside its allowed range.")
    return number


def timestamp(value, name):
    if not str(value or '').strip():
        raise ValueError(f"{name} is required and must include a timezone.")
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        raise ValueError(f"{name} must be an ISO timestamp with a timezone.") from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone.")
    return result


def american_to_implied(american):
    odds = finite(american, 'American odds')
    if abs(odds) < 100 or abs(odds) > 100000:
        raise ValueError('American odds must be <= -100 or >= +100.')
    return 100/(odds+100) if odds > 0 else abs(odds)/(abs(odds)+100)


def decimal_odds(american):
    odds = finite(american, 'American odds')
    return 1 + (odds/100 if odds > 0 else 100/abs(odds))


def devig(over_odds, under_odds):
    """Return no-vig over/under probabilities from a two-way quote."""
    over = american_to_implied(over_odds)
    under = american_to_implied(under_odds)
    total = over + under
    return {'over': over/total, 'under': under/total, 'hold': total-1}


def line_probabilities(pmf, line):
    line = finite(line, 'K line', 0, 40)
    if not (line*2).is_integer():
        raise ValueError('K lines must be whole or half strikeouts.')
    if not pmf or any(finite(p, 'PMF probability', 0, 1) < 0 for p in pmf):
        raise ValueError('A PMF with nonnegative probabilities is required.')
    total = sum(float(p) for p in pmf)
    if abs(total-1) > 1e-6:
        raise ValueError(f'PMF must sum to one; received {total:.9f}.')
    over = sum(float(p) for k,p in enumerate(pmf) if k > line)
    under = sum(float(p) for k,p in enumerate(pmf) if k < line)
    push = float(pmf[int(line)]) if line.is_integer() and int(line) < len(pmf) else 0.
    return {'over': over, 'under': under, 'push': push,
            'conditional_over': over/(over+under) if over+under else None,
            'conditional_under': under/(over+under) if over+under else None}


def settle(actual, line, side):
    actual = finite(actual, 'actual strikeouts', 0, 100)
    line = finite(line, 'K line', 0, 40)
    if actual.is_integer(): actual = int(actual)
    if actual == line: return 'PUSH'
    if side == 'OVER': return 'WIN' if actual > line else 'LOSS'
    if side == 'UNDER': return 'WIN' if actual < line else 'LOSS'
    raise ValueError('Side must be OVER or UNDER.')


def profit(actual, line, side, odds):
    result = settle(actual, line, side)
    return 0. if result == 'PUSH' else (decimal_odds(odds)-1 if result == 'WIN' else -1.)


def _jsonl(path):
    rows=[]
    with Path(path).open(encoding='utf-8') as file:
        for number, line in enumerate(file, 1):
            if not line.strip(): continue
            try: rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f'Invalid prediction JSON on line {number}: {exc}') from None
    return rows


def load_predictions(path, variant):
    rows = {}
    for row in _jsonl(path):
        key=(str(row.get('game_id','')),str(row.get('player_id','')))
        if not all(key): raise ValueError('Each prediction needs game_id and player_id.')
        pmfs=row.get('pmfs',{})
        pmf=pmfs.get(variant)
        if not isinstance(pmf,list):
            raise ValueError(f'Prediction {key} has no exact pmfs.{variant} array. Recreate the DELTA distribution artifact.')
        line_probabilities(pmf, 0.5)  # validates PMF without imposing a market line
        rows[key]=row
    if not rows: raise ValueError('Prediction JSONL has no rows.')
    return rows


def _optional(raw, key):
    value=raw.get(key,'')
    return None if value is None or str(value).strip()=='' else value


def load_market(path, predictions, variant):
    source=Path(path).expanduser().resolve()
    if not source.is_file(): raise ValueError(f'Market file does not exist: {source}')
    rows=[]; seen=set()
    with source.open(newline='',encoding='utf-8-sig') as file:
        reader=csv.DictReader(file)
        required={'game_id','player_id','line','closing_over_odds','closing_under_odds',
                  'game_start_at','source','settlement_definition'}
        missing=required-set(reader.fieldnames or [])
        if missing: raise ValueError(f'Market CSV is missing columns: {sorted(missing)}')
        for number, raw in enumerate(reader, 2):
            key=(str(raw.get('game_id','')).strip(),str(raw.get('player_id','')).strip())
            if not all(key): raise ValueError(f'Market row {number} needs game_id and player_id.')
            if key in seen: raise ValueError(f'Duplicate market row for {key}.')
            seen.add(key)
            if key not in predictions: continue
            if str(raw.get('market_type','K') or 'K').upper()!='K':
                raise ValueError(f'Market row {number} must have market_type K.')
            if str(raw.get('settlement_definition','')).strip().upper()!='FULL_GAME':
                raise ValueError(f'Market row {number} must use FULL_GAME settlement.')
            start=timestamp(raw['game_start_at'], 'game_start_at')
            captured=_optional(raw,'captured_at')
            close_captured=_optional(raw,'closing_captured_at')
            if captured and timestamp(captured,'captured_at')>=start:
                raise ValueError(f'Market row {number} opening capture is not pregame.')
            if close_captured and timestamp(close_captured,'closing_captured_at')>=start:
                raise ValueError(f'Market row {number} closing capture is not pregame.')
            prediction=predictions[key]
            if prediction.get('game_date') and start.date().isoformat()!=str(prediction['game_date']):
                raise ValueError(f'Market row {number} game_start_at date does not match prediction {key}.')
            actual=_optional(raw,'actual_k')
            if actual is None: actual=prediction.get('actual_k')
            if actual is None: raise ValueError(f'Market row {number} needs actual_k or a prediction actual_k.')
            actual=finite(actual,'actual_k',0,100)
            if not actual.is_integer(): raise ValueError(f'Market row {number} actual_k must be an integer.')
            if prediction.get('actual_k') is not None and int(actual)!=int(prediction['actual_k']):
                raise ValueError(f'Market row {number} actual_k disagrees with sealed outcome {key}.')
            shared=_optional(raw,'line')
            opening_line=finite(_optional(raw,'opening_line') or shared,'opening_line',0,40)
            closing_line=finite(_optional(raw,'closing_line') or shared,'closing_line',0,40)
            line_probabilities(prediction['pmfs'][variant], closing_line)
            opening_over=_optional(raw,'opening_over_odds')
            opening_under=_optional(raw,'opening_under_odds')
            if bool(opening_over) != bool(opening_under):
                raise ValueError(f'Market row {number} must provide both opening prices or neither.')
            close_over=finite(raw['closing_over_odds'],'closing_over_odds')
            close_under=finite(raw['closing_under_odds'],'closing_under_odds')
            rows.append({'key':key,'game_id':key[0],'player_id':key[1],
                         'player':prediction.get('player'),'season':prediction.get('season'),
                         'book':_optional(raw,'book') or 'UNSPECIFIED',
                         'game_start_at':raw['game_start_at'],'captured_at':captured,
                         'closing_captured_at':close_captured,'actual_k':int(actual),
                         'opening_line':opening_line,'closing_line':closing_line,
                         'opening_over_odds':float(opening_over) if opening_over else None,
                         'opening_under_odds':float(opening_under) if opening_under else None,
                         'closing_over_odds':close_over,'closing_under_odds':close_under,
                         'source':str(raw['source']).strip(),'prediction':prediction})
    if not rows: raise ValueError('No market rows matched the selected DELTA prediction artifact.')
    return rows, hashlib.sha256(source.read_bytes()).hexdigest()


def binary_scores(actual, line, over_probability, market_probability):
    if actual == line: return None
    target=1. if actual>line else 0.
    model_log=-math.log(max(1e-12, over_probability if target else 1-over_probability))
    market_log=-math.log(max(1e-12, market_probability if target else 1-market_probability))
    return {'model_brier':(over_probability-target)**2,
            'market_brier':(market_probability-target)**2,
            'model_log_loss':model_log,'market_log_loss':market_log}


def evaluate_row(row, variant, threshold):
    pmf=row['prediction']['pmfs'][variant]
    close_probs=line_probabilities(pmf,row['closing_line'])
    close_market=devig(row['closing_over_odds'],row['closing_under_odds'])
    close_scores=binary_scores(row['actual_k'],row['closing_line'],close_probs['conditional_over'],close_market['over'])
    open_record=None; decision='NO_BET'; edge=0.; expected_roi=None; result=None; realized=None; clv=None; clv_status='NO_OPEN_QUOTE'
    if row['opening_over_odds'] is not None:
        open_probs=line_probabilities(pmf,row['opening_line'])
        open_market=devig(row['opening_over_odds'],row['opening_under_odds'])
        candidates=[('OVER',open_probs['conditional_over']-open_market['over'],open_probs['over'],open_probs['push'],row['opening_over_odds']),
                    ('UNDER',open_probs['conditional_under']-open_market['under'],open_probs['under'],open_probs['push'],row['opening_under_odds'])]
        decision,edge,pwin,ppush,price=max(candidates,key=lambda x:x[1])
        if edge < threshold:
            decision='NO_BET'; edge=0.; pwin=ppush=price=None
        else:
            expected_roi=pwin*(decimal_odds(price)-1)-(1-pwin-ppush)
            result=settle(row['actual_k'],row['opening_line'],decision)
            realized=profit(row['actual_k'],row['opening_line'],decision,price)
        open_record={'market':open_market,'model':open_probs,'edge_over':candidates[0][1],
                     'edge_under':candidates[1][1]}
        if row['opening_line']==row['closing_line']:
            selected_side=decision if decision!='NO_BET' else ('OVER' if candidates[0][1]>=candidates[1][1] else 'UNDER')
            clv=close_market[selected_side.lower()] - open_market[selected_side.lower()]
            clv_status='SAME_LINE_PRICE_CLV'
        else: clv_status='LINE_MOVED_UNSCORABLE'
    return {'game_id':row['game_id'],'player_id':row['player_id'],'player':row['player'],
            'season':row['season'],'book':row['book'],'actual_k':row['actual_k'],
            'opening_line':row['opening_line'],'closing_line':row['closing_line'],
            'opening_over_odds':row['opening_over_odds'],'opening_under_odds':row['opening_under_odds'],
            'closing_over_odds':row['closing_over_odds'],'closing_under_odds':row['closing_under_odds'],
            'closing_model':close_probs,'closing_market':close_market,'closing_scores':close_scores,
            'opening':open_record,'decision':decision,'edge':edge,'expected_roi':expected_roi,
            'settlement':result,'realized_roi':realized,'clv':clv,'clv_status':clv_status,
            'source':row['source']}


def mean_or_none(values): return fmean(values) if values else None


def group_summary(rows):
    scored=[r['closing_scores'] for r in rows if r['closing_scores']]
    bets=[r for r in rows if r['decision']!='NO_BET']
    realized=[r['realized_roi'] for r in bets if r['realized_roi'] is not None]
    return {'matched_rows':len(rows),'closing_nonpush_rows':len(scored),'bets':len(bets),
            'model_brier':mean_or_none([r['model_brier'] for r in scored]),
            'market_brier':mean_or_none([r['market_brier'] for r in scored]),
            'model_log_loss':mean_or_none([r['model_log_loss'] for r in scored]),
            'market_log_loss':mean_or_none([r['market_log_loss'] for r in scored]),
            'mean_realized_roi_per_unit':mean_or_none(realized),
            'sum_units':sum(realized)}


def run(prediction_path, market_path, variant='delta_pa', threshold=.05, output=None):
    if variant not in {'baseline','v2','delta_pa','delta_beta'}:
        raise ValueError('Choose baseline, v2, delta_pa or delta_beta.')
    threshold=finite(threshold,'edge threshold',0,1)
    predictions=load_predictions(prediction_path,variant)
    rows,market_sha=load_market(market_path,predictions,variant)
    evaluated=[evaluate_row(row,variant,threshold) for row in rows]
    scored=[r['closing_scores'] for r in evaluated if r['closing_scores']]
    bets=[r for r in evaluated if r['decision']!='NO_BET']
    profits=[r['realized_roi'] for r in bets if r['realized_roi'] is not None]
    clv=[r['clv'] for r in evaluated if r['clv'] is not None]
    report={'status':'HISTORICAL_MARKET_AUDIT_DEVELOPMENT_ONLY',
            'variant':variant,'edge_threshold':threshold,
            'prediction_source':str(Path(prediction_path).resolve()),
            'market_source':str(Path(market_path).resolve()),'market_sha256':market_sha,
            'matched_rows':len(evaluated),'closing_nonpush_rows':len(scored),
            'push_rows':len(evaluated)-len(scored),'opening_quote_rows':sum(r['opening'] is not None for r in evaluated),
            'bets':len(bets),'wins':sum(r['settlement']=='WIN' for r in bets),
            'losses':sum(r['settlement']=='LOSS' for r in bets),'pushes':sum(r['settlement']=='PUSH' for r in bets),
            'model_vs_market':{
                'model_brier':mean_or_none([r['model_brier'] for r in scored]),
                'market_brier':mean_or_none([r['market_brier'] for r in scored]),
                'model_log_loss':mean_or_none([r['model_log_loss'] for r in scored]),
                'market_log_loss':mean_or_none([r['market_log_loss'] for r in scored]),
                'rows':len(scored)},
            'roi':{'mean_realized_roi_per_unit':mean_or_none(profits),
                   'sum_units':sum(profits),'mean_model_expected_roi':mean_or_none([r['expected_roi'] for r in bets]),
                   'settled_bets':len(profits)},
            'clv':{'mean_no_vig_probability_move':mean_or_none(clv),
                   'same_line_rows':len(clv),'line_moved_rows':sum(r['clv_status']=='LINE_MOVED_UNSCORABLE' for r in evaluated)},
            'by_season':{str(season):group_summary([r for r in evaluated if r['season']==season])
                         for season in sorted({r['season'] for r in evaluated})},
            'by_book':{str(book):group_summary([r for r in evaluated if r['book']==book])
                       for book in sorted({r['book'] for r in evaluated})},
            'limitations':['This joins reconstructed historical DELTA distributions to operator-supplied prices; it is not a prospective pregame ledger.',
                           'Opening-price ROI is hypothetical and excludes limits, account restrictions, bet rejection and execution timing.',
                           'CLV is price-only and reported only when opening and closing lines match; line moves remain unscored.',
                           'No result promotes a model or establishes profitability. Use season and series clusters before interpreting an aggregate.'],
            'rows':evaluated}
    if output:
        target=Path(output).expanduser().resolve()
        if target.exists(): raise ValueError('Output exists; choose a new versioned audit path.')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predictions',default=str(ROOT/'audit/delta/PREDICTIONS.jsonl'))
    parser.add_argument('--market-csv',required=True)
    parser.add_argument('--variant',default='delta_pa',choices=['baseline','v2','delta_pa','delta_beta'])
    parser.add_argument('--edge-threshold',type=float,default=.05)
    parser.add_argument('--out',required=True)
    args=parser.parse_args(argv)
    try:
        report=run(args.predictions,args.market_csv,args.variant,args.edge_threshold,args.out)
        print(json.dumps({k:report[k] for k in ('status','variant','matched_rows','closing_nonpush_rows','bets','roi','model_vs_market','clv')},indent=2))
    except (OSError,ValueError,KeyError) as exc:
        parser.exit(2,f'DELTA market audit error: {exc}\n')


if __name__=='__main__': main()
