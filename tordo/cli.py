import argparse
import json
import sys
from pathlib import Path

from tordo.analysis import analyze_set_notes, format_markdown, load_set_notes
from tordo.archive import export_archive
from tordo.bridge_client import BridgeConnectionError, BridgeResponseError, require_ok, send_request
from tordo.client import main as bridge_main
from tordo.diff import diff_archives, write_diff_markdown
from tordo.midi_import import (
    DEFAULT_NOTE_CHUNK_SIZE,
    midi_file_note_chunk_plans,
    midi_file_plan,
    midi_file_structure_plan,
)
from tordo.paths import ensure_parent, tmp_path
from tordo.plan_preflight import prepare_plan_for_apply
from tordo.plans import (
    demo_melody_plan,
    device_insertion_proof_plan,
    device_parameter_proof_plan,
    eurodance_sketch_plan,
    load_plan,
    mini_arrangement_plan,
    mixer_adjust_proof_plan,
    mixer_proof_plan,
    note_metadata_proof_plan,
    section_variation_plan,
    track_note_edit_proof_plan,
    write_plan,
)
from tordo.project_cleanup import append_empty_project_track_cleanup
from tordo.schema import agent_plan_schema
from tordo.verification import (
    verify_device_parameters,
    verify_note_edit,
    verify_note_metadata,
    verify_track_mixer,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tordo CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export the current Live Set into an archive directory.")
    export_parser.add_argument("--out")
    export_parser.add_argument("--host", default="127.0.0.1")
    export_parser.add_argument("--port", default=8765, type=int)
    export_parser.add_argument("--timeout", default=5.0, type=float)
    export_parser.add_argument("--limit-per-clip", default=5000, type=int)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze a set-notes JSON file.")
    analyze_parser.add_argument("input", nargs="?", default=tmp_path("set-notes.json"))
    analyze_parser.add_argument("--json-out", default=tmp_path("set-analysis.json"))
    analyze_parser.add_argument("--md-out", default=tmp_path("set-analysis.md"))

    diff_parser = subparsers.add_parser("diff", help="Diff two export archive directories.")
    diff_parser.add_argument("before")
    diff_parser.add_argument("after")
    diff_parser.add_argument("--json-out", default=tmp_path("archive-diff.json"))
    diff_parser.add_argument("--md-out", default=tmp_path("archive-diff.md"))

    subparsers.add_parser("schema", help="Print the agent-facing plan selector schema.")

    browser_parser = subparsers.add_parser("browser-items", help="Search Live Browser items through the bridge.")
    browser_parser.add_argument("--query", default="")
    browser_parser.add_argument("--exact", action="store_true")
    browser_parser.add_argument("--include-folders", action="store_true")
    browser_parser.add_argument("--root", action="append", dest="roots")
    browser_parser.add_argument("--max-depth", default=8, type=int)
    browser_parser.add_argument("--max-results", default=50, type=int)
    browser_parser.add_argument("--max-nodes", default=20000, type=int)
    browser_parser.add_argument("--host", default="127.0.0.1")
    browser_parser.add_argument("--port", default=8765, type=int)
    browser_parser.add_argument("--timeout", default=30.0, type=float)

    plan_parser = subparsers.add_parser("plan", help="Generate a write plan without touching Live.")
    plan_subparsers = plan_parser.add_subparsers(dest="plan_command", required=True)
    demo_parser = plan_subparsers.add_parser("demo-melody", help="Create a simple demo melody plan.")
    demo_parser.add_argument("--out", default=tmp_path("demo-melody-plan.json"))
    demo_parser.add_argument("--track-name", default="AI Test - Melody")
    demo_parser.add_argument("--clip-name", default="AI Test - 8 Bar Motif")
    demo_parser.add_argument("--scene-index", default=0, type=int)
    arrangement_parser = plan_subparsers.add_parser("mini-arrangement", help="Create a four-track MIDI sketch plan.")
    arrangement_parser.add_argument("--out", default=tmp_path("mini-arrangement-plan.json"))
    arrangement_parser.add_argument("--prefix", default="AI Jam")
    arrangement_parser.add_argument("--scene-index", default=0, type=int)
    arrangement_parser.add_argument("--tempo", default=124.0, type=float)
    arrangement_parser.add_argument("--no-tempo", action="store_true")
    eurodance_parser = plan_subparsers.add_parser(
        "eurodance-sketch",
        help="Create an original high-energy eurodance/ringtone style sketch with Live Browser racks.",
    )
    eurodance_parser.add_argument("--out", default=tmp_path("eurodance-sketch-plan.json"))
    eurodance_parser.add_argument("--prefix", default="Euro Lab")
    eurodance_parser.add_argument("--scene-name", default="Euro Lab Hook Groove")
    eurodance_parser.add_argument("--tempo", default=138.0, type=float)
    eurodance_parser.add_argument("--bars", default=8, type=int)
    eurodance_parser.add_argument("--drum-rack", default="Foundation Dance Kit.adg")
    eurodance_parser.add_argument("--bass-rack", default="Retromancer Bass.adg")
    eurodance_parser.add_argument("--chord-rack", default="Star Eyes Keys.adg")
    eurodance_parser.add_argument("--lead-rack", default="Bouncy Castle Mallets.adg")
    midi_file_parser = plan_subparsers.add_parser(
        "midi-file",
        help="Import a MIDI file into role-based Live tracks with Browser racks.",
    )
    midi_file_parser.add_argument("midi_path")
    midi_file_parser.add_argument("--out", default=tmp_path("midi-file-plan.json"))
    midi_file_parser.add_argument("--prefix")
    midi_file_parser.add_argument("--scene-name")
    midi_file_parser.add_argument("--tempo", default=138.0, type=float)
    midi_file_parser.add_argument("--time-scale", default=0.5, type=float)
    midi_file_parser.add_argument(
        "--split-notes-dir",
        help="Write a structure-only plan to --out and note chunk plans into this directory.",
    )
    midi_file_parser.add_argument("--note-chunk-size", default=DEFAULT_NOTE_CHUNK_SIZE, type=int)
    variation_parser = plan_subparsers.add_parser(
        "section-variation",
        help="Create a second-scene variation on existing four-track MIDI sketch tracks.",
    )
    variation_parser.add_argument("--out", default=tmp_path("section-variation-plan.json"))
    variation_parser.add_argument("--base-track-index", default=5, type=int)
    variation_parser.add_argument(
        "--track-name",
        action="append",
        help="Exact existing track name. Repeat exactly four times for drums, bass, chords, and lead.",
    )
    variation_parser.add_argument("--scene-index", default=1, type=int)
    variation_parser.add_argument("--scene-name", help="Exact existing scene name to target instead of scene-index.")
    variation_parser.add_argument("--prefix", default="AI Jam 01 B")
    metadata_parser = plan_subparsers.add_parser(
        "note-metadata-proof",
        help="Create a tiny MIDI clip with Live 11+ note metadata fields.",
    )
    metadata_parser.add_argument("--out", default=tmp_path("note-metadata-proof-plan.json"))
    metadata_parser.add_argument("--track-name", default="AI Metadata Proof")
    metadata_parser.add_argument("--clip-name", default="Metadata Proof")
    metadata_parser.add_argument("--scene-index", default=0, type=int)
    mixer_parser = plan_subparsers.add_parser(
        "mixer-proof",
        help="Create a track state and mixer parameter proof plan.",
    )
    mixer_parser.add_argument("--out", default=tmp_path("mixer-proof-plan.json"))
    mixer_parser.add_argument("--track-name", default="AI Mixer Proof")
    mixer_adjust_parser = plan_subparsers.add_parser(
        "mixer-adjust-proof",
        help="Adjust an existing track state and mixer parameters.",
    )
    mixer_adjust_parser.add_argument("--out", default=tmp_path("mixer-adjust-proof-plan.json"))
    mixer_adjust_parser.add_argument("--track-index", default=4, type=int)
    mixer_adjust_parser.add_argument("--target-track-name", help="Exact existing track name to adjust.")
    mixer_adjust_parser.add_argument("--track-name", default="AI Mixer Proof Adjusted")
    device_parser = plan_subparsers.add_parser(
        "device-parameter-proof",
        help="Adjust default return-track Reverb and Delay parameters.",
    )
    device_parser.add_argument("--out", default=tmp_path("device-parameter-proof-plan.json"))
    note_edit_parser = plan_subparsers.add_parser(
        "track-note-edit-proof",
        help="Create a MIDI clip, then modify and remove notes by selectors.",
    )
    note_edit_parser.add_argument("--out", default=tmp_path("track-note-edit-proof-plan.json"))
    note_edit_parser.add_argument("--track-name", default="AI Note Edit Proof")
    note_edit_parser.add_argument("--clip-name", default="Note Edit Proof")
    note_edit_parser.add_argument("--scene-index", default=0, type=int)
    device_insert_parser = plan_subparsers.add_parser(
        "device-insertion-proof",
        help="Create a MIDI track and insert native Live devices by UI name.",
    )
    device_insert_parser.add_argument("--out", default=tmp_path("device-insertion-proof-plan.json"))
    device_insert_parser.add_argument("--track-name", default="AI Native Device Proof")
    device_insert_parser.add_argument("--instrument-name", default="Drift")
    device_insert_parser.add_argument("--effect-name", default="Auto Filter")

    apply_parser = subparsers.add_parser("apply-plan", help="Dry-run or apply a write plan to Live.")
    apply_parser.add_argument("plan")
    apply_parser.add_argument("--apply", action="store_true", help="Actually apply the plan. Omit for dry-run.")
    apply_parser.add_argument("--host", default="127.0.0.1")
    apply_parser.add_argument("--port", default=8765, type=int)
    apply_parser.add_argument("--timeout", default=30.0, type=float)
    apply_parser.add_argument(
        "--prepared-out",
        help="Optionally write the snapshot-resolved plan that is sent to Live.",
    )
    apply_parser.add_argument(
        "--no-cleanup-empty-project-tracks",
        action="store_true",
        help="Disable automatic deletion of default empty tracks when applying a creation plan to an empty project.",
    )

    delete_tracks_parser = subparsers.add_parser(
        "delete-tracks-by-name",
        help="Resolve exact track names to indices, then dry-run or delete matching tracks.",
    )
    delete_tracks_parser.add_argument(
        "--name",
        action="append",
        required=True,
        help="Exact track name to delete. Repeat for multiple tracks.",
    )
    delete_tracks_parser.add_argument("--out", default=tmp_path("delete-tracks-by-name-plan.json"))
    delete_tracks_parser.add_argument("--apply", action="store_true", help="Actually apply the delete plan.")
    delete_tracks_parser.add_argument(
        "--allow-non-empty",
        action="store_true",
        help="Allow deleting tracks that contain clips or devices.",
    )
    delete_tracks_parser.add_argument("--host", default="127.0.0.1")
    delete_tracks_parser.add_argument("--port", default=8765, type=int)
    delete_tracks_parser.add_argument("--timeout", default=30.0, type=float)

    verify_parser = subparsers.add_parser(
        "verify-note-metadata",
        help="Verify note metadata in a Live clip against a plan.",
    )
    verify_parser.add_argument("plan")
    verify_parser.add_argument("--track-index", type=int)
    verify_parser.add_argument("--track-name")
    verify_parser.add_argument("--scene-index", type=int)
    verify_parser.add_argument("--scene-name")
    verify_parser.add_argument("--clip-name")
    verify_parser.add_argument("--host", default="127.0.0.1")
    verify_parser.add_argument("--port", default=8765, type=int)
    verify_parser.add_argument("--timeout", default=20.0, type=float)

    verify_mixer_parser = subparsers.add_parser(
        "verify-track-mixer",
        help="Verify track state and mixer values in Live against a plan.",
    )
    verify_mixer_parser.add_argument("plan")
    verify_mixer_parser.add_argument("--track-index", type=int)
    verify_mixer_parser.add_argument("--track-name")
    verify_mixer_parser.add_argument("--host", default="127.0.0.1")
    verify_mixer_parser.add_argument("--port", default=8765, type=int)
    verify_mixer_parser.add_argument("--timeout", default=20.0, type=float)

    verify_device_parser = subparsers.add_parser(
        "verify-device-parameters",
        help="Verify device parameter values in Live against a plan.",
    )
    verify_device_parser.add_argument("plan")
    verify_device_parser.add_argument("--host", default="127.0.0.1")
    verify_device_parser.add_argument("--port", default=8765, type=int)
    verify_device_parser.add_argument("--timeout", default=20.0, type=float)

    verify_note_edit_parser = subparsers.add_parser(
        "verify-note-edit",
        help="Verify final note state in Live against a note edit proof plan.",
    )
    verify_note_edit_parser.add_argument("plan")
    verify_note_edit_parser.add_argument("--track-index", type=int)
    verify_note_edit_parser.add_argument("--track-name")
    verify_note_edit_parser.add_argument("--scene-index", type=int)
    verify_note_edit_parser.add_argument("--scene-name")
    verify_note_edit_parser.add_argument("--clip-name")
    verify_note_edit_parser.add_argument("--host", default="127.0.0.1")
    verify_note_edit_parser.add_argument("--port", default=8765, type=int)
    verify_note_edit_parser.add_argument("--timeout", default=20.0, type=float)

    bridge_parser = subparsers.add_parser("bridge", help="Forward raw bridge commands to tordo.client.")
    bridge_parser.add_argument("bridge_args", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)
    if args.command == "export":
        archive_dir, manifest = export_archive(
            output_dir=args.out,
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            limit_per_clip=args.limit_per_clip,
        )
        print("wrote %s" % archive_dir)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    if args.command == "analyze":
        payload = load_set_notes(args.input)
        analysis = analyze_set_notes(payload)
        ensure_parent(args.json_out).write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n")
        ensure_parent(args.md_out).write_text(format_markdown(analysis))
        print("wrote %s" % args.json_out)
        print("wrote %s" % args.md_out)
        return 0
    if args.command == "diff":
        diff = diff_archives(args.before, args.after)
        ensure_parent(args.json_out).write_text(json.dumps(diff, indent=2, sort_keys=True) + "\n")
        write_diff_markdown(diff, args.md_out)
        print("wrote %s" % args.json_out)
        print("wrote %s" % args.md_out)
        return 0
    if args.command == "schema":
        print(json.dumps(agent_plan_schema(), indent=2, sort_keys=True))
        return 0
    if args.command == "browser-items":
        try:
            response = send_request(
                "browser_items",
                args={
                    "query": args.query,
                    "exact": args.exact,
                    "loadable_only": not args.include_folders,
                    "roots": args.roots,
                    "max_depth": args.max_depth,
                    "max_results": args.max_results,
                    "max_nodes": args.max_nodes,
                },
                host=args.host,
                port=args.port,
                timeout=args.timeout,
            )
            payload = require_ok(response, "browser_items")
        except (BridgeConnectionError, BridgeResponseError) as exc:
            print("browser-items failed: %s" % exc, file=sys.stderr)
            return 1
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.command == "plan":
        if args.plan_command == "demo-melody":
            plan = demo_melody_plan(
                track_name=args.track_name,
                clip_name=args.clip_name,
                scene_index=args.scene_index,
            )
            write_plan(args.out, plan)
            print("wrote %s" % args.out)
            return 0
        if args.plan_command == "mini-arrangement":
            plan = mini_arrangement_plan(scene_index=args.scene_index, tempo=args.tempo, prefix=args.prefix)
            if args.no_tempo:
                plan["operations"] = [op for op in plan["operations"] if op.get("type") != "set_tempo"]
            write_plan(args.out, plan)
            print("wrote %s" % args.out)
            return 0
        if args.plan_command == "eurodance-sketch":
            plan = eurodance_sketch_plan(
                prefix=args.prefix,
                scene_name=args.scene_name,
                tempo=args.tempo,
                bars=args.bars,
                drum_rack=args.drum_rack,
                bass_rack=args.bass_rack,
                chord_rack=args.chord_rack,
                lead_rack=args.lead_rack,
            )
            write_plan(args.out, plan)
            print("wrote %s" % args.out)
            return 0
        if args.plan_command == "midi-file":
            if args.split_notes_dir:
                plan = midi_file_structure_plan(
                    args.midi_path,
                    prefix=args.prefix,
                    scene_name=args.scene_name,
                    tempo=args.tempo,
                    time_scale=args.time_scale,
                )
                note_plans = midi_file_note_chunk_plans(
                    args.midi_path,
                    prefix=args.prefix,
                    scene_name=args.scene_name,
                    time_scale=args.time_scale,
                    note_chunk_size=args.note_chunk_size,
                )
                note_dir = Path(args.split_notes_dir)
                for index, note_plan in enumerate(note_plans, start=1):
                    note_filename = "%03d-%s-%05d.json" % (
                        index,
                        slugify(note_plan["layer"]),
                        note_plan["chunk_note_offset"],
                    )
                    note_path = note_dir / note_filename
                    write_plan(note_path, note_plan)
                plan["note_chunk_plan_count"] = len(note_plans)
                plan["note_chunk_size"] = args.note_chunk_size
                plan["note_chunk_dir"] = str(note_dir)
                write_plan(args.out, plan)
                print("wrote %s" % args.out)
                print("wrote %s note chunk plans to %s" % (len(note_plans), note_dir))
                return 0
            plan = midi_file_plan(
                args.midi_path,
                prefix=args.prefix,
                scene_name=args.scene_name,
                tempo=args.tempo,
                time_scale=args.time_scale,
            )
            write_plan(args.out, plan)
            print("wrote %s" % args.out)
            return 0
        if args.plan_command == "section-variation":
            plan = section_variation_plan(
                base_track_index=args.base_track_index,
                scene_index=args.scene_index,
                prefix=args.prefix,
                track_names=args.track_name,
                scene_name=args.scene_name,
            )
            write_plan(args.out, plan)
            print("wrote %s" % args.out)
            return 0
        if args.plan_command == "note-metadata-proof":
            plan = note_metadata_proof_plan(
                track_name=args.track_name,
                clip_name=args.clip_name,
                scene_index=args.scene_index,
            )
            write_plan(args.out, plan)
            print("wrote %s" % args.out)
            return 0
        if args.plan_command == "mixer-proof":
            plan = mixer_proof_plan(track_name=args.track_name)
            write_plan(args.out, plan)
            print("wrote %s" % args.out)
            return 0
        if args.plan_command == "mixer-adjust-proof":
            plan = mixer_adjust_proof_plan(
                track_index=args.track_index,
                target_track_name=args.target_track_name,
                track_name=args.track_name,
            )
            write_plan(args.out, plan)
            print("wrote %s" % args.out)
            return 0
        if args.plan_command == "device-parameter-proof":
            plan = device_parameter_proof_plan()
            write_plan(args.out, plan)
            print("wrote %s" % args.out)
            return 0
        if args.plan_command == "track-note-edit-proof":
            plan = track_note_edit_proof_plan(
                track_name=args.track_name,
                clip_name=args.clip_name,
                scene_index=args.scene_index,
            )
            write_plan(args.out, plan)
            print("wrote %s" % args.out)
            return 0
        if args.plan_command == "device-insertion-proof":
            plan = device_insertion_proof_plan(
                track_name=args.track_name,
                instrument_name=args.instrument_name,
                effect_name=args.effect_name,
            )
            write_plan(args.out, plan)
            print("wrote %s" % args.out)
            return 0
    if args.command == "apply-plan":
        plan = load_plan(args.plan)
        try:
            snapshot_response = send_request("snapshot", host=args.host, port=args.port, timeout=args.timeout)
            snapshot = require_ok(snapshot_response, "snapshot")
            prepared_plan, preflight_report = prepare_plan_for_apply(plan, snapshot)
            cleanup_report = None
            if not args.no_cleanup_empty_project_tracks:
                prepared_plan, cleanup_report = append_empty_project_track_cleanup(prepared_plan, snapshot)
            if args.prepared_out:
                write_plan(args.prepared_out, prepared_plan)
            response = send_request(
                "apply_plan",
                args={"plan": prepared_plan, "dry_run": not args.apply},
                host=args.host,
                port=args.port,
                timeout=args.timeout,
            )
        except BridgeConnectionError as exc:
            print(
                "apply_plan connection failed: %s\n"
                "If --apply was used, inspect/export the Live Set before retrying; "
                "the plan may have partially applied." % exc,
                file=sys.stderr,
            )
            return 2
        except BridgeResponseError as exc:
            print("apply_plan preflight failed: %s: %s" % (exc.code, exc.message), file=sys.stderr)
            return 1
        except ValueError as exc:
            print("apply_plan preflight refused: %s" % exc, file=sys.stderr)
            return 1
        try:
            payload = require_ok(response, "apply_plan")
        except BridgeResponseError as exc:
            print("apply_plan failed: %s: %s" % (exc.code, exc.message), file=sys.stderr)
            return 1
        if preflight_report_has_entries(preflight_report):
            response["client_preflight"] = preflight_report
            if args.prepared_out:
                response["client_preflight"]["prepared_plan"] = args.prepared_out
        if cleanup_report is not None and cleanup_report.get("applied"):
            response.setdefault("client_preflight", {})
            response["client_preflight"]["empty_project_track_cleanup"] = cleanup_report
            if args.prepared_out:
                response["client_preflight"]["prepared_plan"] = args.prepared_out
        print(json.dumps(response, indent=2, sort_keys=True))
        return 0 if payload else 2
    if args.command == "delete-tracks-by-name":
        try:
            response = delete_tracks_by_name(
                names=args.name,
                out=args.out,
                apply=args.apply,
                allow_non_empty=args.allow_non_empty,
                host=args.host,
                port=args.port,
                timeout=args.timeout,
            )
        except BridgeConnectionError as exc:
            print("delete-tracks-by-name connection failed: %s" % exc, file=sys.stderr)
            return 2
        except BridgeResponseError as exc:
            print("delete-tracks-by-name failed: %s: %s" % (exc.code, exc.message), file=sys.stderr)
            return 1
        except ValueError as exc:
            print("delete-tracks-by-name refused: %s" % exc, file=sys.stderr)
            return 1
        print(json.dumps(response, indent=2, sort_keys=True))
        return 0
    if args.command == "verify-note-metadata":
        try:
            result = verify_note_metadata(
                args.plan,
                track_index=args.track_index,
                track_name=args.track_name,
                scene_index=args.scene_index,
                scene_name=args.scene_name,
                clip_name=args.clip_name,
                host=args.host,
                port=args.port,
                timeout=args.timeout,
            )
        except (BridgeConnectionError, BridgeResponseError, ValueError) as exc:
            print("verify-note-metadata failed: %s" % exc, file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.command == "verify-track-mixer":
        try:
            result = verify_track_mixer(
                args.plan,
                track_index=args.track_index,
                track_name=args.track_name,
                host=args.host,
                port=args.port,
                timeout=args.timeout,
            )
        except (BridgeConnectionError, BridgeResponseError, ValueError) as exc:
            print("verify-track-mixer failed: %s" % exc, file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.command == "verify-device-parameters":
        try:
            result = verify_device_parameters(
                args.plan,
                host=args.host,
                port=args.port,
                timeout=args.timeout,
            )
        except (BridgeConnectionError, BridgeResponseError, ValueError) as exc:
            print("verify-device-parameters failed: %s" % exc, file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.command == "verify-note-edit":
        try:
            result = verify_note_edit(
                args.plan,
                track_index=args.track_index,
                track_name=args.track_name,
                scene_index=args.scene_index,
                scene_name=args.scene_name,
                clip_name=args.clip_name,
                host=args.host,
                port=args.port,
                timeout=args.timeout,
            )
        except (BridgeConnectionError, BridgeResponseError, ValueError) as exc:
            print("verify-note-edit failed: %s" % exc, file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.command == "bridge":
        bridge_args = args.bridge_args
        if bridge_args and bridge_args[0] == "--":
            bridge_args = bridge_args[1:]
        return bridge_main(bridge_args)
    return 2


def delete_tracks_by_name(names, out, apply, allow_non_empty, host, port, timeout):
    snapshot_response = send_request("snapshot", host=host, port=port, timeout=timeout)
    snapshot = require_ok(snapshot_response, "snapshot")
    tracks = snapshot.get("tracks") or []
    targets = resolve_track_names(tracks, names)
    if not allow_non_empty:
        non_empty = [target for target in targets if target["clip_count"] or target["device_count"]]
        if non_empty:
            labels = [
                "%s(index=%s clips=%s devices=%s)"
                % (item["name"], item["index"], item["clip_count"], item["device_count"])
                for item in non_empty
            ]
            raise ValueError("refusing to delete non-empty tracks: %s" % ", ".join(labels))

    operations = []
    for target in sorted(targets, key=lambda item: item["index"], reverse=True):
        operations.append(
            {
                "type": "delete_track",
                "track_index": target["index"],
                "expected_track_name": target["name"],
                "allow_destructive": True,
            }
        )
    plan = {
        "plan_version": 1,
        "name": "delete-tracks-by-name",
        "description": "Delete tracks after resolving exact names to indices from a snapshot.",
        "resolved_tracks": targets,
        "operations": operations,
    }
    write_plan(out, plan)
    apply_response = send_request(
        "apply_plan",
        args={"plan": plan, "dry_run": not apply},
        host=host,
        port=port,
        timeout=timeout,
    )
    require_ok(apply_response, "apply_plan")
    return {
        "ok": True,
        "dry_run": not apply,
        "wrote_plan": out,
        "resolved_tracks": targets,
        "apply_response": apply_response,
    }


def preflight_report_has_entries(report):
    return any(report.get(key) for key in report)


def slugify(value):
    return "".join(char.lower() if char.isalnum() else "-" for char in str(value)).strip("-") or "chunk"


def resolve_track_names(tracks, names):
    if len(set(names)) != len(names):
        raise ValueError("duplicate requested names are not allowed")
    targets = []
    for name in names:
        matches = [track for track in tracks if track.get("name") == name]
        if not matches:
            raise ValueError("no track named %r" % name)
        if len(matches) > 1:
            indexes = [track.get("index") for track in matches]
            raise ValueError("track name %r is not unique, matched indexes %s" % (name, indexes))
        track = matches[0]
        targets.append(
            {
                "index": int(track.get("index")),
                "name": track.get("name"),
                "clip_count": sum(1 for slot in track.get("clip_slots") or [] if slot.get("has_clip")),
                "device_count": len(track.get("devices") or []),
            }
        )
    return targets


if __name__ == "__main__":
    sys.exit(main())
