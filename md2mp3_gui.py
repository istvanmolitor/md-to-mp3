#!/usr/bin/env python3
"""Grafikus felület a md2mp3.py szkripthez (Tkinter).

Használat:
    python3 md2mp3_gui.py

Előfeltétel a md2mp3.py-n felül:
    Tkinter (Debian/Ubuntu-n: sudo apt install python3-tk)
"""

import asyncio
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from md2mp3 import DEFAULT_VOICE, MAX_CHARS, chunk_text, markdown_to_text, synthesize_chunk

VOICES = ["hu-HU-NoemiNeural", "hu-HU-TamasNeural"]


class Md2Mp3App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Markdown -> MP3 konvertáló")
        root.geometry("640x480")
        root.minsize(560, 420)

        self.md_files: list[Path] = []
        self.outdir = tk.StringVar(value=str(Path.cwd() / "mp3"))
        self.voice = tk.StringVar(value=DEFAULT_VOICE)
        self.rate = tk.StringVar(value="+0%")
        self.progress_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.worker_thread: threading.Thread | None = None

        self._build_widgets()
        self.root.after(100, self._poll_queue)

    def _build_widgets(self):
        pad = {"padx": 8, "pady": 4}

        files_frame = ttk.LabelFrame(self.root, text="Markdown fájlok")
        files_frame.pack(fill="both", expand=True, **pad)

        self.files_listbox = tk.Listbox(files_frame, selectmode="extended")
        self.files_listbox.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)

        files_scroll = ttk.Scrollbar(files_frame, orient="vertical", command=self.files_listbox.yview)
        files_scroll.pack(side="left", fill="y", pady=8)
        self.files_listbox.config(yscrollcommand=files_scroll.set)

        files_btns = ttk.Frame(files_frame)
        files_btns.pack(side="left", fill="y", padx=8, pady=8)
        ttk.Button(files_btns, text="Hozzáadás...", command=self.add_files).pack(fill="x", pady=2)
        ttk.Button(files_btns, text="Kijelöltek törlése", command=self.remove_selected).pack(fill="x", pady=2)
        ttk.Button(files_btns, text="Lista ürítése", command=self.clear_files).pack(fill="x", pady=2)

        out_frame = ttk.LabelFrame(self.root, text="Kimeneti mappa")
        out_frame.pack(fill="x", **pad)
        ttk.Entry(out_frame, textvariable=self.outdir).pack(side="left", fill="x", expand=True, padx=8, pady=8)
        ttk.Button(out_frame, text="Tallózás...", command=self.choose_outdir).pack(side="left", padx=8, pady=8)

        opts_frame = ttk.LabelFrame(self.root, text="Beállítások")
        opts_frame.pack(fill="x", **pad)
        ttk.Label(opts_frame, text="Hang:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Combobox(
            opts_frame, textvariable=self.voice, values=VOICES, state="normal", width=25
        ).grid(row=0, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(opts_frame, text="Sebesség:").grid(row=0, column=2, sticky="w", padx=8, pady=4)
        ttk.Entry(opts_frame, textvariable=self.rate, width=10).grid(row=0, column=3, sticky="w", padx=8, pady=4)

        progress_frame = ttk.Frame(self.root)
        progress_frame.pack(fill="x", **pad)
        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate", maximum=100)
        self.progress_bar.pack(fill="x", padx=8, pady=(8, 4))
        self.status_label = ttk.Label(progress_frame, text="Készen áll.")
        self.status_label.pack(anchor="w", padx=8)

        self.start_btn = ttk.Button(self.root, text="Konvertálás indítása", command=self.start_conversion)
        self.start_btn.pack(pady=8)

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Markdown fájlok kiválasztása",
            filetypes=[("Markdown fájlok", "*.md"), ("Minden fájl", "*.*")],
        )
        for p in paths:
            path = Path(p)
            if path not in self.md_files:
                self.md_files.append(path)
                self.files_listbox.insert("end", path.name)

    def remove_selected(self):
        for idx in reversed(self.files_listbox.curselection()):
            self.files_listbox.delete(idx)
            del self.md_files[idx]

    def clear_files(self):
        self.files_listbox.delete(0, "end")
        self.md_files.clear()

    def choose_outdir(self):
        d = filedialog.askdirectory(title="Kimeneti mappa kiválasztása")
        if d:
            self.outdir.set(d)

    def start_conversion(self):
        if not self.md_files:
            messagebox.showwarning("Nincs fájl", "Válassz ki legalább egy Markdown fájlt.")
            return
        if not self.outdir.get().strip():
            messagebox.showwarning("Nincs kimeneti mappa", "Válassz ki egy kimeneti mappát.")
            return
        if self.worker_thread and self.worker_thread.is_alive():
            return

        self.start_btn.config(state="disabled")
        self.progress_bar["value"] = 0
        self.status_label.config(text="Indítás...")

        files = list(self.md_files)
        outdir = Path(self.outdir.get())
        voice = self.voice.get().strip() or DEFAULT_VOICE
        rate = self.rate.get().strip() or "+0%"

        self.worker_thread = threading.Thread(
            target=self._run_worker, args=(files, outdir, voice, rate), daemon=True
        )
        self.worker_thread.start()

    def _run_worker(self, files, outdir, voice, rate):
        try:
            asyncio.run(self._convert_all(files, outdir, voice, rate))
        except Exception as exc:  # noqa: BLE001
            self.progress_queue.put(("error", str(exc)))
        else:
            self.progress_queue.put(("done", None))

    async def _convert_all(self, files, outdir, voice, rate):
        outdir.mkdir(parents=True, exist_ok=True)

        jobs = []
        total_chunks = 0
        for md_path in files:
            raw = md_path.read_text(encoding="utf-8")
            plain = markdown_to_text(raw)
            chunks = chunk_text(plain, MAX_CHARS)
            jobs.append((md_path, chunks))
            total_chunks += len(chunks)

        if total_chunks == 0:
            self.progress_queue.put(("error", "Nincs felolvasható szöveg a kiválasztott fájlokban."))
            return

        done_chunks = 0
        for md_path, chunks in jobs:
            width = max(3, len(str(len(chunks))))

            for idx, chunk in enumerate(chunks, start=1):
                self.progress_queue.put(
                    ("status", f"[{md_path.name}] {idx}/{len(chunks)} rész felolvasása...")
                )
                part_path = outdir / f"{md_path.stem}_{idx:0{width}d}.mp3"
                await synthesize_chunk(chunk, voice, rate, part_path)

                done_chunks += 1
                percent = int(done_chunks / total_chunks * 100)
                self.progress_queue.put(("progress", percent))

            self.progress_queue.put(
                ("status", f"[{md_path.name}] kész -> {len(chunks)} rész mentve ide: {outdir}")
            )

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.progress_queue.get_nowait()
                if kind == "progress":
                    self.progress_bar["value"] = payload
                elif kind == "status":
                    self.status_label.config(text=str(payload))
                elif kind == "error":
                    self.status_label.config(text=f"Hiba: {payload}")
                    messagebox.showerror("Hiba", str(payload))
                    self.start_btn.config(state="normal")
                elif kind == "done":
                    self.progress_bar["value"] = 100
                    self.status_label.config(text="Minden fájl elkészült.")
                    self.start_btn.config(state="normal")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)


def main():
    root = tk.Tk()
    Md2Mp3App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
