from pathlib import Path

ARTIFACTS_DIR = Path("artifacts")
TMP_DIR = ARTIFACTS_DIR / "tmp"


def tmp_path(filename):
    return str(TMP_DIR / filename)


def ensure_parent(path):
    path = Path(path)
    parent = path.parent
    if parent != Path("."):
        parent.mkdir(parents=True, exist_ok=True)
    return path
