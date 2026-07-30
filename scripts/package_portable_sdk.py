#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path, PurePosixPath
import zipfile


def zip_timestamp() -> tuple[int, int, int, int, int, int]:
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "315532800"))
    moment = datetime.fromtimestamp(max(epoch, 315532800), timezone.utc)
    return (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second)


def is_release_file(path: Path, source: Path) -> bool:
    relative = path.relative_to(source)
    return (
        path.is_file()
        and "__pycache__" not in relative.parts
        and path.suffix.lower() not in {".pyc", ".pyo"}
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args()

    source = args.input.resolve()
    if not source.is_dir():
        raise SystemExit(f"SDK input directory does not exist: {source}")
    files = sorted(path for path in source.rglob("*") if is_release_file(path, source))
    if not files:
        raise SystemExit("SDK input directory is empty")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    timestamp = zip_timestamp()
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = PurePosixPath(path.relative_to(source).as_posix())
            name = str(PurePosixPath(args.prefix) / relative)
            info = zipfile.ZipInfo(name, timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
