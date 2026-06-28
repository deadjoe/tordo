import argparse
import json

from tordo.remote_install import DEFAULT_USER_LIBRARY, install_remote_script


def main():
    parser = argparse.ArgumentParser(description="Install TordoBridge into the User Library.")
    parser.add_argument("--target-user-library", default=str(DEFAULT_USER_LIBRARY))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = install_remote_script(args.target_user_library, dry_run=args.dry_run)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
