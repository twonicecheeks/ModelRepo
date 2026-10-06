import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools.evaluate_delta_market import devig, run


class DeltaMarketAudit(unittest.TestCase):
    def prediction(self, path):
        row={'game_id':'123','player_id':'456','player':'Fixture Starter','game_date':'2025-10-01',
             'season':2025,'actual_k':4,
             'pmfs':{'delta_pa':[.1,.1,.1,.7],
                     'delta_beta':[.1,.1,.1,.7],
                     'v2':[.25,.25,.25,.25],
                     'baseline':[.25,.25,.25,.25]}}
        path.write_text(json.dumps(row)+'\n')

    def test_devig_and_half_line_roi_and_clv(self):
        self.assertAlmostEqual(devig(-110,-110)['over'],.5)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);pred=folder/'predictions.jsonl';market=folder/'market.csv';out=folder/'audit.json'
            self.prediction(pred)
            fields=['game_id','player_id','market_type','line','opening_line','opening_over_odds','opening_under_odds',
                    'closing_line','closing_over_odds','closing_under_odds','game_start_at','captured_at',
                    'closing_captured_at','actual_k','source','settlement_definition']
            with market.open('w',newline='') as file:
                writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader();writer.writerow({
                    'game_id':'123','player_id':'456','market_type':'K','line':'2.5','opening_line':'2.5',
                    'opening_over_odds':'-110','opening_under_odds':'-110','closing_line':'2.5',
                    'closing_over_odds':'-120','closing_under_odds':'+100',
                    'game_start_at':'2025-10-01T20:00:00Z','captured_at':'2025-10-01T16:00:00Z',
                    'closing_captured_at':'2025-10-01T19:55:00Z','actual_k':'4',
                    'source':'TEST FIXTURE','settlement_definition':'FULL_GAME'})
            report=run(pred,market,'delta_pa',.05,out)
            self.assertEqual(report['bets'],1)
            self.assertEqual(report['wins'],1)
            self.assertAlmostEqual(report['roi']['sum_units'],100/110)
            self.assertGreater(report['clv']['mean_no_vig_probability_move'],0)
            self.assertLess(report['model_vs_market']['model_brier'],report['model_vs_market']['market_brier'])
            self.assertTrue(out.is_file())

    def test_whole_line_push_and_line_move_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);pred=folder/'predictions.jsonl';market=folder/'market.csv'
            row={'game_id':'123','player_id':'456','player':'Fixture Starter','game_date':'2025-10-01',
                 'season':2025,'actual_k':2,'pmfs':{name:[.1,.2,.3,.4] for name in ['delta_pa','delta_beta','v2','baseline']}}
            pred.write_text(json.dumps(row)+'\n')
            fields=['game_id','player_id','market_type','line','opening_line','opening_over_odds','opening_under_odds',
                    'closing_line','closing_over_odds','closing_under_odds','game_start_at','captured_at',
                    'closing_captured_at','actual_k','source','settlement_definition']
            with market.open('w',newline='') as file:
                writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader();writer.writerow({
                    'game_id':'123','player_id':'456','market_type':'K','line':'2','opening_line':'2',
                    'opening_over_odds':'-110','opening_under_odds':'-110','closing_line':'2.5',
                    'closing_over_odds':'-110','closing_under_odds':'-110',
                    'game_start_at':'2025-10-01T20:00:00Z','captured_at':'2025-10-01T16:00:00Z',
                    'closing_captured_at':'2025-10-01T19:55:00Z','actual_k':'2',
                    'source':'TEST FIXTURE','settlement_definition':'FULL_GAME'})
            report=run(pred,market,'delta_pa',.05)
            self.assertEqual(report['push_rows'],0)
            self.assertEqual(report['closing_nonpush_rows'],1)
            self.assertEqual(report['bets'],1)
            self.assertEqual(report['pushes'],1)
            self.assertEqual(report['clv']['line_moved_rows'],1)
            self.assertIsNone(report['rows'][0]['clv'])
            self.assertEqual(report['rows'][0]['clv_status'],'LINE_MOVED_UNSCORABLE')


if __name__=='__main__':unittest.main()
