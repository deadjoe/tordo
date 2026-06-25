import argparse
import json
import subprocess
import sys
from pathlib import Path

from ableton_agent.bridge_client import DEFAULT_HOST, DEFAULT_PORT, BridgeConnectionError, send_request

DEFAULT_REMOTE_SCRIPT = Path.home() / "Music" / "Ableton" / "User Library" / "Remote Scripts" / "AbletonAgentBridge"


def print_response(response, compact=False):
    if compact:
        print(json.dumps(response, sort_keys=True, separators=(",", ":")))
    else:
        print(json.dumps(response, sort_keys=True, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description="CLI client for AbletonAgentBridge.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--timeout", default=5.0, type=float)
    parser.add_argument("--compact", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ping")
    subparsers.add_parser("capabilities")
    subparsers.add_parser("selected")
    notes_parser = subparsers.add_parser("selected-notes")
    notes_parser.add_argument("--limit", default=5000, type=int)
    notes_parser.add_argument("--diagnostic", action="store_true")

    clip_notes_parser = subparsers.add_parser("clip-notes")
    clip_notes_parser.add_argument("--track-index", required=True, type=int)
    clip_notes_parser.add_argument("--scene-index", required=True, type=int)
    clip_notes_parser.add_argument("--limit", default=5000, type=int)
    clip_notes_parser.add_argument("--diagnostic", action="store_true")

    set_notes_parser = subparsers.add_parser("set-notes")
    set_notes_parser.add_argument("--limit-per-clip", default=5000, type=int)

    browser_parser = subparsers.add_parser("browser-items")
    browser_parser.add_argument("--query", default="")
    browser_parser.add_argument("--exact", action="store_true")
    browser_parser.add_argument("--include-folders", action="store_true")
    browser_parser.add_argument("--root", action="append", dest="roots")
    browser_parser.add_argument("--max-depth", default=8, type=int)
    browser_parser.add_argument("--max-results", default=50, type=int)
    browser_parser.add_argument("--max-nodes", default=20000, type=int)

    subparsers.add_parser("snapshot")
    subparsers.add_parser("doctor")

    raw_parser = subparsers.add_parser("raw")
    raw_parser.add_argument("bridge_command")
    raw_parser.add_argument("--args-json", default="{}")

    args = parser.parse_args(argv)
    command = args.command
    request_args = {}

    if command == "raw":
        command = args.bridge_command
        request_args = json.loads(args.args_json)
    elif command == "selected-notes":
        command = "selected_notes"
        request_args = {"limit": args.limit, "diagnostic": args.diagnostic}
    elif command == "clip-notes":
        command = "clip_notes"
        request_args = {
            "track_index": args.track_index,
            "scene_index": args.scene_index,
            "limit": args.limit,
            "diagnostic": args.diagnostic,
        }
    elif command == "set-notes":
        command = "set_notes"
        request_args = {"limit_per_clip": args.limit_per_clip}
    elif command == "browser-items":
        command = "browser_items"
        request_args = {
            "query": args.query,
            "exact": args.exact,
            "loadable_only": not args.include_folders,
            "roots": args.roots,
            "max_depth": args.max_depth,
            "max_results": args.max_results,
            "max_nodes": args.max_nodes,
        }

    if command == "doctor":
        response = doctor(args.host, args.port, args.timeout)
        print_response(response, compact=args.compact)
        return 0 if response.get("ok") else 2

    try:
        response = send_request(
            command,
            args=request_args,
            host=args.host,
            port=args.port,
            timeout=args.timeout,
        )
    except BridgeConnectionError as exc:
        response = {
            "ok": False,
            "error": {
                "code": "connection_failed",
                "message": str(exc),
                "hint": (
                    "Restart Ableton Live, then select AbletonAgentBridge in "
                    "Settings -> Link, Tempo & MIDI -> Control Surface."
                ),
            },
        }
    print_response(response, compact=args.compact)
    return 0 if response.get("ok") else 2


def doctor(host, port, timeout):
    checks = {
        "remote_script_installed": DEFAULT_REMOTE_SCRIPT.exists(),
        "remote_script_path": str(DEFAULT_REMOTE_SCRIPT),
        "live_processes": live_processes(),
        "bridge_reachable": False,
        "ping": None,
    }
    try:
        response = send_request("ping", host=host, port=port, timeout=timeout)
        checks["bridge_reachable"] = response.get("ok", False)
        checks["ping"] = response
    except BridgeConnectionError as exc:
        checks["ping"] = {
            "ok": False,
            "error": {
                "code": "connection_failed",
                "message": str(exc),
            },
        }
    ok = checks["remote_script_installed"] and checks["bridge_reachable"]
    return {"ok": ok, "payload": checks}


def live_processes():
    try:
        result = subprocess.run(
            ["pgrep", "-fl", "Ableton Live"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


if __name__ == "__main__":
    sys.exit(main())
