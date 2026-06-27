import ast
import glob
import json
import platform
import plistlib
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from tordo.bridge_client import DEFAULT_HOST, DEFAULT_PORT, BridgeConnectionError, send_request

MINIMUM_LIVE_VERSION = "12.4"
EXPECTED_BRIDGE_VERSION = "0.8.0"
DEFAULT_REMOTE_SCRIPT = Path.home() / "Music" / "Ableton" / "User Library" / "Remote Scripts" / "TordoBridge"
REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_BRIDGE = REPO_ROOT / "remote-script" / "TordoBridge" / "bridge.py"


def doctor_report(
    host=DEFAULT_HOST,
    port=DEFAULT_PORT,
    timeout=5.0,
    live_app=None,
    remote_script=None,
    minimum_live_version=MINIMUM_LIVE_VERSION,
):
    checks = []
    add_check(checks, "host_os", platform.system() == "Darwin", "macOS is the current supported host OS")
    add_cli_check(checks)
    add_ableton_check(checks, live_app, minimum_live_version)
    add_remote_script_check(checks, remote_script)
    bridge_payload = add_bridge_checks(checks, host, port, timeout)

    summary = summarize_checks(checks)
    return {
        "ok": summary["failed"] == 0,
        "summary": summary,
        "checks": checks,
        "runtime": {
            "host": host,
            "port": port,
            "bridge_payload": bridge_payload,
        },
    }


def add_cli_check(checks):
    executable = shutil.which("tordo")
    add_check(
        checks,
        "tordo_cli_importable",
        True,
        "tordo Python package is importable",
        {
            "version": package_version("tordo"),
            "python": sys.version.split()[0],
            "module": str(Path(__file__).resolve()),
        },
    )
    add_check(
        checks,
        "python_version",
        sys.version_info >= (3, 11),
        "Python version must be >= 3.11",
        {"version": sys.version.split()[0], "minimum_version": "3.11"},
    )
    add_check(
        checks,
        "tordo_cli_on_path",
        bool(executable),
        "tordo CLI should be available on PATH",
        {"path_executable": executable},
    )


def package_version(package_name):
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return None


def add_ableton_check(checks, live_app, minimum_live_version):
    apps = [inspect_live_app(Path(live_app))] if live_app else find_live_apps()
    apps = [app for app in apps if app is not None]
    if not apps:
        add_check(
            checks,
            "ableton_live_installed",
            False,
            "Ableton Live app was not found in /Applications",
            {"minimum_version": minimum_live_version},
        )
        return

    apps.sort(key=lambda app: app.get("version_tuple") or (), reverse=True)
    selected = apps[0]
    add_check(
        checks,
        "ableton_live_installed",
        True,
        "Ableton Live app found",
        {"selected": public_live_app(selected), "candidates": [public_live_app(app) for app in apps]},
    )
    add_check(
        checks,
        "ableton_live_version",
        version_at_least(selected.get("version"), minimum_live_version),
        "Ableton Live version must be >= %s" % minimum_live_version,
        {"version": selected.get("version"), "minimum_version": minimum_live_version},
    )


def find_live_apps():
    return [inspect_live_app(Path(path)) for path in glob.glob("/Applications/Ableton Live*.app")]


def inspect_live_app(path):
    info_path = path / "Contents" / "Info.plist"
    if not path.exists() or not info_path.exists():
        return None
    try:
        with info_path.open("rb") as handle:
            info = plistlib.load(handle)
    except Exception:
        info = {}
    version = info.get("CFBundleShortVersionString") or info.get("CFBundleVersion")
    return {
        "path": str(path),
        "name": info.get("CFBundleName") or path.name,
        "version": version,
        "version_tuple": version_tuple(version),
    }


def public_live_app(app):
    return {"path": app.get("path"), "name": app.get("name"), "version": app.get("version")}


def add_remote_script_check(checks, remote_script):
    remote_script_path = Path(remote_script).expanduser() if remote_script else DEFAULT_REMOTE_SCRIPT
    bridge_path = remote_script_path / "bridge.py"
    installed_version = bridge_version_from_source(bridge_path)
    expected_version = bridge_version_from_source(SOURCE_BRIDGE) or EXPECTED_BRIDGE_VERSION
    add_check(
        checks,
        "remote_script_installed",
        bridge_path.exists(),
        "TordoBridge Remote Script must be installed in the Ableton User Library",
        {"path": str(remote_script_path), "bridge_py": str(bridge_path), "installed_version": installed_version},
    )
    if bridge_path.exists():
        add_check(
            checks,
            "remote_script_version",
            installed_version == expected_version,
            "Installed TordoBridge version must match this tordo package",
            {"installed_version": installed_version, "expected_version": expected_version},
        )


def bridge_version_from_source(path):
    path = Path(path)
    if not path.exists():
        return None
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "BRIDGE_VERSION":
                    return constant_value(node.value)
    return None


def constant_value(node):
    if isinstance(node, ast.Constant):
        return node.value
    return None


def add_bridge_checks(checks, host, port, timeout):
    live_processes = live_processes_payload()
    add_check(
        checks,
        "ableton_live_running",
        bool(live_processes["live_processes"]),
        "Ableton Live process should be running for runtime control",
        live_processes,
    )
    try:
        ping = send_request("ping", host=host, port=port, timeout=timeout)
    except BridgeConnectionError as exc:
        add_check(
            checks,
            "bridge_reachable",
            False,
            "TordoBridge ping failed",
            {"host": host, "port": port, "error": str(exc)},
        )
        add_check(
            checks,
            "control_surface_selected",
            False,
            "TordoBridge Control Surface cannot be confirmed unless bridge ping succeeds",
        )
        return None

    bridge_ok = bool(ping.get("ok"))
    add_check(checks, "bridge_reachable", bridge_ok, "TordoBridge ping must succeed", ping)
    add_check(
        checks,
        "control_surface_selected",
        bridge_ok,
        "Control Surface selection is inferred from a reachable TordoBridge socket",
    )
    if not bridge_ok:
        return ping

    payload = ping.get("payload") or {}
    expected_version = bridge_version_from_source(SOURCE_BRIDGE) or EXPECTED_BRIDGE_VERSION
    add_check(
        checks,
        "bridge_version",
        payload.get("bridge_version") == expected_version,
        "Loaded TordoBridge version must match this tordo package",
        {"loaded_version": payload.get("bridge_version"), "expected_version": expected_version},
    )
    capabilities = send_request("capabilities", host=host, port=port, timeout=timeout)
    capabilities_ok = bool(capabilities.get("ok"))
    capability_payload = capabilities.get("payload") or {}
    add_check(
        checks,
        "bridge_capabilities",
        capabilities_ok and bool(capability_payload.get("plan_operations")),
        "Bridge capabilities must expose plan operations",
        capabilities,
    )
    return {"ping": ping, "capabilities": capabilities}


def live_processes_payload():
    try:
        result = subprocess.run(
            ["pgrep", "-fl", "Ableton Live"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        return {"processes": [], "live_processes": [], "error": str(exc)}
    processes = [line for line in result.stdout.splitlines() if line.strip()]
    live_processes = [line for line in processes if "Contents/MacOS/Live" in line]
    return {"processes": processes, "live_processes": live_processes}


def add_check(checks, name, ok, message, details=None):
    check = {"name": name, "status": "passed" if ok else "failed", "message": message}
    if details is not None:
        check["details"] = details
    checks.append(check)


def summarize_checks(checks):
    summary = {"passed": 0, "failed": 0}
    for check in checks:
        summary[check["status"]] += 1
    return summary


def version_at_least(version, minimum_version):
    parsed = version_tuple(version)
    minimum = version_tuple(minimum_version)
    if not parsed or not minimum:
        return False
    return parsed >= minimum


def version_tuple(version):
    if not version:
        return ()
    parts = []
    current = ""
    for char in str(version):
        if char.isdigit():
            current += char
        elif char == "." and current:
            parts.append(int(current))
            current = ""
        else:
            break
    if current:
        parts.append(int(current))
    return tuple(parts)


def dumps_report(report, compact=False):
    if compact:
        return json.dumps(report, sort_keys=True, separators=(",", ":"))
    return json.dumps(report, indent=2, sort_keys=True)
