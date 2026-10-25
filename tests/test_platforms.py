import types
import unittest
from unittest.mock import MagicMock, patch

from qcy_h3.core import NOTIFY, SERVICE, WRITE, Controller, QCYError, Settings
from qcy_h3.transports import LinuxTransport, WindowsTransport
from test_controller import configured, response as rcsp_response


class PlatformTests(unittest.TestCase):
    def setUp(self):
        seed = patch("qcy_h3.core.secrets.randbelow", return_value=0)
        seed.start()
        self.addCleanup(seed.stop)

    def test_linux_controller_understands_real_interactive_gatt_transcript(self):
        pending = []
        process = MagicMock()
        process.poll.return_value = None
        state = b"\x01\x01\x02"

        def command(data):
            nonlocal state
            text = data.decode().strip()
            if text == "connect":
                pending.append(b"Connection successful\n")
            elif text == "primary":
                pending.append(b"attr handle: 0x0004, end grp handle: 0x0009 uuid: " + SERVICE.encode() + b"\n")
            elif text.startswith("char-desc"):
                pending.append(b"handle: 0x0006, uuid: " + WRITE.encode() + b"\nhandle: 0x0008, uuid: " + NOTIFY.encode() + b"\nhandle: 0x0009, uuid: 00002902-0000-1000-8000-00805f9b34fb\n")
            elif text.startswith("char-write-req"):
                pending.append(b"Characteristic value was written successfully\n")
            else:
                packet = bytes.fromhex(text.split()[-1])
                if packet[8:10] == b"\x17\x03":
                    state = packet[10:-1]
                    frame = rcsp_response(packet[7])
                else:
                    frame = rcsp_response(packet[7], b"\x17\x03" + state)
                pending.append(b"Notification handle = 0x0008 value: " + frame.hex(" ").encode() + b"\n")

        process.stdin.write.side_effect = command
        with patch("qcy_h3.transports.shutil.which", return_value="installed"), patch("qcy_h3.transports.subprocess.Popen", return_value=process), patch("qcy_h3.transports.select.select", return_value=([process.stdout], [], [])), patch("qcy_h3.transports.os.read", side_effect=lambda *_: pending.pop(0)):
            controller = Controller(LinuxTransport(configured()), configured())
            try:
                self.assertEqual(controller.read(), "barulho")
                self.assertEqual(controller.apply("adaptavel"), "adaptavel")
            finally:
                controller.close()
        process.terminate.assert_called_once()

    def test_windows_controller_uses_gatt_notifications_and_validates_state(self):
        class Client:
            def __init__(self, address, timeout):
                self.address = address
                self.is_connected = False
                self.state = b"\x01\x01\x02"
                self.services = self

            async def connect(self):
                self.is_connected = True

            async def disconnect(self):
                self.is_connected = False

            def get_service(self, uuid):
                return self if uuid == SERVICE else None

            def get_characteristic(self, uuid):
                return uuid in (WRITE, NOTIFY)

            async def start_notify(self, uuid, callback):
                self.callback = callback

            async def write_gatt_char(self, uuid, packet, response=False):
                if packet[8:10] == b"\x17\x03":
                    self.state = packet[10:-1]
                    frame = rcsp_response(packet[7])
                else:
                    frame = rcsp_response(packet[7], b"\x17\x03" + self.state)
                self.callback(None, bytearray(frame[:4]))
                self.callback(None, bytearray(frame[4:]))

        with patch("qcy_h3.transports.importlib.import_module", return_value=types.SimpleNamespace(BleakClient=Client)):
            controller = Controller(WindowsTransport(configured()), configured())
            try:
                self.assertEqual(controller.read(), "barulho")
                self.assertEqual(controller.apply("adaptavel"), "adaptavel")
            finally:
                controller.close()

    def test_linux_restores_audio_even_if_second_connection_fails(self):
        transport = LinuxTransport(configured(), lambda message: None)
        with patch("qcy_h3.transports.shutil.which", return_value="installed"), patch.object(transport, "_start", side_effect=QCYError("conexão falhou")), patch.object(transport, "_audio_connected", return_value=True), patch.object(transport, "_audio") as audio:
            with self.assertRaisesRegex(QCYError, "conexão falhou"):
                Controller(transport, configured()).read()
            self.assertEqual([call.args[0] for call in audio.call_args_list], ["disconnect", "connect"])

    def test_linux_recovers_when_gatt_opens_but_first_anc_query_times_out(self):
        transport = LinuxTransport(configured(), lambda message: None)
        with patch("qcy_h3.transports.shutil.which", return_value="installed"), patch.object(transport, "_start"), patch.object(transport, "write"), patch.object(transport, "read", side_effect=[QCYError("Tempo esgotado"), rcsp_response(2, b"\x17\x03\x01\x01\x02")]), patch.object(transport, "_audio_connected", return_value=True), patch.object(transport, "_audio") as audio:
            controller = Controller(transport, configured())
            try:
                self.assertEqual(controller.read(), "barulho")
            finally:
                controller.close()
            self.assertEqual([call.args[0] for call in audio.call_args_list], ["disconnect", "connect"])

    def test_linux_restores_audio_when_both_protocol_queries_fail(self):
        transport = LinuxTransport(configured(), lambda message: None)
        with patch("qcy_h3.transports.shutil.which", return_value="installed"), patch.object(transport, "_start"), patch.object(transport, "write"), patch.object(transport, "read", side_effect=QCYError("Tempo esgotado")), patch.object(transport, "_audio_connected", return_value=True), patch.object(transport, "_audio") as audio:
            with self.assertRaisesRegex(QCYError, "Tempo esgotado"):
                Controller(transport, configured()).read()
            self.assertEqual([call.args[0] for call in audio.call_args_list], ["disconnect", "connect"])


if __name__ == "__main__":
    unittest.main()
