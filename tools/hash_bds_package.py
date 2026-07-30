#!/usr/bin/env python3
"""Verify an official BDS ZIP and report its executable identity locally."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

EXPECTED = {
    "linux-x64": {
        "archive": "68c52ababde987741029de091c09cd736fe894bc1fe99cf20f9ed5c659f0c180",
        "executable": "bedrock_server",
    },
    "windows-x64": {
        "archive": "fc6c0ad6f82cfb11c65c6756a1a8e49b21ffa8cc203da587df59df365d82a2ad",
        "executable": "bedrock_server.exe",
    },
}


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--platform", choices=sorted(EXPECTED), required=True)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    archive_hash = hash_file(args.zip_path)
    expected = EXPECTED[args.platform]
    if archive_hash != expected["archive"]:
        raise SystemExit(
            f"archive SHA-256 mismatch: expected {expected['archive']}, got {archive_hash}"
        )

    target = expected["executable"]
    with zipfile.ZipFile(args.zip_path) as archive:
        matches = [info for info in archive.infolist() if Path(info.filename).name == target]
        if len(matches) != 1:
            raise SystemExit(f"expected exactly one {target!r}, found {len(matches)}")
        digest = hashlib.sha256()
        size = 0
        with archive.open(matches[0], "r") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)

    result = {
        "platform": args.platform,
        "bds_package_version": "1.26.33.1",
        "archive_sha256": archive_hash,
        "executable_filename": target,
        "executable_sha256": digest.hexdigest(),
        "executable_size": size,
    }
    rendered = json.dumps(result, indent=2) + "\n"
    if args.json_out:
        args.json_out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
