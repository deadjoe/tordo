import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"
REMOTE_BRIDGE_IN_WHEEL = "tordo/remote_assets/TordoBridge/bridge.py"


def main():
    wheel = single_file("*.whl")
    sdist = single_file("*.tar.gz")
    check_wheel_contains_remote_script(wheel)
    check_wheel_installs_and_runs(wheel)
    print(
        json.dumps(
            {
                "ok": True,
                "wheel": str(wheel),
                "sdist": str(sdist),
                "checked": [
                    "wheel_contains_remote_script",
                    "wheel_installs_in_clean_venv",
                    "installed_cli_runs_schema",
                    "installed_cli_installs_remote_script_to_temp_user_library",
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


def single_file(pattern):
    matches = sorted(DIST_DIR.glob(pattern))
    if len(matches) != 1:
        raise SystemExit("expected exactly one %s in %s, found %s" % (pattern, DIST_DIR, len(matches)))
    return matches[0]


def check_wheel_contains_remote_script(wheel):
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    if REMOTE_BRIDGE_IN_WHEEL not in names:
        raise SystemExit("wheel missing %s" % REMOTE_BRIDGE_IN_WHEEL)


def check_wheel_installs_and_runs(wheel):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        venv_path = tmp_path / "venv"
        user_library = tmp_path / "user-library"
        run([sys.executable, "-m", "venv", str(venv_path)])
        python = venv_executable(venv_path, "python")
        tordo = venv_executable(venv_path, "tordo")
        run([str(python), "-m", "pip", "install", "--quiet", str(wheel)])
        run([str(tordo), "schema"], stdout=subprocess.DEVNULL)
        install = run(
            [
                str(tordo),
                "install-remote-script",
                "--target-user-library",
                str(user_library),
                "--compact",
            ],
            capture_output=True,
        )
        payload = json.loads(install.stdout)
        if not payload.get("ok"):
            raise SystemExit("install-remote-script returned not ok: %s" % install.stdout)
        installed_bridge = user_library / "Remote Scripts" / "TordoBridge" / "bridge.py"
        if not installed_bridge.exists():
            raise SystemExit("install-remote-script did not copy bridge.py to %s" % installed_bridge)


def venv_executable(venv_path, name):
    if sys.platform == "win32":
        suffix = ".exe" if name != "python" else ".exe"
        return venv_path / "Scripts" / ("%s%s" % (name, suffix))
    return venv_path / "bin" / name


def run(command, stdout=None, capture_output=False):
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture_output else stdout,
        stderr=subprocess.PIPE if capture_output else None,
    )


if __name__ == "__main__":
    main()
