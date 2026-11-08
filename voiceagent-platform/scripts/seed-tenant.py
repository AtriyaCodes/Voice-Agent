#!/usr/bin/env python3
"""Seeds a tenant configuration for local development.

Usage:
    python scripts/seed-tenant.py --tenant-id acme --display-name "Acme Bank" --voice-id en-in-1 --language en-IN
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--voice-id", default="default")
    parser.add_argument("--language", default="en-IN")
    parser.add_argument("--compliance-mode", choices=["standard", "banking"], default="standard")
    args = parser.parse_args()

    print(f"Seeding tenant {args.tenant_id} ({args.display_name})")
    print("This is a placeholder: wire this to the orchestration-api tenant store (Postgres) once that schema exists.")


if __name__ == "__main__":
    main()
