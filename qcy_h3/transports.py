"""Acesso Bluetooth local: GATT direto no Linux e WinRT via Bleak no Windows."""

from __future__ import annotations

import asyncio
import importlib
import os
import re
import select
import shutil
import subprocess
import sys
import time
from typing import Any, Callable, Pattern

from .core import NOTIFY, SERVICE, WRITE, QCYError, Settings, Transport


class LinuxTransport:
    def __init__(self, settings: Settings, report: Callable[[str], None] = print) -> None:
        self.settings = settings
        self.report = report
        self.process: subprocess.Popen[bytes] | None = None
        self.buffer = b""
        self.write_handle = 0
        self.notify_handle = 0

    def _command(self, command: str) -> None:
        if not self.process or not self.process.stdin:
            raise QCYError("Conexão GATT não está aberta.")
        try:
            self.process.stdin.write((command + "\n").encode("ascii"))
            self.process.stdin.flush()
        except OSError as error:
            raise QCYError(f"Falha ao enviar comando GATT: {error}") from error

    def _expect(self, pattern: Pattern[bytes], timeout: float = 12) -> re.Match[bytes]:
        deadline = time.monotonic() + timeout
        while True:
            match = pattern.search(self.buffer)
            if match:
                self.buffer = self.buffer[match.end():]
                return match
            failure = re.search(rb"(?:Error:|error:|connect error:|Disconnected|Connection failed)[^\r\n]*", self.buffer)
            if failure:
                raise QCYError(f"Falha GATT: {failure.group().decode(errors='replace')[:200]}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise QCYError("Tempo esgotado aguardando resposta do fone.")
            if not self.process or not self.process.stdout:
                raise QCYError("Conexão GATT encerrada.")
            ready, _, _ = select.select([self.process.stdout], [], [], remaining)
            if not ready:
                raise QCYError("Tempo esgotado aguardando resposta do fone.")
            data = os.read(self.process.stdout.fileno(), 4096)
            if not data:
                raise QCYError("gatttool encerrou conexão sem resposta.")
            self.buffer = (self.buffer + data)[-65536:]

    def _start(self) -> None:
        self.buffer = b""
        self.process = subprocess.Popen(
            ["gatttool", "-b", self.settings.ble_address, "-t", "public", "-I"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
        )
        self._command("connect")
        self._expect(re.compile(rb"Connection successful"))
        self._command("primary")
        service = self._expect(re.compile(rb"attr handle\s*[:=]\s*0x([0-9a-f]+), end grp handle\s*[:=]\s*0x([0-9a-f]+) uuid: " + SERVICE.encode(), re.I))
        start, end = (int(part, 16) for part in service.groups())
        self._command(f"char-desc 0x{start:04x} 0x{end:04x}")
        self.write_handle = int(self._expect(re.compile(rb"handle: 0x([0-9a-f]+), uuid: " + WRITE.encode(), re.I)).group(1), 16)
        self.notify_handle = int(self._expect(re.compile(rb"handle: 0x([0-9a-f]+), uuid: " + NOTIFY.encode(), re.I)).group(1), 16)
        descriptor = int(self._expect(re.compile(rb"handle: 0x([0-9a-f]+), uuid: 00002902-0000-1000-8000-00805f9b34fb", re.I)).group(1), 16)
        if not start < self.write_handle < self.notify_handle < descriptor <= end:
            raise QCYError("Mapa GATT do fone não corresponde ao serviço QCY esperado.")
        self._command(f"char-write-req 0x{descriptor:04x} 0100")
        self._expect(re.compile(rb"Characteristic value was written successfully"))

    def _audio_connected(self) -> bool:
        try:
            result = subprocess.run(["bluetoothctl", "info", self.settings.audio_address], capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as error:
            raise QCYError(f"Não foi possível consultar conexão de áudio: {error}") from error
        return result.returncode == 0 and b"Connected: yes" in result.stdout

    def _audio(self, action: str) -> None:
        try:
            result = subprocess.run(["bluetoothctl", action, self.settings.audio_address], capture_output=True, timeout=15)
        except (OSError, subprocess.SubprocessError) as error:
            raise QCYError(f"Falha ao {action} áudio do H3: {error}. Reconecte nas configurações Bluetooth.") from error
        if result.returncode or self._audio_connected() != (action == "connect"):
            raise QCYError(f"Falha ao {action} áudio do H3. Reconecte-o nas configurações Bluetooth.")

    def open(self, ready: Callable[[], None]) -> None:
        self.settings.validate()
        if not shutil.which("gatttool") or not shutil.which("bluetoothctl"):
            raise QCYError("Linux requer gatttool e bluetoothctl instalados e adaptador Bluetooth ligado.")
        try:
            self._start()
            ready()
            return
        except QCYError:
            self.close()
            if not self._audio_connected():
                raise
        self.report("Abrindo controle BLE: áudio será pausado brevemente e reconectado.")
        try:
            self._audio("disconnect")
            # O rádio precisa liberar o enlace de áudio antes da nova conexão BLE.
            time.sleep(1)
            self._start()
            ready()
        finally:
            self._audio("connect")

    def write(self, packet: bytes) -> None:
        self._command(f"char-write-cmd 0x{self.write_handle:04x} {packet.hex()}")

    def read(self, timeout: float) -> bytes:
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            result = self._expect(re.compile(rb"Notification handle = 0x([0-9a-f]+) value: ([0-9a-f ]+)\r?\n", re.I), remaining)
            if int(result.group(1), 16) == self.notify_handle:
                try:
                    return bytes.fromhex(result.group(2).decode("ascii"))
                except ValueError as error:
                    raise QCYError("Notificação GATT inválida.") from error
        raise QCYError("Tempo esgotado aguardando resposta do fone.")

    def close(self) -> None:
        process, self.process = self.process, None
        if process:
            try:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            finally:
                if process.stdin:
                    process.stdin.close()
                if process.stdout:
                    process.stdout.close()


class WindowsTransport:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.runner: asyncio.Runner | None = None
        self.client: Any = None
        self.notifications: asyncio.Queue[bytes] | None = None

    async def _open(self) -> None:
        try:
            bleak = importlib.import_module("bleak")
        except ImportError as error:
            raise QCYError("Windows requer Bleak. Execute: python -m pip install bleak==3.0.2") from error
        self.notifications = asyncio.Queue()
        self.client = bleak.BleakClient(self.settings.ble_address, timeout=15)
        await self.client.connect()
        service = self.client.services.get_service(SERVICE)
        if not service or not service.get_characteristic(WRITE) or not service.get_characteristic(NOTIFY):
            raise QCYError("Serviço GATT do QCY H3 não encontrado nesse dispositivo.")

        def received(_sender: Any, data: bytearray) -> None:
            if self.notifications:
                self.notifications.put_nowait(bytes(data))

        await self.client.start_notify(NOTIFY, received)

    def open(self, ready: Callable[[], None]) -> None:
        self.settings.validate()
        self.runner = asyncio.Runner()
        try:
            self.runner.run(asyncio.wait_for(self._open(), 25))
            ready()
        except Exception as error:
            self.close()
            raise QCYError(f"Falha BLE no Windows: {error}") from error

    def write(self, packet: bytes) -> None:
        if not self.runner or not self.client:
            raise QCYError("Conexão BLE não está aberta.")
        try:
            self.runner.run(asyncio.wait_for(self.client.write_gatt_char(WRITE, packet, response=False), 10))
        except Exception as error:
            raise QCYError(f"Falha na escrita BLE: {error}") from error

    def read(self, timeout: float) -> bytes:
        if not self.runner or self.notifications is None:
            raise QCYError("Conexão BLE não está aberta.")
        try:
            return self.runner.run(asyncio.wait_for(self.notifications.get(), timeout))
        except TimeoutError as error:
            raise QCYError("Tempo esgotado aguardando resposta do fone.") from error

    def close(self) -> None:
        if self.runner:
            try:
                if self.client and self.client.is_connected:
                    self.runner.run(asyncio.wait_for(self.client.disconnect(), 5))
            except Exception:
                pass  # Desconexão é melhor esforço; não altera modo nem conexão de áudio.
            finally:
                self.runner.close()
                self.runner = None
                self.client = None


def make_transport(settings: Settings, report: Callable[[str], None] = print) -> Transport:
    if sys.platform.startswith("linux"):
        return LinuxTransport(settings, report)
    if sys.platform == "win32":
        return WindowsTransport(settings)
    raise QCYError("Este protótipo atende Linux e Windows.")
