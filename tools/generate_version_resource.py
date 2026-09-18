from __future__ import annotations

import argparse
from pathlib import Path

from aggits_video_factory.version import (
    APP_VERSION,
    EXE_FILENAME,
    PRODUCT_NAME,
    WINDOWS_FILE_VERSION,
    WINDOWS_FILE_VERSION_STRING,
)


def render() -> str:
    numeric = ", ".join(str(part) for part in WINDOWS_FILE_VERSION)
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({numeric}),
    prodvers=({numeric}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('FileDescription', '{PRODUCT_NAME}'),
          StringStruct('FileVersion', '{WINDOWS_FILE_VERSION_STRING}'),
          StringStruct('InternalName', '{PRODUCT_NAME}'),
          StringStruct('OriginalFilename', '{EXE_FILENAME}'),
          StringStruct('ProductName', '{PRODUCT_NAME}'),
          StringStruct('ProductVersion', '{APP_VERSION}'),
        ],
      ),
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(render(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
