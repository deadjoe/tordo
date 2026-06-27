import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from tordo.bridge_client import BridgeConnectionError, BridgeResponseError, require_ok, send_request
from tordo.plan_preflight import prepare_plan_for_apply

DEFAULT_OUT_ROOT = Path("artifacts/tmp/real-set-validation")
MISSING_BROWSER_NAME = "Definitely Missing Tordo Rack 20260628.adg"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate the agent contract against the currently open Live Set.")
    parser.add_argument("--out", help="Output directory for JSON and Markdown evidence.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--timeout", default=60.0, type=float)
    parser.add_argument("--limit-per-clip", default=5000, type=int)
    args = parser.parse_args(argv)

    out_dir = Path(args.out) if args.out else default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=False)

    report = {
        "report_version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "out_dir": str(out_dir),
        "checks": [],
    }

    try:
        capabilities_response = send_request("capabilities", host=args.host, port=args.port, timeout=args.timeout)
        capabilities = require_ok(capabilities_response, "capabilities")
        snapshot_response = send_request("snapshot", host=args.host, port=args.port, timeout=args.timeout)
        snapshot = require_ok(snapshot_response, "snapshot")
        set_notes_response = send_request(
            "set_notes",
            args={"limit_per_clip": args.limit_per_clip},
            host=args.host,
            port=args.port,
            timeout=args.timeout,
        )
        set_notes = require_ok(set_notes_response, "set_notes")
    except (BridgeConnectionError, BridgeResponseError) as exc:
        report["ok"] = False
        report["fatal_error"] = str(exc)
        write_json(out_dir / "report.json", report)
        (out_dir / "report.md").write_text(format_report(report))
        raise

    write_json(out_dir / "capabilities.json", capabilities_response)
    write_json(out_dir / "snapshot.json", snapshot_response)
    write_json(out_dir / "set-notes.json", set_notes_response)

    profile = profile_set(snapshot, set_notes, capabilities)
    report["bridge"] = {
        "bridge_version": capabilities.get("bridge_version"),
        "protocol_version": capabilities.get("protocol_version"),
    }
    report["song"] = profile["song"]
    report["profile"] = profile

    add_basic_profile_checks(report, profile)
    run_preflight_refusal_checks(report, snapshot, profile)
    run_dry_run_checks(report, snapshot, args.host, args.port, args.timeout)

    report["ok"] = not any(check["status"] == "failed" for check in report["checks"])
    report["summary"] = summarize_checks(report["checks"])
    write_json(out_dir / "report.json", report)
    (out_dir / "report.md").write_text(format_report(report))

    print("wrote %s" % out_dir)
    print(
        json.dumps(
            {"ok": report["ok"], "summary": report["summary"], "out_dir": str(out_dir)},
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["ok"] else 1


def default_out_dir():
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return DEFAULT_OUT_ROOT / timestamp


def profile_set(snapshot, set_notes, capabilities):
    tracks = snapshot.get("tracks") or []
    scenes = snapshot.get("scenes") or []
    return_tracks = snapshot.get("return_tracks") or []
    song = snapshot.get("song") or {}
    clip_counts = count_snapshot_clips(tracks)
    duplicate_tracks = duplicate_named_items(tracks)
    duplicate_return_tracks = duplicate_named_items(return_tracks)
    duplicate_scenes = duplicate_named_items(scenes)
    duplicate_clips = duplicate_clip_names(tracks, scenes)
    foldable_tracks = [track_summary(track) for track in tracks if track.get("is_foldable")]
    return {
        "song": {
            "name": song.get("name"),
            "tempo": song.get("tempo"),
            "signature_numerator": song.get("signature_numerator"),
            "signature_denominator": song.get("signature_denominator"),
        },
        "bridge_command_count": len(capabilities.get("commands") or []),
        "counts": {
            "tracks": len(tracks),
            "return_tracks": len(return_tracks),
            "scenes": len(scenes),
            "foldable_tracks": len(foldable_tracks),
            "snapshot_clips": clip_counts["total"],
            "snapshot_midi_clips": clip_counts["midi"],
            "snapshot_audio_clips": clip_counts["audio"],
            "set_notes_midi_clips": set_notes.get("midi_clip_count"),
        },
        "duplicates": {
            "tracks": duplicate_tracks,
            "return_tracks": duplicate_return_tracks,
            "scenes": duplicate_scenes,
            "same_track_clips": duplicate_clips,
        },
        "coverage": {
            "has_named_song": bool(song.get("name")),
            "has_duplicate_tracks": bool(duplicate_tracks),
            "has_duplicate_scenes": bool(duplicate_scenes),
            "has_duplicate_same_track_clips": bool(duplicate_clips),
            "has_midi_clips": clip_counts["midi"] > 0,
            "has_audio_clips": clip_counts["audio"] > 0,
            "has_foldable_tracks": bool(foldable_tracks),
            "has_return_tracks": bool(return_tracks),
        },
        "foldable_tracks": foldable_tracks,
    }


def count_snapshot_clips(tracks):
    counts = {"total": 0, "midi": 0, "audio": 0}
    for track in tracks:
        for slot in track.get("clip_slots") or []:
            clip = slot.get("clip")
            if not clip:
                continue
            counts["total"] += 1
            if clip.get("is_midi_clip"):
                counts["midi"] += 1
            if clip.get("is_audio_clip"):
                counts["audio"] += 1
    return counts


def duplicate_named_items(items):
    by_name = defaultdict(list)
    for item in items:
        name = item.get("name")
        if name:
            by_name[name].append(item.get("index"))
    return {name: indexes for name, indexes in sorted(by_name.items()) if len(indexes) > 1}


def duplicate_clip_names(tracks, scenes):
    results = []
    scene_names = {scene.get("index"): scene.get("name") for scene in scenes}
    for track in tracks:
        by_name = defaultdict(list)
        for slot in track.get("clip_slots") or []:
            clip = slot.get("clip")
            if clip and clip.get("name"):
                by_name[clip.get("name")].append(
                    {
                        "scene_index": slot.get("index"),
                        "scene_name": scene_names.get(slot.get("index")),
                    }
                )
        for clip_name, matches in sorted(by_name.items()):
            if len(matches) > 1:
                results.append(
                    {
                        "track_index": track.get("index"),
                        "track_name": track.get("name"),
                        "clip_name": clip_name,
                        "matches": matches,
                    }
                )
    return results


def track_summary(track):
    return {"index": track.get("index"), "name": track.get("name"), "is_foldable": track.get("is_foldable")}


def add_basic_profile_checks(report, profile):
    coverage = profile["coverage"]
    add_check(report, "bridge_snapshot_read", "passed", "snapshot and set_notes were read successfully")
    for key in [
        "has_duplicate_tracks",
        "has_duplicate_scenes",
        "has_duplicate_same_track_clips",
        "has_midi_clips",
        "has_audio_clips",
        "has_foldable_tracks",
    ]:
        status = "passed" if coverage.get(key) else "skipped"
        add_check(report, "coverage_%s" % key, status, coverage_message(key, coverage.get(key)))


def coverage_message(key, present):
    if present:
        return "%s is present in the current Set" % key
    return "%s is not present in the current Set; open a richer real song Set to cover this case" % key


def run_preflight_refusal_checks(report, snapshot, profile):
    duplicates = profile["duplicates"]
    duplicate_tracks = duplicates["tracks"]
    if duplicate_tracks:
        name = next(iter(duplicate_tracks))
        expect_preflight_refusal(
            report,
            snapshot,
            "duplicate_track_name_refusal",
            {
                "plan_version": 1,
                "name": "real-set-validation-duplicate-track-name-refusal",
                "operations": [
                    {"type": "set_track_mixer", "track_selector": {"name": name}, "volume": 0.5}
                ],
            },
            "not unique",
        )
    else:
        add_check(report, "duplicate_track_name_refusal", "skipped", "no duplicate non-empty track names found")

    duplicate_scenes = duplicates["scenes"]
    if duplicate_scenes:
        name = next(iter(duplicate_scenes))
        expect_preflight_refusal(
            report,
            snapshot,
            "duplicate_scene_name_refusal",
            {
                "plan_version": 1,
                "name": "real-set-validation-duplicate-scene-name-refusal",
                "operations": [{"type": "fire_scene", "scene_selector": {"name": name}}],
            },
            "not unique",
        )
    else:
        add_check(report, "duplicate_scene_name_refusal", "skipped", "no duplicate non-empty scene names found")

    duplicate_clips = duplicates["same_track_clips"]
    if duplicate_clips:
        target = duplicate_clips[0]
        expect_preflight_refusal(
            report,
            snapshot,
            "duplicate_clip_without_scene_context_refusal",
            {
                "plan_version": 1,
                "name": "real-set-validation-duplicate-clip-refusal",
                "operations": [
                    {
                        "type": "quantize_clip",
                        "track_selector": {
                            "index": target["track_index"],
                            "expected_name": target["track_name"],
                        },
                        "clip_selector": {"name": target["clip_name"]},
                        "quantization_grid": 5,
                    }
                ],
            },
            "not unique",
        )
    else:
        add_check(report, "duplicate_clip_without_scene_context_refusal", "skipped", "no duplicate clip names found")


def expect_preflight_refusal(report, snapshot, name, plan, expected_text):
    try:
        prepare_plan_for_apply(plan, snapshot)
    except ValueError as exc:
        message = str(exc)
        if expected_text in message:
            add_check(report, name, "passed", message)
        else:
            add_check(report, name, "failed", message)
        return
    add_check(report, name, "failed", "preflight accepted a plan that should have been refused")


def run_dry_run_checks(report, snapshot, host, port, timeout):
    track = first_track(snapshot)
    scene = first_scene(snapshot)
    midi_clip = first_midi_clip(snapshot)

    if track:
        volume = (((track.get("mixer") or {}).get("volume") or {}).get("value")) or 0.85
        run_bridge_dry_run(
            report,
            snapshot,
            "structured_track_position_dry_run",
            {
                "plan_version": 1,
                "name": "real-set-validation-track-position-dry-run",
                "operations": [
                    {
                        "type": "set_track_mixer",
                        "track_selector": {"index": track["index"], "expected_name": track["name"]},
                        "volume": volume,
                    }
                ],
            },
            host,
            port,
            timeout,
        )
        run_bridge_guard_refusal(
            report,
            "bridge_expected_track_name_guard_refusal",
            {
                "plan_version": 1,
                "name": "real-set-validation-expected-track-name-guard",
                "operations": [
                    {
                        "type": "set_track_mixer",
                        "track_index": track["index"],
                        "expected_track_name": wrong_expected_name(track["name"]),
                        "volume": volume,
                    }
                ],
            },
            host,
            port,
            timeout,
        )
        run_bridge_dry_run(
            report,
            snapshot,
            "missing_browser_item_dry_run_refusal",
            {
                "plan_version": 1,
                "name": "real-set-validation-missing-browser-item",
                "operations": [
                    {
                        "type": "load_browser_item",
                        "track_selector": {"index": track["index"], "expected_name": track["name"]},
                        "browser_name": MISSING_BROWSER_NAME,
                        "browser_exact": True,
                        "browser_max_depth": 8,
                        "browser_max_results": 4,
                    }
                ],
            },
            host,
            port,
            timeout,
            expected_bridge_error="not_found",
        )
    else:
        add_check(report, "structured_track_position_dry_run", "skipped", "no regular track found")
        add_check(report, "bridge_expected_track_name_guard_refusal", "skipped", "no regular track found")
        add_check(report, "missing_browser_item_dry_run_refusal", "skipped", "no regular track found")

    if scene:
        run_bridge_dry_run(
            report,
            snapshot,
            "structured_scene_position_dry_run",
            {
                "plan_version": 1,
                "name": "real-set-validation-scene-position-dry-run",
                "operations": [
                    {"type": "fire_scene", "scene_selector": {"index": scene["index"], "expected_name": scene["name"]}}
                ],
            },
            host,
            port,
            timeout,
        )
        run_bridge_guard_refusal(
            report,
            "bridge_expected_scene_name_guard_refusal",
            {
                "plan_version": 1,
                "name": "real-set-validation-expected-scene-name-guard",
                "operations": [
                    {
                        "type": "fire_scene",
                        "scene_index": scene["index"],
                        "expected_scene_name": wrong_expected_name(scene["name"]),
                    }
                ],
            },
            host,
            port,
            timeout,
        )
    else:
        add_check(report, "structured_scene_position_dry_run", "skipped", "no scene found")
        add_check(report, "bridge_expected_scene_name_guard_refusal", "skipped", "no scene found")

    if midi_clip:
        run_bridge_dry_run(
            report,
            snapshot,
            "structured_clip_scene_context_dry_run",
            {
                "plan_version": 1,
                "name": "real-set-validation-clip-scene-context-dry-run",
                "operations": [
                    {
                        "type": "quantize_clip",
                        "track_selector": {
                            "index": midi_clip["track_index"],
                            "expected_name": midi_clip["track_name"],
                        },
                        "scene_selector": {
                            "index": midi_clip["scene_index"],
                            "expected_name": midi_clip["scene_name"],
                        },
                        "clip_selector": {"name": midi_clip["clip_name"]},
                        "quantization_grid": 5,
                    }
                ],
            },
            host,
            port,
            timeout,
        )
        run_bridge_guard_refusal(
            report,
            "bridge_expected_clip_name_guard_refusal",
            {
                "plan_version": 1,
                "name": "real-set-validation-expected-clip-name-guard",
                "operations": [
                    {
                        "type": "quantize_clip",
                        "track_index": midi_clip["track_index"],
                        "expected_track_name": midi_clip["track_name"],
                        "scene_index": midi_clip["scene_index"],
                        "expected_scene_name": midi_clip["scene_name"],
                        "expected_clip_name": wrong_expected_name(midi_clip["clip_name"]),
                        "quantization_grid": 5,
                    }
                ],
            },
            host,
            port,
            timeout,
        )
    else:
        add_check(report, "structured_clip_scene_context_dry_run", "skipped", "no MIDI clip found")
        add_check(report, "bridge_expected_clip_name_guard_refusal", "skipped", "no MIDI clip found")


def run_bridge_dry_run(report, snapshot, name, plan, host, port, timeout, expected_bridge_error=None):
    try:
        prepared, preflight_report = prepare_plan_for_apply(plan, snapshot)
    except ValueError as exc:
        add_check(report, name, "failed", "preflight refused unexpectedly: %s" % exc)
        return

    response = send_request(
        "apply_plan",
        args={"plan": prepared, "dry_run": True},
        host=host,
        port=port,
        timeout=timeout,
    )
    if expected_bridge_error:
        if not response.get("ok") and (response.get("error") or {}).get("code") == expected_bridge_error:
            add_check(
                report,
                name,
                "passed",
                "%s: %s" % (expected_bridge_error, (response.get("error") or {}).get("message")),
                {"client_preflight": preflight_report},
            )
        else:
            add_check(report, name, "failed", "expected bridge error %s, got %s" % (expected_bridge_error, response))
        return

    if response.get("ok"):
        add_check(
            report,
            name,
            "passed",
            "bridge dry-run accepted %s operation(s)" % len(prepared.get("operations") or []),
            {"client_preflight": preflight_report, "bridge_payload": response.get("payload")},
        )
    else:
        add_check(report, name, "failed", json.dumps(response.get("error") or response, sort_keys=True))


def run_bridge_guard_refusal(report, name, plan, host, port, timeout):
    response = send_request(
        "apply_plan",
        args={"plan": plan, "dry_run": True},
        host=host,
        port=port,
        timeout=timeout,
    )
    error = response.get("error") or {}
    if not response.get("ok") and error.get("code") == "bad_plan" and "Expected" in (error.get("message") or ""):
        add_check(report, name, "passed", "%s: %s" % (error.get("code"), error.get("message")))
        return
    add_check(report, name, "failed", "expected bridge expected-name guard refusal, got %s" % response)


def wrong_expected_name(actual_name):
    return "__tordo_expected_name_mismatch__%s" % (actual_name or "unnamed")


def first_track(snapshot):
    tracks = snapshot.get("tracks") or []
    return tracks[0] if tracks else None


def first_scene(snapshot):
    scenes = snapshot.get("scenes") or []
    return scenes[0] if scenes else None


def first_midi_clip(snapshot):
    scenes = {scene.get("index"): scene for scene in snapshot.get("scenes") or []}
    for track in snapshot.get("tracks") or []:
        for slot in track.get("clip_slots") or []:
            clip = slot.get("clip")
            if clip and clip.get("is_midi_clip"):
                scene = scenes.get(slot.get("index")) or {}
                return {
                    "track_index": track.get("index"),
                    "track_name": track.get("name"),
                    "scene_index": slot.get("index"),
                    "scene_name": scene.get("name"),
                    "clip_name": clip.get("name"),
                }
    return None


def add_check(report, name, status, message, details=None):
    check = {"name": name, "status": status, "message": message}
    if details is not None:
        check["details"] = details
    report["checks"].append(check)


def summarize_checks(checks):
    summary = {"passed": 0, "failed": 0, "skipped": 0}
    for check in checks:
        summary[check["status"]] += 1
    return summary


def format_report(report):
    lines = ["# Real Set Contract Validation", ""]
    if report.get("fatal_error"):
        lines.extend(["Fatal error: `%s`" % report["fatal_error"], ""])
        return "\n".join(lines)

    lines.extend(
        [
            "- Created at: `%s`" % report.get("created_at"),
            "- Bridge: `%s`" % ((report.get("bridge") or {}).get("bridge_version")),
            "- Song: `%s`" % ((report.get("song") or {}).get("name") or ""),
            "",
            "## Profile",
            "",
        ]
    )
    counts = ((report.get("profile") or {}).get("counts")) or {}
    for key in sorted(counts):
        lines.append("- %s: `%s`" % (key, counts[key]))
    lines.append("")

    coverage = ((report.get("profile") or {}).get("coverage")) or {}
    lines.extend(["## Coverage", ""])
    for key in sorted(coverage):
        lines.append("- %s: `%s`" % (key, coverage[key]))
    lines.append("")

    lines.extend(["## Checks", "", "| Check | Status | Message |", "| --- | --- | --- |"])
    for check in report.get("checks") or []:
        lines.append(
            "| `%s` | `%s` | %s |"
            % (check.get("name"), check.get("status"), markdown_escape(check.get("message") or ""))
        )
    lines.append("")

    lines.extend(
        [
            "## Interpretation",
            "",
            "This harness is read-only plus bridge dry-run. It validates contract behavior against the "
            "currently open Set but does not prove durable object identity.",
            "Skipped coverage means the current Set does not contain that real-project feature; "
            "open a richer song Set and rerun the same command.",
            "",
        ]
    )
    return "\n".join(lines)


def markdown_escape(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
