import json
import socket

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PROTOCOL_VERSION = 1


class BridgeConnectionError(RuntimeError):
    pass


class BridgeResponseError(RuntimeError):
    def __init__(self, command, code, message):
        super().__init__("%s failed: %s: %s" % (command, code, message))
        self.command = command
        self.code = code
        self.message = message


def send_request(command, args=None, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=5.0):
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "command": command,
        "args": args or {},
    }
    raw = json.dumps(payload).encode("utf-8") + b"\n"
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(raw)
            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\n" in chunk:
                    break
    except OSError as exc:
        raise BridgeConnectionError(str(exc)) from exc

    if not chunks:
        raise BridgeConnectionError("empty response from bridge")
    line = b"".join(chunks).split(b"\n", 1)[0]
    return json.loads(line.decode("utf-8"))


def require_ok(response, command):
    if response.get("ok"):
        return response.get("payload")
    error = response.get("error") or {}
    code = error.get("code", "unknown_error")
    message = error.get("message", "unknown error")
    raise BridgeResponseError(command, code, message)
