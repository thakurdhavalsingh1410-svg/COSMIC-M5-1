from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_FILE = PROJECT_ROOT / "main.py"
WEB_URL = "http://localhost:8765"
ICON_FILE = PROJECT_ROOT / "assets" / "cosmic.ico"


class CosmicLauncher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("COSMIC Launcher")
        if ICON_FILE.exists():
            try:
                self.iconbitmap(str(ICON_FILE))
            except Exception:
                pass
        self.geometry("520x520")
        self.minsize(470, 480)
        self.configure(bg="#030712")
        self._process: subprocess.Popen | None = None
        self._build_ui()
        self._tick_status()

    def _build_ui(self):
        outer = tk.Frame(self, bg="#030712")
        outer.pack(fill="both", expand=True, padx=22, pady=22)

        shell = tk.Frame(
            outer,
            bg="#071426",
            highlightbackground="#22d3ee",
            highlightthickness=1,
        )
        shell.pack(fill="both", expand=True)

        header = tk.Frame(shell, bg="#071426")
        header.pack(fill="x", padx=26, pady=(26, 12))

        title = tk.Label(
            header,
            text="C O S M I C",
            bg="#071426",
            fg="#67e8f9",
            font=("Segoe UI", 27, "bold"),
        )
        title.pack()

        subtitle = tk.Label(
            header,
            text="Your Personal AI Command System",
            bg="#071426",
            fg="#cbd5e1",
            font=("Segoe UI", 11),
        )
        subtitle.pack(pady=(4, 0))

        orb = tk.Canvas(shell, width=150, height=150, bg="#071426", highlightthickness=0)
        orb.pack(pady=14)
        self._orb = orb
        self._draw_orb()

        self.status = tk.Label(
            shell,
            text="Ready",
            bg="#071426",
            fg="#34d399",
            font=("Segoe UI", 11, "bold"),
        )
        self.status.pack(pady=(0, 14))

        buttons = tk.Frame(shell, bg="#071426")
        buttons.pack(fill="x", padx=34, pady=6)

        self._button(buttons, "Start COSMIC Phone Ready", self.start_cosmic, primary=True)
        self._button(buttons, "Open Web Dashboard", self.open_web)
        self._button(buttons, "Open Project Folder", self.open_project)
        self._button(buttons, "Check Files", self.check_files)

        note = tk.Label(
            shell,
            text=(
                "Launcher works offline. COSMIC's AI voice/chat still needs internet "
                "when it connects to Gemini."
            ),
            bg="#071426",
            fg="#8aa3b8",
            wraplength=410,
            justify="center",
            font=("Segoe UI", 9),
        )
        note.pack(side="bottom", padx=28, pady=(12, 22))

    def _button(self, parent: tk.Widget, text: str, command, primary: bool = False):
        bg = "#0e7490" if primary else "#0b1d33"
        hover = "#0891b2" if primary else "#123653"
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg="#e5faff",
            activebackground=hover,
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            font=("Segoe UI", 11, "bold"),
            height=2,
        )
        button.pack(fill="x", pady=7)
        button.bind("<Enter>", lambda _: button.configure(bg=hover))
        button.bind("<Leave>", lambda _: button.configure(bg=bg))
        return button

    def _draw_orb(self):
        canvas = self._orb
        canvas.delete("all")
        cx, cy = 75, 75
        for radius, color in [
            (70, "#123653"),
            (58, "#164e63"),
            (46, "#2563eb"),
            (34, "#7c3aed"),
            (22, "#020617"),
            (10, "#67e8f9"),
        ]:
            canvas.create_oval(
                cx - radius,
                cy - radius,
                cx + radius,
                cy + radius,
                outline="#22d3ee" if radius in {70, 46} else "",
                width=2,
                fill=color,
            )
        canvas.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill="#ffffff", outline="")

    def _set_status(self, text: str, color: str = "#34d399"):
        self.status.configure(text=text, fg=color)

    def _python_command(self) -> list[str] | None:
        candidates = [
            [str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")],
            ["py", "-3.12"],
            ["py", "-3"],
            ["python"],
        ]
        for command in candidates:
            if len(command) == 1 and command[0].endswith("python.exe") and not Path(command[0]).exists():
                continue
            try:
                result = subprocess.run(
                    command + ["--version"],
                    cwd=PROJECT_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=4,
                )
                if result.returncode == 0:
                    return command
            except Exception:
                continue
        return None

    def start_cosmic(self):
        if not MAIN_FILE.exists():
            messagebox.showerror("COSMIC Launcher", f"main.py was not found:\n{MAIN_FILE}")
            return

        if self._process and self._process.poll() is None:
            self._set_status("COSMIC is already running", "#facc15")
            webbrowser.open(WEB_URL)
            return

        command = self._python_command()
        if not command:
            messagebox.showerror(
                "COSMIC Launcher",
                "Python was not found. Install Python 3.12, then run requirements.txt.",
            )
            self._set_status("Python not found", "#fb7185")
            return

        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NEW_CONSOLE

        try:
            self._process = subprocess.Popen(
                command + ["main.py", "--phone", "--open-web"],
                cwd=PROJECT_ROOT,
                creationflags=flags,
            )
            self._set_status("Starting COSMIC phone access...", "#67e8f9")
            threading.Thread(target=self._open_web_after_delay, daemon=True).start()
        except Exception as exc:
            messagebox.showerror("COSMIC Launcher", f"Could not start COSMIC:\n{exc}")
            self._set_status("Launch failed", "#fb7185")

    def _open_web_after_delay(self):
        time.sleep(3)
        webbrowser.open(WEB_URL)
        self._set_status("COSMIC launched", "#34d399")

    def open_web(self):
        webbrowser.open(WEB_URL)
        self._set_status("Opening web dashboard", "#67e8f9")

    def open_project(self):
        if os.name == "nt":
            os.startfile(PROJECT_ROOT)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(PROJECT_ROOT)])
        self._set_status("Opening project folder", "#67e8f9")

    def check_files(self):
        missing = []
        for filename in ["main.py", "ui.py", "web_server.py", "requirements.txt"]:
            if not (PROJECT_ROOT / filename).exists():
                missing.append(filename)
        if missing:
            messagebox.showwarning("COSMIC Launcher", "Missing files:\n" + "\n".join(missing))
            self._set_status("Some files are missing", "#facc15")
        else:
            messagebox.showinfo("COSMIC Launcher", "COSMIC project files look good.")
            self._set_status("Project files look good", "#34d399")

    def _tick_status(self):
        if self._process and self._process.poll() is not None:
            self._set_status("COSMIC stopped", "#facc15")
            self._process = None
        self.after(1500, self._tick_status)


if __name__ == "__main__":
    app = CosmicLauncher()
    app.mainloop()


