#!/usr/bin/env python3
from pathlib import Path
import importlib.util
root=Path(__file__).resolve().parents[2]
p=root/"scripts/nfl/diagnose_omega_propsmadness_sportsbook_schema_0179.py"
spec=importlib.util.spec_from_file_location("m",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

assert m.candidate_direct_book({"bet":{"sportsbook":{"name":"pinnacle"}}})=="pinnacle"
assert m.candidate_direct_book({"sportsBook":{"slug":"fanduel"}})=="fanduel"
assert m.candidate_direct_book({"bet":{"odds":{"books":[{"name":"pinnacle"}]}}}) is None

paths=m.collect_interesting_paths({"bet":{"odds":{"books":[{"name":"pinnacle","price":-110}]}}})
names={x["path"] for x in paths}
assert "$.bet.odds" in names
assert any("books" in x for x in names)
assert any("price" in x for x in names)
print("PASS OMEGA 0.17.9 sportsbook-schema diagnostic contracts")
