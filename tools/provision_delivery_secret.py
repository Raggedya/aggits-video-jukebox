from __future__ import annotations

import getpass
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aggits_video_factory.store import ProjectStore


def main() -> int:
    secret = getpass.getpass("Delivery HMAC secret: ").strip()
    confirm = getpass.getpass("Confirm delivery HMAC secret: ").strip()
    if not secret or secret != confirm:
        print("Secret was empty or did not match; nothing was saved.", file=sys.stderr)
        return 1
    store = ProjectStore()
    store.save_delivery_secret(secret)
    print(f"Delivery secret stored with Windows DPAPI in {store.settings_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
