import argparse
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "remote-script" / "TordoBridge"
DEFAULT_USER_LIBRARY = Path.home() / "Music" / "Ableton" / "User Library"


def install(target_root, dry_run=False):
    target_root = Path(target_root).expanduser()
    target = target_root / "Remote Scripts" / "TordoBridge"

    if not SOURCE.exists():
        raise SystemExit("source remote script missing: %s" % SOURCE)

    print("source: %s" % SOURCE)
    print("target: %s" % target)

    if dry_run:
        print("dry run: no files copied")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    print("installed")
    print("restart Ableton Live, then select TordoBridge as a Control Surface.")


def main():
    parser = argparse.ArgumentParser(description="Install TordoBridge into the User Library.")
    parser.add_argument("--target-user-library", default=str(DEFAULT_USER_LIBRARY))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    install(args.target_user_library, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
