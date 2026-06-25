from __future__ import absolute_import, print_function

import json
import queue
import socket
import threading
import traceback

try:
    import Live
except ImportError:
    Live = None

try:
    from _Framework.ControlSurface import ControlSurface
except ImportError:
    from ableton.v2.control_surface import ControlSurface


HOST = "127.0.0.1"
PORT = 8765
BRIDGE_VERSION = "0.8.0"
PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 1024 * 1024
MAX_NOTES_PER_CLIP = 20000
DEFAULT_NOTES_LIMIT = 5000
MAX_PLAN_OPERATIONS = 64
REQUEST_PROCESS_TIMEOUT_SECONDS = 120.0
MAX_WRITE_ATTEMPTS_REPORTED = 24
MAX_BROWSER_SEARCH_NODES = 20000
BROWSER_ROOT_NAMES = [
    "sounds",
    "drums",
    "instruments",
    "audio_effects",
    "midi_effects",
    "max_for_live",
    "plug_ins",
    "clips",
    "samples",
    "packs",
    "user_library",
    "current_project",
]
NOTE_FIELDS = [
    "note_id",
    "pitch",
    "start_time",
    "duration",
    "velocity",
    "mute",
    "probability",
    "velocity_deviation",
    "release_velocity",
]
COMMANDS = [
    "ping",
    "capabilities",
    "browser_items",
    "selected",
    "snapshot",
    "selected_notes",
    "clip_notes",
    "set_notes",
    "apply_plan",
]


class TordoBridge(ControlSurface):
    """Small JSON bridge for AI-agent experiments."""

    def __init__(self, c_instance):
        super(TordoBridge, self).__init__(c_instance)
        self._requests = queue.Queue()
        self._stop_event = threading.Event()
        self._server_socket = None
        self._server_thread = threading.Thread(target=self._serve, name="TordoBridge")
        self._server_thread.daemon = True
        self._server_thread.start()
        self._log("started on %s:%s" % (HOST, PORT))

    def disconnect(self):
        self._stop_event.set()
        try:
            if self._server_socket is not None:
                self._server_socket.close()
        except Exception:
            pass
        self._log("stopped")
        try:
            super(TordoBridge, self).disconnect()
        except Exception:
            pass

    def update_display(self):
        try:
            super(TordoBridge, self).update_display()
        except Exception:
            pass

        for _ in range(16):
            try:
                item = self._requests.get_nowait()
            except queue.Empty:
                break
            self._complete_request(item)

    def _serve(self):
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((HOST, PORT))
            server.listen(8)
            server.settimeout(0.5)
            self._server_socket = server
        except Exception as exc:
            self._log("failed to bind %s:%s: %s" % (HOST, PORT, exc))
            return

        while not self._stop_event.is_set():
            try:
                conn, _addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as exc:
                self._log("accept failed: %s" % exc)
                continue

            client = threading.Thread(target=self._handle_connection, args=(conn,))
            client.daemon = True
            client.start()

    def _handle_connection(self, conn):
        result = None
        try:
            raw = self._read_request(conn)
            request = json.loads(raw.decode("utf-8"))
            event = threading.Event()
            item = {"request": request, "event": event, "response": None}
            self._requests.put(item)
            if not event.wait(REQUEST_PROCESS_TIMEOUT_SECONDS):
                result = error_response(
                    "timeout",
                    "Live did not process the request within %ss" % REQUEST_PROCESS_TIMEOUT_SECONDS,
                )
            else:
                result = item["response"]
        except Exception as exc:
            result = error_response("bad_request", str(exc))
        finally:
            try:
                payload = json.dumps(result, sort_keys=True).encode("utf-8") + b"\n"
                conn.sendall(payload)
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

    def _read_request(self, conn):
        conn.settimeout(2.0)
        chunks = []
        total = 0
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_REQUEST_BYTES:
                raise ValueError("request too large")
            if b"\n" in chunk:
                break
        if not chunks:
            raise ValueError("empty request")
        return b"".join(chunks).split(b"\n", 1)[0]

    def _complete_request(self, item):
        try:
            request = item["request"]
            command = request.get("command")
            args = request.get("args") or {}
            if command == "ping":
                payload = self._ping()
            elif command == "capabilities":
                payload = self._capabilities()
            elif command == "browser_items":
                payload = self._browser_items(args)
            elif command == "selected":
                payload = self._selected()
            elif command == "selected_notes":
                payload = self._selected_notes(args)
            elif command == "clip_notes":
                payload = self._clip_notes(args)
            elif command == "set_notes":
                payload = self._set_notes(args)
            elif command == "snapshot":
                payload = self._snapshot()
            elif command == "apply_plan":
                payload = self._apply_plan(args)
            else:
                item["response"] = error_response("unknown_command", "Unknown command: %r" % command)
                return
            item["response"] = success_response(payload)
        except BridgeRequestError as exc:
            item["response"] = error_response(exc.code, exc.message)
        except Exception as exc:
            self._log("request failed: %s\n%s" % (exc, traceback.format_exc()))
            item["response"] = error_response("internal_error", str(exc))
        finally:
            item["event"].set()

    def _ping(self):
        song = self.song()
        return {
            "bridge": "TordoBridge",
            "bridge_version": BRIDGE_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "host": HOST,
            "port": PORT,
            "song_name": safe_get(song, "name"),
            "tempo": safe_get(song, "tempo"),
            "current_song_time": safe_get(song, "current_song_time"),
        }

    def _capabilities(self):
        return {
            "bridge": "TordoBridge",
            "bridge_version": BRIDGE_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "commands": list(COMMANDS),
            "transport": {
                "host": HOST,
                "port": PORT,
                "framing": "newline-delimited-json",
                "max_request_bytes": MAX_REQUEST_BYTES,
                "request_process_timeout_seconds": REQUEST_PROCESS_TIMEOUT_SECONDS,
            },
            "limits": {
                "default_notes_limit": DEFAULT_NOTES_LIMIT,
                "max_notes_per_clip": MAX_NOTES_PER_CLIP,
                "max_plan_operations": MAX_PLAN_OPERATIONS,
            },
            "read_only": False,
            "write_commands": ["apply_plan"],
            "safety": {
                "dry_run_supported": True,
                "overwrites_existing_clips": False,
                "write_model": "explicit-plan",
                "target_guards": ["expected_track_name", "expected_scene_name", "expected_clip_name"],
            },
            "plan_operations": [
                "set_tempo",
                "set_transport",
                "set_track_state",
                "set_track_mixer",
                "set_device_parameter",
                "create_midi_track",
                "create_audio_track",
                "create_return_track",
                "duplicate_track",
                "delete_track",
                "create_scene",
                "duplicate_scene",
                "delete_scene",
                "insert_device",
                "load_browser_item",
                "create_midi_clip",
                "add_notes",
                "modify_notes",
                "remove_notes",
                "quantize_clip",
                "duplicate_clip_loop",
                "crop_clip",
                "fire_clip_slot",
                "stop_clip_slot",
                "fire_scene",
            ],
            "note_write": {
                "preferred": "add_new_notes",
                "preferred_payload": "MidiNoteSpecification",
                "modify": "apply_note_modifications",
                "delete": "remove_notes_by_id",
                "fallback": "replace_selected_notes",
            },
        }

    def _selected(self):
        view = self.song().view
        track = safe_get(view, "selected_track")
        scene = safe_get(view, "selected_scene")
        clip_slot = safe_get(view, "highlighted_clip_slot")
        detail_clip = safe_get(view, "detail_clip")
        return {
            "track": track_summary(track),
            "scene": scene_summary(scene),
            "highlighted_clip": clip_summary(safe_get(clip_slot, "clip")),
            "detail_clip": clip_summary(detail_clip),
        }

    def _browser_items(self, args):
        return browser_items_payload(self.application(), args)

    def _snapshot(self):
        song = self.song()
        return {
            "song": song_summary(song),
            "selected": self._selected(),
            "tracks": [track_snapshot(track, index) for index, track in enumerate(safe_list(song, "tracks"))],
            "return_tracks": [
                track_snapshot(track, index) for index, track in enumerate(safe_list(song, "return_tracks"))
            ],
            "master_track": track_snapshot(safe_get(song, "master_track"), 0),
            "scenes": [scene_summary(scene, index) for index, scene in enumerate(safe_list(song, "scenes"))],
        }

    def _selected_notes(self, args):
        clip = selected_clip(self.song())
        limit = clamp_int(args.get("limit"), 1, MAX_NOTES_PER_CLIP, DEFAULT_NOTES_LIMIT)
        return clip_notes_payload(clip, limit, include_attempts=bool(args.get("diagnostic")))

    def _clip_notes(self, args):
        song = self.song()
        track_index = required_index(args, "track_index")
        scene_index = required_index(args, "scene_index")
        track, scene, clip = clip_by_indices(song, track_index, scene_index)
        limit = clamp_int(args.get("limit"), 1, MAX_NOTES_PER_CLIP, DEFAULT_NOTES_LIMIT)

        payload = clip_notes_payload(clip, limit, include_attempts=bool(args.get("diagnostic")))
        payload["track_index"] = track_index
        payload["scene_index"] = scene_index
        payload["track"] = track_summary(track)
        payload["scene"] = scene_summary(scene, scene_index)
        return payload

    def _set_notes(self, args):
        song = self.song()
        limit_per_clip = clamp_int(args.get("limit_per_clip"), 1, MAX_NOTES_PER_CLIP, DEFAULT_NOTES_LIMIT)
        clips = []

        scenes = safe_list(song, "scenes")
        for track_index, track in enumerate(safe_list(song, "tracks")):
            for scene_index, slot in enumerate(safe_list(track, "clip_slots")):
                clip = safe_get(slot, "clip")
                if clip is None or not safe_get(clip, "is_midi_clip"):
                    continue
                payload = clip_notes_payload(clip, limit_per_clip, include_attempts=False)
                payload["track_index"] = track_index
                payload["scene_index"] = scene_index
                payload["track"] = track_summary(track)
                payload["scene"] = scene_summary(safe_index(scenes, scene_index), scene_index)
                clips.append(payload)

        return {
            "song": song_summary(song),
            "midi_clip_count": len(clips),
            "clips": clips,
        }

    def _apply_plan(self, args):
        plan = args.get("plan")
        dry_run = bool(args.get("dry_run", True))
        if not isinstance(plan, dict):
            raise BridgeRequestError("bad_argument", "apply_plan requires a plan object")
        return apply_plan(self.song(), plan, dry_run=dry_run, application=self.application())

    def _log(self, message):
        try:
            self.log_message("[TordoBridge] %s" % message)
        except Exception:
            pass


def response_meta():
    return {
        "bridge": "TordoBridge",
        "bridge_version": BRIDGE_VERSION,
        "protocol_version": PROTOCOL_VERSION,
    }


def success_response(payload):
    return {"ok": True, "payload": payload, "meta": response_meta()}


def error_response(code, message):
    return {"ok": False, "error": {"code": code, "message": message}, "meta": response_meta()}


class BridgeRequestError(Exception):
    def __init__(self, code, message):
        Exception.__init__(self, message)
        self.code = code
        self.message = message


def safe_get(obj, name, default=None):
    if obj is None:
        return default
    try:
        return getattr(obj, name)
    except Exception:
        return default


def safe_call(obj, name, default=None):
    if obj is None:
        return default
    try:
        return getattr(obj, name)()
    except Exception:
        return default


def safe_list(obj, name):
    value = safe_get(obj, name, [])
    try:
        return list(value)
    except Exception:
        return []


def safe_index(values, index):
    try:
        return values[index]
    except Exception:
        return None


def browser_items_payload(application, args):
    browser = safe_get(application, "browser")
    if browser is None:
        raise BridgeRequestError("not_supported", "Live browser is not available")
    result = search_browser_items(browser, args)
    return {
        "query": result["query"],
        "exact": result["exact"],
        "roots": result["roots"],
        "loadable_only": result["loadable_only"],
        "max_depth": result["max_depth"],
        "visited_count": result["visited_count"],
        "truncated": result["truncated"],
        "items": result["items"],
    }


def search_browser_items(browser, args):
    query = args.get("query")
    exact = bool(args.get("exact", False))
    loadable_only = bool(args.get("loadable_only", True))
    max_depth = clamp_int(args.get("max_depth"), 0, 16, 8)
    max_results = clamp_int(args.get("max_results"), 1, 200, 50)
    max_nodes = clamp_int(args.get("max_nodes"), 1, MAX_BROWSER_SEARCH_NODES, MAX_BROWSER_SEARCH_NODES)
    root_names = browser_root_names(args.get("roots"))
    roots = [(name, safe_get(browser, name)) for name in root_names]
    roots = [(name, item) for name, item in roots if item is not None]

    state = {"visited": 0, "truncated": False}
    items = []
    for root_name, root in roots:
        walk_browser_item(
            root,
            root_name,
            [safe_get(root, "name") or root_name],
            0,
            max_depth,
            query,
            exact,
            loadable_only,
            max_results,
            max_nodes,
            state,
            items,
        )
        if len(items) >= max_results or state["truncated"]:
            break

    return {
        "query": query,
        "exact": exact,
        "roots": [name for name, _item in roots],
        "loadable_only": loadable_only,
        "max_depth": max_depth,
        "visited_count": state["visited"],
        "truncated": state["truncated"],
        "items": items,
    }


def browser_root_names(raw_roots):
    if raw_roots is None:
        return list(BROWSER_ROOT_NAMES)
    if isinstance(raw_roots, str):
        raw_roots = [raw_roots]
    if not isinstance(raw_roots, list):
        raise BridgeRequestError("bad_argument", "browser roots must be a string or list")
    roots = []
    for root in raw_roots:
        if root not in BROWSER_ROOT_NAMES:
            raise BridgeRequestError("bad_argument", "Unsupported browser root: %s" % root)
        roots.append(root)
    return roots


def walk_browser_item(
    item,
    root_name,
    path,
    depth,
    max_depth,
    query,
    exact,
    loadable_only,
    max_results,
    max_nodes,
    state,
    items,
):
    if item is None or len(items) >= max_results or state["truncated"]:
        return
    state["visited"] += 1
    if state["visited"] > max_nodes:
        state["truncated"] = True
        return

    if browser_item_matches(item, query, exact, loadable_only):
        items.append(browser_item_summary(item, root_name, path, depth))
        if len(items) >= max_results:
            return

    if depth >= max_depth:
        return
    children = safe_list(item, "children")
    for child in children:
        child_name = safe_get(child, "name") or ""
        walk_browser_item(
            child,
            root_name,
            path + [child_name],
            depth + 1,
            max_depth,
            query,
            exact,
            loadable_only,
            max_results,
            max_nodes,
            state,
            items,
        )
        if len(items) >= max_results or state["truncated"]:
            return


def browser_item_matches(item, query, exact, loadable_only):
    if loadable_only and safe_get(item, "is_loadable") is not True:
        return False
    if query is None or query == "":
        return True
    name = safe_get(item, "name") or ""
    uri = safe_get(item, "uri") or ""
    if exact:
        return query == name or query == uri
    needle = str(query).lower()
    return needle in name.lower() or needle in uri.lower()


def browser_item_summary(item, root_name, path, depth):
    return {
        "name": safe_get(item, "name"),
        "uri": safe_get(item, "uri"),
        "root": root_name,
        "path": [part for part in path if part],
        "depth": depth,
        "is_loadable": safe_get(item, "is_loadable"),
        "is_folder": safe_get(item, "is_folder"),
    }


def resolve_browser_item(browser, operation):
    if browser is None:
        raise BridgeRequestError("not_supported", "Live browser is not available")
    uri = operation.get("browser_uri")
    query = operation.get("browser_name") or operation.get("browser_query") or uri
    if not query:
        raise BridgeRequestError(
            "bad_plan",
            "load_browser_item requires browser_uri, browser_name, or browser_query",
        )

    exact = bool(operation.get("browser_exact", True))
    args = {
        "query": query,
        "exact": exact,
        "loadable_only": True,
        "roots": operation.get("browser_roots"),
        "max_depth": operation.get("browser_max_depth", 10),
        "max_results": operation.get("browser_max_results", 12),
        "max_nodes": operation.get("browser_max_nodes", MAX_BROWSER_SEARCH_NODES),
    }
    result = search_browser_items(browser, args)
    items = result["items"]
    if uri:
        items = [item for item in items if item.get("uri") == uri]
    if not items:
        raise BridgeRequestError("not_found", "No loadable browser item matched %r" % query)
    if len(items) > 1:
        names = ["%s <%s>" % (item.get("name"), item.get("uri")) for item in items[:8]]
        raise BridgeRequestError(
            "bad_plan",
            "Browser item match is ambiguous for %r: %s" % (query, "; ".join(names)),
        )
    item_ref = find_browser_item_by_uri(browser, items[0].get("uri"), operation)
    if item_ref is None:
        raise BridgeRequestError("not_found", "Matched browser item disappeared: %r" % items[0].get("uri"))
    return item_ref, items[0]


def find_browser_item_by_uri(browser, uri, operation):
    if not uri:
        return None
    args = {
        "query": uri,
        "exact": True,
        "loadable_only": True,
        "roots": operation.get("browser_roots"),
        "max_depth": operation.get("browser_max_depth", 10),
        "max_results": 1,
        "max_nodes": operation.get("browser_max_nodes", MAX_BROWSER_SEARCH_NODES),
    }
    root_names = browser_root_names(args.get("roots"))
    roots = [(name, safe_get(browser, name)) for name in root_names]
    roots = [(name, item) for name, item in roots if item is not None]
    state = {"visited": 0, "truncated": False}
    for _root_name, root in roots:
        found = find_browser_item_by_uri_in_tree(
            root,
            uri,
            0,
            clamp_int(args.get("max_depth"), 0, 16, 10),
            clamp_int(args.get("max_nodes"), 1, MAX_BROWSER_SEARCH_NODES, MAX_BROWSER_SEARCH_NODES),
            state,
        )
        if found is not None:
            return found
    return None


def find_browser_item_by_uri_in_tree(item, uri, depth, max_depth, max_nodes, state):
    if item is None or state["truncated"]:
        return None
    state["visited"] += 1
    if state["visited"] > max_nodes:
        state["truncated"] = True
        return None
    if safe_get(item, "uri") == uri and safe_get(item, "is_loadable") is True:
        return item
    if depth >= max_depth:
        return None
    for child in safe_list(item, "children"):
        found = find_browser_item_by_uri_in_tree(child, uri, depth + 1, max_depth, max_nodes, state)
        if found is not None:
            return found
    return None


def safe_number(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    return None


def clamp_int(value, minimum, maximum, default):
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def required_index(args, name):
    if name not in args:
        raise BridgeRequestError("missing_argument", "Missing required argument: %s" % name)
    try:
        parsed = int(args.get(name))
    except Exception:
        raise BridgeRequestError("bad_argument", "Argument %s must be an integer" % name)
    if parsed < 0:
        raise BridgeRequestError("bad_argument", "Argument %s must be >= 0" % name)
    return parsed


def selected_clip(song):
    view = song.view
    detail_clip = safe_get(view, "detail_clip")
    if detail_clip is not None:
        return detail_clip
    clip_slot = safe_get(view, "highlighted_clip_slot")
    return safe_get(clip_slot, "clip")


def song_summary(song):
    return {
        "name": safe_get(song, "name"),
        "tempo": safe_get(song, "tempo"),
        "signature_numerator": safe_get(song, "signature_numerator"),
        "signature_denominator": safe_get(song, "signature_denominator"),
        "is_playing": safe_get(song, "is_playing"),
        "current_song_time": safe_get(song, "current_song_time"),
    }


def clip_by_indices(song, track_index, scene_index):
    tracks = safe_list(song, "tracks")
    scenes = safe_list(song, "scenes")
    if track_index >= len(tracks):
        raise BridgeRequestError("not_found", "No track at index %s" % track_index)
    if scene_index >= len(scenes):
        raise BridgeRequestError("not_found", "No scene at index %s" % scene_index)

    track = tracks[track_index]
    slots = safe_list(track, "clip_slots")
    if scene_index >= len(slots):
        raise BridgeRequestError(
            "not_found",
            "Track %s has no clip slot at scene index %s" % (track_index, scene_index),
        )

    clip = safe_get(slots[scene_index], "clip")
    if clip is None:
        raise BridgeRequestError(
            "not_found",
            "No clip at track index %s, scene index %s" % (track_index, scene_index),
        )
    return track, scenes[scene_index], clip


def track_summary(track):
    if track is None:
        return None
    return {
        "name": safe_get(track, "name"),
        "is_foldable": safe_get(track, "is_foldable"),
        "can_be_armed": safe_get(track, "can_be_armed"),
        "arm": safe_get(track, "arm"),
        "mute": safe_get(track, "mute"),
        "solo": safe_get(track, "solo"),
    }


def track_snapshot(track, index):
    if track is None:
        return None
    clip_slots = safe_list(track, "clip_slots")
    devices = safe_list(track, "devices")
    return {
        "index": index,
        "name": safe_get(track, "name"),
        "is_foldable": safe_get(track, "is_foldable"),
        "can_be_armed": safe_get(track, "can_be_armed"),
        "arm": safe_get(track, "arm"),
        "mute": safe_get(track, "mute"),
        "solo": safe_get(track, "solo"),
        "mixer": mixer_summary(safe_get(track, "mixer_device")),
        "clip_slots": [clip_slot_summary(slot, slot_index) for slot_index, slot in enumerate(clip_slots)],
        "devices": [device_summary(device, device_index) for device_index, device in enumerate(devices)],
    }


def mixer_summary(mixer):
    if mixer is None:
        return None
    return {
        "volume": mixer_parameter_summary(safe_get(mixer, "volume")),
        "panning": mixer_parameter_summary(safe_get(mixer, "panning")),
        "sends": [
            mixer_parameter_summary(parameter, index)
            for index, parameter in enumerate(safe_list(mixer, "sends"))
        ],
    }


def mixer_parameter_summary(parameter, index=None):
    if parameter is None:
        return None
    payload = {
        "name": safe_get(parameter, "name"),
        "value": safe_get(parameter, "value"),
        "min": safe_get(parameter, "min"),
        "max": safe_get(parameter, "max"),
        "is_enabled": safe_get(parameter, "is_enabled"),
        "is_quantized": safe_get(parameter, "is_quantized"),
    }
    if index is not None:
        payload["index"] = index
    return payload


def scene_summary(scene, index=None):
    if scene is None:
        return None
    payload = {
        "name": safe_get(scene, "name"),
        "color": safe_number(safe_get(scene, "color")),
        "tempo": safe_get(scene, "tempo"),
        "is_empty": safe_get(scene, "is_empty"),
    }
    if index is not None:
        payload["index"] = index
    return payload


def clip_slot_summary(slot, index):
    clip = safe_get(slot, "clip")
    return {
        "index": index,
        "has_clip": bool(clip),
        "clip": clip_summary(clip),
    }


def clip_summary(clip):
    if clip is None:
        return None
    return {
        "name": safe_get(clip, "name"),
        "color": safe_number(safe_get(clip, "color")),
        "is_audio_clip": safe_get(clip, "is_audio_clip"),
        "is_midi_clip": safe_get(clip, "is_midi_clip"),
        "length": safe_get(clip, "length"),
        "start_marker": safe_get(clip, "start_marker"),
        "end_marker": safe_get(clip, "end_marker"),
        "looping": safe_get(clip, "looping"),
        "loop_start": safe_get(clip, "loop_start"),
        "loop_end": safe_get(clip, "loop_end"),
    }


def read_clip_notes(clip, include_attempts=False):
    attempts = []
    best = {"source": "unavailable", "notes": []}

    if hasattr(clip, "get_all_notes_extended"):
        best = choose_notes_attempt(
            best,
            attempts,
            "get_all_notes_extended_return",
            lambda: clip.get_all_notes_extended({"return": NOTE_FIELDS}),
        )
        best = choose_notes_attempt(
            best,
            attempts,
            "get_all_notes_extended",
            lambda: clip.get_all_notes_extended(),
        )

    if hasattr(clip, "get_notes_extended"):
        length = safe_get(clip, "length", 0) or 0
        request = {
            "from_pitch": 0,
            "pitch_span": 128,
            "from_time": 0,
            "time_span": length,
            "return": NOTE_FIELDS,
        }
        best = choose_notes_attempt(
            best,
            attempts,
            "get_notes_extended_dict",
            lambda: clip.get_notes_extended(request),
        )
        best = choose_notes_attempt(
            best,
            attempts,
            "get_notes_extended_args_pitch_first",
            lambda: clip.get_notes_extended(0, 128, 0, length),
        )
        best = choose_notes_attempt(
            best,
            attempts,
            "get_notes_extended_args_time_first",
            lambda: clip.get_notes_extended(0, 0, length, 128),
        )

    if hasattr(clip, "get_notes"):
        length = safe_get(clip, "length", 0) or 0
        best = choose_notes_attempt(
            best,
            attempts,
            "get_notes_legacy",
            lambda: clip.get_notes(0, 0, length, 128),
        )

    if include_attempts:
        best["attempts"] = attempts
    return best


def clip_notes_payload(clip, limit, include_attempts=False):
    if clip is None:
        return {
            "clip": None,
            "notes": [],
            "note_count": 0,
            "returned_count": 0,
            "truncated": False,
            "source": None,
            "warning": "No clip.",
        }
    if not safe_get(clip, "is_midi_clip"):
        return {
            "clip": clip_summary(clip),
            "notes": [],
            "note_count": 0,
            "returned_count": 0,
            "truncated": False,
            "source": None,
            "warning": "Clip is not a MIDI clip.",
        }

    notes_payload = read_clip_notes(clip, include_attempts=include_attempts)
    notes = [normalize_note(note) for note in notes_payload["notes"]]
    notes = [note for note in notes if note is not None]
    notes.sort(key=lambda note: (note.get("start_time", 0), note.get("pitch", 0), note.get("duration", 0)))

    note_count = len(notes)
    truncated = note_count > limit
    payload = {
        "clip": clip_summary(clip),
        "notes": notes[:limit],
        "note_count": note_count,
        "returned_count": min(note_count, limit),
        "truncated": truncated,
        "source": notes_payload["source"],
    }
    if include_attempts:
        payload["attempts"] = notes_payload.get("attempts")
    return payload


def apply_plan(song, plan, dry_run=True, application=None):
    operations = plan.get("operations")
    if plan.get("plan_version") != 1:
        raise BridgeRequestError("bad_plan", "Unsupported plan_version: %r" % plan.get("plan_version"))
    if not isinstance(operations, list):
        raise BridgeRequestError("bad_plan", "Plan operations must be a list")
    if len(operations) > MAX_PLAN_OPERATIONS:
        raise BridgeRequestError("bad_plan", "Plan has too many operations")

    context = PlanContext(song, dry_run=dry_run, application=application)
    summaries = []
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise BridgeRequestError("bad_plan", "Operation %s must be an object" % index)
        operation_type = operation.get("type")
        if operation_type == "create_midi_track":
            summaries.append(apply_create_midi_track(context, operation))
        elif operation_type == "create_audio_track":
            summaries.append(apply_create_audio_track(context, operation))
        elif operation_type == "create_return_track":
            summaries.append(apply_create_return_track(context, operation))
        elif operation_type == "duplicate_track":
            summaries.append(apply_duplicate_track(context, operation))
        elif operation_type == "delete_track":
            summaries.append(apply_delete_track(context, operation))
        elif operation_type == "create_scene":
            summaries.append(apply_create_scene(context, operation))
        elif operation_type == "duplicate_scene":
            summaries.append(apply_duplicate_scene(context, operation))
        elif operation_type == "delete_scene":
            summaries.append(apply_delete_scene(context, operation))
        elif operation_type == "set_tempo":
            summaries.append(apply_set_tempo(context, operation))
        elif operation_type == "set_transport":
            summaries.append(apply_set_transport(context, operation))
        elif operation_type == "set_track_state":
            summaries.append(apply_set_track_state(context, operation))
        elif operation_type == "set_track_mixer":
            summaries.append(apply_set_track_mixer(context, operation))
        elif operation_type == "set_device_parameter":
            summaries.append(apply_set_device_parameter(context, operation))
        elif operation_type == "insert_device":
            summaries.append(apply_insert_device(context, operation))
        elif operation_type == "load_browser_item":
            summaries.append(apply_load_browser_item(context, operation))
        elif operation_type == "create_midi_clip":
            summaries.append(apply_create_midi_clip(context, operation))
        elif operation_type == "add_notes":
            summaries.append(apply_add_notes(context, operation))
        elif operation_type == "modify_notes":
            summaries.append(apply_modify_notes(context, operation))
        elif operation_type == "remove_notes":
            summaries.append(apply_remove_notes(context, operation))
        elif operation_type == "quantize_clip":
            summaries.append(apply_quantize_clip(context, operation))
        elif operation_type == "duplicate_clip_loop":
            summaries.append(apply_duplicate_clip_loop(context, operation))
        elif operation_type == "crop_clip":
            summaries.append(apply_crop_clip(context, operation))
        elif operation_type == "fire_clip_slot":
            summaries.append(apply_fire_clip_slot(context, operation))
        elif operation_type == "stop_clip_slot":
            summaries.append(apply_stop_clip_slot(context, operation))
        elif operation_type == "fire_scene":
            summaries.append(apply_fire_scene(context, operation))
        else:
            raise BridgeRequestError("bad_plan", "Unsupported operation type: %r" % operation_type)

    return {
        "dry_run": dry_run,
        "plan_name": plan.get("name"),
        "operation_count": len(operations),
        "operations": summaries,
    }


class PlanContext(object):
    def __init__(self, song, dry_run=True, application=None):
        self.song = song
        self.dry_run = dry_run
        self.application = application
        self.browser = safe_get(application, "browser")
        self.refs = {}
        self.track_count = len(safe_list(song, "tracks"))
        self.return_track_count = len(safe_list(song, "return_tracks"))
        self.scene_count = len(safe_list(song, "scenes"))

    def store_ref(self, ref_id, value):
        if not ref_id:
            return
        if ref_id in self.refs:
            raise BridgeRequestError("bad_plan", "Duplicate operation id: %s" % ref_id)
        self.refs[ref_id] = value

    def resolve_track(self, operation):
        if "track_ref" in operation:
            ref = self.refs.get(operation.get("track_ref"))
            if ref is None or ref.get("kind") != "track":
                raise BridgeRequestError("bad_plan", "Unknown track_ref: %s" % operation.get("track_ref"))
            return ref
        track_index = required_index(operation, "track_index")
        tracks = safe_list(self.song, "tracks")
        if track_index >= len(tracks):
            raise BridgeRequestError("not_found", "No track at index %s" % track_index)
        track = tracks[track_index]
        assert_expected_track_name(operation, track, track_index, "track")
        return {"kind": "track", "track": track, "track_index": track_index}

    def resolve_clip(self, operation):
        if "clip_ref" in operation:
            ref = self.refs.get(operation.get("clip_ref"))
            if ref is None or ref.get("kind") != "clip":
                raise BridgeRequestError("bad_plan", "Unknown clip_ref: %s" % operation.get("clip_ref"))
            return ref
        track_ref = self.resolve_track(operation)
        scene_ref = self.resolve_scene(operation)
        scene_index = scene_ref["scene_index"]
        if self.dry_run:
            if operation.get("expected_clip_name") is not None and track_ref.get("track") is not None:
                slots = safe_list(track_ref["track"], "clip_slots")
                if scene_index >= len(slots):
                    raise BridgeRequestError("not_found", "No clip slot at scene index %s" % scene_index)
                clip = safe_get(slots[scene_index], "clip")
                if clip is None:
                    raise BridgeRequestError("not_found", "No clip at scene index %s" % scene_index)
                assert_expected_clip_name(operation, clip, scene_index)
            return {"kind": "clip", "clip": None, "track_index": track_ref["track_index"], "scene_index": scene_index}
        track = track_ref["track"]
        slots = safe_list(track, "clip_slots")
        if scene_index >= len(slots):
            raise BridgeRequestError("not_found", "No clip slot at scene index %s" % scene_index)
        clip = safe_get(slots[scene_index], "clip")
        if clip is None:
            raise BridgeRequestError("not_found", "No clip at scene index %s" % scene_index)
        assert_expected_clip_name(operation, clip, scene_index)
        return {"kind": "clip", "clip": clip, "track_index": track_ref["track_index"], "scene_index": scene_index}

    def resolve_scene(self, operation):
        if "scene_ref" in operation:
            ref = self.refs.get(operation.get("scene_ref"))
            if ref is None or ref.get("kind") != "scene":
                raise BridgeRequestError("bad_plan", "Unknown scene_ref: %s" % operation.get("scene_ref"))
            if ref.get("scene") is not None:
                assert_expected_scene_name(operation, ref.get("scene"), ref.get("scene_index"))
            return ref
        scene_index = required_index(operation, "scene_index")
        scenes = safe_list(self.song, "scenes")
        if scene_index >= len(scenes):
            raise BridgeRequestError("not_found", "No scene at index %s" % scene_index)
        scene = scenes[scene_index]
        assert_expected_scene_name(operation, scene, scene_index)
        return {"kind": "scene", "scene": scene, "scene_index": scene_index}


def apply_create_midi_track(context, operation):
    return apply_create_regular_track(context, operation, "midi")


def apply_create_audio_track(context, operation):
    return apply_create_regular_track(context, operation, "audio")


def apply_create_regular_track(context, operation, track_kind):
    ref_id = require_operation_id(operation)
    requested_index = operation.get("index", -1)
    try:
        requested_index = int(requested_index)
    except Exception:
        raise BridgeRequestError("bad_plan", "create_%s_track index must be an integer" % track_kind)

    current_track_count = context.track_count if context.dry_run else len(safe_list(context.song, "tracks"))
    track_index = current_track_count if requested_index < 0 else requested_index
    if track_index > current_track_count:
        raise BridgeRequestError("bad_plan", "create_%s_track index is out of range" % track_kind)

    name = operation.get("name") or "AI %s Track" % track_kind.title()
    if context.dry_run:
        context.store_ref(ref_id, {"kind": "track", "track": None, "track_index": track_index})
        context.track_count += 1
    else:
        if track_kind == "audio":
            context.song.create_audio_track(track_index)
        else:
            context.song.create_midi_track(track_index)
        track = safe_list(context.song, "tracks")[track_index]
        try:
            track.name = name
        except Exception:
            pass
        context.store_ref(ref_id, {"kind": "track", "track": track, "track_index": track_index})

    return {
        "type": "create_%s_track" % track_kind,
        "id": ref_id,
        "track_index": track_index,
        "name": name,
    }


def apply_create_return_track(context, operation):
    ref_id = require_operation_id(operation)
    requested_index = operation.get("index", -1)
    try:
        requested_index = int(requested_index)
    except Exception:
        raise BridgeRequestError("bad_plan", "create_return_track index must be an integer")

    current_count = context.return_track_count if context.dry_run else len(safe_list(context.song, "return_tracks"))
    return_track_index = current_count if requested_index < 0 else requested_index
    if return_track_index > current_count:
        raise BridgeRequestError("bad_plan", "create_return_track index is out of range")

    name = operation.get("name") or "AI Return Track"
    if context.dry_run:
        context.store_ref(
            ref_id,
            {"kind": "return_track", "track": None, "track_index": return_track_index},
        )
        context.return_track_count += 1
    else:
        context.song.create_return_track(return_track_index)
        track = safe_list(context.song, "return_tracks")[return_track_index]
        try:
            track.name = name
        except Exception:
            pass
        context.store_ref(
            ref_id,
            {"kind": "return_track", "track": track, "track_index": return_track_index},
        )

    return {
        "type": "create_return_track",
        "id": ref_id,
        "track_index": return_track_index,
        "name": name,
    }


def apply_duplicate_track(context, operation):
    source = context.resolve_track(operation)
    ref_id = operation.get("id")
    new_index = source["track_index"] + 1
    name = operation.get("name")
    if not context.dry_run:
        try:
            context.song.duplicate_track(source["track_index"])
        except Exception as exc:
            raise BridgeRequestError("write_failed", "Failed to duplicate track %s: %s" % (source["track_index"], exc))
        tracks = safe_list(context.song, "tracks")
        track = safe_index(tracks, new_index)
        if track is not None and name:
            try:
                track.name = name
            except Exception:
                pass
        if ref_id:
            context.store_ref(ref_id, {"kind": "track", "track": track, "track_index": new_index})
    else:
        context.track_count += 1
        if ref_id:
            context.store_ref(ref_id, {"kind": "track", "track": None, "track_index": new_index})
    return {
        "type": "duplicate_track",
        "id": ref_id,
        "source_track_index": source["track_index"],
        "track_index": new_index,
        "name": name,
    }


def apply_delete_track(context, operation):
    require_allow_destructive(operation, "delete_track")
    track_index = required_index(operation, "track_index")
    tracks = safe_list(context.song, "tracks")
    if track_index >= len(tracks):
        raise BridgeRequestError("not_found", "No track at index %s" % track_index)
    name = safe_get(tracks[track_index], "name")
    assert_expected_track_name(operation, tracks[track_index], track_index, "track")
    if not context.dry_run:
        try:
            context.song.delete_track(track_index)
        except Exception as exc:
            raise BridgeRequestError("write_failed", "Failed to delete track %s: %s" % (track_index, exc))
    return {"type": "delete_track", "track_index": track_index, "name": name}


def apply_create_scene(context, operation):
    ref_id = require_operation_id(operation)
    requested_index = operation.get("index", -1)
    try:
        requested_index = int(requested_index)
    except Exception:
        raise BridgeRequestError("bad_plan", "create_scene index must be an integer")
    current_count = context.scene_count if context.dry_run else len(safe_list(context.song, "scenes"))
    scene_index = current_count if requested_index < 0 else requested_index
    if scene_index > current_count:
        raise BridgeRequestError("bad_plan", "create_scene index is out of range")
    name = operation.get("name") or "AI Scene"
    if context.dry_run:
        context.store_ref(ref_id, {"kind": "scene", "scene": None, "scene_index": scene_index})
        context.scene_count += 1
    else:
        context.song.create_scene(scene_index)
        scene = safe_list(context.song, "scenes")[scene_index]
        try:
            scene.name = name
        except Exception:
            pass
        context.store_ref(ref_id, {"kind": "scene", "scene": scene, "scene_index": scene_index})
    return {"type": "create_scene", "id": ref_id, "scene_index": scene_index, "name": name}


def apply_duplicate_scene(context, operation):
    scene_ref = context.resolve_scene(operation)
    scene_index = scene_ref["scene_index"]
    ref_id = operation.get("id")
    new_index = scene_index + 1
    name = operation.get("name")
    if not context.dry_run:
        try:
            context.song.duplicate_scene(scene_index)
        except Exception as exc:
            raise BridgeRequestError("write_failed", "Failed to duplicate scene %s: %s" % (scene_index, exc))
        scene = safe_index(safe_list(context.song, "scenes"), new_index)
        if scene is not None and name:
            try:
                scene.name = name
            except Exception:
                pass
        if ref_id:
            context.store_ref(ref_id, {"kind": "scene", "scene": scene, "scene_index": new_index})
    else:
        context.scene_count += 1
        if ref_id:
            context.store_ref(ref_id, {"kind": "scene", "scene": None, "scene_index": new_index})
    return {
        "type": "duplicate_scene",
        "id": ref_id,
        "source_scene_index": scene_index,
        "scene_index": new_index,
        "name": name,
    }


def apply_delete_scene(context, operation):
    require_allow_destructive(operation, "delete_scene")
    scene_ref = context.resolve_scene(operation)
    scene_index = scene_ref["scene_index"]
    name = safe_get(scene_ref.get("scene"), "name")
    if not context.dry_run:
        try:
            context.song.delete_scene(scene_index)
        except Exception as exc:
            raise BridgeRequestError("write_failed", "Failed to delete scene %s: %s" % (scene_index, exc))
    return {"type": "delete_scene", "scene_index": scene_index, "name": name}


def apply_set_tempo(context, operation):
    tempo = positive_float(operation.get("tempo"), "set_tempo tempo")
    if tempo < 20 or tempo > 999:
        raise BridgeRequestError("bad_plan", "set_tempo tempo must be between 20 and 999")
    previous = safe_get(context.song, "tempo")
    if not context.dry_run:
        context.song.tempo = tempo
    return {
        "type": "set_tempo",
        "previous": previous,
        "tempo": tempo,
    }


def apply_set_transport(context, operation):
    song = context.song
    action = operation.get("action")
    updates = []
    for field in ("metronome", "loop", "punch_in", "punch_out", "overdub", "session_record"):
        if field in operation:
            value = required_bool(operation.get(field), "set_transport %s" % field)
            updates.append({"field": field, "previous": safe_get(song, field), "value": value})
    for field in ("current_song_time", "loop_start", "start_time"):
        if field in operation:
            value = non_negative_float(operation.get(field), "set_transport %s" % field)
            updates.append({"field": field, "previous": safe_get(song, field), "value": value})
    if "loop_length" in operation:
        value = positive_float(operation.get("loop_length"), "set_transport loop_length")
        updates.append({"field": "loop_length", "previous": safe_get(song, "loop_length"), "value": value})

    if not context.dry_run:
        for update in updates:
            try:
                setattr(song, update["field"], update["value"])
            except Exception as exc:
                raise BridgeRequestError("write_failed", "Failed to set transport %s: %s" % (update["field"], exc))
        apply_transport_action(song, operation)

    return {
        "type": "set_transport",
        "action": action,
        "updates": updates,
    }


def apply_transport_action(song, operation):
    action = operation.get("action")
    if action in (None, "", "none"):
        return
    try:
        if action in ("play", "start"):
            song.start_playing()
        elif action == "stop":
            song.stop_playing()
        elif action == "continue":
            song.continue_playing()
        elif action == "jump_by":
            song.jump_by(float(operation.get("beats", 0.0)))
        elif action == "stop_all_clips":
            if "quantized" in operation:
                song.stop_all_clips(1 if required_bool(operation.get("quantized"), "stop_all_clips quantized") else 0)
            else:
                song.stop_all_clips()
        elif action == "tap_tempo":
            song.tap_tempo()
        else:
            raise BridgeRequestError("bad_plan", "Unsupported transport action: %s" % action)
    except BridgeRequestError:
        raise
    except Exception as exc:
        raise BridgeRequestError("write_failed", "Failed transport action %s: %s" % (action, exc))


def apply_set_track_state(context, operation):
    track_ref = context.resolve_track(operation)
    track = track_ref.get("track")
    updates = []

    if "name" in operation:
        name = str(operation.get("name"))
        updates.append(track_state_update(track, "name", name))
    for field in ("mute", "solo", "arm"):
        if field in operation:
            value = required_bool(operation.get(field), "set_track_state %s" % field)
            if field == "arm" and value and track is not None and not safe_get(track, "can_be_armed"):
                raise BridgeRequestError("bad_plan", "Track %s cannot be armed" % track_ref["track_index"])
            updates.append(track_state_update(track, field, value))

    if not updates:
        raise BridgeRequestError("bad_plan", "set_track_state requires at least one field")

    if not context.dry_run and track is not None:
        for update in updates:
            try:
                setattr(track, update["field"], update["value"])
            except Exception as exc:
                raise BridgeRequestError(
                    "write_failed",
                    "Failed to set track %s %s: %s" % (track_ref["track_index"], update["field"], exc),
                )

    return {
        "type": "set_track_state",
        "track_index": track_ref["track_index"],
        "updates": updates,
    }


def track_state_update(track, field, value):
    return {
        "field": field,
        "previous": safe_get(track, field),
        "value": value,
    }


def apply_set_track_mixer(context, operation):
    track_ref = context.resolve_track(operation)
    track = track_ref.get("track")
    mixer = safe_get(track, "mixer_device")
    updates = []

    if "volume" in operation:
        updates.append(
            mixer_update("volume", safe_get(mixer, "volume"), operation.get("volume"), context.dry_run)
        )
    if "panning" in operation:
        updates.append(
            mixer_update("panning", safe_get(mixer, "panning"), operation.get("panning"), context.dry_run)
        )
    updates.extend(send_updates(mixer, operation.get("sends"), context.dry_run))

    if not updates:
        raise BridgeRequestError("bad_plan", "set_track_mixer requires volume, panning, or sends")

    if not context.dry_run:
        for update in updates:
            parameter = update.pop("_parameter")
            if parameter is None:
                raise BridgeRequestError("write_failed", "Missing mixer parameter: %s" % update["parameter"])
            try:
                parameter.value = update["value"]
            except Exception as exc:
                raise BridgeRequestError(
                    "write_failed",
                    "Failed to set track %s %s: %s" % (track_ref["track_index"], update["parameter"], exc),
                )
    else:
        for update in updates:
            update.pop("_parameter", None)

    return {
        "type": "set_track_mixer",
        "track_index": track_ref["track_index"],
        "updates": updates,
    }


def apply_set_device_parameter(context, operation):
    target = resolve_device_parameter(context.song, operation)
    parameter = target["parameter"]
    value = parameter_value(target["parameter_name"], parameter, operation.get("value"))
    previous = safe_get(parameter, "value")
    if not context.dry_run:
        try:
            parameter.value = value
        except Exception as exc:
            raise BridgeRequestError(
                "write_failed",
                "Failed to set %s: %s" % (target["label"], exc),
            )

    return {
        "type": "set_device_parameter",
        "track_type": target["track_type"],
        "track_index": target["track_index"],
        "track_name": target["track_name"],
        "device_index": target["device_index"],
        "device_name": target["device_name"],
        "parameter_index": target["parameter_index"],
        "parameter_name": target["parameter_name"],
        "previous": previous,
        "value": value,
        "min": parameter_min(target["parameter_name"], parameter),
        "max": parameter_max(target["parameter_name"], parameter),
    }


def apply_insert_device(context, operation):
    target = resolve_plan_track_target(context, operation)
    track = target["track"]
    device_name = operation.get("device_name")
    if not device_name:
        raise BridgeRequestError("bad_plan", "insert_device requires device_name")
    target_index = operation.get("target_index")
    if target_index is not None:
        target_index = int_range(target_index, 0, 256, "insert_device target_index")

    previous_device_count = len(safe_list(track, "devices"))
    if not context.dry_run:
        try:
            if target_index is None:
                track.insert_device(str(device_name))
            else:
                track.insert_device(str(device_name), target_index)
        except Exception as exc:
            raise BridgeRequestError("write_failed", "Failed to insert device %r: %s" % (device_name, exc))

    return {
        "type": "insert_device",
        "track_type": target["track_type"],
        "track_index": target["track_index"],
        "track_name": target["track_name"],
        "device_name": device_name,
        "target_index": target_index,
        "previous_device_count": previous_device_count,
    }


def apply_load_browser_item(context, operation):
    target = resolve_plan_track_target(context, operation)
    track = target["track"]
    previous_device_count = len(safe_list(track, "devices"))
    item_ref, item_info = resolve_browser_item(context.browser, operation)

    if not context.dry_run:
        view = safe_get(context.song, "view")
        try:
            view.selected_track = track
        except Exception as exc:
            raise BridgeRequestError(
                "write_failed",
                "Failed to select track %r before loading browser item: %s" % (target["track_name"], exc),
            )
        try:
            context.browser.load_item(item_ref)
        except Exception as exc:
            raise BridgeRequestError(
                "write_failed",
                "Failed to load browser item %r: %s" % (item_info.get("name"), exc),
            )

    return {
        "type": "load_browser_item",
        "track_type": target["track_type"],
        "track_index": target["track_index"],
        "track_name": target["track_name"],
        "browser_item": item_info,
        "previous_device_count": previous_device_count,
    }


def resolve_device_parameter(song, operation):
    track_type, track_index, track = resolve_track_target(song, operation)
    device_index = required_index(operation, "device_index")
    parameter_index = required_index(operation, "parameter_index")

    devices = safe_list(track, "devices")
    if device_index >= len(devices):
        raise BridgeRequestError(
            "not_found",
            "No device at %s track %s device index %s" % (track_type, track_index, device_index),
        )
    device = devices[device_index]
    assert_optional_name(operation, "device_name", safe_get(device, "name"), "device")

    parameters = safe_list(device, "parameters")
    if parameter_index >= len(parameters):
        raise BridgeRequestError(
            "not_found",
            "No parameter at %s track %s device %s parameter index %s"
            % (track_type, track_index, device_index, parameter_index),
        )
    parameter = parameters[parameter_index]
    assert_optional_name(operation, "parameter_name", safe_get(parameter, "name"), "parameter")
    if safe_get(parameter, "is_enabled") is False:
        raise BridgeRequestError("bad_plan", "Device parameter is disabled: %s" % safe_get(parameter, "name"))

    label = "%s:%s device:%s parameter:%s" % (track_type, track_index, device_index, parameter_index)
    return {
        "track_type": track_type,
        "track_index": track_index,
        "track_name": safe_get(track, "name"),
        "device_index": device_index,
        "device_name": safe_get(device, "name"),
        "parameter_index": parameter_index,
        "parameter_name": safe_get(parameter, "name"),
        "parameter": parameter,
        "label": label,
    }


def resolve_track_target(song, operation):
    track_type = operation.get("track_type", "track")
    if track_type == "track":
        track_index = required_index(operation, "track_index")
        tracks = safe_list(song, "tracks")
    elif track_type in ("return", "return_track"):
        track_type = "return"
        track_index = required_index(operation, "track_index")
        tracks = safe_list(song, "return_tracks")
    elif track_type == "master":
        track_index = 0
        track = safe_get(song, "master_track")
        assert_expected_track_name(operation, track, track_index, "master track")
        return track_type, track_index, track
    else:
        raise BridgeRequestError("bad_plan", "Unsupported track_type: %s" % track_type)

    if track_index >= len(tracks):
        raise BridgeRequestError("not_found", "No %s track at index %s" % (track_type, track_index))
    track = tracks[track_index]
    assert_expected_track_name(operation, track, track_index, "%s track" % track_type)
    return track_type, track_index, track


def resolve_plan_track_target(context, operation):
    if "track_ref" in operation:
        track_ref = context.resolve_track(operation)
        track = track_ref["track"]
        return {
            "track_type": "track",
            "track_index": track_ref["track_index"],
            "track": track,
            "track_name": safe_get(track, "name"),
        }
    track_type, track_index, track = resolve_track_target(context.song, operation)
    return {
        "track_type": track_type,
        "track_index": track_index,
        "track": track,
        "track_name": safe_get(track, "name"),
    }


def require_allow_destructive(operation, operation_type):
    if operation.get("allow_destructive") is True:
        return
    raise BridgeRequestError(
        "bad_plan",
        "%s requires allow_destructive: true" % operation_type,
    )


def assert_optional_name(operation, field, actual, label):
    expected = operation.get(field)
    if expected is None:
        return
    if expected != actual:
        raise BridgeRequestError(
            "bad_plan",
            "Expected %s %s %r, got %r" % (label, field, expected, actual),
        )


def assert_expected_track_name(operation, track, track_index, label):
    expected_name = operation.get("expected_track_name")
    if expected_name is None:
        return
    actual_name = safe_get(track, "name")
    if expected_name != actual_name:
        raise BridgeRequestError(
            "bad_plan",
            "Expected %s %s name %r, got %r" % (label, track_index, expected_name, actual_name),
        )


def assert_expected_scene_name(operation, scene, scene_index):
    expected_name = operation.get("expected_scene_name")
    if expected_name is None:
        return
    actual_name = safe_get(scene, "name")
    if expected_name != actual_name:
        raise BridgeRequestError(
            "bad_plan",
            "Expected scene %s name %r, got %r" % (scene_index, expected_name, actual_name),
        )


def assert_expected_clip_name(operation, clip, scene_index):
    expected_name = operation.get("expected_clip_name")
    if expected_name is None:
        return
    actual_name = safe_get(clip, "name")
    if expected_name != actual_name:
        raise BridgeRequestError(
            "bad_plan",
            "Expected clip at scene %s name %r, got %r" % (scene_index, expected_name, actual_name),
        )


def mixer_update(parameter_name, parameter, raw_value, dry_run):
    value = parameter_value(parameter_name, parameter, raw_value)
    return {
        "parameter": parameter_name,
        "previous": safe_get(parameter, "value"),
        "value": value,
        "min": parameter_min(parameter_name, parameter),
        "max": parameter_max(parameter_name, parameter),
        "_parameter": parameter if not dry_run else None,
    }


def send_updates(mixer, raw_sends, dry_run):
    if raw_sends is None:
        return []
    sends = safe_list(mixer, "sends")
    updates = []
    for send in parse_sends(raw_sends):
        send_index = send["index"]
        parameter = safe_index(sends, send_index)
        if sends and parameter is None:
            raise BridgeRequestError("not_found", "No send at index %s" % send_index)
        updates.append(
            mixer_update("send:%s" % send_index, parameter, send["value"], dry_run)
        )
    return updates


def parse_sends(raw_sends):
    if isinstance(raw_sends, dict):
        sends = []
        for index, value in raw_sends.items():
            sends.append({"index": int_range(index, 0, 64, "send index"), "value": value})
        return sorted(sends, key=lambda item: item["index"])
    if not isinstance(raw_sends, list):
        raise BridgeRequestError("bad_plan", "set_track_mixer sends must be a list or object")

    sends = []
    for item in raw_sends:
        if not isinstance(item, dict):
            raise BridgeRequestError("bad_plan", "Each send update must be an object")
        sends.append(
            {
                "index": int_range(item.get("index"), 0, 64, "send index"),
                "value": item.get("value"),
            }
        )
    return sends


def parameter_value(parameter_name, parameter, raw_value):
    try:
        value = float(raw_value)
    except Exception:
        raise BridgeRequestError("bad_plan", "%s value must be a number" % parameter_name)
    minimum = parameter_min(parameter_name, parameter)
    maximum = parameter_max(parameter_name, parameter)
    if value < minimum or value > maximum:
        raise BridgeRequestError(
            "bad_plan",
            "%s value must be between %s and %s" % (parameter_name, minimum, maximum),
        )
    if parameter is not None and safe_get(parameter, "is_enabled") is False:
        raise BridgeRequestError("bad_plan", "%s parameter is disabled" % parameter_name)
    return value


def parameter_min(parameter_name, parameter):
    value = safe_get(parameter, "min")
    if value is not None:
        return value
    if parameter_name == "panning":
        return -1.0
    return 0.0


def parameter_max(parameter_name, parameter):
    value = safe_get(parameter, "max")
    if value is not None:
        return value
    return 1.0


def apply_create_midi_clip(context, operation):
    ref_id = require_operation_id(operation)
    track_ref = context.resolve_track(operation)
    scene_ref = context.resolve_scene(operation)
    scene_index = scene_ref["scene_index"]
    length = positive_float(operation.get("length"), "create_midi_clip length")
    name = operation.get("name") or "AI MIDI Clip"

    if context.dry_run:
        context.store_ref(
            ref_id,
            {
                "kind": "clip",
                "clip": None,
                "track_index": track_ref["track_index"],
                "scene_index": scene_index,
                "length": length,
            },
        )
    else:
        track = track_ref["track"]
        slots = safe_list(track, "clip_slots")
        if scene_index >= len(slots):
            raise BridgeRequestError("not_found", "No clip slot at scene index %s" % scene_index)
        slot = slots[scene_index]
        if safe_get(slot, "clip") is not None:
            raise BridgeRequestError(
                "would_overwrite",
                "Refusing to overwrite clip at track %s scene %s" % (track_ref["track_index"], scene_index),
            )
        slot.create_clip(length)
        clip = safe_get(slot, "clip")
        try:
            clip.name = name
        except Exception:
            pass
        context.store_ref(
            ref_id,
            {"kind": "clip", "clip": clip, "track_index": track_ref["track_index"], "scene_index": scene_index},
        )

    return {
        "type": "create_midi_clip",
        "id": ref_id,
        "track_index": track_ref["track_index"],
        "scene_index": scene_index,
        "length": length,
        "name": name,
    }


def apply_add_notes(context, operation):
    clip_ref = context.resolve_clip(operation)
    raw_notes = operation.get("notes")
    if not isinstance(raw_notes, list):
        raise BridgeRequestError("bad_plan", "add_notes notes must be a list")
    notes = [normalize_plan_note(note) for note in raw_notes]
    if len(notes) > MAX_NOTES_PER_CLIP:
        raise BridgeRequestError("bad_plan", "add_notes has too many notes")

    if not context.dry_run:
        write_result = write_notes_to_clip(clip_ref["clip"], notes)
    else:
        write_result = {"source": "dry_run", "returned_note_count": None}

    return {
        "type": "add_notes",
        "clip_ref": operation.get("clip_ref"),
        "track_index": clip_ref["track_index"],
        "scene_index": clip_ref["scene_index"],
        "note_count": len(notes),
        "source": write_result.get("source"),
        "returned_note_count": write_result.get("returned_note_count"),
        "write_attempts": write_result.get("attempts"),
    }


def apply_modify_notes(context, operation):
    clip_ref = context.resolve_clip(operation)
    raw_patches = operation.get("patches")
    if not isinstance(raw_patches, list):
        raise BridgeRequestError("bad_plan", "modify_notes patches must be a list")
    patches = [normalize_note_patch(patch) for patch in raw_patches]
    if not context.dry_run:
        modified_notes, matched_note_ids = build_modified_notes(clip_ref["clip"], patches)
        write_result = apply_note_modifications(clip_ref["clip"], modified_notes)
    else:
        matched_note_ids = []
        write_result = {"source": "dry_run", "modified_count": len(patches), "attempts": []}

    return {
        "type": "modify_notes",
        "clip_ref": operation.get("clip_ref"),
        "track_index": clip_ref["track_index"],
        "scene_index": clip_ref["scene_index"],
        "patch_count": len(patches),
        "matched_note_ids": matched_note_ids,
        "source": write_result.get("source"),
        "modified_count": write_result.get("modified_count"),
        "write_attempts": write_result.get("attempts"),
    }


def apply_remove_notes(context, operation):
    clip_ref = context.resolve_clip(operation)
    mode = remove_notes_mode(operation)
    if context.dry_run:
        return {
            "type": "remove_notes",
            "clip_ref": operation.get("clip_ref"),
            "track_index": clip_ref["track_index"],
            "scene_index": clip_ref["scene_index"],
            "mode": mode,
            "removed_note_ids": [],
            "source": "dry_run",
        }

    if mode == "region":
        result = remove_notes_by_region(clip_ref["clip"], operation.get("region"))
        removed_note_ids = []
    else:
        note_ids = resolve_remove_note_ids(clip_ref["clip"], operation)
        result = remove_notes_by_id(clip_ref["clip"], note_ids)
        removed_note_ids = note_ids

    return {
        "type": "remove_notes",
        "clip_ref": operation.get("clip_ref"),
        "track_index": clip_ref["track_index"],
        "scene_index": clip_ref["scene_index"],
        "mode": mode,
        "removed_note_ids": removed_note_ids,
        "source": result.get("source"),
        "write_attempts": result.get("attempts"),
    }


def apply_quantize_clip(context, operation):
    clip_ref = context.resolve_clip(operation)
    grid = int_range(operation.get("quantization_grid"), 0, 64, "quantize_clip quantization_grid")
    amount = float_range(operation.get("amount", 1.0), 0.0, 1.0, "quantize_clip amount")
    if not context.dry_run:
        clip = clip_ref["clip"]
        if not hasattr(clip, "quantize"):
            raise BridgeRequestError("write_failed", "Clip does not support quantize")
        try:
            clip.quantize(grid, amount)
        except Exception as exc:
            raise BridgeRequestError("write_failed", "Failed to quantize clip: %s" % exc)
    return {
        "type": "quantize_clip",
        "clip_ref": operation.get("clip_ref"),
        "track_index": clip_ref["track_index"],
        "scene_index": clip_ref["scene_index"],
        "quantization_grid": grid,
        "amount": amount,
    }


def apply_duplicate_clip_loop(context, operation):
    clip_ref = context.resolve_clip(operation)
    if not context.dry_run:
        clip = clip_ref["clip"]
        if not hasattr(clip, "duplicate_loop"):
            raise BridgeRequestError("write_failed", "Clip does not support duplicate_loop")
        try:
            clip.duplicate_loop()
        except Exception as exc:
            raise BridgeRequestError("write_failed", "Failed to duplicate clip loop: %s" % exc)
    return {
        "type": "duplicate_clip_loop",
        "clip_ref": operation.get("clip_ref"),
        "track_index": clip_ref["track_index"],
        "scene_index": clip_ref["scene_index"],
    }


def apply_crop_clip(context, operation):
    clip_ref = context.resolve_clip(operation)
    if not context.dry_run:
        clip = clip_ref["clip"]
        if not hasattr(clip, "crop"):
            raise BridgeRequestError("write_failed", "Clip does not support crop")
        try:
            clip.crop()
        except Exception as exc:
            raise BridgeRequestError("write_failed", "Failed to crop clip: %s" % exc)
    return {
        "type": "crop_clip",
        "clip_ref": operation.get("clip_ref"),
        "track_index": clip_ref["track_index"],
        "scene_index": clip_ref["scene_index"],
    }


def apply_fire_clip_slot(context, operation):
    target = resolve_clip_slot(context, operation)
    if not context.dry_run:
        fire_clip_slot(target["slot"], operation)
    return {
        "type": "fire_clip_slot",
        "track_index": target["track_index"],
        "scene_index": target["scene_index"],
        "has_clip": target["has_clip"],
    }


def apply_stop_clip_slot(context, operation):
    target = resolve_clip_slot(context, operation)
    if not context.dry_run:
        try:
            target["slot"].stop()
        except Exception as exc:
            raise BridgeRequestError("write_failed", "Failed to stop clip slot: %s" % exc)
    return {
        "type": "stop_clip_slot",
        "track_index": target["track_index"],
        "scene_index": target["scene_index"],
        "has_clip": target["has_clip"],
    }


def apply_fire_scene(context, operation):
    scene_ref = context.resolve_scene(operation)
    scene_index = scene_ref["scene_index"]
    if not context.dry_run:
        try:
            scene_ref["scene"].fire()
        except Exception as exc:
            raise BridgeRequestError("write_failed", "Failed to fire scene %s: %s" % (scene_index, exc))
    return {"type": "fire_scene", "scene_index": scene_index, "scene_name": safe_get(scene_ref.get("scene"), "name")}


def resolve_clip_slot(context, operation):
    track_ref = context.resolve_track(operation)
    scene_ref = context.resolve_scene(operation)
    scene_index = scene_ref["scene_index"]
    if context.dry_run:
        if operation.get("expected_clip_name") is not None and track_ref.get("track") is not None:
            slots = safe_list(track_ref["track"], "clip_slots")
            if scene_index >= len(slots):
                raise BridgeRequestError("not_found", "No clip slot at scene index %s" % scene_index)
            clip = safe_get(slots[scene_index], "clip")
            if clip is None:
                raise BridgeRequestError("not_found", "No clip at scene index %s" % scene_index)
            assert_expected_clip_name(operation, clip, scene_index)
        return {
            "track_index": track_ref["track_index"],
            "scene_index": scene_index,
            "slot": None,
            "has_clip": None,
        }
    slots = safe_list(track_ref["track"], "clip_slots")
    if scene_index >= len(slots):
        raise BridgeRequestError("not_found", "No clip slot at scene index %s" % scene_index)
    slot = slots[scene_index]
    clip = safe_get(slot, "clip")
    if operation.get("expected_clip_name") is not None:
        if clip is None:
            raise BridgeRequestError("not_found", "No clip at scene index %s" % scene_index)
        assert_expected_clip_name(operation, clip, scene_index)
    return {
        "track_index": track_ref["track_index"],
        "scene_index": scene_index,
        "slot": slot,
        "has_clip": bool(clip),
    }


def fire_clip_slot(slot, operation):
    try:
        record_length = operation.get("record_length")
        launch_quantization = operation.get("launch_quantization")
        if record_length is not None and launch_quantization is not None:
            slot.fire(float(record_length), int(launch_quantization))
        elif record_length is not None:
            slot.fire(float(record_length))
        elif launch_quantization is not None:
            slot.fire(None, int(launch_quantization))
        else:
            slot.fire()
    except Exception as exc:
        raise BridgeRequestError("write_failed", "Failed to fire clip slot: %s" % exc)


def normalize_note_patch(patch):
    if not isinstance(patch, dict):
        raise BridgeRequestError("bad_plan", "Each modify_notes patch must be an object")
    selector = note_selector_from_patch(patch)
    updates = normalize_note_updates(patch.get("set"))
    allow_multiple = bool(patch.get("allow_multiple", False))
    return {"selector": selector, "updates": updates, "allow_multiple": allow_multiple}


def note_selector_from_patch(patch):
    if "note_id" in patch:
        return {"note_id": int_range(patch.get("note_id"), 0, 2147483647, "note_id")}
    if "match" in patch:
        return {"match": normalize_note_match(patch.get("match"))}
    raise BridgeRequestError("bad_plan", "modify_notes patch requires note_id or match")


def normalize_note_updates(raw_updates):
    if not isinstance(raw_updates, dict):
        raise BridgeRequestError("bad_plan", "note patch set must be an object")
    updates = {}
    for key, value in raw_updates.items():
        if key == "pitch":
            updates[key] = int_range(value, 0, 127, "note pitch")
        elif key == "start_time":
            updates[key] = non_negative_float(value, "note start_time")
        elif key == "duration":
            updates[key] = positive_float(value, "note duration")
        elif key == "velocity":
            updates[key] = int_range(value, 1, 127, "note velocity")
        elif key == "mute":
            updates[key] = required_bool(value, "note mute")
        elif key == "probability":
            updates[key] = float_range(value, 0.0, 1.0, "note probability")
        elif key == "velocity_deviation":
            updates[key] = float_range(value, -127.0, 127.0, "note velocity_deviation")
        elif key == "release_velocity":
            updates[key] = int_range(value, 0, 127, "note release_velocity")
        else:
            raise BridgeRequestError("bad_plan", "Unsupported note update field: %s" % key)
    if not updates:
        raise BridgeRequestError("bad_plan", "note patch set cannot be empty")
    return updates


def normalize_note_match(raw_match):
    if not isinstance(raw_match, dict):
        raise BridgeRequestError("bad_plan", "note match must be an object")
    match = {}
    for key, value in raw_match.items():
        if key == "note_id":
            match[key] = int_range(value, 0, 2147483647, "note_id")
        elif key == "pitch":
            match[key] = int_range(value, 0, 127, "note pitch")
        elif key in ("start_time", "duration", "velocity", "probability", "velocity_deviation", "release_velocity"):
            match[key] = float(value)
        elif key == "mute":
            match[key] = required_bool(value, "note mute")
        else:
            raise BridgeRequestError("bad_plan", "Unsupported note match field: %s" % key)
    if not match:
        raise BridgeRequestError("bad_plan", "note match cannot be empty")
    return match


def build_modified_notes(clip, patches):
    note_store = read_note_entries_for_edit(clip)
    matched_note_ids = []
    for patch in patches:
        matches = find_note_entries(note_store["entries"], patch["selector"])
        if not matches:
            raise BridgeRequestError("not_found", "No note matched selector %r" % patch["selector"])
        if len(matches) > 1 and not patch["allow_multiple"]:
            raise BridgeRequestError(
                "bad_plan",
                "Selector %r matched %s notes; set allow_multiple to modify all"
                % (patch["selector"], len(matches)),
            )
        for entry in matches:
            updated = dict(entry["note"])
            for key, value in patch["updates"].items():
                updated[key] = value
            if "note_id" not in updated:
                raise BridgeRequestError("bad_plan", "Cannot modify note without note_id")
            update_note_object(entry["raw"], patch["updates"])
            matched_note_ids.append(updated.get("note_id"))
    return note_store["raw_collection"], matched_note_ids


def apply_note_modifications(clip, notes):
    if clip is None:
        raise BridgeRequestError("bad_plan", "Cannot modify notes without a clip")
    if not hasattr(clip, "apply_note_modifications"):
        raise BridgeRequestError("write_failed", "Clip does not support apply_note_modifications")
    attempts = []
    payloads = [("apply_note_modifications_raw_collection", notes)]
    try:
        payloads.append(("apply_note_modifications_wrapped_list", {"notes": list(notes)}))
        payloads.append(("apply_note_modifications_wrapped_tuple", {"notes": tuple(notes)}))
        payloads.append(("apply_note_modifications_list", list(notes)))
        payloads.append(("apply_note_modifications_tuple", tuple(notes)))
    except Exception as exc:
        attempts.append("prepare fallback payloads: %s" % exc)
    for name, payload in payloads:
        try:
            clip.apply_note_modifications(payload)
            attempts.append("%s: ok" % name)
            return {"source": name, "modified_count": safe_len(notes), "attempts": trim_attempts(attempts)}
        except Exception as exc:
            attempts.append("%s: %s" % (name, exc))
    raise BridgeRequestError("write_failed", "; ".join(attempts))


def remove_notes_mode(operation):
    if "region" in operation:
        return "region"
    if "note_ids" in operation or "match" in operation or "matches" in operation:
        return "ids"
    raise BridgeRequestError("bad_plan", "remove_notes requires note_ids, match, matches, or region")


def resolve_remove_note_ids(clip, operation):
    if "note_ids" in operation:
        raw_note_ids = operation.get("note_ids")
        if not isinstance(raw_note_ids, list):
            raise BridgeRequestError("bad_plan", "remove_notes note_ids must be a list")
        return [int_range(value, 0, 2147483647, "note_id") for value in raw_note_ids]

    selectors = []
    if "match" in operation:
        selectors.append({"match": normalize_note_match(operation.get("match"))})
    if "matches" in operation:
        raw_matches = operation.get("matches")
        if not isinstance(raw_matches, list):
            raise BridgeRequestError("bad_plan", "remove_notes matches must be a list")
        selectors.extend([{"match": normalize_note_match(match)} for match in raw_matches])
    if not selectors:
        raise BridgeRequestError("bad_plan", "remove_notes has no note selectors")

    note_store = read_note_entries_for_edit(clip)
    note_ids = []
    for selector in selectors:
        matches = find_note_entries(note_store["entries"], selector)
        if not matches:
            raise BridgeRequestError("not_found", "No note matched selector %r" % selector)
        for entry in matches:
            note_id = entry["note"].get("note_id")
            if note_id is None:
                raise BridgeRequestError("bad_plan", "Cannot remove matched note without note_id")
            if note_id not in note_ids:
                note_ids.append(note_id)
    return note_ids


def remove_notes_by_id(clip, note_ids):
    if clip is None:
        raise BridgeRequestError("bad_plan", "Cannot remove notes without a clip")
    if not note_ids:
        raise BridgeRequestError("bad_plan", "remove_notes note_ids cannot be empty")
    if not hasattr(clip, "remove_notes_by_id"):
        raise BridgeRequestError("write_failed", "Clip does not support remove_notes_by_id")
    attempts = []
    for name, payload in [
        ("remove_notes_by_id_list", note_ids),
        ("remove_notes_by_id_tuple", tuple(note_ids)),
    ]:
        try:
            clip.remove_notes_by_id(payload)
            attempts.append("%s: ok" % name)
            return {"source": name, "attempts": trim_attempts(attempts)}
        except Exception as exc:
            attempts.append("%s: %s" % (name, exc))
    raise BridgeRequestError("write_failed", "; ".join(attempts))


def remove_notes_by_region(clip, raw_region):
    if clip is None:
        raise BridgeRequestError("bad_plan", "Cannot remove notes without a clip")
    if not isinstance(raw_region, dict):
        raise BridgeRequestError("bad_plan", "remove_notes region must be an object")
    if not hasattr(clip, "remove_notes_extended"):
        raise BridgeRequestError("write_failed", "Clip does not support remove_notes_extended")
    from_pitch = int_range(raw_region.get("from_pitch", 0), 0, 127, "region from_pitch")
    pitch_span = int_range(raw_region.get("pitch_span", 128), 1, 128, "region pitch_span")
    from_time = non_negative_float(raw_region.get("from_time", 0.0), "region from_time")
    time_span = positive_float(raw_region.get("time_span"), "region time_span")
    try:
        clip.remove_notes_extended(from_pitch, pitch_span, from_time, time_span)
        return {"source": "remove_notes_extended", "attempts": ["remove_notes_extended: ok"]}
    except Exception as exc:
        raise BridgeRequestError("write_failed", "Failed to remove notes by region: %s" % exc)


def read_note_entries_for_edit(clip):
    if clip is None:
        raise BridgeRequestError("bad_plan", "Cannot edit notes without a clip")
    if not safe_get(clip, "is_midi_clip"):
        raise BridgeRequestError("bad_plan", "Cannot edit notes in a non-MIDI clip")
    if not hasattr(clip, "get_all_notes_extended"):
        raise BridgeRequestError("write_failed", "Clip does not support get_all_notes_extended")
    try:
        raw_collection = clip.get_all_notes_extended()
        raw_notes = list(raw_collection)
    except Exception as exc:
        raise BridgeRequestError("write_failed", "Failed to read notes for edit: %s" % exc)
    if len(raw_notes) > MAX_NOTES_PER_CLIP:
        raise BridgeRequestError("bad_plan", "Cannot edit notes: clip has too many notes")
    entries = []
    for raw in raw_notes:
        note = normalize_note(raw)
        if not note:
            continue
        if "note_id" not in note:
            raise BridgeRequestError("bad_plan", "Cannot edit notes: note_id is not available")
        entries.append({"note": note, "raw": raw})
    return {"raw_collection": raw_collection, "entries": entries}


def update_note_object(note_object, updates):
    for key, value in updates.items():
        try:
            setattr(note_object, key, value)
        except Exception as exc:
            raise BridgeRequestError("write_failed", "Failed to update note %s: %s" % (key, exc))
    return note_object


def find_note_entries(entries, selector):
    if "note_id" in selector:
        note_id = selector.get("note_id")
        return [entry for entry in entries if entry["note"].get("note_id") == note_id]
    match = selector.get("match") or {}
    return [entry for entry in entries if note_matches(entry["note"], match)]


def note_matches(note, match):
    for key, expected in match.items():
        actual = note.get(key)
        if isinstance(expected, float):
            try:
                if abs(float(actual) - expected) > 0.0001:
                    return False
            except Exception:
                return False
        elif actual != expected:
            return False
    return True


def write_notes_to_clip(clip, notes):
    if clip is None:
        raise BridgeRequestError("bad_plan", "Cannot add notes without a clip")
    note_dicts = [plan_note_to_dict(note) for note in notes]
    attempts = []
    note_specs, spec_errors = plan_notes_to_specifications(notes)
    attempts.extend(spec_errors)
    if hasattr(clip, "add_new_notes"):
        spec_payloads = []
        if note_specs:
            spec_payloads = [
                ("add_new_notes_spec_tuple", tuple(note_specs)),
                ("add_new_notes_spec_list", note_specs),
            ]
        for name, payload in [
            *spec_payloads,
            ("add_new_notes_wrapped_list", {"notes": note_dicts}),
            ("add_new_notes_wrapped_tuple", {"notes": tuple(note_dicts)}),
            ("add_new_notes_list_dicts", note_dicts),
            ("add_new_notes_tuple_dicts", tuple(note_dicts)),
        ]:
            try:
                result = clip.add_new_notes(payload)
                attempts.append("%s: ok" % name)
                return write_notes_result(name, result, attempts)
            except Exception as exc:
                attempts.append("%s: %s" % (name, exc))

    if hasattr(clip, "replace_selected_notes"):
        try:
            if hasattr(clip, "select_all_notes"):
                clip.select_all_notes()
            clip.replace_selected_notes(tuple(plan_note_to_legacy_tuple(note) for note in notes))
            if hasattr(clip, "deselect_all_notes"):
                clip.deselect_all_notes()
            attempts.append("replace_selected_notes: ok")
            return write_notes_result("replace_selected_notes", None, attempts)
        except Exception as exc:
            attempts.append("replace_selected_notes: %s" % exc)

    raise BridgeRequestError("write_failed", "; ".join(attempts) or "No supported note write API")


def plan_notes_to_specifications(notes):
    note_class = midi_note_specification_class()
    if note_class is None:
        return [], ["MidiNoteSpecification: unavailable"]

    specifications = []
    errors = []
    for index, note in enumerate(notes):
        specification, note_errors = plan_note_to_specification(note_class, note)
        errors.extend(["note %s %s" % (index, error) for error in note_errors])
        if specification is None:
            return [], errors
        specifications.append(specification)
    return specifications, errors


def midi_note_specification_class():
    if Live is None:
        return None
    clip_module = safe_get(Live, "Clip")
    return safe_get(clip_module, "MidiNoteSpecification")


def plan_note_to_specification(note_class, note):
    full_payload = plan_note_to_dict(note)
    base_payload = {
        "pitch": note["pitch"],
        "start_time": note["start_time"],
        "duration": note["duration"],
        "velocity": note["velocity"],
        "mute": note["mute"],
    }
    errors = []

    try:
        return note_class(**full_payload), errors
    except Exception as exc:
        errors.append("MidiNoteSpecification full kwargs: %s" % exc)

    try:
        specification = note_class(**base_payload)
    except Exception as exc:
        errors.append("MidiNoteSpecification base kwargs: %s" % exc)
    else:
        errors.extend(set_note_specification_extras(specification, note))
        return specification, errors

    try:
        specification = note_class()
    except Exception as exc:
        errors.append("MidiNoteSpecification empty constructor: %s" % exc)
        return None, errors

    for key, value in full_payload.items():
        try:
            setattr(specification, key, value)
        except Exception as exc:
            errors.append("MidiNoteSpecification setattr %s: %s" % (key, exc))
    return specification, errors


def set_note_specification_extras(specification, note):
    errors = []
    for key in ("probability", "velocity_deviation", "release_velocity"):
        if key not in note:
            continue
        try:
            setattr(specification, key, note[key])
        except Exception as exc:
            errors.append("MidiNoteSpecification setattr %s: %s" % (key, exc))
    return errors


def write_notes_result(source, result, attempts):
    return {
        "source": source,
        "returned_note_count": returned_note_count(result),
        "attempts": trim_attempts(attempts),
    }


def trim_attempts(attempts):
    if len(attempts) <= MAX_WRITE_ATTEMPTS_REPORTED:
        return attempts
    omitted = len(attempts) - MAX_WRITE_ATTEMPTS_REPORTED
    return attempts[:MAX_WRITE_ATTEMPTS_REPORTED] + ["... %s more attempts omitted" % omitted]


def returned_note_count(result):
    if result is None:
        return None
    if isinstance(result, dict):
        for key in ("note_ids", "notes"):
            if key in result:
                return safe_len(result.get(key))
        return None
    return safe_len(result)


def safe_len(value):
    try:
        return len(value)
    except Exception:
        pass
    try:
        return len(list(value))
    except Exception:
        return None


def require_operation_id(operation):
    ref_id = operation.get("id")
    if not ref_id:
        raise BridgeRequestError("bad_plan", "Operation requires an id")
    return ref_id


def positive_float(value, label):
    try:
        parsed = float(value)
    except Exception:
        raise BridgeRequestError("bad_plan", "%s must be a number" % label)
    if parsed <= 0:
        raise BridgeRequestError("bad_plan", "%s must be > 0" % label)
    return parsed


def normalize_plan_note(note):
    if not isinstance(note, dict):
        raise BridgeRequestError("bad_plan", "Each note must be an object")
    pitch = int_range(note.get("pitch"), 0, 127, "note pitch")
    start_time = non_negative_float(note.get("start_time"), "note start_time")
    duration = positive_float(note.get("duration"), "note duration")
    velocity = int_range(note.get("velocity", 100), 1, 127, "note velocity")
    normalized = {
        "pitch": pitch,
        "start_time": start_time,
        "duration": duration,
        "velocity": velocity,
        "mute": bool(note.get("mute", False)),
    }
    if "probability" in note:
        normalized["probability"] = float_range(note.get("probability"), 0.0, 1.0, "note probability")
    if "velocity_deviation" in note:
        normalized["velocity_deviation"] = float_range(
            note.get("velocity_deviation"),
            -127.0,
            127.0,
            "note velocity_deviation",
        )
    if "release_velocity" in note:
        normalized["release_velocity"] = int_range(note.get("release_velocity"), 0, 127, "note release_velocity")
    return normalized


def plan_note_to_dict(note):
    payload = {
        "pitch": note["pitch"],
        "start_time": note["start_time"],
        "duration": note["duration"],
        "velocity": note["velocity"],
        "mute": note["mute"],
    }
    for key in ("probability", "velocity_deviation", "release_velocity"):
        if key in note:
            payload[key] = note[key]
    return payload


def plan_note_to_legacy_tuple(note):
    return (note["pitch"], note["start_time"], note["duration"], note["velocity"], note["mute"])


def int_range(value, minimum, maximum, label):
    try:
        parsed = int(value)
    except Exception:
        raise BridgeRequestError("bad_plan", "%s must be an integer" % label)
    if parsed < minimum or parsed > maximum:
        raise BridgeRequestError("bad_plan", "%s must be between %s and %s" % (label, minimum, maximum))
    return parsed


def required_bool(value, label):
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise BridgeRequestError("bad_plan", "%s must be a boolean" % label)


def float_range(value, minimum, maximum, label):
    try:
        parsed = float(value)
    except Exception:
        raise BridgeRequestError("bad_plan", "%s must be a number" % label)
    if parsed < minimum or parsed > maximum:
        raise BridgeRequestError("bad_plan", "%s must be between %s and %s" % (label, minimum, maximum))
    return parsed


def non_negative_float(value, label):
    try:
        parsed = float(value)
    except Exception:
        raise BridgeRequestError("bad_plan", "%s must be a number" % label)
    if parsed < 0:
        raise BridgeRequestError("bad_plan", "%s must be >= 0" % label)
    return parsed


def choose_notes_attempt(best, attempts, name, callback):
    try:
        raw = callback()
        notes = unpack_notes_result(raw)
        attempts.append({"source": name, "count": len(notes), "raw_type": type(raw).__name__})
        if len(notes) > len(best["notes"]):
            return {"source": name, "notes": notes}
    except Exception as exc:
        attempts.append({"source": name, "count": None, "error": str(exc)})
    return best


def unpack_notes_result(result):
    if result is None:
        return []
    if isinstance(result, dict):
        notes = result.get("notes", [])
        try:
            return list(notes)
        except Exception:
            return []
    try:
        return list(result)
    except Exception:
        return []


def normalize_note(note):
    if isinstance(note, dict):
        return normalize_note_dict(note)
    if hasattr(note, "items"):
        try:
            return normalize_note_dict(dict(note.items()))
        except Exception:
            pass
    object_note = normalize_note_object(note)
    if object_note:
        return object_note
    try:
        values = list(note)
    except Exception:
        return None
    if len(values) >= 5:
        return {
            "pitch": values[0],
            "start_time": values[1],
            "duration": values[2],
            "velocity": values[3],
            "mute": bool(values[4]),
        }
    return None


def normalize_note_dict(note):
    normalized = {}
    for key in NOTE_FIELDS:
        if key in note:
            normalized[key] = note[key]
    return normalized


def normalize_note_object(note):
    normalized = {}
    for key in NOTE_FIELDS:
        value = safe_get(note, key, None)
        if value is not None:
            normalized[key] = value
    if normalized:
        return normalized
    return None


def device_summary(device, index):
    if device is None:
        return None
    parameters = safe_list(device, "parameters")
    return {
        "index": index,
        "name": safe_get(device, "name"),
        "class_name": safe_get(device, "class_name"),
        "type": safe_get(device, "type"),
        "is_active": safe_get(device, "is_active"),
        "parameters": [parameter_summary(parameter, idx) for idx, parameter in enumerate(parameters[:24])],
        "parameter_count": len(parameters),
    }


def parameter_summary(parameter, index):
    if parameter is None:
        return None
    return {
        "index": index,
        "name": safe_get(parameter, "name"),
        "value": safe_get(parameter, "value"),
        "min": safe_get(parameter, "min"),
        "max": safe_get(parameter, "max"),
        "is_enabled": safe_get(parameter, "is_enabled"),
        "is_quantized": safe_get(parameter, "is_quantized"),
    }
