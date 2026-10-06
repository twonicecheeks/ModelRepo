"""Create the read-only HTML preview from the release's code and real seed data."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.core import Store, canonical, now
from app.simulator import simulate
from app.validation import evaluate
from app.mlb import MLB


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--state-output',type=Path)
    parser.add_argument('--page',choices=['delta','deltatest','mlb','mlbtest'],default='mlb')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory() as d:
        store=Store(Path(d)/'preview.sqlite3',ROOT/'seed')
        state=store.state()
        state['mlb']=MLB(store).state()
        sim=simulate(state['forecasts'],{'game_id':'2026_03_BAL_DAL','team':'BAL','draws':2500,
                     'seed':2709,'pace':1,'rush_shift':0,'competition':0,'volume_cv':.15})
        sim.update(created_at=now(),input_snapshot_id=state['forecast_snapshot']['id'],snapshot_id='PREVIEW_RESEARCH_SCENARIO')
        validation=evaluate(state['scores'])
        state.update(last_simulation=sim,validation=validation,data_path='Shown on your Mac in the running app.',
                     inbox='Shown on your Mac in the running app.',csrf='',odds_key_configured=False,
                     odds_last={},odds_last_failure=None,odds_budget={},odds_quota={},jobs=[])
        html=(ROOT/'web/index.html').read_text()
        html=html.replace('<link rel="stylesheet" href="/styles.css">','<style>'+(ROOT/'web/styles.css').read_text()+'</style>')
        html=html.replace('<script src="/app.js" defer></script>','')
        js=canonical(state).replace('<','\\u003c')
        html=html.replace('</body>','<script>window.OMEGA_PREVIEW='+js+';if(!location.hash)location.hash='+json.dumps(args.page)+';</script><script>'+(ROOT/'web/app.js').read_text()+'</script></body>')
        args.output.write_text(html,encoding='utf-8')
        if args.state_output:args.state_output.write_text(canonical(state),encoding='utf-8')
        store.db.close()
    print('Created read-only OMEGA / DELTA preview: twelve views, real playoff and DELTA replay, saved data, and provenance.')


if __name__=='__main__':main()
