#!/usr/bin/env python3
"""Validate the isolated NFL Phase 1B Python dependency pins.

Certifi releases use calendar-style versions and the package runtime string may
zero-pad month/day components (for example 2026.07.22) while the distribution
metadata / requirement pin uses 2026.7.22.  Compare numeric components rather
than raw presentation strings so equivalent versions do not fail bootstrap.
"""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import ssl

PYARROW_PIN = "25.0.1"
CERTIFI_PIN = "2026.7.22"


def numeric_version(value: str) -> tuple[int, ...]:
    parts = value.strip().split(".")
    if not parts or any(not p.isdigit() for p in parts):
        raise ValueError(f"unsupported numeric version: {value!r}")
    return tuple(int(p) for p in parts)


def versions_equivalent(left: str, right: str) -> bool:
    return numeric_version(left) == numeric_version(right)


def validate_dependencies() -> dict[str, str]:
    import certifi
    import pyarrow

    pyarrow_meta = metadata.version("pyarrow")
    certifi_meta = metadata.version("certifi")
    certifi_runtime = getattr(certifi, "__version__", certifi_meta)

    if not versions_equivalent(pyarrow_meta, PYARROW_PIN):
        raise AssertionError(f"pyarrow distribution {pyarrow_meta} != pin {PYARROW_PIN}")
    if not versions_equivalent(pyarrow.__version__, PYARROW_PIN):
        raise AssertionError(f"pyarrow runtime {pyarrow.__version__} != pin {PYARROW_PIN}")
    if not versions_equivalent(certifi_meta, CERTIFI_PIN):
        raise AssertionError(f"certifi distribution {certifi_meta} != pin {CERTIFI_PIN}")
    if not versions_equivalent(certifi_runtime, CERTIFI_PIN):
        raise AssertionError(f"certifi runtime {certifi_runtime} != pin {CERTIFI_PIN}")

    ctx = ssl.create_default_context(cafile=certifi.where())
    if ctx.verify_mode != ssl.CERT_REQUIRED:
        raise AssertionError(f"TLS verify_mode must be CERT_REQUIRED, found {ctx.verify_mode}")
    if ctx.check_hostname is not True:
        raise AssertionError("TLS hostname verification must remain enabled")

    return {
        "pyarrowDistribution": pyarrow_meta,
        "pyarrowRuntime": pyarrow.__version__,
        "certifiDistribution": certifi_meta,
        "certifiRuntime": certifi_runtime,
        "certifiBundle": certifi.where(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        info = validate_dependencies()
    except Exception as exc:
        if not args.quiet:
            print(f"FAIL NFL Phase 1B dependency validation: {exc}")
        return 1
    if not args.quiet:
        print(f"PASS isolated pyarrow {info['pyarrowRuntime']}")
        print(
            "PASS pinned certifi "
            f"{CERTIFI_PIN} (distribution {info['certifiDistribution']} · runtime {info['certifiRuntime']}) "
            "/ TLS verification REQUIRED"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
