import csv,json,subprocess,sys,tempfile,unittest
from pathlib import Path

class MarketLedgerTest(unittest.TestCase):
    def script(self):
        # after install this test lives at ROOT/tests/models/nfl/omega
        return Path(__file__).resolve().parents[4]/'scripts/nfl/append_omega_tackle_market_snapshot.py'

    def test_market_snapshot_storage_and_model_field_rejection(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);inp=root/'capture.csv'
            fields=['book','player_name','market_kind','line','over_odds_american','under_odds_american']
            with inp.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerow({'book':'fanduel','player_name':'X','market_kind':'tackles_assists','line':'7.5','over_odds_american':'-110','under_odds_american':'-110'})
            p=subprocess.run([sys.executable,str(self.script()),str(inp),'--root',str(root)],text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr+p.stdout)
            ptr=(root/'data/raw/nfl/omega/CURRENT_MARKET_SNAPSHOT').read_text().strip()
            man=json.loads((root/f'data/raw/nfl/omega/market_snapshots/{ptr}/MARKET_SNAPSHOT_MANIFEST.json').read_text())
            self.assertFalse(man['modelFieldsPresent'])
            bad=root/'bad.json';bad.write_text(json.dumps([{'book':'x','player_name':'Y','market_kind':'solo_tackles','line':5.5,'over_odds_american':-110,'under_odds_american':-110,'edge':0.1}]))
            q=subprocess.run([sys.executable,str(self.script()),str(bad),'--root',str(root)],text=True,capture_output=True)
            self.assertNotEqual(q.returncode,0)

if __name__=='__main__':unittest.main()
