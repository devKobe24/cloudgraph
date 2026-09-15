"""Build the designer bundle and copy it into the Python package.

Contributors need Node for this; end users never do, because the built asset is
committed and shipped inside the wheel.

    python -m tools.build_web            # build and copy
    python -m tools.build_web --check    # fail if the committed asset is stale
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBUI = ROOT / "webui"
BUILT = WEBUI / "dist" / "index.html"
TARGET = ROOT / "awsgraph" / "assets" / "designer.html"


def build() -> None:
    if not (WEBUI / "node_modules").is_dir():
        subprocess.run(["npm", "ci"], cwd=WEBUI, check=True)
    subprocess.run(["npm", "run", "build"], cwd=WEBUI, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="verify the committed asset matches a fresh build"
    )
    args = parser.parse_args(argv)

    build()
    fresh = BUILT.read_text(encoding="utf-8")

    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else ""
        if current != fresh:
            print(
                f"{TARGET.relative_to(ROOT)} is stale. "
                "Run `python -m tools.build_web` and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"{TARGET.relative_to(ROOT)} is up to date.")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(fresh, encoding="utf-8")
    print(f"Wrote {TARGET.relative_to(ROOT)} ({len(fresh):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
