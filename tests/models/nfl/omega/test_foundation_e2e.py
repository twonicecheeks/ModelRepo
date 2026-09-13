import csv,json,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path

class FoundationE2ETest(unittest.TestCase):
    def repo_root(self): return Path(__file__).resolve().parents[4]

    def test_build_does_not_open_2025(self):
        try:
            import pyarrow as pa, pyarrow.parquet as pq
        except ModuleNotFoundError:
            self.skipTest('pyarrow unavailable in this interpreter')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);sid='SYNTHETIC_OMEGA'
            (root/'packages/models/nfl/omega').mkdir(parents=True)
            shutil.copy2(self.repo_root()/'packages/models/nfl/omega/tackle_events.py',root/'packages/models/nfl/omega/tackle_events.py')
            (root/'data/normalized/nfl').mkdir(parents=True)
            (root/'data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT').write_text(sid+'\n')
            norm=root/f'data/normalized/nfl/phase1/{sid}';norm.mkdir(parents=True)
            game_fields=['game_id','season','game_type','week','gameday','away_team','home_team']
            with (norm/'game_identity.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=game_fields);w.writeheader()
                for season in range(2016,2026):w.writerow({'game_id':f'{season}_01_A_B','season':season,'game_type':'REG','week':1,'gameday':f'{season}-09-01','away_team':'A','home_team':'B'})
            raw=root/f'data/raw/nfl/nflverse/snapshots/{sid}';raw.mkdir(parents=True)
            blobs=root/'blobs';blobs.mkdir()
            players=blobs/'players.parquet';pq.write_table(pa.Table.from_pylist([{'gsis_id':'P1','display_name':'Player One','position':'LB','position_group':'LB','pfr_id':'PFR1'},{'gsis_id':'P2','display_name':'Player Two','position':'S','position_group':'DB','pfr_id':'PFR2'}]),players)
            assets=[{'source':'players','season':None,'blobPath':str(players.relative_to(root))}]
            for season in range(2016,2025):
                p=blobs/f'pbp_{season}.parquet'
                pq.write_table(pa.Table.from_pylist([{'game_id':f'{season}_01_A_B','play_id':1,'season':season,'week':1,'posteam':'A','defteam':'B','play_type':'run','rush_attempt':1,'special_teams_play':0,'solo_tackle_1_player_id':'P1','solo_tackle_1_player_name':'One','solo_tackle_1_team':'B','assist_tackle_1_player_id':None,'assist_tackle_1_player_name':None,'assist_tackle_1_team':None,'tackle_with_assist_1_player_id':None,'tackle_with_assist_1_player_name':None,'tackle_with_assist_1_team':None}]),p)
                assets.append({'source':'play_by_play','season':season,'blobPath':str(p.relative_to(root))})
            # Deliberately invalid 2025 file. Build must not try to open it.
            p25=blobs/'pbp_2025.parquet';p25.write_text('DO NOT OPEN')
            assets.append({'source':'play_by_play','season':2025,'blobPath':str(p25.relative_to(root))})
            (raw/'SOURCE_MANIFEST.json').write_text(json.dumps({'analysisSeasons':list(range(2016,2026)),'assets':assets}))
            snapdir=root/f'data/raw/nfl/nflverse/phase2c_context/snapshots/CTX';snapdir.mkdir(parents=True)
            sp=blobs/'snap_2016.parquet';pq.write_table(pa.Table.from_pylist([{'game_id':'2016_01_A_B','pfr_player_id':'PFR1','defense_snaps':55,'defense_pct':0.9,'special_teams_snaps':4,'special_teams_pct':0.1}]),sp)
            (snapdir/'SOURCE_MANIFEST.json').write_text(json.dumps({'sourcePhase1SnapshotId':sid,'createdAt':'2026-01-01T00:00:00Z','assets':[{'source':'snap_counts','season':2016,'blobPath':str(sp.relative_to(root))}]}))
            script=self.repo_root()/'scripts/nfl/build_omega_tackle_foundation.py'
            p=subprocess.run([sys.executable,str(script),'--root',str(root)],text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr+p.stdout)
            audit=json.loads((root/f'data/normalized/nfl/omega_tackle/{sid}/OMEGA_TACKLE_FOUNDATION_AUDIT.json').read_text())
            self.assertEqual(audit['omegaHoldoutPbpRowsRead'],0)
            self.assertEqual(audit['omegaHoldoutTackleOutcomesRead'],0)
            self.assertEqual(audit['creditEvents'],9)
            self.assertFalse(audit['modelFitPerformed'])
            self.assertEqual(audit['marketFieldsRead'],0)

if __name__=='__main__':unittest.main()
