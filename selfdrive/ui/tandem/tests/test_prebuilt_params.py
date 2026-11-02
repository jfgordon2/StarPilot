"""The device runs prebuilt (the committed `prebuilt` file): it never recompiles, so the param registry it knows is the one
compiled into the committed common/params_pyx.so and libcommon.a. A key added to params_keys.h without rebuilding those is
unknown on the device, and reading or writing it raises UnknownKeyName, which crashes the UI."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.skipif(not (ROOT / "prebuilt").exists(), reason="only matters while the device runs prebuilt binaries")
@pytest.mark.parametrize("binary", ["common/params_pyx.so", "common/libcommon.a"])
def test_every_param_key_is_in_the_committed_binaries(binary):
  keys = re.findall(r'^\s*\{"(\w+)",\s*\{', (ROOT / "common/params_keys.h").read_text(), re.MULTILINE)
  compiled = (ROOT / binary).read_bytes()
  missing = [k for k in keys if k.encode() not in compiled]
  assert len(keys) > 100 and not missing, f"rebuild {binary} for: {missing}"
