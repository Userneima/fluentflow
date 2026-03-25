"""Start FastAPI with uvicorn from a TCC-safe working copy."""

from __future__ import annotations

import os
import sys


def main() -> None:
    repo = os.environ.get("FLUENTFLOW_REPO", "").strip()
    extra = os.environ.get("FLUENTFLOW_EXTRA_SITE", "").strip()
    port_s = os.environ.get("FLUENTFLOW_PORT", "8000").strip()

    if not repo:
        sys.stderr.write("FLUENTFLOW_REPO must be set\n")
        raise SystemExit(1)

    for p in (extra, repo):
        if p and os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)

    os.chdir(repo)

    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=int(port_s),
        app_dir=repo,
    )


if __name__ == "__main__":
    main()
