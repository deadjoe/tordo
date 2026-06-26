import json
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

from tordo.archive import export_archive, write_json
from tordo.bridge_client import require_ok, send_request
from tordo.midi_import import (
    DEFAULT_NOTE_CHUNK_SIZE,
    layer_clip_name,
    layer_notes,
    layer_track_name,
    midi_file_context,
    midi_file_note_chunk_plans,
    midi_file_structure_plan,
)
from tordo.plan_preflight import prepare_plan_for_apply
from tordo.plans import write_plan
from tordo.project_cleanup import append_empty_project_track_cleanup, is_default_empty_track

HOLDER_TRACK_NAME = "Tordo Proof Hold"


def run_midi_import_proof(
    midi_path,
    prefix=None,
    scene_name=None,
    tempo=138.0,
    time_scale=0.5,
    note_chunk_size=DEFAULT_NOTE_CHUNK_SIZE,
    work_dir=None,
    export_out=None,
    replace_existing=False,
    allow_non_empty_project=False,
    overwrite=False,
    cleanup_empty_project_tracks=True,
    host="127.0.0.1",
    port=8765,
    timeout=180.0,
    limit_per_clip=20000,
):
    parsed, prefix, scene_name, layers, clip_length = midi_file_context(
        midi_path,
        prefix=prefix,
        scene_name=scene_name,
        time_scale=time_scale,
    )
    slug = slugify(prefix)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    work_root = Path(work_dir) if work_dir else Path("artifacts/tmp/proofs") / ("%s-%s" % (slug, stamp))
    archive_dir = Path(export_out) if export_out else Path("exports") / ("%s-proof-%s" % (slug, stamp))
    prepare_output_dir(work_root, overwrite=overwrite)
    if archive_dir.exists():
        if not overwrite:
            raise ValueError("export output already exists: %s" % archive_dir)
        shutil.rmtree(archive_dir)

    plans_dir = work_root / "plans"
    responses_dir = work_root / "responses"
    note_chunks_dir = plans_dir / "note-chunks"
    plans_dir.mkdir(parents=True, exist_ok=True)
    responses_dir.mkdir(parents=True, exist_ok=True)
    note_chunks_dir.mkdir(parents=True, exist_ok=True)

    expected_targets = midi_import_targets(prefix, scene_name, layers)
    initial_snapshot = get_snapshot(host, port, timeout)
    preflight_state = inspect_project_state(initial_snapshot, expected_targets)
    validate_project_state(
        preflight_state,
        replace_existing=replace_existing,
        allow_non_empty_project=allow_non_empty_project,
    )

    cleanup_report = None
    if preflight_state["target_tracks"] or preflight_state["target_scene"] is not None:
        cleanup_report = cleanup_existing_targets(
            initial_snapshot,
            expected_targets,
            responses_dir,
            host=host,
            port=port,
            timeout=timeout,
        )

    structure_plan = midi_file_structure_plan(
        midi_path,
        prefix=prefix,
        scene_name=scene_name,
        tempo=tempo,
        time_scale=time_scale,
    )
    note_plans = midi_file_note_chunk_plans(
        midi_path,
        prefix=prefix,
        scene_name=scene_name,
        time_scale=time_scale,
        note_chunk_size=note_chunk_size,
    )
    structure_plan["note_chunk_plan_count"] = len(note_plans)
    structure_plan["note_chunk_size"] = note_chunk_size
    structure_plan["note_chunk_dir"] = str(note_chunks_dir)

    structure_path = plans_dir / "structure-plan.json"
    write_plan(structure_path, structure_plan)
    note_plan_paths = write_note_chunk_plans(note_plans, note_chunks_dir)

    structure_response = apply_plan_to_live(
        structure_plan,
        prepared_path=plans_dir / "structure-prepared.json",
        response_path=responses_dir / "structure-apply.json",
        cleanup_empty_project_tracks=cleanup_empty_project_tracks and not (cleanup_report or {}).get("holder_created"),
        host=host,
        port=port,
        timeout=timeout,
    )

    holder_delete_response = None
    if cleanup_report and cleanup_report.get("holder_created"):
        holder_delete_response = delete_tracks_by_name_plan(
            [HOLDER_TRACK_NAME],
            responses_dir / "holder-delete.json",
            host=host,
            port=port,
            timeout=timeout,
        )

    note_responses = []
    for path, note_plan in zip(note_plan_paths, note_plans):
        response = apply_plan_to_live(
            note_plan,
            prepared_path=plans_dir / ("prepared-%s" % path.name),
            response_path=responses_dir / ("%s.response.json" % path.stem),
            cleanup_empty_project_tracks=False,
            host=host,
            port=port,
            timeout=timeout,
        )
        note_responses.append(chunk_response_summary(path, note_plan, response))

    archive_path, manifest = export_archive(
        output_dir=archive_dir,
        host=host,
        port=port,
        timeout=timeout,
        limit_per_clip=limit_per_clip,
    )
    verification = verify_midi_import_archive(
        archive_path,
        midi_path,
        prefix=prefix,
        scene_name=scene_name,
        time_scale=time_scale,
    )
    ok = verification["ok"]
    report = {
        "ok": ok,
        "proof": "midi-import",
        "midi_path": str(midi_path),
        "prefix": prefix,
        "scene_name": scene_name,
        "tempo": tempo,
        "time_scale": time_scale,
        "clip_length": clip_length,
        "work_dir": str(work_root),
        "archive_dir": str(archive_path),
        "structure_plan": str(structure_path),
        "note_chunk_dir": str(note_chunks_dir),
        "note_chunk_count": len(note_plans),
        "expected_targets": expected_targets,
        "preflight_state": preflight_state,
        "cleanup": cleanup_report,
        "holder_delete": response_summary(holder_delete_response) if holder_delete_response else None,
        "structure_apply": response_summary(structure_response),
        "note_chunks": note_responses,
        "manifest": manifest,
        "verification": verification,
    }
    write_json(work_root / "proof-report.json", report)
    write_proof_markdown(work_root / "proof-report.md", report)
    return report


def apply_plan_to_live(
    plan,
    prepared_path,
    response_path,
    cleanup_empty_project_tracks,
    host,
    port,
    timeout,
):
    snapshot = get_snapshot(host, port, timeout)
    prepared, preflight_report = prepare_plan_for_apply(plan, snapshot)
    cleanup_report = None
    if cleanup_empty_project_tracks:
        prepared, cleanup_report = append_empty_project_track_cleanup(prepared, snapshot)
    write_plan(prepared_path, prepared)
    response = send_request(
        "apply_plan",
        args={"plan": prepared, "dry_run": False},
        host=host,
        port=port,
        timeout=timeout,
    )
    require_ok(response, "apply_plan")
    if report_has_entries(preflight_report):
        response["client_preflight"] = preflight_report
        response["client_preflight"]["prepared_plan"] = str(prepared_path)
    if cleanup_report is not None and cleanup_report.get("applied"):
        response.setdefault("client_preflight", {})
        response["client_preflight"]["empty_project_track_cleanup"] = cleanup_report
        response["client_preflight"]["prepared_plan"] = str(prepared_path)
    write_json(response_path, response)
    return response


def cleanup_existing_targets(snapshot, expected_targets, responses_dir, host, port, timeout):
    stop_response = send_request(
        "apply_plan",
        args={
            "plan": {
                "plan_version": 1,
                "name": "proof-stop-live",
                "operations": [
                    {"type": "set_transport", "action": "stop_all_clips", "quantized": False},
                    {"type": "set_transport", "action": "stop"},
                ],
            },
            "dry_run": False,
        },
        host=host,
        port=port,
        timeout=timeout,
    )
    require_ok(stop_response, "apply_plan")
    write_json(responses_dir / "cleanup-stop-live.json", stop_response)

    target_tracks = [
        track for track in snapshot.get("tracks") or [] if track.get("name") in expected_targets["track_names"]
    ]
    holder_created = False
    if target_tracks and len(target_tracks) == len(snapshot.get("tracks") or []):
        holder_response = send_request(
            "apply_plan",
            args={
                "plan": {
                    "plan_version": 1,
                    "name": "proof-holder-track",
                    "operations": [
                        {
                            "id": "track.proof_hold",
                            "type": "create_midi_track",
                            "index": -1,
                            "name": HOLDER_TRACK_NAME,
                        }
                    ],
                },
                "dry_run": False,
            },
            host=host,
            port=port,
            timeout=timeout,
        )
        require_ok(holder_response, "apply_plan")
        write_json(responses_dir / "cleanup-holder-create.json", holder_response)
        holder_created = True

    track_delete_response = None
    if target_tracks:
        track_delete_response = delete_tracks_by_name_plan(
            [track.get("name") for track in target_tracks],
            responses_dir / "cleanup-delete-tracks.json",
            allow_non_empty=True,
            host=host,
            port=port,
            timeout=timeout,
        )

    scene_delete_response = None
    target_scene = find_scene(snapshot, expected_targets["scene_name"])
    if target_scene is not None:
        scene_plan = {
            "plan_version": 1,
            "name": "proof-delete-scene",
            "operations": [
                {
                    "type": "delete_scene",
                    "scene_index": target_scene.get("index"),
                    "expected_scene_name": target_scene.get("name"),
                    "allow_destructive": True,
                }
            ],
        }
        scene_delete_response = send_request(
            "apply_plan",
            args={"plan": scene_plan, "dry_run": False},
            host=host,
            port=port,
            timeout=timeout,
        )
        require_ok(scene_delete_response, "apply_plan")
        write_json(responses_dir / "cleanup-delete-scene.json", scene_delete_response)

    return {
        "holder_created": holder_created,
        "stopped_live": response_summary(stop_response),
        "deleted_tracks": response_summary(track_delete_response) if track_delete_response else None,
        "deleted_scene": response_summary(scene_delete_response) if scene_delete_response else None,
    }


def delete_tracks_by_name_plan(names, response_path, host, port, timeout, allow_non_empty=False):
    snapshot = get_snapshot(host, port, timeout)
    tracks = snapshot.get("tracks") or []
    targets = []
    for name in names:
        matches = [track for track in tracks if track.get("name") == name]
        if not matches:
            raise ValueError("no track named %r" % name)
        if len(matches) > 1:
            raise ValueError("track name %r is not unique" % name)
        track = matches[0]
        if not allow_non_empty and not is_empty_track(track):
            raise ValueError("refusing to delete non-empty track %r" % name)
        targets.append(track)
    plan = {
        "plan_version": 1,
        "name": "proof-delete-tracks",
        "operations": [
            {
                "type": "delete_track",
                "track_index": track.get("index"),
                "expected_track_name": track.get("name"),
                "allow_destructive": True,
            }
            for track in sorted(targets, key=lambda item: item.get("index"), reverse=True)
        ],
    }
    response = send_request(
        "apply_plan",
        args={"plan": plan, "dry_run": False},
        host=host,
        port=port,
        timeout=timeout,
    )
    require_ok(response, "apply_plan")
    write_json(response_path, response)
    return response


def verify_midi_import_archive(archive_dir, midi_path, prefix, scene_name, time_scale):
    parsed, prefix, scene_name, layers, _clip_length = midi_file_context(
        midi_path,
        prefix=prefix,
        scene_name=scene_name,
        time_scale=time_scale,
    )
    set_notes_response = json.loads((Path(archive_dir) / "set-notes.json").read_text())
    set_notes = require_ok(set_notes_response, "set_notes")
    clips = set_notes.get("clips") or []
    actual_by_target = {}
    for clip_payload in clips:
        track = clip_payload.get("track") or {}
        scene = clip_payload.get("scene") or {}
        clip = clip_payload.get("clip") or {}
        actual_by_target[(track.get("name"), scene.get("name"), clip.get("name"))] = clip_payload.get("notes") or []

    checks = []
    total_expected = 0
    total_actual = 0
    ok = True
    for layer in layers:
        track_name = layer_track_name(layer, prefix)
        clip_name = layer_clip_name(layer, prefix)
        expected_notes = layer_notes(parsed, layer, time_scale)
        actual_notes = actual_by_target.get((track_name, scene_name, clip_name), [])
        expected_counter = Counter(note_key(note) for note in expected_notes)
        actual_counter = Counter(note_key(note) for note in actual_notes)
        missing = sum((expected_counter - actual_counter).values())
        extra = sum((actual_counter - expected_counter).values())
        check_ok = missing == 0 and extra == 0
        ok = ok and check_ok
        total_expected += len(expected_notes)
        total_actual += len(actual_notes)
        checks.append(
            {
                "ok": check_ok,
                "track_name": track_name,
                "scene_name": scene_name,
                "clip_name": clip_name,
                "expected_notes": len(expected_notes),
                "actual_notes": len(actual_notes),
                "missing": missing,
                "extra": extra,
            }
        )
    return {
        "ok": ok,
        "total_expected_notes": total_expected,
        "total_actual_notes": total_actual,
        "clips": checks,
    }


def write_note_chunk_plans(note_plans, note_chunks_dir):
    paths = []
    for index, note_plan in enumerate(note_plans, start=1):
        note_filename = "%03d-%s-%05d.json" % (
            index,
            slugify(note_plan["layer"]),
            note_plan["chunk_note_offset"],
        )
        path = note_chunks_dir / note_filename
        write_plan(path, note_plan)
        paths.append(path)
    return paths


def write_proof_markdown(path, report):
    verification = report["verification"]
    lines = [
        "# MIDI Import Proof",
        "",
        "- OK: `%s`" % report["ok"],
        "- MIDI: `%s`" % report["midi_path"],
        "- Prefix: `%s`" % report["prefix"],
        "- Scene: `%s`" % report["scene_name"],
        "- Archive: `%s`" % report["archive_dir"],
        "- Note chunks: `%s`" % report["note_chunk_count"],
        "- Expected notes: `%s`" % verification["total_expected_notes"],
        "- Actual notes: `%s`" % verification["total_actual_notes"],
        "",
        "## Clips",
        "",
        "| Clip | Expected | Actual | Missing | Extra |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for item in verification["clips"]:
        lines.append(
            "| %s / %s | %s | %s | %s | %s |"
            % (
                item["track_name"],
                item["clip_name"],
                item["expected_notes"],
                item["actual_notes"],
                item["missing"],
                item["extra"],
            )
        )
    path.write_text("\n".join(lines) + "\n")


def inspect_project_state(snapshot, expected_targets):
    tracks = snapshot.get("tracks") or []
    target_tracks = [track_summary(track) for track in tracks if track.get("name") in expected_targets["track_names"]]
    non_target_tracks = [track for track in tracks if track.get("name") not in expected_targets["track_names"]]
    non_default_non_empty = [track_summary(track) for track in non_target_tracks if not is_default_empty_track(track)]
    return {
        "track_count": len(tracks),
        "target_tracks": target_tracks,
        "target_scene": scene_summary(find_scene(snapshot, expected_targets["scene_name"])),
        "non_default_non_empty_tracks": non_default_non_empty,
    }


def validate_project_state(state, replace_existing, allow_non_empty_project):
    if (state["target_tracks"] or state["target_scene"]) and not replace_existing:
        raise ValueError("target tracks or scene already exist; use --replace-existing to overwrite them")
    if state["non_default_non_empty_tracks"] and not allow_non_empty_project:
        names = [track["name"] for track in state["non_default_non_empty_tracks"]]
        raise ValueError("project is not empty enough for proof: %s" % ", ".join(names))


def prepare_output_dir(path, overwrite):
    if path.exists():
        if not overwrite:
            raise ValueError("work directory already exists: %s" % path)
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=False)


def midi_import_targets(prefix, scene_name, layers):
    return {
        "scene_name": scene_name,
        "track_names": [layer_track_name(layer, prefix) for layer in layers],
        "clip_names": [layer_clip_name(layer, prefix) for layer in layers],
    }


def get_snapshot(host, port, timeout):
    response = send_request("snapshot", host=host, port=port, timeout=timeout)
    return require_ok(response, "snapshot")


def report_has_entries(report):
    return any(report.get(key) for key in report)


def response_summary(response):
    if response is None:
        return None
    payload = response.get("payload") or {}
    return {
        "ok": response.get("ok", False),
        "plan_name": payload.get("plan_name"),
        "operation_count": payload.get("operation_count"),
    }


def chunk_response_summary(path, note_plan, response):
    operation = (response.get("payload") or {}).get("operations", [{}])[0]
    preflight = response.get("client_preflight") or {}
    return {
        "path": str(path),
        "layer": note_plan.get("layer"),
        "chunk_number": note_plan.get("chunk_number"),
        "chunk_note_offset": note_plan.get("chunk_note_offset"),
        "chunk_note_count": note_plan.get("chunk_note_count"),
        "ok": response.get("ok", False),
        "operation_count": (response.get("payload") or {}).get("operation_count"),
        "resolved_clips": len(preflight.get("resolved_clips") or []),
        "written_notes": operation.get("note_count"),
        "source": operation.get("source"),
    }


def track_summary(track):
    return {
        "index": track.get("index"),
        "name": track.get("name"),
        "clip_count": sum(1 for slot in track.get("clip_slots") or [] if slot.get("has_clip")),
        "device_count": len(track.get("devices") or []),
    }


def scene_summary(scene):
    if scene is None:
        return None
    return {
        "index": scene.get("index"),
        "name": scene.get("name"),
        "is_empty": scene.get("is_empty"),
    }


def find_scene(snapshot, name):
    for scene in snapshot.get("scenes") or []:
        if scene.get("name") == name:
            return scene
    return None


def is_empty_track(track):
    return not track_summary(track)["clip_count"] and not track.get("devices")


def note_key(note):
    return (
        int(note["pitch"]),
        round(float(note["start_time"]), 6),
        round(float(note["duration"]), 6),
        round(float(note.get("velocity", 0)), 3),
    )


def slugify(value):
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or "proof"
