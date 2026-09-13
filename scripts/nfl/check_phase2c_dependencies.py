#!/usr/bin/env python3
import importlib.metadata as metadata
PIN='2.3.5'
def main():
    import numpy
    meta=metadata.version('numpy')
    if meta!=PIN or numpy.__version__!=PIN:raise AssertionError(f'numpy pin mismatch: distribution={meta} runtime={numpy.__version__} expected={PIN}')
    print(f'PASS isolated numpy {numpy.__version__} · Phase2C vectorized research fitter')
    return 0
if __name__=='__main__':raise SystemExit(main())
