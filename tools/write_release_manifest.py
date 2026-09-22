from __future__ import annotations

import argparse
import hashlib
import platform
from datetime import datetime, timezone
from pathlib import Path

import PyInstaller

from aggits_video_factory.version import APP_VERSION, RELEASE_TAG


LEGACY_EXE_SHA256 = "2297E207272F84AA9B0FADD648DC5AB31E14109BC1D83054906270CD50780FB5"
LEGACY_TAG = "crispy-bits-business-v2.3.0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--python-tests", required=True, type=int)
    parser.add_argument("--worker-tests", required=True, type=int)
    parser.add_argument("--worker-deployment", default="NOT DEPLOYED")
    parser.add_argument("--d1-migration", default="NOT APPLIED")
    parser.add_argument("--delivery-verification", default="NOT EXECUTED")
    args = parser.parse_args()

    exe = args.exe.resolve(strict=True)
    built_at = datetime.fromtimestamp(exe.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    manifest = f"""CRISPY BITS DESKTOP RELEASE MANIFEST
=====================================

Product: Crispy Bits Desktop
Version: {APP_VERSION}
EXE filename: {exe.name}
EXE SHA-256: {sha256(exe)}
EXE size: {exe.stat().st_size} bytes
Build timestamp (UTC): {built_at}
Source commit: {args.commit}
Source local tag: {RELEASE_TAG}
Python version: {platform.python_version()}
Python architecture: {platform.machine()}
PyInstaller version: {PyInstaller.__version__}
Project schema version: 3
Python tests: {args.python_tests}/{args.python_tests} passing
Worker tests: {args.worker_tests}/{args.worker_tests} passing
Packaged-resource smoke: PASS
Windows version metadata: PASS
Code signing: UNSIGNED - NO TRUSTED CODE-SIGNING CERTIFICATE CONFIGURED
Production Worker: {args.worker_deployment}
D1 delivery-security migration: {args.d1_migration}
Authenticated production delivery verification: {args.delivery_verification}

Protected rollback baseline
---------------------------
Legacy product: Crispy Bits Business v2.3.0
Legacy EXE SHA-256: {LEGACY_EXE_SHA256}
Legacy source tag: {LEGACY_TAG}

Known unresolved release items
------------------------------
- Production delivery provisioning is incomplete unless the three statuses above say otherwise.
- The executable is not Authenticode-signed.
"""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(manifest, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
