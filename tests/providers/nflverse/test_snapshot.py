#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import json
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "packages/providers/nflverse/src"
import sys
sys.path.insert(0, str(SRC))
import snapshot

plan = snapshot.build_asset_plan([2016], [2015])
assert [(a.source, a.season) for a in plan] == [
    ("schedules", None), ("players", None),
    ("weekly_rosters", 2015), ("play_by_play", 2015),
    ("weekly_rosters", 2016), ("play_by_play", 2016),
]
assert all(a.url.startswith("https://github.com/nflverse/") for a in plan)

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    calls=[]
    def fake(url, path):
        calls.append(url)
        path.write_bytes(("fixture:"+url).encode())
        return {"etag":"fixture", "lastModified":"now", "contentType":"application/octet-stream", "finalUrl":url}
    m1 = snapshot.acquire_snapshot(root, analysis_seasons=[2016], history_seed_seasons=[2015], fetcher=fake)
    data1 = snapshot.load_manifest(m1, root=root)
    assert data1["analysisSeasons"] == [2016]
    assert data1["historySeedSeasons"] == [2015]
    assert data1["trainingWindowFrozen"] is False
    assert data1["oddsPapiRequests"] == 0
    assert len(data1["assets"]) == 6
    assert len(calls) == 6
    assert (root/"data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT").read_text().strip() == data1["snapshotId"]
    blobs = list((root/"data/raw/nfl/nflverse/blobs").rglob("*"))
    blob_files = [p for p in blobs if p.is_file()]
    assert len(blob_files) == 6

    # Same bytes in a second immutable snapshot reuse content-addressed blobs.
    m2 = snapshot.acquire_snapshot(root, analysis_seasons=[2016], history_seed_seasons=[2015], fetcher=fake)
    data2 = snapshot.load_manifest(m2, root=root)
    assert data2["snapshotId"] != data1["snapshotId"]
    assert [a["sha256"] for a in data2["assets"]] == [a["sha256"] for a in data1["assets"]]
    assert len([p for p in (root/"data/raw/nfl/nflverse/blobs").rglob("*") if p.is_file()]) == 6
print("PASS NFL snapshot acquisition: immutable manifests, SHA256 blob reuse, zero market dependency")

# TLS regression: urllib must receive an explicit certificate-validating context
# built from the pinned certifi CA bundle. Never disable certificate verification.
import io
import types
from unittest import mock

fake_certifi = types.SimpleNamespace(where=lambda: "/fixture/cacert.pem")
fake_context = object()
with mock.patch.dict(sys.modules, {"certifi": fake_certifi}):
    with mock.patch.object(snapshot.ssl, "create_default_context", return_value=fake_context) as make_ctx:
        ctx = snapshot._verified_tls_context()
        assert ctx is fake_context
        make_ctx.assert_called_once_with(cafile="/fixture/cacert.pem")

class FakeResponse(io.BytesIO):
    def __init__(self, payload=b"secure fixture"):
        super().__init__(payload)
        self.headers = {"ETag": "tls-fixture", "Last-Modified": "now", "Content-Type": "application/octet-stream"}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()
    def geturl(self):
        return "https://github.com/nflverse/final"

with tempfile.TemporaryDirectory() as td:
    target = Path(td) / "fixture.bin"
    with mock.patch.object(snapshot, "_verified_tls_context", return_value=fake_context):
        with mock.patch.object(snapshot.urllib.request, "urlopen", return_value=FakeResponse()) as urlopen:
            meta = snapshot._download_http("https://github.com/nflverse/test", target, retries=1)
            assert target.read_bytes() == b"secure fixture"
            assert meta["finalUrl"] == "https://github.com/nflverse/final"
            kwargs = urlopen.call_args.kwargs
            assert kwargs["context"] is fake_context
            assert kwargs["timeout"] == 120
print("PASS NFL TLS acquisition: explicit certifi CA context, hostname/certificate verification not bypassed")
