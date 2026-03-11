#!/usr/bin/env python3
"""
Spotify to YouTube Downloader — GUI
-------------------------------------
Scarica una playlist di Spotify cercando le canzoni su YouTube.

Requisiti:
    pip install yt-dlp spotipy
    ffmpeg installato sul sistema
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import threading
import webbrowser
import os
import sys
import re
import shutil
from datetime import datetime
import json


def _find_cmd(name: str) -> list:
    import shutil, os, sys
    frozen = getattr(sys, "frozen", False)
    
    # 1. Cerca nel PATH di sistema (metodo definitivo dopo riavvio)
    exe = shutil.which(name) or shutil.which(name + ".exe")
    if exe:
        return [exe]

    # 2. Fallback: Cerca nella cartella dell'eseguibile (se non hai ancora riavviato)
    base_path = os.path.dirname(sys.executable) if frozen else os.path.dirname(__file__)
    local_tool = os.path.join(base_path, "pythofy_tools", name + ".exe")
    if os.path.exists(local_tool):
        return [local_tool]

    # 3. Fallback per sviluppo (script .py)
    if not frozen:
        module = name.replace("-", "_")
        return [sys.executable, "-m", module]

    return [name]





# ──────────────────────────────────────────────
#  PALETTE & STILE  —  dark music app (indigo/slate)
# ──────────────────────────────────────────────
BG        = "#0a0e1a"   # blu-notte profondo
BG2       = "#10152a"   # pannelli
BG3       = "#181d30"   # input / log
BG4       = "#1e2438"   # hover / bordi
ACCENT    = "#7c6ff7"   # indaco principale
ACCENT2   = "#a594ff"   # indaco chiaro (hover)
ACCENT3   = "#4f46a8"   # indaco scuro (pressed)
TEXT      = "#e8eaf6"   # testo principale
TEXT_DIM  = "#5c6380"   # testo secondario
TEXT_MID  = "#9096b8"   # testo medio
ERROR_CLR = "#e05c7a"   # rosso-rosa
WARN_CLR  = "#c9a84c"   # ambra
OK_CLR    = "#6fcf97"   # verde salvia
FONT_MAIN = ("Segoe UI", 10)
FONT_MONO = ("Cascadia Code", 9) if True else ("Consolas", 9)
FONT_BIG  = ("Segoe UI Semibold", 13)
FONT_TITLE= ("Segoe UI Light", 17)


class YouTubeDownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Spotify → YouTube Downloader")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(680, 580)
        self.geometry("680x950")

        self._process = None
        self._running = False
        self._num_songs_var = tk.IntVar(value=100)
        self._csv_songs = None
        self._songs_list = []
        self._current_song_idx = 0
        self._done_file    = None
        self._already_done = set()
        self._retry_count = {}  # Traccia i retry per ogni canzone
        self._max_retries = 3  # Numero massimo di tentativi

        self._build_ui()
        self._check_deps_async()

    # ──────────────────────────────────────────
    #  UI
    # ──────────────────────────────────────────
    def _build_ui(self):
        self.configure(bg=BG)

        # ── Header ──────────────────────────────
        header = tk.Frame(self, bg=BG, pady=16)
        header.pack(fill="x", padx=28)

        # Titolo con icona
        title_frame = tk.Frame(header, bg=BG)
        title_frame.pack(side="left")
        tk.Label(title_frame, text="♫", font=("Segoe UI", 22),
                 bg=BG, fg=ACCENT).pack(side="left", padx=(0, 10))
        tk.Label(title_frame, text="Pythofy",
                 font=("Segoe UI Light", 20), bg=BG, fg=TEXT).pack(side="left")
        tk.Label(title_frame, text=" Downloader",
                 font=("Segoe UI Light", 20), bg=BG, fg=ACCENT2).pack(side="left")

        # Status pill a destra
        status_frame = tk.Frame(header, bg=BG4, padx=12, pady=4)
        status_frame.pack(side="right", pady=6)
        self._status_dot = tk.Label(status_frame, text="●", font=("Segoe UI", 9),
                                    bg=BG4, fg=WARN_CLR)
        self._status_dot.pack(side="left", padx=(0, 5))
        self._status_lbl = tk.Label(status_frame, text="Avvio…",
                                    font=("Segoe UI", 9), bg=BG4, fg=TEXT_MID)
        self._status_lbl.pack(side="left")

        # Separatore sottile colorato
        sep = tk.Frame(self, bg=ACCENT3, height=1)
        sep.pack(fill="x")

        # ── Form card ───────────────────────────
        card = tk.Frame(self, bg=BG2, pady=20)
        card.pack(fill="x", padx=20, pady=(16, 0))

        inner = tk.Frame(card, bg=BG2)
        inner.pack(fill="x", padx=20)
        inner.columnconfigure(0, weight=1)

        # URL
        self._field_label(inner, "URL SPOTIFY (PLAYLIST O BRANO)").grid(
            row=0, column=0, sticky="w", pady=(0, 5))
        url_row = tk.Frame(inner, bg=BG2)
        url_row.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        url_row.columnconfigure(0, weight=1)

        self._song_var = tk.StringVar()
        self._make_entry(url_row, self._song_var).grid(
            row=0, column=0, sticky="ew", ipady=9, padx=(0, 8))
        self._pill_btn(url_row, "Paste", self._paste_text).grid(row=0, column=1)

        # Output dir
        self._field_label(inner, "DESTINATION DIRECTORY").grid(
            row=2, column=0, sticky="w", pady=(0, 5))
        dir_row = tk.Frame(inner, bg=BG2)
        dir_row.grid(row=3, column=0, sticky="ew", pady=(0, 16))
        dir_row.columnconfigure(0, weight=1)

        self._dir_var = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "Downloads", "Pythofy"))
        self._make_entry(dir_row, self._dir_var).grid(
            row=0, column=0, sticky="ew", ipady=9, padx=(0, 8))
        self._pill_btn(dir_row, "Browse", self._browse_dir).grid(row=0, column=1)

        # Audio quality + number of songs
        bottom_row = tk.Frame(inner, bg=BG2)
        bottom_row.grid(row=4, column=0, sticky="w")

        qual_outer = tk.Frame(bottom_row, bg=BG2)
        qual_outer.pack(side="left", padx=(0, 30))
        self._field_label(qual_outer, "AUDIO QUALITY").pack(anchor="w", pady=(0, 5))
        self._qual_var = tk.StringVar(value="192")
        self._make_combobox(qual_outer, self._qual_var,
                            ["128", "192", "256", "320"]).pack(anchor="w")

        num_outer = tk.Frame(bottom_row, bg=BG2)
        num_outer.pack(side="left")
        self._field_label(num_outer, "SONGS TO DOWNLOAD (MAX 100)").pack(anchor="w", pady=(0, 5))
        self._num_songs_var = tk.IntVar(value=100)
        num_spin = tk.Spinbox(num_outer, from_=1, to=100, textvariable=self._num_songs_var,
                              font=("Segoe UI", 10), bg=BG3, fg=TEXT,
                              buttonbackground=BG4, relief="flat", bd=0,
                              highlightthickness=1, highlightbackground=BG4,
                              highlightcolor=ACCENT, width=5, wrap=False)
        num_spin.pack(anchor="w", ipady=8)

        # ── CSV Exportify ────────────────────────
        csv_card = tk.Frame(self, bg=BG2)
        csv_card.pack(fill="x", padx=20, pady=(12, 0))
        csv_inner = tk.Frame(csv_card, bg=BG2)
        csv_inner.pack(fill="x", padx=20, pady=14)

        # Titolo sezione
        self._field_label(csv_inner, "PLAYLIST WITH MORE THAN 100 SONGS").pack(anchor="w", pady=(0, 6))

        # Riga info + link
        info_row = tk.Frame(csv_inner, bg=BG2)
        info_row.pack(fill="x", anchor="w", pady=(0, 8))

        tk.Label(info_row, text="The Spotify embed shows a maximum of 100 tracks. For larger playlists, use ",
                 font=("Segoe UI", 9), bg=BG2, fg=TEXT_MID).pack(side="left")

        link = tk.Label(info_row, text="Exportify",
                        font=("Segoe UI", 9, "underline"), bg=BG2, fg=ACCENT, cursor="hand2")
        link.pack(side="left")
        link.bind("<Button-1>", lambda e: webbrowser.open("https://exportify.net"))

        tk.Label(info_row, text=" to export the playlist as a CSV file, then import it below.",
                 font=("Segoe UI", 9), bg=BG2, fg=TEXT_MID).pack(side="left")

        # Riga tutorial passo-passo
        steps_frame = tk.Frame(csv_inner, bg=BG2)
        steps_frame.pack(fill="x", anchor="w", pady=(0, 10))

        steps_text = (
            "① Go to exportify.net  →  ② Click \"Log in with Spotify\"  →  "
            "③ Find your playlist  →  ④ Click \"Export\"  →  ⑤ Import the CSV below"
        )
        tk.Label(steps_frame, text=steps_text,
                 font=("Segoe UI", 8), bg=BG2, fg=TEXT_MID).pack(anchor="w")

        # Riga file CSV + pulsante importa
        csv_file_row = tk.Frame(csv_inner, bg=BG2)
        csv_file_row.pack(fill="x", anchor="w")
        csv_file_row.columnconfigure(0, weight=1)

        self._csv_var = tk.StringVar(value="")
        csv_entry = self._make_entry(csv_file_row, self._csv_var)
        csv_entry.grid(row=0, column=0, sticky="ew", ipady=9, padx=(0, 8))
        csv_entry.config(state="readonly", readonlybackground=BG3)

        self._pill_btn(csv_file_row, "Import CSV", self._import_csv).grid(row=0, column=1)

        # ── Progress ────────────────────────────
        prog_card = tk.Frame(self, bg=BG2)
        prog_card.pack(fill="x", padx=20, pady=(8, 0))
        prog_inner = tk.Frame(prog_card, bg=BG2)
        prog_inner.pack(fill="x", padx=20, pady=12)

        self._progress = ttk.Progressbar(prog_inner, mode="indeterminate",
                                         style="indigo.Horizontal.TProgressbar")
        self._progress.pack(fill="x")

        self._track_lbl = tk.Label(prog_inner, text="", font=("Segoe UI", 9),
                                   bg=BG2, fg=TEXT_MID)
        self._track_lbl.pack(anchor="w", pady=(6, 0))

        # ── Pulsanti ────────────────────────────
        btn_row = tk.Frame(self, bg=BG, pady=10)
        btn_row.pack(fill="x", padx=20)

        self._dl_btn = self._action_btn(btn_row, "⬇  Scarica",
                                        self._start_download, primary=True)
        self._dl_btn.pack(side="left")

        self._stop_btn = self._action_btn(btn_row, "⏹  Stop",
                                          self._stop_download, primary=False)
        self._stop_btn.pack(side="left", padx=(10, 0))
        self._stop_btn.config(state="disabled")

        self._open_btn = self._action_btn(btn_row, "📂  Apri cartella",
                                          self._open_folder, primary=False)
        self._open_btn.pack(side="right")

        # ── Log ─────────────────────────────────
        log_outer = tk.Frame(self, bg=BG)
        log_outer.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        log_hdr = tk.Frame(log_outer, bg=BG)
        log_hdr.pack(fill="x", pady=(4, 6))
        tk.Label(log_hdr, text="CONSOLE", font=("Segoe UI", 8),
                 bg=BG, fg=TEXT_DIM).pack(side="left")
        self._pill_btn(log_hdr, "Pulisci", self._clear_log,
                       tiny=True).pack(side="right")

        log_card = tk.Frame(log_outer, bg=BG3,
                            highlightthickness=1, highlightbackground=BG4)
        log_card.pack(fill="both", expand=True)

        self._log = tk.Text(log_card, font=("Cascadia Code", 9),
                            bg=BG3, fg=TEXT_MID,
                            insertbackground=ACCENT, relief="flat", bd=10,
                            state="disabled", wrap="word",
                            selectbackground=BG4, selectforeground=TEXT)
        scroll = ttk.Scrollbar(log_card, orient="vertical",
                               command=self._log.yview)
        self._log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._log.pack(side="left", fill="both", expand=True)

        self._log.tag_config("ok",   foreground=OK_CLR)
        self._log.tag_config("err",  foreground=ERROR_CLR)
        self._log.tag_config("warn", foreground=WARN_CLR)
        self._log.tag_config("dim",  foreground=TEXT_DIM)
        self._log.tag_config("bold", foreground=TEXT,
                             font=("Cascadia Code", 9, "bold"))

        # ── ttk styles ──────────────────────────
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("indigo.Horizontal.TProgressbar",
            troughcolor=BG4, background=ACCENT,
            darkcolor=ACCENT3, lightcolor=ACCENT2,
            bordercolor=BG4, thickness=4)

        style.configure("TScrollbar", background=BG4,
            troughcolor=BG3, bordercolor=BG3,
            arrowcolor=BG4, relief="flat")

        style.configure("indigo.TCombobox",
            fieldbackground=BG3, background=BG3,
            foreground=TEXT, arrowcolor=ACCENT2,
            selectbackground=BG3, selectforeground=TEXT,
            bordercolor=BG4, lightcolor=BG4,
            darkcolor=BG4)

        style.map("indigo.TCombobox",
            fieldbackground=[("readonly", BG3)],
            selectbackground=[("readonly", BG3)],
            selectforeground=[("readonly", TEXT)]
        )

        style.configure("indigo.TEntry",
            fieldbackground=BG3,
            background=BG3,
            foreground=TEXT,
            bordercolor=BG4,
            lightcolor=BG4,
            darkcolor=BG4
        )

        self.option_add("*TCombobox*Listbox.background", BG3)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", TEXT)

    # ──────────────────────────────────────────
    #  Widget helpers
    # ──────────────────────────────────────────
    def _field_label(self, parent, text):
        return tk.Label(parent, text=text,
                        font=("Segoe UI", 8), bg=parent.cget("bg"),
                        fg=TEXT_DIM)

    def _label(self, parent, text):
        return tk.Label(parent, text=text, font=FONT_MAIN,
                        bg=parent.cget("bg"), fg=TEXT_DIM)

    def _make_entry(self, parent, var):
        e = tk.Entry(parent, textvariable=var,
                     font=("Segoe UI", 10), bg=BG3, fg=TEXT,
                     insertbackground=ACCENT2, relief="flat", bd=0,
                     highlightthickness=1,
                     highlightbackground=BG4,
                     highlightcolor=ACCENT)
        return e

    def _make_combobox(self, parent, var, values):
        cb = ttk.Combobox(parent, textvariable=var, values=values,
                          state="readonly", style="indigo.TCombobox",
                          font=("Segoe UI", 10), width=8)
        return cb

    def _pill_btn(self, parent, text, cmd, tiny=False):
        fnt  = ("Segoe UI", 8)  if tiny else ("Segoe UI", 9)
        padx = 8                if tiny else 14
        pady = 3                if tiny else 6
        b = tk.Button(parent, text=text, command=cmd,
                      font=fnt, bg=BG4, fg=TEXT_MID,
                      activebackground=ACCENT3, activeforeground=TEXT,
                      relief="flat", bd=0, padx=padx, pady=pady,
                      cursor="hand2")
        return b

    def _action_btn(self, parent, text, cmd, primary=True):
        bg  = ACCENT   if primary else BG4
        fg  = "#ffffff" if primary else TEXT_MID
        abg = ACCENT2  if primary else ACCENT3
        afg = "#ffffff"
        b = tk.Button(parent, text=text, command=cmd,
                      font=("Segoe UI Semibold", 10),
                      bg=bg, fg=fg,
                      activebackground=abg, activeforeground=afg,
                      relief="flat", bd=0, padx=20, pady=8,
                      cursor="hand2")
        return b

    def _btn(self, parent, text, cmd, accent=True, small=False):
        """Compatibilità con codice esistente"""
        return self._action_btn(parent, text, cmd, primary=accent)

    def _combobox(self, parent, var, values):
        return self._make_combobox(parent, var, values)

    # ──────────────────────────────────────────
    #  Log
    # ──────────────────────────────────────────
    def _log_write(self, text, tag=""):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.configure(state="normal")
        self._log.insert("end", f"[{ts}] ", "dim")
        self._log.insert("end", text + "\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    # ──────────────────────────────────────────
    #  Azioni UI
    # ──────────────────────────────────────────
    def _paste_text(self):
        try:
            text = self.clipboard_get()
            self._song_var.set(text.strip())
        except tk.TclError:
            pass

    def _browse_dir(self):
        d = filedialog.askdirectory(title="Scegli cartella di destinazione",
                                    initialdir=self._dir_var.get())
        if d:
            self._dir_var.set(d)

    def _open_folder(self):
        path = self._dir_var.get()
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    # ──────────────────────────────────────────
    #  Controllo dipendenze
    # ──────────────────────────────────────────
    def _check_deps_async(self):
        threading.Thread(target=self._check_deps, daemon=True).start()

    def _check_deps(self):
        ok_ytdlp = self._check_ytdlp()
        ok_ffmpeg = self._which("ffmpeg")

        if ok_ytdlp and ok_ffmpeg:
            self.after(0, lambda: self._set_status("Pronto", ACCENT))
            self.after(0, lambda: self._log_write("yt-dlp e ffmpeg trovati ✓", "ok"))
        else:
            msgs = []
            if not ok_ytdlp:
                msgs.append("yt-dlp not found  → run PythofySetup.exe to install dependencies")
            if not ok_ffmpeg:
                msgs.append("ffmpeg not found  → run PythofySetup.exe to install dependencies")
            self.after(0, lambda: self._set_status("Dipendenze mancanti", ERROR_CLR))
            for m in msgs:
                self.after(0, lambda m=m: self._log_write(m, "err"))

    def _check_ytdlp(self):
        try:
            subprocess.run(_find_cmd("yt-dlp") + [ "--version"], 
                         capture_output=True, timeout=8)
            return True
        except Exception:
            return False

    def _which(self, cmd):
        try:
            subprocess.run([cmd, "--version"], capture_output=True, timeout=8)
            return True
        except Exception:
            return False

    def _set_status(self, text, color):
        self._status_lbl.config(text=text)
        self._status_dot.config(fg=color)

    # ──────────────────────────────────────────
    #  Download
    # ──────────────────────────────────────────
    def _import_csv(self):
        """Importa un CSV Exportify e carica le canzoni in memoria"""
        import csv as _csv
        path = filedialog.askopenfilename(
            title="Seleziona CSV Exportify",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            songs = []
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    name    = (row.get("Track Name") or row.get("name") or "").strip()
                    artists = (row.get("Artist Name(s)") or row.get("artists") or "").strip()
                    if name and artists:
                        songs.append(f"{artists} - {name}")
                    elif name:
                        songs.append(name)
            if not songs:
                messagebox.showerror("CSV vuoto", "Nessuna canzone trovata nel CSV.")
                return
            self._csv_songs = songs
            self._csv_var.set(f"{os.path.basename(path)}  ({len(songs)} canzoni)")
            self._log_write(f"\U0001f4c4 CSV importato: {len(songs)} canzoni da {os.path.basename(path)}", "ok")
        except Exception as e:
            messagebox.showerror("Errore CSV", f"Impossibile leggere il file:\n{e}")

    def _start_download(self):
        url = self._song_var.get().strip()
        out = self._dir_var.get().strip()
        csv_songs = getattr(self, "_csv_songs", None)

        if not url and not csv_songs:
            messagebox.showwarning("Input mancante", "Inserisci l'URL di una playlist/brano Spotify o importa un CSV Exportify.")
            return
        if url and "spotify.com" not in url:
            messagebox.showwarning("URL non valido", "L'URL deve essere un link a una playlist o brano Spotify.")
            return
        if url and not ("playlist" in url or "track" in url):
            messagebox.showwarning("URL non valido", "L'URL deve essere un link a una playlist o brano Spotify.")
            return
        if not out:
            messagebox.showwarning("Cartella mancante", "Specifica una cartella di destinazione.")
            return

        os.makedirs(out, exist_ok=True)

        self._running = True
        self._dl_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._progress.start(12)
        self._set_status("Estrazione canzoni\u2026", WARN_CLR)
        if url:
            self._log_write(f"URL Playlist: {url}", "bold")
        self._log_write(f"Destinazione: {out}", "dim")

        threading.Thread(target=self._extract_and_download,
                         args=(url, out, self._qual_var.get(), csv_songs),
                         daemon=True).start()

    def _extract_and_download(self, spotify_url, out, quality, csv_songs=None):
        """Estrae le canzoni da Spotify e le scarica da YouTube"""
        try:
            if csv_songs:
                self.after(0, lambda n=len(csv_songs): self._log_write(
                    f"\U0001f4c4 Uso lista da CSV: {n} canzoni", "ok"))
                songs = csv_songs
            else:
                # Controlla se è un brano singolo o una playlist
                if self._is_track_url(spotify_url):
                    self.after(0, lambda: self._log_write("\U0001f50d Leggo il brano da Spotify\u2026", "dim"))
                    song_info = self._get_track_info(spotify_url)
                    if song_info:
                        songs = [song_info]
                    else:
                        songs = None
                else:
                    try:
                        num_songs = int(self._num_songs_var.get())
                    except Exception:
                        num_songs = 100
                    num_songs = max(1, min(100, num_songs))
                    self.after(0, lambda: self._log_write("\U0001f50d Leggo la playlist da Spotify\u2026", "dim"))
                    songs = self._get_songs_requests(spotify_url, num_songs)

            if not songs:
                self.after(0, lambda: self._log_write(
                    "❌ Impossibile estrarre le canzoni dalla playlist", "err"))
                self.after(0, lambda: self._set_status("Errore", ERROR_CLR))
                self._running = False
                self.after(0, self._on_done)
                return

            # Crea una sottocartella per questo download
            playlist_name = None
            if not self._is_track_url(spotify_url):
                # Estrai il nome della playlist
                playlist_name = self._get_playlist_name(spotify_url)
            
            subfolder_name = self._get_download_subfolder_name(spotify_url, songs, playlist_name)
            out = os.path.join(out, subfolder_name)
            os.makedirs(out, exist_ok=True)
            self.after(0, lambda: self._log_write(f"📁 Cartella: {subfolder_name}", "dim"))

            # Step 2: carica la lista di canzoni già scaricate (resume)
            done_file = self._done_file_path(spotify_url, out)
            already_done = self._load_done(done_file)

            if already_done:
                skipped = sum(1 for s in songs if s in already_done)
                if skipped:
                    self.after(0, lambda: self._log_write(
                        f"⏭ Resume: salto {skipped} canzoni già scaricate", "ok"))

            self._songs_list  = songs
            self._done_file   = done_file
            self._already_done = already_done
            self._current_song_idx = 0
            self._download_next_song(out, quality)

        except Exception as e:
            self.after(0, lambda: self._log_write(f"❌ Errore: {e}", "err"))
            self.after(0, lambda: self._set_status("Errore", ERROR_CLR))
            self._running = False
            self.after(0, self._on_done)

    def _done_file_path(self, spotify_url, out):
        """Percorso del file che traccia le canzoni già scaricate"""
        playlist_id = self._extract_playlist_id(spotify_url) or "playlist"
        return os.path.join(out, f".pythofy_done_{playlist_id}.json")

    def _load_done(self, done_file):
        """Carica il set delle canzoni già scaricate"""
        try:
            if os.path.exists(done_file):
                with open(done_file, "r", encoding="utf-8") as f:
                    return set(json.load(f))
        except Exception:
            pass
        return set()

    def _save_done(self, done_file, already_done):
        """Salva il set delle canzoni già scaricate"""
        try:
            with open(done_file, "w", encoding="utf-8") as f:
                json.dump(list(already_done), f, ensure_ascii=False)
        except Exception:
            pass


    def _extract_playlist_id(self, url):
        """Estrae l'ID della playlist dall'URL Spotify"""
        match = re.search(r'playlist/([a-zA-Z0-9]+)', url)
        return match.group(1) if match else None

    def _extract_track_id(self, url):
        """Estrae l'ID del brano dall'URL Spotify"""
        match = re.search(r'track/([a-zA-Z0-9]+)', url)
        return match.group(1) if match else None

    def _is_track_url(self, url):
        """Controlla se l'URL è un brano Spotify"""
        return "track" in url and self._extract_track_id(url) is not None

    def _is_playlist_url(self, url):
        """Controlla se l'URL è una playlist Spotify"""
        return "playlist" in url and self._extract_playlist_id(url) is not None

    def _get_download_subfolder_name(self, spotify_url, songs, playlist_name=None):
        """
        Genera il nome della sottocartella in base al tipo di download.
        Per brani singoli: usa il nome del brano.
        Per playlist: usa il nome della playlist.
        """
        if len(songs) == 1 and self._is_track_url(spotify_url):
            # È un brano singolo: usa il nome del brano
            song_name = songs[0]
            # Rimuovi caratteri non validi per nomi di file/cartella
            safe_name = re.sub(r'[<>:"/\\|?*]', '', song_name).strip()
            return safe_name[:80]  # Limita la lunghezza
        else:
            # È una playlist
            if playlist_name:
                safe_name = re.sub(r'[<>:"/\\|?*]', '', playlist_name).strip()
                return f"Playlist_{safe_name}"[:100]
            else:
                playlist_id = self._extract_playlist_id(spotify_url) or "playlist"
                return f"Playlist_{playlist_id}"

    def _get_playlist_name(self, spotify_url):
        """
        Estrae il nome della playlist da Spotify.
        Ritorna il nome della playlist.
        """
        try:
            import urllib.request, ssl

            playlist_id = self._extract_playlist_id(spotify_url)
            if not playlist_id:
                return None

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
            self.after(0, lambda: self._log_write("   📡 scarico nome playlist…", "dim"))

            req = urllib.request.Request(embed_url, headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            data = None
            for script in scripts:
                if "spotify:playlist" in script:
                    try:
                        data = json.loads(script)
                        break
                    except Exception:
                        continue

            if not data:
                return None

            # Estrai il nome della playlist
            meta = data.get("props", {}).get("pageProps", {}).get("meta", {})
            playlist_title = meta.get("name", "").strip()

            if not playlist_title:
                # Fallback: cerca in altri path possibili
                data_entity = (
                    data.get("props", {})
                        .get("pageProps", {})
                        .get("state", {})
                        .get("data", {})
                        .get("entity", {})
                )
                playlist_title = data_entity.get("title", "").strip()

            return playlist_title if playlist_title else None

        except Exception as e:
            return None

    def _get_track_info(self, spotify_url):
        """
        Estrae le informazioni di un singolo brano da Spotify.
        Ritorna una stringa nel formato: "Artista - Nome Brano"
        """
        try:
            import urllib.request, ssl

            track_id = self._extract_track_id(spotify_url)
            if not track_id:
                self.after(0, lambda: self._log_write("❌ ID brano non trovato nell'URL", "err"))
                return None

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            embed_url = f"https://open.spotify.com/embed/track/{track_id}"
            self.after(0, lambda: self._log_write("   📡 scarico pagina embed Spotify…", "dim"))

            req = urllib.request.Request(embed_url, headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            data = None
            for script in scripts:
                if "spotify:track" in script:
                    try:
                        data = json.loads(script)
                        break
                    except Exception:
                        continue

            if not data:
                self.after(0, lambda: self._log_write("⚠ JSON non trovato nella pagina embed", "warn"))
                return None

            # Estrai il nome del brano e gli artisti
            meta = data.get("props", {}).get("pageProps", {}).get("meta", {})
            title = meta.get("name", "").strip()
            artist_list = meta.get("artists", [])
            artist_names = ", ".join([a.get("name", "") for a in artist_list if a.get("name")])

            if not title:
                # Fallback: cerca in altri path possibili
                data_entity = (
                    data.get("props", {})
                        .get("pageProps", {})
                        .get("state", {})
                        .get("data", {})
                        .get("entity", {})
                )
                title = data_entity.get("title", "").strip()
                artist_names = data_entity.get("subtitle", "").strip()

            if not title:
                self.after(0, lambda: self._log_write("❌ Impossibile estrarre i dati del brano", "err"))
                return None

            song_name = f"{artist_names} - {title}" if artist_names else title
            self.after(0, lambda: self._log_write(
                f"🎵 Brano trovato: {song_name}", "ok"))
            return song_name

        except Exception as e:
            self.after(0, lambda e=e: self._log_write(f"⚠ Errore estrazione brano: {e}", "warn"))
            return None

    def _get_songs_requests(self, spotify_url, num_songs=100):
        """
        Estrae le canzoni dalla pagina embed di Spotify.
        Poiché l'embed ignora l'offset, fa più richieste alla stessa pagina
        e si ferma quando ha raggiunto num_songs o non trova nuove canzoni.
        """
        try:
            import urllib.request, ssl, time

            playlist_id = self._extract_playlist_id(spotify_url)
            if not playlist_id:
                self.after(0, lambda: self._log_write("❌ ID playlist non trovato nell'URL", "err"))
                return None

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
            self.after(0, lambda: self._log_write("   📡 scarico pagina embed Spotify…", "dim"))

            req = urllib.request.Request(embed_url, headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            data = None
            for script in scripts:
                if "spotify:track" in script and "trackList" in script:
                    try:
                        data = json.loads(script)
                        break
                    except Exception:
                        continue

            if not data:
                self.after(0, lambda: self._log_write("⚠ JSON non trovato nella pagina embed", "warn"))
                return None

            track_list = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("state", {})
                    .get("data", {})
                    .get("entity", {})
                    .get("trackList", [])
            )

            if not track_list:
                return None

            songs = []
            for t in track_list:
                title    = t.get("title", "").strip()
                subtitle = t.get("subtitle", "").strip()
                if title and subtitle:
                    songs.append(f"{subtitle} - {title}")
                elif title:
                    songs.append(title)

            if not songs:
                return None

            # Tronca al numero dichiarato dall'utente
            if num_songs < len(songs):
                songs = songs[:num_songs]

            if num_songs > len(songs):
                self.after(0, lambda g=len(songs), t=num_songs: self._log_write(
                    f"   ⚠ L'embed mostra solo {g} canzoni su {t} dichiarate — scarico quelle disponibili", "warn"))

            self.after(0, lambda n=len(songs): self._log_write(
                f"📋 Trovate {n} canzoni", "ok"))
            return songs

        except Exception as e:
            self.after(0, lambda e=e: self._log_write(f"⚠ Errore scraping embed: {e}", "warn"))
            return None
    def _get_spotify_anon_token(self, ctx=None):
        """
        Ottiene un token anonimo da Spotify usando l'endpoint pubblico
        che non richiede autenticazione.
        """
        try:
            import urllib.request, ssl
            if ctx is None:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            # Endpoint pubblico che restituisce un token anonimo valido
            req = urllib.request.Request(
                "https://open.spotify.com/get_access_token?reason=transport&productType=web_player",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                    "Referer": "https://open.spotify.com/",
                }
            )
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                data = json.loads(resp.read().decode())
                token = data.get("accessToken")
                if token:
                    return token
        except Exception:
            pass
        return None

    def _get_spotify_songs_spotdl(self, spotify_url):
        """Estrae le canzoni dalla playlist usando spotdl save → JSON"""
        import tempfile, json as _json, time

        try:
            tmp_dir  = tempfile.mkdtemp()
            tmp_file = os.path.join(tmp_dir, "playlist.spotdl")

            self.after(0, lambda: self._log_write("🔍 Connessione a Spotify per recuperare i metadati…", "dim"))

            # Avvia spotdl save in background e mostra un heartbeat ogni secondo
            proc = subprocess.Popen(
                _find_cmd("spotdl") + [ "save", spotify_url,
                 "--save-file", tmp_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            dots = 0
            while proc.poll() is None:
                time.sleep(1)
                dots += 1
                msg = f"   ⏳ recupero metadati in corso{'.' * (dots % 4 + 1)}"
                self.after(0, lambda m=msg: self._log_write(m, "dim"))

            # Leggi eventuale output residuo
            remaining = proc.stdout.read()
            if remaining:
                for line in remaining.splitlines():
                    if line.strip():
                        self.after(0, lambda l=line.strip(): self._log_write(f"   spotdl: {l}", "dim"))

            if not os.path.exists(tmp_file):
                self.after(0, lambda: self._log_write(
                    "❌ spotdl save non ha prodotto il file — controlla che spotdl sia aggiornato", "err"))
                return None

            with open(tmp_file, "r", encoding="utf-8") as f:
                data = _json.load(f)

            songs = []
            entries = data if isinstance(data, list) else data.get("songs", [])
            for entry in entries:
                name    = entry.get("name", "")
                artists = entry.get("artist") or ", ".join(entry.get("artists", []))
                if name and artists:
                    songs.append(f"{artists} - {name}")
                elif name:
                    songs.append(name)

            os.remove(tmp_file)

            # Stampa l'elenco completo delle canzoni trovate
            if songs:
                self.after(0, lambda: self._log_write(f"📋 Trovate {len(songs)} canzoni:", "ok"))
                for i, s in enumerate(songs, 1):
                    idx, song = i, s  # evita closure loop bug
                    self.after(0, lambda i=idx, s=song: self._log_write(f"   {i:>2}. {s}", "dim"))

            return songs if songs else None

        except Exception as e:
            self.after(0, lambda: self._log_write(f"Errore con spotdl: {str(e)[:80]}", "warn"))
            return None


    def _download_next_song(self, out, quality):
        """Scarica la prossima canzone della lista, saltando quelle già fatte"""
        # Avanza fino alla prossima canzone non ancora scaricata
        while self._current_song_idx < len(self._songs_list):
            song = self._songs_list[self._current_song_idx]
            if song in self._already_done:
                self._current_song_idx += 1
                n = self._current_song_idx
                self.after(0, lambda n=n, s=song: self._log_write(
                    f"⏭  [{n}/{len(self._songs_list)}] già scaricata: {s}", "dim"))
            else:
                break

        if not self._running or self._current_song_idx >= len(self._songs_list):
            if self._running:
                total = len(self._songs_list)
                self.after(0, lambda: self._log_write(
                    f"✅ Tutti i download completati! ({total} canzoni)", "ok"))
                self.after(0, lambda: self._set_status("Completato", ACCENT))
            self._running = False
            self.after(0, self._on_done)
            return

        song = self._songs_list[self._current_song_idx]
        self._current_song_idx += 1
        idx = self._current_song_idx

        self.after(0, lambda: self._log_write(
            f"━━━ [{idx}/{len(self._songs_list)}] {song}", "bold"))
        self.after(0, lambda: self._log_write(
            f"   🔎 cerco su YouTube: {song}…", "dim"))
        self.after(0, lambda: self._track_lbl.config(
            text=f"⏳  [{idx}/{len(self._songs_list)}] {song}  —  ricerca su YouTube"))

        def on_complete(success):
            if success:
                self._already_done.add(song)
                self._save_done(self._done_file, self._already_done)
                self.after(0, lambda: self._log_write(f"   ✓ scaricata: {song}", "ok"))
                self._retry_count.pop(song, None)  # Resetta contatore retry
                self._download_next_song(out, quality)
            else:
                # Gestisci il retry
                current_retry = self._retry_count.get(song, 0)
                if current_retry < self._max_retries:
                    self._retry_count[song] = current_retry + 1
                    self.after(0, lambda c=current_retry+1, m=self._max_retries:
                        self._log_write(f"   🔄 Riprovo ({c}/{m})...", "warn"))
                    # Riprova subito
                    self.after(500, lambda: self._download_song_youtube(song, out, quality, on_complete))
                else:
                    self.after(0, lambda: self._log_write(f"   ❌ Saltato dopo {self._max_retries} tentativi", "err"))
                    self._retry_count.pop(song, None)  # Resetta contatore
                    self._download_next_song(out, quality)

        self._download_song_youtube(song, out, quality, on_complete)

    def _run_ytdlp(self, song, out, quality):
        # Comando yt-dlp per cercare e scaricare da YouTube
        cmd = _find_cmd("yt-dlp") + [
            f"ytsearch:{song}",
            "-x",  # Estrai solo audio
            "-f", "bestaudio",
            "--audio-format", "mp3",
            "--audio-quality", quality,
            "-o", os.path.join(out, "%(title)s.%(ext)s"),
            "--no-warnings",
            "--embed-metadata",
            "--embed-thumbnail",
        ]
        
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in self._process.stdout:
                line = line.rstrip()
                if not line:
                    continue
                tag = self._classify_line(line)
                self.after(0, lambda l=line, t=tag: self._log_write(l, t))
                
                # Aggiorna il label della canzone
                self._update_track_label(line)

            self._process.wait()
            rc = self._process.returncode

            if rc == 0:
                self.after(0, lambda: self._log_write("✓ Canzone scaricata", "ok"))
            elif self._running:
                self.after(0, lambda: self._log_write(f"⚠ Errore nel download (codice {rc})", "warn"))
        except FileNotFoundError:
            self.after(0, lambda: self._log_write("❌ yt-dlp non trovato. Installalo con: pip install yt-dlp", "err"))
            self.after(0, lambda: self._set_status("Errore", ERROR_CLR))
        except Exception as e:
            self.after(0, lambda: self._log_write(f"❌ Errore: {e}", "err"))
            self.after(0, lambda: self._set_status("Errore", ERROR_CLR))

    def _download_song_youtube(self, song, out, quality, on_complete):
        """Scarica una singola canzone da YouTube (versione per batch)"""
        import time

        cmd = _find_cmd("yt-dlp") + [
            f"ytsearch:{song}",
            "-x",
            "-f", "bestaudio",
            "--audio-format", "mp3",
            "--audio-quality", quality,
            "-o", os.path.join(out, "%(title)s.%(ext)s"),
            "--no-warnings",
            "--embed-metadata",
            "--embed-thumbnail",
        ]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            last_heartbeat = time.time()
            phase = "ricerca"

            for line in self._process.stdout:
                if not self._running:
                    self._process.terminate()
                    break

                line = line.rstrip()
                if not line:
                    continue

                l = line.lower()
                if "searching" in l or "ytsearch" in l:
                    phase = "ricerca su YouTube"
                elif "[download]" in l and "%" in l:
                    m = re.search(r'(\d+\.\d+)%', line)
                    if m:
                        phase = f"download {m.group(1)}%"
                elif "[ffmpeg]" in l or "converting" in l:
                    phase = "conversione in mp3"
                elif "deleting" in l:
                    phase = "pulizia file temporanei"

                tag = self._classify_line(line)
                self.after(0, lambda l=line, t=tag: self._log_write(f"   {l}", t))

                now = time.time()
                if now - last_heartbeat >= 1.0:
                    last_heartbeat = now
                    p = phase
                    idx = self._current_song_idx
                    total = len(self._songs_list)
                    s = self._songs_list[idx - 1] if idx > 0 else song
                    self.after(0, lambda p=p, s=s, i=idx, t=total:
                        self._track_lbl.config(text=f"⏳  [{i}/{t}] {s}  —  {p}"))

            self._process.wait()
            rc = self._process.returncode

            if self._running:
                on_complete(rc == 0)
        except Exception as e:
            if self._running:
                self.after(0, lambda: self._log_write(
                    f"⚠ Errore nel download: {str(e)[:80]}", "warn"))
                on_complete(False)

    def _classify_line(self, line):
        l = line.lower()
        if any(w in l for w in ("error", "failed", "❌", "unable")):
            return "err"
        if any(w in l for w in ("warning", "warn", "skip")):
            return "warn"
        if any(w in l for w in ("downloaded", "complete", "✅", "done", "finished", "deleting")):
            return "ok"
        return ""

    def _update_track_label(self, line):
        """Estrae il titolo della canzone dall'output di yt-dlp e aggiorna il label"""
        l = line.strip()
        
        # Cerca pattern di yt-dlp
        if any(keyword in l for keyword in ("[youtube]", "Downloading", "[ffmpeg]", "Extracting")):
            # Estrai il titolo dal pattern "[youtube] video_id: Downloading webpage"
            match = re.search(r'\[youtube\]\s+([^:]+):\s+(.+)', l)
            if match:
                title = match.group(2)
            else:
                title = l
            
            # Rimuovi prefissi comuni
            for prefix in ["[youtube]", "[ffmpeg]", "Downloading", "Extracting"]:
                title = title.replace(prefix, "").strip()
            
            if title and len(title) > 5:
                self.after(0, lambda text=title: self._track_lbl.config(text=f"⏳  {text}"))

    def _stop_download(self):
        self._running = False
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self._log_write("⏹ Download interrotto dall'utente.", "warn")
            self._set_status("Interrotto", WARN_CLR)
        self._on_done()

    def _on_done(self):
        self._progress.stop()
        self._dl_btn.config(state="normal")
        self._stop_btn.config(state="disabled")
        self._track_lbl.config(text="")


# ──────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    app = YouTubeDownloaderApp()
    app.mainloop()