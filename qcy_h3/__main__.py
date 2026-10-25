"""Terminal e ponto de entrada da interface desktop."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from .core import LABELS, MODES, Controller, QCYError, load_settings, save_settings, settings_path
from .transports import make_transport


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Controle local do ANC do QCY H3 comum.")
    parser.add_argument("--config", type=Path, default=settings_path(), help="Arquivo de preferências local.")
    parser.add_argument("--ble-address", help="Endereço do canal BLE de controle.")
    parser.add_argument("--audio-address", help="Endereço Bluetooth de áudio.")
    parser.add_argument("action", choices=("status", "set", "gui"), nargs="?", default="gui")
    parser.add_argument("mode", choices=tuple(MODES), nargs="?")
    args = parser.parse_args(argv)
    if (args.action == "set") != (args.mode is not None):
        parser.error("Use set com normal, barulho ou adaptavel; outras ações não recebem modo.")
    controller = None
    try:
        settings = load_settings(args.config)
        if args.ble_address:
            settings.ble_address = args.ble_address
        if args.audio_address:
            settings.audio_address = args.audio_address
        if args.action == "gui":
            from .gui import run_gui
            run_gui(settings, args.config)
            return 0
        settings.validate()
        controller = Controller(make_transport(settings, lambda message: print(message, file=sys.stderr)), settings)
        mode = controller.apply(args.mode) if args.action == "set" else controller.read()
        if args.action == "set":
            settings.preferred_mode = args.mode
            save_settings(args.config, settings)
        print(f"ANC confirmado: {LABELS.get(mode, mode)}")
        return 0
    except (QCYError, OSError, subprocess.SubprocessError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 1
    finally:
        if controller:
            controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
