#!/usr/bin/env python3
"""
Pythofy — Spotify & YouTube to MP3 Downloader
---------------------------------------------
Download songs from Spotify, YouTube, or playlists as MP3 files.

Requirements:
    yt-dlp and ffmpeg installed
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
    # pythofy_tools ha priorità: usa sempre la versione bundled se disponibile
    base_path = os.path.dirname(sys.executable) if frozen else os.path.dirname(__file__)
    local_tool = os.path.join(base_path, "pythofy_tools", name + ".exe")
    if os.path.exists(local_tool):
        return [local_tool]
    exe = shutil.which(name) or shutil.which(name + ".exe")
    if exe:
        return [exe]
    if not frozen:
        module = name.replace("-", "_")
        return [sys.executable, "-m", module]
    return [name]


# Flag per nascondere finestre console su Windows
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ──────────────────────────────────────────────────────────────
#  PALETTE  —  terminal-luxe: near-black + acid green + zinc
# ──────────────────────────────────────────────────────────────
BG        = "#0d0d0d"   # true black background
BG2       = "#111111"   # panels
BG3       = "#161616"   # inputs / console bg
BG4       = "#1e1e1e"   # borders / hover
BG5       = "#252525"   # slightly lighter border
ACCENT    = "#a3e635"   # acid lime green (primary)
ACCENT2   = "#bef264"   # lighter lime (hover)
ACCENT3   = "#4d7c0f"   # dark lime (pressed)
TEXT      = "#e4e4e4"   # primary text
TEXT_DIM  = "#444444"   # muted labels
TEXT_MID  = "#888888"   # secondary text
TEXT_SUB  = "#666666"   # subtle text
ERROR_CLR = "#f87171"   # red
WARN_CLR  = "#fbbf24"   # amber
OK_CLR    = "#a3e635"   # same as accent
BORDER    = "#222222"   # default border
MONO      = "Arial"
SANS      = "Arial"

APP_VERSION  = "1.3.0"
GITHUB_REPO  = "goldyreal/PythofyDownloader"


class YouTubeDownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Pythofy v{APP_VERSION}")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(1080, 580)
        self.geometry("1080x680")

        self._process = None
        self._running = False
        self._num_songs_var = tk.IntVar(value=100)
        self._csv_songs = None
        self._csv_file_name = None
        self._songs_list = []
        self._current_song_idx = 0
        self._done_file    = None
        self._already_done = set()
        self._retry_count  = {}
        self._max_retries  = 3
        self._is_youtube_mode = False

        self._setup_styles()
        self._build_ui()
        self._check_deps_async()
        self.after(1500, self._check_updates_async)
        self.after(200, self._check_rollback_available)

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("app.Horizontal.TProgressbar",
            troughcolor=BG4, background=ACCENT,
            darkcolor=ACCENT3, lightcolor=ACCENT2,
            bordercolor=BG4, thickness=2)
        style.configure("TScrollbar",
            background=BG4, troughcolor=BG3,
            bordercolor=BG3, arrowcolor=BG4, relief="flat")
        style.configure("app.TCombobox",
            fieldbackground=BG3, background=BG3,
            foreground=TEXT, arrowcolor=TEXT_MID,
            selectbackground=BG3, selectforeground=TEXT,
            bordercolor=BG4, lightcolor=BG4, darkcolor=BG4)
        style.map("app.TCombobox",
            fieldbackground=[("readonly", BG3)],
            selectbackground=[("readonly", BG3)],
            selectforeground=[("readonly", TEXT)])
        self.option_add("*TCombobox*Listbox.background", BG3)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT3)
        self.option_add("*TCombobox*Listbox.selectForeground", TEXT)

    def _build_ui(self):
        # ── Top bar ─────────────────────────────
        topbar = tk.Frame(self, bg=BG2, height=48)
        topbar.pack(fill="x", side="top")
        topbar.pack_propagate(False)

        wm = tk.Frame(topbar, bg=BG2)
        wm.pack(side="left", padx=(20, 0))
        tk.Label(wm, text="PY", font=(MONO, 13, "bold"), bg=BG2, fg=ACCENT).pack(side="left")
        tk.Label(wm, text="THOFY", font=(MONO, 13, "bold"), bg=BG2, fg=TEXT).pack(side="left")
        tk.Label(wm, text=" /downloader", font=(MONO, 9), bg=BG2, fg=TEXT_DIM).pack(side="left", padx=(6, 0))

        status_r = tk.Frame(topbar, bg=BG2)
        status_r.pack(side="right", padx=(0, 20))
        self._status_dot = tk.Label(status_r, text="◆", font=(MONO, 8), bg=BG2, fg=WARN_CLR)
        self._status_dot.pack(side="left", padx=(0, 6))
        self._status_lbl = tk.Label(status_r, text="starting", font=(MONO, 9), bg=BG2, fg=TEXT_MID)
        self._status_lbl.pack(side="left")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", side="top")

        # ── Main content area ───────────────────
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, side="top")

        self._left = tk.Frame(main, bg=BG, width=440)
        self._left.pack(side="left", fill="both", expand=False)
        self._left.pack_propagate(False)

        self._vsep = tk.Frame(main, bg=BORDER, width=1)
        self._vsep.pack(side="left", fill="y")

        self._right = tk.Frame(main, bg=BG3)
        self._right.pack(side="left", fill="both", expand=True)

        self._build_left(self._left)
        self._build_console(self._right)
        self._build_statusbar()

    def _build_left(self, parent):
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=BG)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def on_canvas_resize(e):
            canvas.itemconfig(win, width=e.width)

        inner.bind("<Configure>", on_configure)
        canvas.bind("<Configure>", on_canvas_resize)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(
            int(-1*(e.delta/120)), "units"))

        pad = dict(padx=28)

        # SOURCE
        self._section_label(inner, "SPOTIFY OR YOUTUBE URL (Playlist / Single Song)").pack(anchor="w", pady=(28, 10), **pad)
        url_wrap = tk.Frame(inner, bg=BG)
        url_wrap.pack(fill="x", **pad)
        url_wrap.columnconfigure(0, weight=1)
        self._song_var = tk.StringVar()
        self._entry(url_wrap, self._song_var).grid(row=0, column=0, sticky="ew", ipady=10)
        self._ghost_btn(url_wrap, "PASTE", self._paste_text).grid(row=0, column=1, padx=(8, 0))

        # DESTINATION
        self._section_label(inner, "DESTINATION").pack(anchor="w", pady=(22, 10), **pad)
        dir_wrap = tk.Frame(inner, bg=BG)
        dir_wrap.pack(fill="x", **pad)
        dir_wrap.columnconfigure(0, weight=1)
        self._dir_var = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "Downloads", "Pythofy"))
        self._entry(dir_wrap, self._dir_var).grid(row=0, column=0, sticky="ew", ipady=10)
        self._ghost_btn(dir_wrap, "BROWSE", self._browse_dir).grid(row=0, column=1, padx=(8, 0))

        # OPTIONS
        self._section_label(inner, "Options").pack(anchor="w", pady=(22, 10), **pad)
        opts = tk.Frame(inner, bg=BG)
        opts.pack(fill="x", **pad)

        q_frame = tk.Frame(opts, bg=BG)
        q_frame.pack(side="left", padx=(0, 32))
        self._micro_label(q_frame, "BITRATE (kbps)").pack(anchor="w", pady=(0, 6))
        self._qual_var = tk.StringVar(value="192")
        ttk.Combobox(q_frame, textvariable=self._qual_var,
                     values=["128", "192", "256", "320"],
                     state="readonly", style="app.TCombobox",
                     font=(SANS, 10), width=7).pack(anchor="w")

        n_frame = tk.Frame(opts, bg=BG)
        n_frame.pack(side="left")
        self._micro_label(n_frame, "TRACK LIMIT").pack(anchor="w", pady=(0, 6))
        self._num_songs_var = tk.IntVar(value=100)
        tk.Spinbox(n_frame, from_=1, to=100, textvariable=self._num_songs_var,
                   font=(SANS, 10), bg=BG3, fg=TEXT,
                   buttonbackground=BG4, relief="flat", bd=0,
                   highlightthickness=1, highlightbackground=BG4,
                   highlightcolor=ACCENT, width=5, wrap=False).pack(anchor="w", ipady=8)

        # DIVIDER
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", padx=28, pady=(24, 0))

        # LARGE PLAYLISTS
        self._section_label(inner, "LARGE PLAYLISTS (100+ TRACKS)").pack(
            anchor="w", pady=(20, 8), **pad)
        info_line = tk.Frame(inner, bg=BG)
        info_line.pack(anchor="w", **pad)
        tk.Label(info_line, text="Export using ", font=(SANS, 9), bg=BG, fg=TEXT_SUB).pack(side="left")
        lnk = tk.Label(info_line, text="exportify.net",
                       font=(SANS, 9, "underline"), bg=BG, fg=ACCENT, cursor="hand2")
        lnk.pack(side="left")
        lnk.bind("<Button-1>", lambda e: webbrowser.open("https://exportify.net"))
        tk.Label(info_line, text=" → then import the CSV below",
                 font=(SANS, 9), bg=BG, fg=TEXT_SUB).pack(side="left")
        help_btn = tk.Label(info_line, text="?", font=(SANS, 9, "bold"), bg=BG, fg=ACCENT, cursor="hand2")
        help_btn.pack(side="left", padx=(6, 0))
        help_btn.bind("<Button-1>", lambda e: self._show_exportify_tutorial())

        csv_row = tk.Frame(inner, bg=BG)
        csv_row.pack(fill="x", padx=28, pady=(10, 0))
        csv_row.columnconfigure(0, weight=1)
        self._csv_var = tk.StringVar(value="")
        csv_e = self._entry(csv_row, self._csv_var)
        csv_e.grid(row=0, column=0, sticky="ew", ipady=10)
        csv_e.config(state="readonly", readonlybackground=BG3)
        self._ghost_btn(csv_row, "IMPORT CSV", self._import_csv).grid(row=0, column=1, padx=(8, 0))

        # DIVIDER
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", padx=28, pady=(28, 0))

        # PROGRESS
        prog_outer = tk.Frame(inner, bg=BG)
        prog_outer.pack(fill="x", padx=28, pady=(20, 0))
        self._progress = ttk.Progressbar(prog_outer, mode="indeterminate",
                                          style="app.Horizontal.TProgressbar")
        self._progress.pack(fill="x")
        self._track_lbl = tk.Label(prog_outer, text="",
                                    font=(MONO, 8), bg=BG, fg=TEXT_MID)
        self._track_lbl.pack(anchor="w", pady=(8, 0))

        # ACTION BUTTONS
        btn_area = tk.Frame(inner, bg=BG)
        btn_area.pack(fill="x", padx=28, pady=(20, 32))
        self._dl_btn = self._primary_btn(btn_area, "DOWNLOAD", self._start_download)
        self._dl_btn.pack(side="left")
        self._stop_btn = self._ghost_btn(btn_area, "STOP", self._stop_download)
        self._stop_btn.pack(side="left", padx=(10, 0))
        self._stop_btn.config(state="disabled")
        self._open_btn = self._ghost_btn(btn_area, "OPEN FOLDER", self._open_folder)
        self._open_btn.pack(side="left", padx=(10, 0))

    def _build_console(self, parent):
        hdr = tk.Frame(parent, bg=BG2, height=36)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="CONSOLE", font=(MONO, 8, "bold"), bg=BG2, fg=TEXT_DIM).pack(side="left", padx=14)
        clr = tk.Label(hdr, text="CLEAR", font=(MONO, 8), bg=BG2, fg=TEXT_DIM, cursor="hand2")
        clr.pack(side="right", padx=14)
        clr.bind("<Button-1>", lambda e: self._clear_log())
        # Rollback button — visibile solo se esiste il .old
        self._rollback_lbl = tk.Label(hdr, text="↩ ROLLBACK", font=(MONO, 8), bg=BG2, fg=WARN_CLR, cursor="hand2")
        self._rollback_lbl.bind("<Button-1>", lambda e: self._confirm_rollback())
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", side="top")

        log_frame = tk.Frame(parent, bg=BG3)
        log_frame.pack(fill="both", expand=True, side="top")
        self._log = tk.Text(log_frame, font=(MONO, 8), bg=BG3, fg=TEXT_MID,
                            insertbackground=ACCENT, relief="flat", bd=12,
                            state="disabled", wrap="word",
                            selectbackground=BG4, selectforeground=TEXT)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self._log.yview)
        self._log.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._log.pack(side="left", fill="both", expand=True)
        self._log.tag_config("ok",   foreground=OK_CLR)
        self._log.tag_config("err",  foreground=ERROR_CLR)
        self._log.tag_config("warn", foreground=WARN_CLR)
        self._log.tag_config("dim",  foreground=TEXT_DIM)
        self._log.tag_config("bold", foreground=TEXT, font=(MONO, 8, "bold"))

    def _build_statusbar(self):
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", side="bottom")
        bar = tk.Frame(self, bg=BG2, height=26)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self._bar_lbl = tk.Label(bar, text="", font=(MONO, 8), bg=BG2, fg=TEXT_DIM)
        self._bar_lbl.pack(side="left", padx=14)

    # ── Widget helpers ─────────────────────────
    def _section_label(self, parent, text):
        f = tk.Frame(parent, bg=BG)
        tk.Label(f, text=text, font=(MONO, 8, "bold"), bg=BG, fg=ACCENT).pack(side="left")
        return f

    def _micro_label(self, parent, text):
        return tk.Label(parent, text=text, font=(MONO, 7), bg=BG, fg=TEXT_DIM)

    def _entry(self, parent, var, placeholder=""):
        return tk.Entry(parent, textvariable=var, font=(SANS, 10),
                        bg=BG3, fg=TEXT, insertbackground=ACCENT,
                        relief="flat", bd=0, highlightthickness=1,
                        highlightbackground=BG4, highlightcolor=ACCENT)

    def _primary_btn(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd,
                         font=(MONO, 9, "bold"), bg=ACCENT, fg="#000000",
                         activebackground=ACCENT2, activeforeground="#000000",
                         relief="flat", bd=0, padx=22, pady=9, cursor="hand2")

    def _ghost_btn(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd,
                         font=(MONO, 8), bg=BG4, fg=TEXT_MID,
                         activebackground=BG5, activeforeground=TEXT,
                         relief="flat", bd=0, padx=14, pady=9, cursor="hand2")

    # Backward-compat aliases
    def _field_label(self, parent, text):
        return tk.Label(parent, text=text, font=(MONO, 7),
                        bg=parent.cget("bg"), fg=TEXT_DIM)
    def _make_entry(self, parent, var):
        return self._entry(parent, var)
    def _make_combobox(self, parent, var, values):
        return ttk.Combobox(parent, textvariable=var, values=values,
                            state="readonly", style="app.TCombobox",
                            font=(SANS, 10), width=8)
    def _pill_btn(self, parent, text, cmd, tiny=False):
        return self._ghost_btn(parent, text, cmd)
    def _action_btn(self, parent, text, cmd, primary=True):
        return self._primary_btn(parent, text, cmd) if primary else self._ghost_btn(parent, text, cmd)
    def _btn(self, parent, text, cmd, accent=True, small=False):
        return self._action_btn(parent, text, cmd, primary=accent)
    def _combobox(self, parent, var, values):
        return self._make_combobox(parent, var, values)

    # ── Log ────────────────────────────────────
    def _log_write(self, text, tag=""):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.configure(state="normal")
        self._log.insert("end", f"[{ts}] ", "dim")
        self._log.insert("end", text + "\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")
        short = text[:90] + ("…" if len(text) > 90 else "")
        self._bar_lbl.config(text=short)

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    # ── UI Actions ─────────────────────────────
    def _paste_text(self):
        try:
            text = self.clipboard_get()
            self._song_var.set(text.strip())
        except tk.TclError:
            pass

    def _browse_dir(self):
        d = filedialog.askdirectory(title="Choose destination folder",
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

    def _show_exportify_tutorial(self):
        """Show a tutorial window for Exportify"""
        tutorial = tk.Toplevel(self)
        tutorial.title("Exportify Tutorial")
        tutorial.geometry("500x600")
        tutorial.configure(bg=BG)
        
        # Header
        hdr = tk.Frame(tutorial, bg=BG2, height=40)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="How to Export from Spotify with Exportify", 
                 font=(SANS, 11, "bold"), bg=BG2, fg=ACCENT).pack(side="left", padx=14, pady=8)
        
        tk.Frame(tutorial, bg=BORDER, height=1).pack(fill="x", side="top")
        
        # Content
        content = tk.Frame(tutorial, bg=BG)
        content.pack(fill="both", expand=True, side="top", padx=20, pady=20)
        
        tutorial_text = """Step 1: Go to exportify.net
Open your browser and visit https://exportify.net

Step 2: Login with Spotify
Click "Log in with Spotify" and authorize the app

Step 3: Select Your Playlist
Choose the playlist you want to download from your Spotify library

Step 4: Export as CSV
Click "Export" to download the playlist as a CSV file

Step 5: Import into Pythofy
Click "IMPORT CSV" in Pythofy and select the file you just downloaded

Step 6: Download
Click "DOWNLOAD" and Pythofy will download all songs from your playlist"""
        
        txt = tk.Text(content, font=(SANS, 9), bg=BG3, fg=TEXT,
                     wrap="word", relief="flat", bd=0, padx=10, pady=10,
                     selectbackground=BG4, selectforeground=TEXT)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", tutorial_text)
        txt.config(state="disabled")
        
        # Footer with link
        footer = tk.Frame(tutorial, bg=BG)
        footer.pack(fill="x", side="bottom", padx=20, pady=14)
        tk.Label(footer, text="Or visit ", font=(SANS, 9), bg=BG, fg=TEXT_SUB).pack(side="left")
        lnk = tk.Label(footer, text="exportify.net", font=(SANS, 9, "underline"), 
                      bg=BG, fg=ACCENT, cursor="hand2")
        lnk.pack(side="left")
        lnk.bind("<Button-1>", lambda e: webbrowser.open("https://exportify.net"))
        tk.Label(footer, text=" directly →", font=(SANS, 9), bg=BG, fg=TEXT_SUB).pack(side="left")

    # ── Dependency check ───────────────────────
    def _check_deps_async(self):
        threading.Thread(target=self._check_deps, daemon=True).start()

    def _check_deps(self):
        ok_ytdlp  = self._check_ytdlp()
        ok_ffmpeg = self._which("ffmpeg")
        if ok_ytdlp and ok_ffmpeg:
            self.after(0, lambda: self._set_status("ready", ACCENT))
            self.after(0, lambda: self._log_write("✓ yt-dlp and ffmpeg found", "ok"))
        else:
            msgs = []
            if not ok_ytdlp:
                msgs.append("yt-dlp not found  → run PythofySetup.exe to install dependencies")
            if not ok_ffmpeg:
                msgs.append("ffmpeg not found  → run PythofySetup.exe to install dependencies")
            self.after(0, lambda: self._set_status("missing deps", ERROR_CLR))
            for m in msgs:
                self.after(0, lambda m=m: self._log_write(m, "err"))

    def _check_ytdlp(self):
        try:
            subprocess.run(
                _find_cmd("yt-dlp") + ["--version"],
                capture_output=True, timeout=8, creationflags=_NO_WINDOW,
            )
            return True
        except Exception:
            return False

    def _which(self, cmd):
        try:
            subprocess.run(
                _find_cmd(cmd) + ["--version"],
                capture_output=True, timeout=8, creationflags=_NO_WINDOW,
            )
            return True
        except Exception:
            return False

    def _set_status(self, text, color):
        self._status_lbl.config(text=text)
        self._status_dot.config(fg=color)

    def _import_csv(self):
        """Import an Exportify CSV and load songs into memory"""
        import csv as _csv
        path = filedialog.askopenfilename(
            title="Select Exportify CSV",
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
                messagebox.showerror("CSV empty", "No songs found in the CSV.")
                return
            self._csv_songs = songs
            self._csv_file_name = os.path.splitext(os.path.basename(path))[0]
            self._csv_var.set(f"{os.path.basename(path)}  ({len(songs)} songs)")
            self._log_write(f"\U0001f4c4 CSV imported: {len(songs)} songs from {os.path.basename(path)}", "ok")
        except Exception as e:
            messagebox.showerror("CSV Error", f"Unable to read the file:\n{e}")

    def _start_download(self):
        url = self._song_var.get().strip()
        out = self._dir_var.get().strip()
        csv_songs = getattr(self, "_csv_songs", None)

        if not url and not csv_songs:
            messagebox.showwarning("Missing input", "Enter a Spotify/YouTube URL or import a CSV file.")
            return
        
        # URL validation
        is_spotify = url and "spotify.com" in url
        is_youtube = url and ("youtube.com" in url or "youtu.be" in url)
        
        if url and not is_spotify and not is_youtube:
            messagebox.showwarning("Invalid URL", "Use a Spotify or YouTube URL.")
            return
        
        if url and is_spotify:
            if not ("playlist" in url or "track" in url):
                messagebox.showwarning("Invalid Spotify URL", "Use a Spotify track or playlist link.")
                return
        
        if not out:
            messagebox.showwarning("Missing folder", "Select a destination folder.")
            return

        os.makedirs(out, exist_ok=True)

        self._running = True
        self._dl_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._progress.start(12)
        self._set_status("Estrazione canzoni\u2026", WARN_CLR)
        if url:
            if is_youtube:
                self._log_write(f"URL YouTube: {url}", "bold")
            else:
                self._log_write(f"URL Spotify: {url}", "bold")
        self._log_write(f"Destination: {out}", "dim")

        threading.Thread(target=self._extract_and_download,
                         args=(url, out, self._qual_var.get(), csv_songs),
                         daemon=True).start()

    def _extract_and_download(self, spotify_url, out, quality, csv_songs=None):
        """Extract songs from Spotify/YouTube and download them"""
        try:
            # Determina il tipo di URL e source
            is_youtube = self._is_youtube_url(spotify_url) if spotify_url else False
            source = "youtube" if is_youtube else "spotify"
            is_playlist = False
            playlist_name = None
            
            if csv_songs:
                self.after(0, lambda n=len(csv_songs): self._log_write(
                    f"Using CSV list: {n} songs", "ok"))
                songs = csv_songs
                # CSV is always treated as a playlist (multiple songs)
                is_playlist = True
                source = "spotify"  # CSV songs are searched on YouTube
                playlist_name = self._csv_file_name or "Imported"  # Use CSV filename as playlist name
            elif is_youtube:
                # Gestisci download da YouTube
                self.after(0, lambda: self._log_write("YouTube URL detected", "dim"))
                
                if self._is_youtube_playlist_url(spotify_url):
                    # È una playlist YouTube
                    is_playlist = True
                    self.after(0, lambda: self._log_write("   Playlist found", "dim"))
                    playlist_name = self._get_youtube_playlist_name(spotify_url)
                    songs = self._extract_youtube_playlist_songs(spotify_url)
                else:
                    # È un video YouTube singolo
                    is_playlist = False
                    self.after(0, lambda: self._log_write("   Single video", "dim"))
                    songs = [spotify_url]  # Usa l'URL diretto
            else:
                # Gestisci download da Spotify
                # Check if it is a single track or a playlist
                if self._is_track_url(spotify_url):
                    is_playlist = False
                    self.after(0, lambda: self._log_write("Reading track from Spotify...", "dim"))
                    song_info = self._get_track_info(spotify_url)
                    if song_info:
                        songs = [song_info]
                    else:
                        songs = None
                else:
                    is_playlist = True
                    try:
                        num_songs = int(self._num_songs_var.get())
                    except Exception:
                        num_songs = 100
                    num_songs = max(1, min(100, num_songs))
                    self.after(0, lambda: self._log_write("Reading playlist from Spotify...", "dim"))
                    playlist_name = self._get_playlist_name(spotify_url)
                    songs = self._get_songs_requests(spotify_url, num_songs)

            if not songs:
                self.after(0, lambda: self._log_write(
                    "Failed to extract songs", "err"))
                self.after(0, lambda: self._set_status("Error", ERROR_CLR))
                self._running = False
                self.after(0, self._on_done)
                return

            # Build path: out/source/[Playlist_name/]
            out = os.path.join(out, source)
            
            if is_playlist:
                # For playlists, create a subfolder with the playlist name
                safe_playlist_name = self._get_safe_folder_name(playlist_name or "Playlist")
                playlist_folder = f"Playlist_{safe_playlist_name}"
                out = os.path.join(out, playlist_folder)
                self.after(0, lambda: self._log_write(
                    f"Saving to: {source}/{playlist_folder}", "dim"))
            else:
                # For single tracks, files go directly into the source folder
                self.after(0, lambda: self._log_write(
                    f"Saving to: {source}", "dim"))
            
            os.makedirs(out, exist_ok=True)

            # Load universal tracking file from base Pythofy folder
            done_file = self._done_file_path(self._dir_var.get())
            already_done = self._load_done(done_file, out)

            if already_done:
                skipped = sum(1 for s in songs if s in already_done)
                if skipped:
                    self.after(0, lambda: self._log_write(
                        f"Resuming: skipping {skipped} already downloaded", "ok"))

            self._songs_list  = songs
            self._done_file = done_file
            self._already_done = already_done
            self._done_key = out
            self._current_song_idx = 0
            self._is_youtube_mode = is_youtube  # Traccia se siamo in modalità YouTube
            self._download_next_song(out, quality)

        except Exception as e:
            self.after(0, lambda: self._log_write(f"❌ Error: {e}", "err"))
            self.after(0, lambda: self._set_status("Error", ERROR_CLR))
            self._running = False
            self.after(0, self._on_done)

    def _done_file_path(self, base_path):
        return os.path.join(base_path, ".pythofy_downloaded.json")

    def _load_done(self, done_file, playlist_key):
        try:
            if os.path.exists(done_file):
                with open(done_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return set(data.get(playlist_key, []))
        except Exception:
            pass
        return set()
    
    def _save_done(self, done_file, already_done, playlist_key):
        try:
            data = {}
            if os.path.exists(done_file):
                with open(done_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data[playlist_key] = list(already_done)
            with open(done_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


    def _extract_playlist_id(self, url):
        """Extract the playlist ID from a Spotify URL"""
        match = re.search(r'playlist/([a-zA-Z0-9]+)', url)
        return match.group(1) if match else None

    def _extract_track_id(self, url):
        """Extract the track ID from a Spotify URL"""
        match = re.search(r'track/([a-zA-Z0-9]+)', url)
        return match.group(1) if match else None

    def _is_track_url(self, url):
        """Check if the URL is a Spotify track"""
        return "track" in url and self._extract_track_id(url) is not None

    def _is_playlist_url(self, url):
        """Check if the URL is a Spotify playlist"""
        return "playlist" in url and self._extract_playlist_id(url) is not None

    def _is_youtube_url(self, url):
        """Check if the URL is a YouTube link"""
        return "youtube.com" in url or "youtu.be" in url

    def _is_youtube_playlist_url(self, url):
        """Check if the URL is a YouTube playlist"""
        return ("youtube.com/playlist" in url or 
                "youtube.com/@" in url or 
                "youtube.com/channel" in url or 
                "&list=" in url)

    def _is_youtube_video_url(self, url):
        """Check if the URL is a single YouTube video"""
        return ("youtube.com/watch" in url or "youtu.be/" in url) and not self._is_youtube_playlist_url(url)

    def _extract_youtube_video_id(self, url):
        """Extract the video ID from a YouTube URL"""
        # youtu.be/VIDEO_ID
        match = re.search(r'youtu\.be/([^/?&]+)', url)
        if match:
            return match.group(1)
        # youtube.com/watch?v=VIDEO_ID
        match = re.search(r'(?:youtube\.com/watch\?v=|v/)([^&]+)', url)
        if match:
            return match.group(1)
        return None

    def _get_download_subfolder_name(self, spotify_url, songs, playlist_name=None, is_youtube=False):
        """
        Generate subfolder name based on download type.
        """
        if is_youtube:
            if len(songs) == 1 and self._is_youtube_video_url(spotify_url):
                # È un video singolo YouTube
                title = self._get_youtube_video_title(spotify_url)
                if title:
                    safe_name = re.sub(r'[<>:"/\\|?*]', '', title).strip()
                    return safe_name[:100]
            # È una playlist YouTube
            if playlist_name:
                safe_name = re.sub(r'[<>:"/\\|?*]', '', playlist_name).strip()
                return f"YouTube_Playlist_{safe_name}"[:100]
            else:
                return "YouTube_Playlist"
        else:
            # Spotify
            if len(songs) == 1 and self._is_track_url(spotify_url):
                # È un brano singolo: usa il nome del brano
                song_name = songs[0]
                # Remove invalid filesystem characters
                safe_name = re.sub(r'[<>:"/\\|?*]', '', song_name).strip()
                return safe_name[:80]  # Limit length
            else:
                # È una playlist
                if playlist_name:
                    safe_name = re.sub(r'[<>:"/\\|?*]', '', playlist_name).strip()
                    return f"Playlist_{safe_name}"[:100]
                else:
                    playlist_id = self._extract_playlist_id(spotify_url) or "playlist"
                    return f"Playlist_{playlist_id}"

    def _get_safe_folder_name(self, name):
        """Convert a name into a filesystem-safe folder name"""
        if not name:
            return "Playlist"
        # Remove invalid filesystem characters
        safe_name = re.sub(r'[<>:"/\\|?*]', '', name).strip()
        # Limit length
        return safe_name[:80] if safe_name else "Playlist"

    def _get_progress_bar(self, percentage):
        """Create a simple text progress bar - e.g., '[████░░░░░] 40%'"""
        filled = int(percentage / 5)  # 20 chars total
        empty = 20 - filled
        bar = "█" * filled + "░" * empty
        return f"[{bar}] {percentage:.1f}%"

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
            self.after(0, lambda: self._log_write("   Fetching playlist name...", "dim"))

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
                # Fallback: try alternative data path
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
                self.after(0, lambda: self._log_write("Track ID not found", "err"))
                return None

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            embed_url = f"https://open.spotify.com/embed/track/{track_id}"
            self.after(0, lambda: self._log_write("   📡 Fetching Spotify embed page…", "dim"))

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
                self.after(0, lambda: self._log_write("⚠ JSON not found in embed page", "warn"))
                return None

            # Extract track name and artists
            meta = data.get("props", {}).get("pageProps", {}).get("meta", {})
            title = meta.get("name", "").strip()
            artist_list = meta.get("artists", [])
            artist_names = ", ".join([a.get("name", "") for a in artist_list if a.get("name")])

            if not title:
                # Fallback: try alternative data path
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
                self.after(0, lambda: self._log_write("Failed to extract track info", "err"))
                return None

            song_name = f"{artist_names} - {title}" if artist_names else title
            self.after(0, lambda: self._log_write(
                f"🎵 Brano trovato: {song_name}", "ok"))
            return song_name

        except Exception as e:
            self.after(0, lambda e=e: self._log_write(f"⚠ Error: {str(e)[:60]}", "warn"))
            return None

    def _get_songs_requests(self, spotify_url, num_songs=100):
        """
        Extract songs from the Spotify embed page.
        """
        try:
            import urllib.request, ssl, time

            playlist_id = self._extract_playlist_id(spotify_url)
            if not playlist_id:
                self.after(0, lambda: self._log_write("Playlist ID not found", "err"))
                return None

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
            self.after(0, lambda: self._log_write("   📡 Fetching Spotify embed page…", "dim"))

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
                self.after(0, lambda: self._log_write("⚠ JSON not found in embed page", "warn"))
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

            # Truncate to user-specified number
            if num_songs < len(songs):
                songs = songs[:num_songs]

            if num_songs > len(songs):
                self.after(0, lambda g=len(songs), t=num_songs: self._log_write(
                    f"   Only {g} tracks available (out of {t})", "warn"))

            self.after(0, lambda n=len(songs): self._log_write(
                f"📋 Found {n} songs", "ok"))
            return songs

        except Exception as e:
            self.after(0, lambda e=e: self._log_write(f"⚠ Error: {str(e)[:60]}", "warn"))
            return None
    def _get_spotify_anon_token(self, ctx=None):
        """
        Obtain an anonymous token from Spotify using the public endpoint.
        """
        try:
            import urllib.request, ssl
            if ctx is None:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            # Public endpoint returning a valid anonymous token
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
        """Extract songs from a playlist using spotdl save → JSON"""
        import tempfile, json as _json, time

        try:
            tmp_dir  = tempfile.mkdtemp()
            tmp_file = os.path.join(tmp_dir, "playlist.spotdl")

            self.after(0, lambda: self._log_write("🔍 Connessione a Spotify per recuperare i metadati…", "dim"))

            # Start spotdl save in background
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
                msg = f"   ⏳ Fetching metadata{'.' * (dots % 4 + 1)}"
                self.after(0, lambda m=msg: self._log_write(m, "dim"))

            # Read any remaining output
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

            # Print the full list of found songs
            if songs:
                self.after(0, lambda: self._log_write(f"📋 Found {len(songs)} songs:", "ok"))
                for i, s in enumerate(songs, 1):
                    idx, song = i, s  # evita closure loop bug
                    self.after(0, lambda i=idx, s=song: self._log_write(f"   {i:>2}. {s}", "dim"))

            return songs if songs else None

        except Exception as e:
            self.after(0, lambda: self._log_write(f"Error with spotdl: {str(e)[:80]}", "warn"))
            return None

    # ──────────────────────────────────────────
    #  YOUTUBE FUNCTIONS
    # ──────────────────────────────────────────

    def _get_youtube_video_title(self, youtube_url):
        """Extract the title of a YouTube video using yt-dlp"""
        try:
            cmd = _find_cmd("yt-dlp") + [
                youtube_url,
                "--print", "title",
                "--no-warnings",
                "--quiet",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace", creationflags=_NO_WINDOW,
            )
            if result.returncode == 0:
                title = result.stdout.strip().split('\n')[0]
                return title if title else None
            return None
        except Exception as e:
            self.after(0, lambda: self._log_write(f"   ⚠ Error retrieving YouTube title: {str(e)[:60]}", "warn"))
            return None

    def _get_youtube_playlist_name(self, youtube_url):
        """Extract the name of a YouTube playlist using yt-dlp"""
        try:
            cmd = _find_cmd("yt-dlp") + [
                youtube_url,
                "--playlist-items", "1:1",
                "--print", "playlist_title",
                "--no-warnings",
                "--quiet",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace", creationflags=_NO_WINDOW,
            )
            if result.returncode == 0:
                title = result.stdout.strip().split('\n')[0]
                return title if title else None
            return None
        except Exception as e:
            self.after(0, lambda: self._log_write(f"   ⚠ Error retrieving YouTube playlist name: {str(e)[:60]}", "warn"))
            return None

    def _extract_youtube_playlist_songs(self, youtube_url):
        """Extract the list of video URLs from a YouTube playlist using yt-dlp"""
        try:
            self.after(0, lambda: self._log_write("   📡 Extracting videos from YouTube playlist…", "dim"))
            
            cmd = _find_cmd("yt-dlp") + [
                youtube_url,
                "--print", "original_url",
                "--flat-playlist",
                "--no-warnings",
                "--quiet",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace", creationflags=_NO_WINDOW,
            )

            if result.returncode != 0:
                err = (result.stderr or result.stdout or "")[:120].strip()
                self.after(0, lambda e=err: self._log_write(f"   ⚠ yt-dlp error: {e}", "warn"))
                return None

            lines = result.stdout.strip().split('\n')
            urls = [line.strip() for line in lines if line.strip() and ("youtube.com" in line or "youtu.be" in line)]

            if not urls:
                self.after(0, lambda: self._log_write("   ⚠ No videos found in playlist", "warn"))
                return None

            self.after(0, lambda n=len(urls): self._log_write(f"   Found {n} videos", "ok"))
            return urls
            
        except Exception as e:
            self.after(0, lambda: self._log_write(f"   ⚠ Error: could not extract playlist", "warn"))
            return None

    def _download_next_song(self, out, quality):
        """Download the next song in the list, skipping already downloaded ones"""
        # Advance to next undownloaded song
        while self._current_song_idx < len(self._songs_list):
            song = self._songs_list[self._current_song_idx]
            if song in self._already_done:
                self._current_song_idx += 1
                n = self._current_song_idx
                self.after(0, lambda n=n, s=song: self._log_write(
                    f"[{n}/{len(self._songs_list)}] Already downloaded", "dim"))
            else:
                break

        if not self._running or self._current_song_idx >= len(self._songs_list):
            if self._running:
                total = len(self._songs_list)
                self.after(0, lambda: self._log_write(
                    f"✓ Complete! ({total} songs)", "ok"))
                self.after(0, lambda: self._set_status("Complete", ACCENT))
            self._running = False
            self.after(0, self._on_done)
            return

        song = self._songs_list[self._current_song_idx]
        self._current_song_idx += 1
        idx = self._current_song_idx

        # Get title for display
        display_title = song
        is_youtube_mode = getattr(self, "_is_youtube_mode", False)
        if is_youtube_mode and ("youtube.com" in song or "youtu.be" in song):
            title = self._get_youtube_video_title(song)
            if title:
                display_title = title

        self.after(0, lambda: self._log_write(
            f"[{idx}/{len(self._songs_list)}] - {display_title}", "bold"))
        
        # Determine if searching YouTube or using direct URL
        if is_youtube_mode and ("youtube.com" in song or "youtu.be" in song):
            self.after(0, lambda t=display_title: self._track_lbl.config(
                text=f"⏳ [{idx}/{len(self._songs_list)}] {t}  -  downloading"))
        else:
            self.after(0, lambda t=display_title: self._track_lbl.config(
                text=f"⏳ [{idx}/{len(self._songs_list)}] {t}  -  searching..."))

        def on_complete(success):
            if success:
                self._already_done.add(song)
                self._save_done(self._done_file, self._already_done, self._done_key)
                self.after(0, lambda: self._log_write(f"   ✓ Done", "ok"))
                self._retry_count.pop(song, None)  # Resetta contatore retry
                self._download_next_song(out, quality)
            else:
                # Gestisci il retry
                current_retry = self._retry_count.get(song, 0)
                if current_retry < self._max_retries:
                    self._retry_count[song] = current_retry + 1
                    self.after(0, lambda c=current_retry+1, m=self._max_retries:
                        self._log_write(f"   Retry ({c}/{m})...", "warn"))
                    # Riprova in un thread separato per non bloccare l'UI
                    def retry_download():
                        import time
                        time.sleep(1)  # Wait 1 second before retrying
                        if self._running:
                            self._download_song_youtube(song, out, quality, on_complete)
                    
                    retry_thread = threading.Thread(target=retry_download, daemon=True)
                    retry_thread.start()
                else:
                    self.after(0, lambda: self._log_write(f"   Skipped after {self._max_retries} retries", "err"))
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
                
                # Update the track label
                self._update_track_label(line)

            self._process.wait()
            rc = self._process.returncode

            if rc == 0:
                self.after(0, lambda: self._log_write("✓ Canzone scaricata", "ok"))
            elif self._running:
                self.after(0, lambda: self._log_write(f"⚠ Errore nel download (codice {rc})", "warn"))
        except FileNotFoundError:
            self.after(0, lambda: self._log_write("❌ yt-dlp non trovato. Installalo con: pip install yt-dlp", "err"))
            self.after(0, lambda: self._set_status("Error", ERROR_CLR))
        except Exception as e:
            self.after(0, lambda: self._log_write(f"❌ Error: {e}", "err"))
            self.after(0, lambda: self._set_status("Error", ERROR_CLR))

    def _download_song_youtube(self, song, out, quality, on_complete):
        """Download a single song from YouTube (batch version)"""
        import time
        import threading

        # Determine if search or direct URL
        is_youtube_mode = getattr(self, "_is_youtube_mode", False)
        is_direct_url = is_youtube_mode and ("youtube.com" in song or "youtu.be" in song)
        
        if is_direct_url:
            # Usa l'URL diretto
            search_query = song
            search_type = "URL YouTube"
        else:
            # Usa ytsearch per cercare su YouTube
            search_query = f"ytsearch:{song}"
            search_type = "searching"

        cmd = _find_cmd("yt-dlp") + [
            search_query,
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
            phase = search_type
            process_completed = False

            # Funzione per leggere l'output con timeout
            def read_output():
                nonlocal process_completed, last_heartbeat, phase
                last_progress = 0
                progress_logged = False
                try:
                    for line in self._process.stdout:
                        if not self._running:
                            self._process.terminate()
                            break

                        line = line.rstrip()
                        if not line:
                            continue

                        l = line.lower()
                        
                        # Only log important lines, filter out noise
                        should_log = False
                        if "[youtube]" in l and "extracting" in l:
                            # Don't log raw output, show simplified message
                            phase = "extracting"
                            self.after(0, lambda: self._log_write(f"   Getting info...", "dim"))
                        elif "[download]" in l and "%" in l:
                            # Extract progress percentage
                            m = re.search(r'(\d+\.\d+)%', line)
                            if m:
                                progress = float(m.group(1))
                                # Only show progress bar every 20%
                                if progress - last_progress >= 20 or progress >= 100:
                                    last_progress = progress
                                    progress_bar = self._get_progress_bar(progress)
                                    self.after(0, lambda pb=progress_bar: self._log_write(f"   Downloading: {pb}", ""))
                                    progress_logged = True
                                phase = f"downloading {m.group(1)}%"
                        elif "[extractaudio]" in l:
                            should_log = True
                            phase = "finalizing"
                        elif "error" in l or "failed" in l:
                            should_log = True
                        
                        if should_log:
                            tag = self._classify_line(line)
                            self.after(0, lambda l=line, t=tag: self._log_write(f"   {l}", t))
                            
                            # Add status message for finalization phase
                            if "[extractaudio]" in l and "destination" in l:
                                self.after(0, lambda: self._log_write(f"   Adding metadata & thumbnails...", "dim"))

                        now = time.time()
                        if now - last_heartbeat >= 1.0:
                            last_heartbeat = now
                            p = phase
                            idx = self._current_song_idx
                            total = len(self._songs_list)
                            s = self._songs_list[idx - 1] if idx > 0 else song
                            self.after(0, lambda p=p, s=s, i=idx, t=total:
                                self._track_lbl.config(text=f"⏳ [{i}/{t}] {s}  -  {p}"))
                    
                    process_completed = True
                except Exception as e:
                    error_msg = str(e)[:60]
                    self.after(0, lambda m=error_msg: self._log_write(f"   ⚠ Error reading output: {m}", "warn"))

            # Start reading in a thread
            reader_thread = threading.Thread(target=read_output, daemon=True)
            reader_thread.start()

            # Wait for process with timeout (15 min)
            self._process.wait(timeout=900)
            rc = self._process.returncode

            # Wait for reader to finish
            reader_thread.join(timeout=5)

            if self._running:
                on_complete(rc == 0)
        except subprocess.TimeoutExpired:
            # Timeout: termina il processo
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except:
                try:
                    self._process.kill()
                except:
                    pass
            if self._running:
                self.after(0, lambda: self._log_write(
                    f"⚠ Download timeout (> 15 min), saltato", "warn"))
                on_complete(False)
        except Exception as e:
            # Assicurati che il processo sia terminato
            try:
                if self._process and self._process.poll() is None:
                    self._process.terminate()
                    self._process.wait(timeout=5)
            except:
                pass
            if self._running:
                error_msg = str(e)[:80]
                self.after(0, lambda m=error_msg: self._log_write(
                    f"⚠ Errore nel download: {m}", "warn"))
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
        """Extract the song title from yt-dlp output and update the label"""
        l = line.strip()
        
        # Look for yt-dlp output patterns
        if any(keyword in l for keyword in ("[youtube]", "Downloading", "[ffmpeg]", "Extracting")):
            # Estrai il titolo dal pattern "[youtube] video_id: Downloading webpage"
            match = re.search(r'\[youtube\]\s+([^:]+):\s+(.+)', l)
            if match:
                title = match.group(2)
            else:
                title = l
            
            # Remove common prefixes
            for prefix in ["[youtube]", "[ffmpeg]", "Downloading", "Extracting"]:
                title = title.replace(prefix, "").strip()
            
            if title and len(title) > 5:
                self.after(0, lambda text=title: self._track_lbl.config(text=f"⏳  {text}"))

    def _stop_download(self):
        self._running = False
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self._log_write("Download stopped", "warn")
            self._set_status("Stopped", WARN_CLR)
        self._on_done()

    # ══════════════════════════════════════════
    #  AUTO-UPDATE
    # ══════════════════════════════════════════

    def _check_updates_async(self):
        threading.Thread(target=self._check_updates, daemon=True).start()

    def _check_updates(self):
        self.after(0, lambda: self._log_write("Checking for updates…", "dim"))
        try:
            import urllib.request, json as _json, ssl

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "Pythofy-Updater"})
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                data = _json.loads(resp.read().decode())

            latest_tag = data.get("tag_name", "").lstrip("v")
            if not latest_tag:
                self.after(0, lambda: self._log_write("⚠ Could not read latest version", "warn"))
                return

            def _ver(s):
                try:
                    return tuple(int(x) for x in s.split("."))
                except Exception:
                    return (0,)

            if _ver(latest_tag) <= _ver(APP_VERSION):
                self.after(0, lambda: self._log_write("✓ Pythofy is up to date!", "ok"))
                return

            assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
            self.after(0, lambda v=latest_tag, a=assets: self._show_update_dialog(v, a))

        except Exception as e:
            self.after(0, lambda e=e: self._log_write(f"⚠ Update check failed: {str(e)[:60]}", "warn"))

    def _show_update_dialog(self, new_version, assets):
        self._log_write(f"🆕 Update available: v{new_version}", "ok")

        win = tk.Toplevel(self)
        win.title("Update Available")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.grab_set()

        # Centra la finestra
        win.update_idletasks()
        w, h = 420, 220
        x = self.winfo_x() + (self.winfo_width()  - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

        # Header
        hdr = tk.Frame(win, bg=ACCENT, height=4)
        hdr.pack(fill="x")

        body = tk.Frame(win, bg=BG, padx=32, pady=24)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Update available",
                 font=(MONO, 13, "bold"), bg=BG, fg=TEXT).pack(anchor="w")
        tk.Label(body, text=f"v{APP_VERSION}  →  v{new_version}",
                 font=(SANS, 10), bg=BG, fg=TEXT_MID).pack(anchor="w", pady=(6, 0))
        tk.Label(body, text="Pythofy.exe, yt-dlp.exe and ffmpeg.exe will be updated.",
                 font=(SANS, 9), bg=BG, fg=TEXT_SUB).pack(anchor="w", pady=(4, 0))

        self._update_progress_var = tk.StringVar(value="")
        prog_lbl = tk.Label(body, textvariable=self._update_progress_var,
                            font=(MONO, 8), bg=BG, fg=ACCENT)
        prog_lbl.pack(anchor="w", pady=(10, 0))

        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(anchor="w", pady=(14, 0))

        update_btn = self._primary_btn(btn_row, "UPDATE NOW", lambda: None)
        update_btn.pack(side="left")
        skip_btn = self._ghost_btn(btn_row, "SKIP", win.destroy)
        skip_btn.pack(side="left", padx=(10, 0))

        def do_update():
            update_btn.config(state="disabled")
            skip_btn.config(state="disabled")
            threading.Thread(
                target=self._do_update,
                args=(assets, win),
                daemon=True
            ).start()

        update_btn.config(command=do_update)

    def _do_update(self, assets, win):
        import urllib.request, ssl, os, sys, tempfile, shutil, zipfile

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        frozen = getattr(sys, "frozen", False)
        base_path = os.path.dirname(sys.executable) if frozen else os.path.dirname(__file__)
        tools_path = os.path.join(base_path, "pythofy_tools")

        # Asset da scaricare: "Pythofy - Portable.zip"
        ASSET_NAME = "Pythofy.-.Portable.zip"
        url = assets.get(ASSET_NAME)
        if not url:
            self.after(0, lambda: self._update_progress_var.set(
                f"❌ Asset \"{ASSET_NAME}\" not found in release"))
            return

        tmp_dir = tempfile.mkdtemp(prefix="pythofy_update_")
        zip_path = os.path.join(tmp_dir, "update.zip")

        try:
            # ── Scarica lo zip ──────────────────────────────────────
            self.after(0, lambda: self._update_progress_var.set("Downloading update…"))
            req = urllib.request.Request(url, headers={"User-Agent": "Pythofy-Updater"})
            with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded_bytes = 0
                chunk = 65536
                with open(zip_path, "wb") as f:
                    while True:
                        buf = resp.read(chunk)
                        if not buf:
                            break
                        f.write(buf)
                        downloaded_bytes += len(buf)
                        if total:
                            pct = int(downloaded_bytes / total * 100)
                            self.after(0, lambda p=pct:
                                self._update_progress_var.set(f"Downloading… {p}%"))

            # ── Estrai lo zip ───────────────────────────────────────
            self.after(0, lambda: self._update_progress_var.set("Extracting…"))
            extract_dir = os.path.join(tmp_dir, "extracted")
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(extract_dir)

            # Lo zip può avere una cartella radice (es. "Pythofy - Portable/")
            # Trova la root che contiene Pythofy.exe
            root = extract_dir
            for entry in os.listdir(extract_dir):
                candidate = os.path.join(extract_dir, entry)
                if os.path.isdir(candidate) and os.path.exists(
                        os.path.join(candidate, "Pythofy.exe")):
                    root = candidate
                    break

            # ── Copia i file ────────────────────────────────────────
            # pythofy_tools: yt-dlp.exe e ffmpeg.exe
            src_tools = os.path.join(root, "pythofy_tools")
            os.makedirs(tools_path, exist_ok=True)
            for tool in ("yt-dlp.exe", "ffmpeg.exe"):
                src = os.path.join(src_tools, tool)
                if os.path.exists(src):
                    self.after(0, lambda t=tool: self._update_progress_var.set(
                        f"Installing {t}…"))
                    shutil.copy2(src, os.path.join(tools_path, tool))

            # Pythofy.exe — non puoi sovrascrivere l'exe in esecuzione su Windows:
            # rinomina il vecchio in .old, poi copia il nuovo
            new_exe_src = os.path.join(root, "Pythofy.exe")
            new_exe_dst = os.path.join(base_path, "Pythofy.exe")
            if os.path.exists(new_exe_src):
                self.after(0, lambda: self._update_progress_var.set("Installing Pythofy.exe…"))
                if frozen:
                    old_path = new_exe_dst + ".old"
                    try:
                        os.replace(new_exe_dst, old_path)
                    except Exception:
                        pass
                shutil.copy2(new_exe_src, new_exe_dst)

            self.after(0, lambda: self._update_progress_var.set("✓ Update complete — restarting…"))
            self.after(0, lambda: win.after(1200, lambda: self._restart_app(new_exe_dst if frozen else None)))

        except Exception as e:
            err = str(e)[:80]
            self.after(0, lambda e=err: self._update_progress_var.set(f"❌ Error: {e}"))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _restart_app(self, exe_path=None):
        import subprocess, sys, os
        target = exe_path or sys.executable
        # Cleanup .old dopo il riavvio (best-effort, lo elimina il nuovo processo)
        subprocess.Popen(
            [target],
            creationflags=_NO_WINDOW,
            close_fds=True,
        )
        self.destroy()
        sys.exit(0)


    # ══════════════════════════════════════════
    #  ROLLBACK
    # ══════════════════════════════════════════

    def _old_exe_path(self):
        import sys, os
        frozen = getattr(sys, "frozen", False)
        base = os.path.dirname(sys.executable) if frozen else os.path.dirname(__file__)
        return os.path.join(base, "Pythofy.exe.old")

    def _check_rollback_available(self):
        if os.path.exists(self._old_exe_path()):
            self._rollback_lbl.pack(side="right", padx=(0, 8))
        else:
            self._rollback_lbl.pack_forget()

    def _confirm_rollback(self):
        if not os.path.exists(self._old_exe_path()):
            self._log_write("⚠ No previous version found", "warn")
            return
        win = tk.Toplevel(self)
        win.title("Rollback")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.grab_set()
        win.update_idletasks()
        w, h = 380, 160
        x = self.winfo_x() + (self.winfo_width()  - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

        tk.Frame(win, bg=WARN_CLR, height=4).pack(fill="x")
        body = tk.Frame(win, bg=BG, padx=28, pady=20)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Restore previous version?",
                 font=(MONO, 11, "bold"), bg=BG, fg=TEXT).pack(anchor="w")
        tk.Label(body, text="The current version will be removed. The app will restart.",
                 font=(SANS, 9), bg=BG, fg=TEXT_SUB).pack(anchor="w", pady=(6, 14))

        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(anchor="w")
        self._ghost_btn(btn_row, "RESTORE", lambda: [win.destroy(), self._do_rollback()]).pack(side="left")
        self._ghost_btn(btn_row, "CANCEL",  win.destroy).pack(side="left", padx=(10, 0))

    def _do_rollback(self):
        import sys, shutil
        frozen = getattr(sys, "frozen", False)
        old_path = self._old_exe_path()
        if not os.path.exists(old_path):
            self._log_write("❌ Previous version file not found", "err")
            return
        base = os.path.dirname(sys.executable) if frozen else os.path.dirname(__file__)
        current = os.path.join(base, "Pythofy.exe")
        broken  = current + ".broken"
        try:
            # Sposta il corrente in .broken, rimetti il .old al suo posto
            if frozen:
                try:
                    os.replace(current, broken)
                except Exception:
                    pass
            shutil.copy2(old_path, current)
            os.remove(old_path)
            self._log_write("↩ Rollback complete — restarting…", "ok")
            self.after(1200, lambda: self._restart_app(current if frozen else None))
        except Exception as e:
            self._log_write(f"❌ Rollback failed: {str(e)[:60]}", "err")


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