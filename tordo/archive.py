import json
import re
from datetime import datetime
from pathlib import Path

from tordo.analysis import analyze_set_notes, format_markdown
from tordo.bridge_client import require_ok, send_request

DEFAULT_EXPORTS_DIR = Path("exports")


def export_archive(output_dir=None, host="127.0.0.1", port=8765, timeout=5.0, limit_per_clip=5000):
    capabilities_response = send_request("capabilities", host=host, port=port, timeout=timeout)
    capabilities = require_ok(capabilities_response, "capabilities")

    snapshot_response = send_request("snapshot", host=host, port=port, timeout=timeout)
    snapshot = require_ok(snapshot_response, "snapshot")

    set_notes_response = send_request(
        "set_notes",
        args={"limit_per_clip": limit_per_clip},
        host=host,
        port=port,
        timeout=timeout,
    )
    set_notes = require_ok(set_notes_response, "set_notes")
    analysis = analyze_set_notes(set_notes)

    archive_dir = Path(output_dir) if output_dir else default_archive_dir(set_notes)
    archive_dir.mkdir(parents=True, exist_ok=False)

    write_json(archive_dir / "capabilities.json", capabilities_response)
    write_json(archive_dir / "snapshot.json", snapshot_response)
    write_json(archive_dir / "set-notes.json", set_notes_response)
    write_json(archive_dir / "analysis.json", analysis)
    (archive_dir / "analysis.md").write_text(format_markdown(analysis))

    manifest = build_manifest(archive_dir, capabilities, snapshot, set_notes, analysis)
    write_json(archive_dir / "manifest.json", manifest)
    return archive_dir, manifest


def default_archive_dir(set_notes_payload):
    song = set_notes_payload.get("song") or {}
    name = song.get("name") or "untitled"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return DEFAULT_EXPORTS_DIR / ("%s-%s" % (slugify(name), timestamp))


def build_manifest(archive_dir, capabilities, snapshot, set_notes, analysis):
    song = set_notes.get("song") or {}
    return {
        "archive_version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "archive_dir": str(archive_dir),
        "song": {
            "name": song.get("name"),
            "tempo": song.get("tempo"),
            "signature_numerator": song.get("signature_numerator"),
            "signature_denominator": song.get("signature_denominator"),
        },
        "bridge": {
            "bridge_version": capabilities.get("bridge_version"),
            "protocol_version": capabilities.get("protocol_version"),
            "commands": capabilities.get("commands", []),
        },
        "counts": {
            "tracks": len(snapshot.get("tracks", [])),
            "scenes": len(snapshot.get("scenes", [])),
            "midi_clips": set_notes.get("midi_clip_count"),
            "total_notes": analysis.get("total_note_count"),
            "tonal_notes": analysis.get("tonal_note_count"),
            "bars": (analysis.get("timeline") or {}).get("bar_count"),
        },
        "estimated_key": analysis.get("estimated_key"),
        "files": {
            "capabilities": "capabilities.json",
            "snapshot": "snapshot.json",
            "set_notes": "set-notes.json",
            "analysis_json": "analysis.json",
            "analysis_md": "analysis.md",
        },
    }


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def slugify(value):
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or "untitled"
