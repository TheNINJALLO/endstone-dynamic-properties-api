from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[2]
PACKAGER = ROOT / "scripts" / "package_portable_sdk.py"


def test_portable_sdk_is_repeatable_and_excludes_python_cache(tmp_path: Path):
    stage = tmp_path / "stage"
    (stage / "python" / "package" / "__pycache__").mkdir(parents=True)
    (stage / "README.md").write_text("portable SDK\n", encoding="utf-8")
    (stage / "python" / "package" / "module.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
    (stage / "python" / "package" / "__pycache__" / "module.pyc").write_bytes(
        b"generated cache"
    )
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = "1785370000"
    outputs = (tmp_path / "first.zip", tmp_path / "second.zip")

    for output in outputs:
        subprocess.run(
            [
                sys.executable,
                str(PACKAGER),
                "--input",
                str(stage),
                "--output",
                str(output),
                "--prefix",
                "portable-sdk",
            ],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    with zipfile.ZipFile(outputs[0]) as archive:
        names = archive.namelist()
    assert "portable-sdk/README.md" in names
    assert "portable-sdk/python/package/module.py" in names
    assert not any("__pycache__" in name or name.endswith((".pyc", ".pyo")) for name in names)
