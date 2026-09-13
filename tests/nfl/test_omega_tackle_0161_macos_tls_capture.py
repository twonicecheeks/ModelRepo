#!/usr/bin/env python3
from pathlib import Path
import importlib.util, tempfile, os
ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'scripts/nfl/capture_omega_tackle_016_2026_pregame.py'
text=p.read_text()
# Security regression: never "fix" TLS by disabling verification.
for forbidden in ('CERT_NONE','_create_unverified_context','--insecure',"'-k'",'"-k"'):
    assert forbidden not in text, forbidden
assert "shutil.which('curl')" in text
assert "'--fail','--location'" in text
assert "'transport':'system_curl_tls_verified'" in text
assert "'tlsVerificationDisabled':False" in text
spec=importlib.util.spec_from_file_location('cap0161',p)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
status,h=m._parse_curl_headers('HTTP/1.1 302 Found\r\nLocation: x\r\n\r\nHTTP/2 200\r\nETag: abc\r\nContent-Type: text/csv\r\n\r\n')
assert status==200 and h['etag']=='abc' and h['content-type']=='text/csv'
assert m.roster_status('ACT')=='ACTIVE_ROSTER'
assert m.game_status('Questionable')=='QUESTIONABLE'
print('PASS OMEGA 0.16.1 macOS TLS capture hotfix regression')
