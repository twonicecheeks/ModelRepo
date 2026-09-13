#!/usr/bin/env python3
from pathlib import Path
import csv
import hashlib
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "packages/providers/nflverse/src"
sys.path.insert(0, str(SRC))
import normalize
import snapshot
import contract


def h(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pbp(game_id, season, week, team, opp, sign=1):
    return [
        {"game_id":game_id,"season":season,"week":week,"posteam":team,"defteam":opp,"qb_dropback":1,"rush":0,"epa":0.2*sign,"success":1,"cpoe":2.0*sign,"sack":0,"yards_gained":22,"interception":0,"fumble_lost":0,"no_play":0,"qb_kneel":0},
        {"game_id":game_id,"season":season,"week":week,"posteam":team,"defteam":opp,"qb_dropback":0,"rush":1,"epa":0.1*sign,"success":1,"cpoe":None,"sack":0,"yards_gained":11,"interception":0,"fumble_lost":0,"no_play":0,"qb_kneel":0},
    ]

with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    # historical feature core is a project source dependency of normalization
    core_src = ROOT/"packages/models/nfl/game/historical_feature_core.py"
    core_dst = root/"packages/models/nfl/game/historical_feature_core.py"
    core_dst.parent.mkdir(parents=True); core_dst.write_bytes(core_src.read_bytes())

    blobdir=root/"data/raw/nfl/nflverse/blobs/aa"; blobdir.mkdir(parents=True)
    schedules=blobdir/"sched"
    fields=["game_id","season","game_type","week","gameday","weekday","gametime","away_team","home_team","location","away_rest","home_rest","away_score","home_score","home_moneyline","away_moneyline","spread_line"]
    rows=[
      {"game_id":"2015_01_OAK_SD","season":2015,"game_type":"REG","week":1,"gameday":"2015-09-13","away_team":"OAK","home_team":"SD","location":"Home","away_rest":7,"home_rest":7,"away_score":17,"home_score":20,"home_moneyline":-120,"spread_line":-2.5},
      {"game_id":"2016_01_OAK_SD","season":2016,"game_type":"REG","week":1,"gameday":"2016-09-11","away_team":"OAK","home_team":"SD","location":"Home","away_rest":7,"home_rest":7,"away_score":24,"home_score":21,"home_moneyline":-110,"spread_line":-1.0},
      {"game_id":"2025_01_LV_LAC","season":2025,"game_type":"REG","week":1,"gameday":"2025-09-07","away_team":"LV","home_team":"LAC","location":"Home","away_rest":7,"home_rest":7,"away_score":14,"home_score":27,"home_moneyline":-160,"spread_line":-3.5},
    ]
    with schedules.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n'); w.writeheader(); w.writerows(rows)

    fake_files={}
    def add(name, data=b'parquet-fixture'):
        p=blobdir/name; p.write_bytes(data+name.encode()); fake_files[name]=p; return p
    players=add('players')
    for s in [2015,2016,2025]:
        add(f'roster_{s}'); add(f'pbp_{s}')

    assets=[]
    def asset(source, season, path, filename):
        return {"source":source,"season":season,"filename":filename,"url":"fixture://"+filename,"sha256":h(path),"bytes":path.stat().st_size,"blobPath":str(path.relative_to(root)),"fetchedAt":"2026-09-08T00:00:00Z","etag":None,"lastModified":None,"contentType":None,"finalUrl":None}
    assets.append(asset('schedules',None,schedules,'games.csv'))
    assets.append(asset('players',None,players,'players.parquet'))
    for s in [2015,2016,2025]:
        assets.append(asset('weekly_rosters',s,fake_files[f'roster_{s}'],f'roster_weekly_{s}.parquet'))
        assets.append(asset('play_by_play',s,fake_files[f'pbp_{s}'],f'play_by_play_{s}.parquet'))
    snapdir=root/'data/raw/nfl/nflverse/snapshots/fixture'; snapdir.mkdir(parents=True)
    manifest=snapdir/'SOURCE_MANIFEST.json'
    manifest.write_text(json.dumps({"snapshotSchemaVersion":snapshot.SNAPSHOT_SCHEMA_VERSION,"snapshotId":"fixture","createdAt":"2026-09-08T00:00:00Z","provider":"nflverse","contractVersion":contract.CONTRACT_VERSION,"analysisSeasons":[2016,2025],"historySeedSeasons":[2015],"trainingWindowFrozen":False,"marketDependency":False,"oddsPapiRequests":0,"assets":assets}))

    player_rows=[
      {"gsis_id":"00-0000001","display_name":"QB One","position":"QB","position_group":"QB","latest_team":"LV"},
      {"gsis_id":"00-0000002","display_name":"QB Two","position":"QB","position_group":"QB","latest_team":"LAC"},
    ]
    roster_rows={s:[
      {"season":s,"week":1,"team":"OAK" if s<2020 else "LV","gsis_id":"00-0000001","full_name":"QB One","position":"QB","depth_chart_position":"QB","status":"ACT","game_type":"REG"},
      {"season":s,"week":1,"team":"SD" if s<2017 else "LAC","gsis_id":"00-0000002","full_name":"QB Two","position":"QB","depth_chart_position":"QB","status":"ACT","game_type":"REG"},
    ] for s in [2015,2016,2025]}
    pbp_rows={
      2015: pbp('2015_01_OAK_SD',2015,1,'OAK','SD',1)+pbp('2015_01_OAK_SD',2015,1,'SD','OAK',-1),
      2016: pbp('2016_01_OAK_SD',2016,1,'OAK','SD',2)+pbp('2016_01_OAK_SD',2016,1,'SD','OAK',-2),
      2025: pbp('2025_01_LV_LAC',2025,1,'LV','LAC',3)+pbp('2025_01_LV_LAC',2025,1,'LAC','LV',-3),
    }
    def fake_parquet(path, columns):
        n=path.name
        if n=='players': return player_rows
        if n.startswith('roster_'): return roster_rows[int(n.split('_')[1])]
        if n.startswith('pbp_'): return pbp_rows[int(n.split('_')[1])]
        raise AssertionError(n)
    normalize._parquet_rows=fake_parquet
    def fake_pbp_parquet(path):
        rows = fake_parquet(path, normalize.PBP_REQUIRED_COLUMNS)
        return rows, {"noPlaySource":"no_play", "qbKneelSource":"qb_kneel", "columns":list(normalize.PBP_REQUIRED_COLUMNS)}
    normalize._pbp_parquet_rows=fake_pbp_parquet

    audit_path=normalize.normalize_snapshot(root,manifest)
    assert audit_path.exists()
    out=audit_path.parent
    with (out/'game_identity.csv').open() as f: ids=list(csv.DictReader(f))
    g2016=next(r for r in ids if r['season']=='2016')
    assert g2016['source_away_team']=='OAK' and g2016['away_team']=='LV'
    assert g2016['source_home_team']=='SD' and g2016['home_team']=='LAC'
    with (out/'pregame_features.csv').open() as f: feats=list(csv.DictReader(f))
    f2016=next(r for r in feats if r['season']=='2016')
    assert f2016['away_prior_season_off_dropback_epa'] != ''
    assert f2016['home_prior_season_off_dropback_epa'] != ''
    f2025=next(r for r in feats if r['season']=='2025')
    assert f2025['split_state']=='HOLDOUT_NEVER_FIT'
    forbidden={'home_moneyline','away_moneyline','spread_line','home_score','away_score'}
    assert not (forbidden & set(f2016))
    audit=json.loads((out/'NFLVERSE_COVERAGE_AUDIT.json').read_text())
    assert audit['marketIsolation']['pass'] is True
    assert 'home_moneyline' in audit['marketIsolation']['sourceMarketColumnsObserved']
    assert audit['qbRosterIdentity']['resolvedGsisPct']==100.0
    assert (root/'data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT').read_text().strip()=='fixture'
print("PASS NFL normalization: relocation continuity, target/market isolation, holdout tagging, identity coverage")
