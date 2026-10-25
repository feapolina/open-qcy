import tempfile
import unittest
import io
import sys
import types
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from qcy_h3.core import Controller, QCYError, Settings, load_settings, save_settings


def configured(**changes):
    return Settings(**{
        "ble_address": "02:00:00:00:00:01",
        "audio_address": "02:00:00:00:00:02",
        **changes,
    })


def response(sequence, payload=b"", status=0):
    body = bytes((status, sequence)) + payload
    return b"\xfe\xdc\xba\x00\xff" + len(body).to_bytes(2, "big") + body + b"\xef"


class Headset:
    def __init__(self, state=b"\x01\x01\x02"):
        self.state = state
        self.writes = []
        self.pending = []
        self.opens = 0
        self.closed = False
        self.status = 0
        self.ignore_set = False
        self.fragment = False
        self.wrong_sequence = False

    def open(self, ready):
        self.opens += 1
        ready()

    def close(self):
        self.closed = True

    def write(self, packet):
        self.writes.append(packet)
        sequence, payload = packet[7], packet[8:-1]
        if payload == b"\xfe\x01\x17":
            reply = response(sequence, b"\x17\x03" + self.state, self.status)
        else:
            if not self.ignore_set and not self.status:
                self.state = payload[2:]
            reply = response(sequence, status=self.status)
        if self.wrong_sequence:
            reply = response((sequence + 1) % 256, b"\x17\x03" + self.state)
        self.pending.extend([reply[:2], reply[2:7], reply[7:]] if self.fragment else [reply])

    def read(self, timeout):
        if not self.pending:
            raise QCYError("Tempo esgotado aguardando resposta do fone.")
        return self.pending.pop(0)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        seed = patch("qcy_h3.core.secrets.randbelow", return_value=0)
        seed.start()
        self.addCleanup(seed.stop)

    def test_reads_mode_from_captured_response(self):
        headset = Headset()
        self.assertEqual(Controller(headset, configured()).read(), "barulho")
        self.assertEqual(headset.writes[0], bytes.fromhex("fedcbac0ff000401fe0117ef"))

    def test_applies_and_reads_back_adaptive(self):
        headset = Headset()
        self.assertEqual(Controller(headset, configured()).apply("adaptavel"), "adaptavel")
        self.assertEqual(headset.state, b"\x01\x05\x00")
        self.assertEqual(len(headset.writes), 3)

    def test_handles_fragmented_notifications(self):
        headset = Headset()
        headset.fragment = True
        self.assertEqual(Controller(headset, configured()).read(), "barulho")

    def test_rejects_remote_failure(self):
        headset = Headset()
        headset.status = 3
        with self.assertRaisesRegex(QCYError, "status.*3"):
            Controller(headset, configured()).read()
        self.assertTrue(headset.closed)

    def test_does_not_accept_another_sequence(self):
        headset = Headset()
        headset.wrong_sequence = True
        with self.assertRaisesRegex(QCYError, "Tempo esgotado"):
            Controller(headset, configured()).read()

    def test_rejects_false_success_when_state_does_not_change(self):
        headset = Headset()
        headset.ignore_set = True
        with self.assertRaisesRegex(QCYError, "não confirmou"):
            Controller(headset, configured()).apply("adaptavel")

    def test_unknown_mode_is_not_converted(self):
        self.assertIn("Desconhecido", Controller(Headset(b"\x09\x08\x07"), configured()).read())

    def test_invalid_mode_never_reaches_bluetooth(self):
        headset = Headset()
        with self.assertRaises(QCYError):
            Controller(headset, configured()).apply("reset")
        self.assertEqual(headset.opens, 0)
        self.assertEqual(headset.writes, [])

    def test_new_session_uses_fresh_sequence_seed(self):
        with patch("qcy_h3.core.secrets.randbelow", side_effect=[0, 80]):
            first, second = Headset(), Headset()
            Controller(first, configured()).read()
            Controller(second, configured()).read()
            self.assertEqual(first.writes[0][7], 1)
            self.assertEqual(second.writes[0][7], 81)

    def test_restores_preference_only_once_per_connection(self):
        headset = Headset()
        controller = Controller(headset, configured(restore=True))
        self.assertEqual(controller.read(), "adaptavel")
        headset.state = b"\x02\x00\x00"
        self.assertEqual(controller.read(), "normal")
        controller.close()
        self.assertEqual(controller.read(), "adaptavel")
        self.assertEqual(headset.opens, 2)

    def test_malformed_length_and_terminator_fail(self):
        for bad in (bytes.fromhex("fedcba00ff1000"), bytes.fromhex("fedcba00ff0002000100")):
            with self.subTest(bad=bad):
                headset = Headset()
                headset.write = lambda packet: headset.pending.append(bad)
                with self.assertRaises(QCYError):
                    Controller(headset, configured()).read()


class SettingsTests(unittest.TestCase):
    def test_defaults_do_not_contain_device_identifiers(self):
        settings = Settings()
        self.assertEqual(settings.ble_address, "")
        self.assertEqual(settings.audio_address, "")

    def test_round_trip_and_default_restore_disabled(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            self.assertFalse(load_settings(path).restore)
            settings = configured(restore=True, preferred_mode="normal")
            save_settings(path, settings)
            self.assertEqual(load_settings(path), settings)

    def test_invalid_settings_do_not_overwrite_previous_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            save_settings(path, configured())
            previous = path.read_bytes()
            with self.assertRaises(QCYError):
                save_settings(path, configured(ble_address="invalid"))
            self.assertEqual(path.read_bytes(), previous)

    def test_malformed_json_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text('{"restore": "false"}', encoding="utf-8")
            with self.assertRaises(QCYError):
                load_settings(path)

    def test_failed_atomic_replace_preserves_preferences(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            save_settings(path, configured())
            previous = path.read_bytes()
            with patch("qcy_h3.core.os.replace", side_effect=OSError("disco indisponível")):
                with self.assertRaisesRegex(QCYError, "disco indisponível"):
                    save_settings(path, configured(restore=True))
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual(list(path.parent.iterdir()), [path])


class FirstRunTests(unittest.TestCase):
    def test_gui_opens_without_personal_configuration(self):
        from qcy_h3.__main__ import main
        opened = []
        gui = types.SimpleNamespace(run_gui=lambda settings, path: opened.append(settings))
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, {"qcy_h3.gui": gui}):
            self.assertEqual(main(["--config", str(Path(folder) / "settings.json"), "gui"]), 0)
        self.assertEqual(opened[0].ble_address, "")

    def test_status_requires_addresses_before_any_bluetooth_access(self):
        from qcy_h3.__main__ import main
        with tempfile.TemporaryDirectory() as folder, patch("qcy_h3.__main__.make_transport") as transport, redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--config", str(Path(folder) / "settings.json"), "status"]), 1)
            transport.assert_not_called()


if __name__ == "__main__":
    unittest.main()
