"""Protocolo confirmado no H3 V0.9.1.2; sem comandos de firmware ou reset."""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Protocol

MODES = {"normal": b"\x02\x00\x00", "barulho": b"\x01\x01\x02", "adaptavel": b"\x01\x05\x00"}
LABELS = {"normal": "Normal", "barulho": "Barulho", "adaptavel": "Adaptável"}
SERVICE = "0000a002-0000-1000-8000-00805f9b34fb"
WRITE = "00000001-0000-1000-8000-00805f9b34fb"
NOTIFY = "00000002-0000-1000-8000-00805f9b34fb"


class QCYError(Exception):
    """Falha apresentada ao usuário sem indicar sucesso da operação."""


@dataclass
class Settings:
    ble_address: str = ""
    audio_address: str = ""
    restore: bool = False
    preferred_mode: str = "adaptavel"

    def validate(self) -> None:
        for address in (self.ble_address, self.audio_address):
            if not isinstance(address, str) or not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", address):
                raise QCYError("Endereço Bluetooth inválido. Use seis pares hexadecimais separados por dois-pontos.")
        if type(self.restore) is not bool or not isinstance(self.preferred_mode, str) or self.preferred_mode not in MODES:
            raise QCYError("Preferências inválidas: restauração deve ser booleana e modo deve ser conhecido.")


def settings_path() -> Path:
    base = os.environ.get("APPDATA") if os.name == "nt" else os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / "qcy-h3" / "settings.json"


def load_settings(path: Path) -> Settings:
    if not path.exists():
        return Settings()
    try:
        settings = Settings(**json.loads(path.read_text(encoding="utf-8")))
        settings.validate()
        return settings
    except (OSError, ValueError, TypeError) as error:
        raise QCYError(f"Não foi possível carregar preferências: {error}") from error


def save_settings(path: Path, settings: Settings) -> None:
    settings.validate()
    temporary: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = stream.name
            json.dump(asdict(settings), stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise QCYError(f"Não foi possível salvar preferências: {error}") from error
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


class Transport(Protocol):
    def open(self, ready: Callable[[], None]) -> None: ...
    def write(self, packet: bytes) -> None: ...
    def read(self, timeout: float) -> bytes: ...
    def close(self) -> None: ...


class Decoder:
    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        frames = []
        while len(self.buffer) >= 3:
            if self.buffer[:3] != b"\xfe\xdc\xba":
                raise QCYError("Cabeçalho RCSP inválido.")
            if len(self.buffer) < 7:
                break
            length = int.from_bytes(self.buffer[5:7], "big")
            if not 1 <= length <= 1024:
                raise QCYError("Comprimento RCSP inválido.")
            size = length + 8
            if len(self.buffer) < size:
                break
            frame = bytes(self.buffer[:size])
            del self.buffer[:size]
            if frame[-1] != 0xEF:
                raise QCYError("Terminador RCSP inválido.")
            frames.append(frame)
        return frames


class Controller:
    def __init__(self, transport: Transport, settings: Settings | None = None) -> None:
        self.transport = transport
        self.settings = settings or Settings()
        self.settings.validate()
        self.connected = False
        # H3 pode ignorar sequências reutilizadas após reconectar; variar início evita o padrão fixo.
        self.sequence = secrets.randbelow(256)
        self.decoder = Decoder()
        self.lock = threading.RLock()

    def _request(self, payload: bytes) -> bytes:
        self.sequence = (self.sequence + 1) % 256
        body = bytes((self.sequence,)) + payload
        packet = b"\xfe\xdc\xba\xc0\xff" + len(body).to_bytes(2, "big") + body + b"\xef"
        self.transport.write(packet)
        deadline = time.monotonic() + 6
        while (remaining := deadline - time.monotonic()) > 0:
            for frame in self.decoder.feed(self.transport.read(remaining)):
                if frame[3] & 0x80 or frame[4] != 0xFF:
                    continue
                body = frame[7:-1]
                if len(body) < 2:
                    raise QCYError("Resposta RCSP incompleta.")
                if body[1] != self.sequence:
                    continue
                if body[0]:
                    raise QCYError(f"Fone recusou comando: status {body[0]}.")
                return body[2:]
        raise QCYError("Tempo esgotado aguardando resposta do fone.")

    def _read(self) -> str:
        payload = self._request(b"\xfe\x01\x17")
        if len(payload) != 5 or payload[:2] != b"\x17\x03":
            raise QCYError("Resposta ANC inválida.")
        return next((mode for mode, value in MODES.items() if value == payload[2:]), f"Desconhecido ({payload[2:].hex(' ')})")

    def _apply(self, mode: str) -> str:
        self._request(b"\x17\x03" + MODES[mode])
        state = self._read()
        if state != mode:
            raise QCYError(f"Fone não confirmou {LABELS[mode]}; retornou {LABELS.get(state, state)}.")
        return state

    def _connect(self) -> str:
        state = ""

        def ready() -> None:
            nonlocal state
            self.decoder = Decoder()
            state = self._read()

        self.transport.open(ready)
        self.connected = True
        if self.settings.restore and state != self.settings.preferred_mode:
            return self._apply(self.settings.preferred_mode)
        return state

    def read(self) -> str:
        with self.lock:
            try:
                return self._read() if self.connected else self._connect()
            except (QCYError, OSError):
                self.close()
                raise

    def apply(self, mode: str) -> str:
        if mode not in MODES:
            raise QCYError("Modo inválido. Escolha normal, barulho ou adaptavel.")
        with self.lock:
            try:
                if not self.connected:
                    self._connect()
                return self._apply(mode)
            except (QCYError, OSError):
                self.close()
                raise

    def close(self) -> None:
        with self.lock:
            self.connected = False
            self.transport.close()
