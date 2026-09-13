from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
installer = HERE / "install_omega_tackle_0152.command"
text = installer.read_text(encoding="utf-8")

for forbidden in (
    'cp "$HERE"/packages/models/nfl/omega/*',
    'cp "$HERE"/scripts/nfl/*',
    'cp "$HERE"/tests/nfl/*',
):
    assert forbidden not in text, f"unsafe wildcard copy remains: {forbidden}"

assert 'packages/models/nfl/omega/*.py' in text
assert 'scripts/nfl/*.py' in text
assert 'scripts/nfl/*.command' in text
assert 'tests/nfl/*.py' in text
print("PASS OMEGA 0.15.2 installer test-path hotfix regression")
