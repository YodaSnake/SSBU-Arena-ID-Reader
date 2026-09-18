from __future__ import annotations

import base64
import hashlib
import json
import uuid
from typing import Any

import websocket

OBS_URL = "ws://127.0.0.1:4455"


class ObsError(RuntimeError):
    pass


def build_authentication(password: str, salt: str, challenge: str) -> str:
    secret = base64.b64encode(
        hashlib.sha256((password + salt).encode("utf-8")).digest()
    ).decode("ascii")
    return base64.b64encode(
        hashlib.sha256((secret + challenge).encode("utf-8")).digest()
    ).decode("ascii")


class ObsClient:
    def __init__(self, password: str, url: str = OBS_URL, timeout: float = 5.0) -> None:
        self.password = password
        self.url = url
        self.timeout = timeout
        self._ws: websocket.WebSocket | None = None

    def __enter__(self) -> "ObsClient":
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def connect(self) -> None:
        if self._ws is not None:
            return

        ws: websocket.WebSocket | None = None
        try:
            ws = websocket.create_connection(
                self.url,
                timeout=self.timeout,
                subprotocols=["obswebsocket.json"],
            )
            hello = self._receive(ws)
            if hello.get("op") != 0:
                raise ObsError("OBS returned an unexpected handshake message.")

            hello_data = hello.get("d", {})
            identify: dict[str, Any] = {"rpcVersion": 1, "eventSubscriptions": 0}
            authentication = hello_data.get("authentication")
            if authentication is not None:
                if not self.password:
                    raise ObsError("OBS WebSocket requires a password.")
                identify["authentication"] = build_authentication(
                    self.password,
                    authentication["salt"],
                    authentication["challenge"],
                )

            ws.send(json.dumps({"op": 1, "d": identify}))
            identified = self._receive(ws)
            if identified.get("op") != 2:
                raise ObsError("OBS WebSocket authentication failed.")
            self._ws = ws
        except ObsError:
            if ws is not None:
                ws.close()
            raise
        except Exception as exc:
            if ws is not None:
                ws.close()
            raise ObsError(f"Could not connect to OBS: {exc}") from exc

    def close(self) -> None:
        if self._ws is not None:
            self._ws.close()
            self._ws = None

    def list_inputs(self) -> list[str]:
        data = self.request("GetInputList")
        names = [
            item["inputName"]
            for item in data.get("inputs", [])
            if isinstance(item.get("inputName"), str)
        ]
        return sorted(names, key=str.casefold)

    def get_source_screenshot(self, source_name: str) -> bytes:
        data = self.request(
            "GetSourceScreenshot",
            {"sourceName": source_name, "imageFormat": "png"},
        )
        image_data = data.get("imageData")
        if not isinstance(image_data, str) or "," not in image_data:
            raise ObsError("OBS returned an invalid screenshot payload.")
        try:
            return base64.b64decode(image_data.split(",", 1)[1], validate=True)
        except ValueError as exc:
            raise ObsError("OBS returned an invalid screenshot image.") from exc

    def request(
        self,
        request_type: str,
        request_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._ws is None:
            raise ObsError("OBS WebSocket is not connected.")

        request_id = uuid.uuid4().hex
        payload: dict[str, Any] = {
            "op": 6,
            "d": {"requestType": request_type, "requestId": request_id},
        }
        if request_data:
            payload["d"]["requestData"] = request_data
        self._ws.send(json.dumps(payload))

        while True:
            message = self._receive(self._ws)
            if message.get("op") != 7:
                continue
            data = message.get("d", {})
            if data.get("requestId") != request_id:
                continue
            status = data.get("requestStatus", {})
            if not status.get("result"):
                comment = status.get("comment") or "OBS rejected the request."
                raise ObsError(str(comment))
            response_data = data.get("responseData", {})
            return response_data if isinstance(response_data, dict) else {}

    @staticmethod
    def _receive(ws: websocket.WebSocket) -> dict[str, Any]:
        raw = ws.recv()
        if not isinstance(raw, str):
            raise ObsError("OBS returned a non-text WebSocket message.")
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ObsError("OBS returned invalid JSON.") from exc
        if not isinstance(message, dict):
            raise ObsError("OBS returned an invalid WebSocket message.")
        return message
