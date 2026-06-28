import shutil
from importlib import resources
from pathlib import Path

REMOTE_SCRIPT_NAME = "TordoBridge"
DEFAULT_USER_LIBRARY = Path.home() / "Music" / "Ableton" / "User Library"
REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_REMOTE_SCRIPT = REPO_ROOT / "remote-script" / REMOTE_SCRIPT_NAME
PACKAGE_REMOTE_SCRIPT = ("remote_assets", REMOTE_SCRIPT_NAME)


def install_remote_script(target_user_library=None, dry_run=False):
    source = remote_script_source()
    target_user_library = Path(target_user_library or DEFAULT_USER_LIBRARY).expanduser()
    target = target_user_library / "Remote Scripts" / REMOTE_SCRIPT_NAME
    source_version = bridge_version(source)
    installed_version = bridge_version(target)

    report = {
        "ok": True,
        "dry_run": bool(dry_run),
        "source": str(source),
        "target": str(target),
        "source_version": source_version,
        "installed_version_before": installed_version,
        "actions": [],
        "manual_steps": [
            "Restart Ableton Live after installing or updating the Remote Script.",
            "In Live Settings -> Link, Tempo & MIDI, select TordoBridge as a Control Surface.",
            "Run tordo doctor again and continue only when installed and loaded bridge versions match.",
        ],
    }

    if not source_exists(source):
        report.update(
            {
                "ok": False,
                "error": {
                    "code": "remote_script_source_missing",
                    "message": "TordoBridge source was not found in the package or repository checkout.",
                },
            }
        )
        return report

    report["actions"].append("copy %s to %s" % (source, target))
    if dry_run:
        return report

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    copy_tree(source, target)
    report["installed_version_after"] = bridge_version(target)
    return report


def remote_script_source():
    if REPO_REMOTE_SCRIPT.exists():
        return REPO_REMOTE_SCRIPT
    package_root = resources.files("tordo")
    source = package_root
    for part in PACKAGE_REMOTE_SCRIPT:
        source = source.joinpath(part)
    return source


def source_bridge_version():
    return bridge_version(remote_script_source())


def bridge_version(source):
    bridge = source.joinpath("bridge.py")
    if not bridge.is_file():
        return None
    for line in bridge.read_text().splitlines():
        if line.startswith("BRIDGE_VERSION"):
            return line.split("=", 1)[1].strip().strip("\"'")
    return None


def source_exists(source):
    return source.joinpath("bridge.py").is_file()


def copy_tree(source, target):
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name == "__pycache__" or item.name.endswith((".pyc", ".pyo")):
            continue
        destination = target / item.name
        if item.is_dir():
            copy_tree(item, destination)
        else:
            destination.write_bytes(item.read_bytes())
