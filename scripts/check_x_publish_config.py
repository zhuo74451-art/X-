from __future__ import annotations

import os


def _env(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def main() -> None:
    required = [
        "X_API_KEY",
        "X_API_SECRET",
        "X_ACCESS_TOKEN",
        "X_ACCESS_TOKEN_SECRET",
    ]
    missing = [k for k in required if not _env(k)]

    print("[check_x_publish_config] X publish env check (no network, no post)")
    print(f"- AUTO_PUBLISH_ENABLED: {_env('AUTO_PUBLISH_ENABLED', 'false') or 'false'}")
    print(f"- AUTO_PUBLISH_DRY_RUN: {_env('AUTO_PUBLISH_DRY_RUN', 'true') or 'true'}")

    if missing:
        print("- ok: false")
        print("- missing:", ",".join(missing))
        raise SystemExit(2)

    print("- ok: true")
    print("- missing: (none)")


if __name__ == "__main__":
    main()

