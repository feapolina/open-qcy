"""Interface pequena; toda operação Bluetooth roda fora da thread gráfica."""

from __future__ import annotations

import queue
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from .core import LABELS, Controller, QCYError, Settings, save_settings
from .transports import make_transport


class Desktop:
    def __init__(self, root: tk.Tk, settings: Settings, path: Path) -> None:
        self.root, self.settings, self.path = root, settings, path
        self.controller: Controller | None = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self.closing = False
        root.title("QCY H3 — Controle de ANC")
        root.minsize(500, 350)
        panel = ttk.Frame(root, padding=20)
        panel.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)
        ttk.Label(panel, text="QCY H3", font=("TkDefaultFont", 18, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        self.ble = tk.StringVar(value=settings.ble_address)
        self.audio = tk.StringVar(value=settings.audio_address)
        self.mode = tk.StringVar(value=LABELS[settings.preferred_mode])
        self.restore = tk.BooleanVar(value=settings.restore)
        self.state = tk.StringVar(value="ANC atual: não consultado")
        self.status = tk.StringVar(value="Pronto. Conecte o fone; celular não é necessário.")
        self.controls: list[ttk.Entry | ttk.Checkbutton | ttk.Button] = []
        for row, (label, value) in enumerate((("Endereço BLE de controle", self.ble), ("Endereço Bluetooth de áudio", self.audio)), 1):
            ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            entry = ttk.Entry(panel, textvariable=value, width=24)
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            self.controls.append(entry)
        ttk.Label(panel, textvariable=self.state, font=("TkDefaultFont", 12, "bold")).grid(row=3, column=0, columnspan=2, sticky="w", pady=15)
        ttk.Label(panel, text="Modo desejado").grid(row=4, column=0, sticky="w")
        self.selector = ttk.Combobox(panel, textvariable=self.mode, values=list(LABELS.values()), state="readonly")
        self.selector.grid(row=4, column=1, sticky="ew")
        self.controls.append(self.selector)
        checkbox = ttk.Checkbutton(panel, text="Restaurar modo preferido ao conectar", variable=self.restore, command=self._save_restore)
        checkbox.grid(row=5, column=0, columnspan=2, sticky="w", pady=12)
        self.controls.append(checkbox)
        buttons = ttk.Frame(panel)
        buttons.grid(row=6, column=0, columnspan=2, sticky="ew", pady=8)
        for text, command in (("Conectar / Reconectar", self.connect), ("Consultar", lambda: self.submit(self._read)), ("Aplicar", self.apply)):
            button = ttk.Button(buttons, text=text, command=command)
            button.pack(side="left", padx=(0, 8))
            self.controls.append(button)
        ttk.Label(panel, textvariable=self.status, wraplength=490).grid(row=7, column=0, columnspan=2, sticky="w", pady=10)
        ttk.Label(panel, text="Linux pode pausar áudio brevemente para abrir controle.\nA preferência só é salva após aplicação confirmada.", wraplength=490).grid(row=8, column=0, columnspan=2, sticky="w")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self._pump)

    def _busy(self, busy: bool) -> None:
        for control in self.controls:
            control.configure(state="disabled" if busy else "normal")
        if not busy:
            self.selector.configure(state="readonly")

    def _report(self, message: str) -> None:
        self.messages.put(("progress", message))

    def _save_restore(self) -> None:
        updated = replace(self.settings, restore=self.restore.get())
        try:
            save_settings(self.path, updated)
        except QCYError as error:
            self.restore.set(self.settings.restore)
            messagebox.showerror("Preferências", str(error), parent=self.root)
            return
        self.settings = updated
        if self.controller:
            self.controller.settings = updated
        self.status.set("Preferência salva. Restauração vale na próxima conexão de controle.")

    def connect(self) -> None:
        updated = replace(self.settings, ble_address=self.ble.get().strip(), audio_address=self.audio.get().strip())
        try:
            updated.validate()
            save_settings(self.path, updated)
        except QCYError as error:
            messagebox.showerror("Configuração", str(error), parent=self.root)
            return
        self.settings = updated

        def operation() -> str:
            if self.controller:
                self.controller.close()
            self.controller = Controller(make_transport(updated, self._report), updated)
            return self.controller.read()

        self.submit(operation)

    def _read(self) -> str:
        if not self.controller:
            raise QCYError("Clique em Conectar primeiro.")
        return self.controller.read()

    def apply(self) -> None:
        mode = next(key for key, label in LABELS.items() if label == self.mode.get())

        def operation() -> str:
            if not self.controller:
                raise QCYError("Clique em Conectar primeiro.")
            state = self.controller.apply(mode)
            updated = replace(self.settings, preferred_mode=mode)
            save_settings(self.path, updated)
            self.settings = updated
            self.controller.settings = updated
            return state

        self.submit(operation)

    def submit(self, operation: Callable[[], str]) -> None:
        self._busy(True)
        self.status.set("Aguardando Bluetooth…")
        future = self.executor.submit(operation)

        def finished(result: Future[str]) -> None:
            try:
                self.messages.put(("state", result.result()))
            except Exception as error:
                self.messages.put(("error", str(error)))

        future.add_done_callback(finished)

    def _pump(self) -> None:
        while not self.messages.empty():
            kind, message = self.messages.get_nowait()
            if kind == "closed":
                self.executor.shutdown(wait=False)
                self.root.destroy()
                return
            if kind == "state":
                self.state.set(f"ANC confirmado: {LABELS.get(message, message)}")
                self.status.set("Conexão de controle aberta.")
            elif kind == "error":
                self.state.set("ANC atual: não confirmado")
                self.status.set(f"Erro: {message}")
            else:
                self.status.set(message)
            if kind in ("state", "error") and not self.closing:
                self._busy(False)
        self.root.after(100, self._pump)

    def close(self) -> None:
        if self.closing:
            return
        self.closing = True
        self._busy(True)
        self.status.set("Encerrando conexão de controle…")

        def finish() -> None:
            try:
                if self.controller:
                    self.controller.close()
            finally:
                self.messages.put(("closed", ""))

        self.executor.submit(finish)


def run_gui(settings: Settings, path: Path) -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise QCYError(f"Interface gráfica indisponível: {error}. Use status ou set pelo terminal.") from error
    Desktop(root, settings, path)
    root.mainloop()
