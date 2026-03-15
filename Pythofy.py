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


def _is_admin():
    """True se il processo ha già privilegi di amministratore."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _relaunch_as_admin(extra_args):
    """Rilancia l'exe corrente come amministratore con ShellExecute runas."""
    import ctypes, sys
    frozen = getattr(sys, "frozen", False)
    exe = sys.executable
    if frozen:
        params = " ".join(extra_args)
    else:
        script = os.path.abspath(__file__)
        params = f'"{script}" ' + " ".join(extra_args)
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        return int(ret) > 32
    except Exception:
        return False


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

APP_VERSION  = "1.6.0"
GITHUB_REPO  = "goldyreal/PythofyDownloader"



def _config_path():
    import sys, os
    frozen = getattr(sys, "frozen", False)
    base = os.path.dirname(sys.executable) if frozen else os.path.dirname(__file__)
    return os.path.join(base, ".pythofy_config.json")

def _load_config():
    try:
        p = _config_path()
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_config(data):
    try:
        p = _config_path()
        existing = _load_config()
        existing.update(data)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

class YouTubeDownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Pythofy v{APP_VERSION}")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(1080, 580)
        self.geometry("1080x680")

        self._process = None          # compatibilità (usato da _stop_download legacy)
        self._active_procs = []        # lista processi paralleli attivi
        self._active_procs_lock = threading.Lock()
        self._active_downloads = {}    # proc -> set di filepath (raw + converted)
        self._active_downloads_lock = threading.Lock()
        self._dl_semaphore = threading.Semaphore(3)  # max 3 download in parallelo
        self._active_workers = 0       # worker attivi (protetto da _idx_lock)
        self._idx_lock = threading.Lock()
        self._running = False
        self._pending_batches = []   # lista di (url, out, quality, csv_songs, fmt)
        self._downloaded_urls = set()  # URL già scaricati o in coda (deduplicazione)
        self._queue_session_active = False  # True se la queue è "in uso"
        self._num_songs_var = tk.IntVar(value=100)
        self._parallel_var = tk.IntVar(value=3)   # download paralleli
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
        def _on_canvas_scroll(e):
            # Scrolla il canvas solo se il popup dei suggerimenti NON è aperto
            if getattr(self, "_suggest_popup", None) and self._suggest_popup.winfo_exists():
                return
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_canvas_scroll)

        pad = dict(padx=28)

        # SOURCE
        self._section_label(inner, "URL OR SONG NAME (Spotify / YouTube / SoundCloud)").pack(anchor="w", pady=(28, 10), **pad)
        url_wrap = tk.Frame(inner, bg=BG)
        url_wrap.pack(fill="x", **pad)
        url_wrap.columnconfigure(0, weight=1)
        self._song_var = tk.StringVar()
        self._url_entry = self._entry(url_wrap, self._song_var)
        self._url_entry.grid(row=0, column=0, sticky="ew", ipady=10)
        self._ghost_btn(url_wrap, "PASTE", self._paste_text).grid(row=0, column=1, padx=(8, 0))

        # Dropdown autocomplete — popup Toplevel (funziona dentro canvas scorrevole)
        self._search_results_data = []
        self._search_after_id = None
        self._suggest_popup = None

        # Bind per la ricerca in tempo reale
        self._song_var.trace_add("write", self._on_url_changed)
        self._url_entry.bind("<FocusOut>", self._hide_suggestions_delayed)
        self._url_entry.bind("<Escape>", lambda e: self._hide_suggestions())
        self._url_entry.bind("<Down>", self._focus_suggestions)

        # DESTINATION
        self._section_label(inner, "DESTINATION").pack(anchor="w", pady=(22, 10), **pad)
        dir_wrap = tk.Frame(inner, bg=BG)
        dir_wrap.pack(fill="x", **pad)
        dir_wrap.columnconfigure(0, weight=1)
        _cfg = _load_config()
        self._dir_var = tk.StringVar(
            value=_cfg.get("last_dest", os.path.join(os.path.expanduser("~"), "Downloads", "Pythofy")))
        self._entry(dir_wrap, self._dir_var).grid(row=0, column=0, sticky="ew", ipady=10)
        self._ghost_btn(dir_wrap, "BROWSE", self._browse_dir).grid(row=0, column=1, padx=(8, 0))

        # OPTIONS — riga 1: Bitrate, Format, Track Limit
        self._section_label(inner, "Options").pack(anchor="w", pady=(22, 10), **pad)
        opts1 = tk.Frame(inner, bg=BG)
        opts1.pack(fill="x", **pad)

        q_frame = tk.Frame(opts1, bg=BG)
        q_frame.pack(side="left", padx=(0, 32))
        self._micro_label(q_frame, "BITRATE (kbps)").pack(anchor="w", pady=(0, 6))
        self._qual_var = tk.StringVar(value="192")
        ttk.Combobox(q_frame, textvariable=self._qual_var,
                     values=["128", "192", "256", "320"],
                     state="readonly", style="app.TCombobox",
                     font=(SANS, 10), width=7).pack(anchor="w")

        fmt_frame = tk.Frame(opts1, bg=BG)
        fmt_frame.pack(side="left", padx=(0, 32))
        self._micro_label(fmt_frame, "FORMAT").pack(anchor="w", pady=(0, 6))
        self._fmt_var = tk.StringVar(value="mp3")
        ttk.Combobox(fmt_frame, textvariable=self._fmt_var,
                     values=["mp3", "flac", "m4a", "ogg", "wav"],
                     state="readonly", style="app.TCombobox",
                     font=(SANS, 10), width=6).pack(anchor="w")

        n_frame = tk.Frame(opts1, bg=BG)
        n_frame.pack(side="left", padx=(0, 32))
        self._micro_label(n_frame, "TRACK LIMIT").pack(anchor="w", pady=(0, 6))
        self._num_songs_var = tk.IntVar(value=100)
        tk.Spinbox(n_frame, from_=1, to=100, textvariable=self._num_songs_var,
                   font=(SANS, 10), bg=BG3, fg=TEXT,
                   buttonbackground=BG4, relief="flat", bd=0,
                   highlightthickness=1, highlightbackground=BG4,
                   highlightcolor=ACCENT, width=5, wrap=False).pack(anchor="w", ipady=8)

        p_frame = tk.Frame(opts1, bg=BG)
        p_frame.pack(side="left")
        self._micro_label(p_frame, "PARALLEL DL").pack(anchor="w", pady=(0, 6))
        tk.Spinbox(p_frame, from_=1, to=20, textvariable=self._parallel_var,
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
        self._ghost_btn(csv_row, "CLEAR", self._clear_csv).grid(row=0, column=2, padx=(6, 0))

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
        self._ghost_btn(btn_area, "SONGS", self._open_songs_window).pack(side="left", padx=(10, 0))

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

        # ── Queue panel ────────────────────────────
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", side="top")
        queue_hdr = tk.Frame(parent, bg=BG2, height=30)
        queue_hdr.pack(fill="x", side="top")
        queue_hdr.pack_propagate(False)
        tk.Label(queue_hdr, text="QUEUE", font=(MONO, 8, "bold"), bg=BG2, fg=TEXT_DIM).pack(side="left", padx=14)
        self._queue_count_lbl = tk.Label(queue_hdr, text="", font=(MONO, 8), bg=BG2, fg=TEXT_SUB)
        self._queue_count_lbl.pack(side="left")
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", side="top")

        queue_frame = tk.Frame(parent, bg=BG3, height=160)
        queue_frame.pack(fill="x", side="top")
        queue_frame.pack_propagate(False)

        self._queue_list = tk.Text(queue_frame, font=(MONO, 8), bg=BG3, fg=TEXT_MID,
                                    relief="flat", bd=8, state="disabled", wrap="none",
                                    selectbackground=BG4, selectforeground=TEXT,
                                    height=8)
        q_scroll = ttk.Scrollbar(queue_frame, orient="vertical", command=self._queue_list.yview)
        self._queue_list.configure(yscrollcommand=q_scroll.set)
        q_scroll.pack(side="right", fill="y")
        self._queue_list.pack(side="left", fill="both", expand=True)
        self._queue_list.tag_config("queued",      foreground=TEXT_SUB)
        self._queue_list.tag_config("downloading", foreground=WARN_CLR)
        self._queue_list.tag_config("done",        foreground=OK_CLR)
        self._queue_list.tag_config("error",       foreground=ERROR_CLR)
        self._queue_list.tag_config("skipped",     foreground=TEXT_DIM)

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

    # ── Ricerca / Autocomplete ─────────────────────
    def _is_plain_search(self, text):
        """True se il testo non è un URL ma una ricerca libera"""
        return bool(text) and not any(x in text for x in (
            "spotify.com", "youtube.com", "youtu.be", "soundcloud.com", "http://", "https://"
        ))

    def _on_url_changed(self, *args):
        if getattr(self, "_selecting", False):
            return
        text = self._song_var.get().strip()
        if self._search_after_id:
            self.after_cancel(self._search_after_id)
            self._search_after_id = None
        if len(text) >= 3 and self._is_plain_search(text):
            # Se il popup è già aperto con risultati, aspetta meno e appende
            delay = 300 if (self._suggest_popup and self._suggest_popup.winfo_exists()) else 600
            self._search_after_id = self.after(delay, lambda t=text: self._run_search_async(t, append=self._suggest_popup is not None and self._suggest_popup.winfo_exists()))
        else:
            # Testo cancellato o URL: chiudi E cancella la ricerca in corso
            self._cancel_search()
            self._close_popup()

    def _cancel_search(self):
        """Incrementa il token per fermare qualsiasi thread di ricerca attivo."""
        self._search_token = getattr(self, "_search_token", 0) + 1

    def _run_search_async(self, query, append=False):
        # Nuovo token = vecchio thread si ferma
        self._search_token = getattr(self, "_search_token", 0) + 1
        token = self._search_token
        # Se NON stiamo appendendo, svuota il popup esistente
        if not append:
            if self._suggest_popup and self._suggest_popup.winfo_exists():
                self._suggest_listbox.delete(0, "end")
                self._search_results_data = []
        threading.Thread(
            target=self._fetch_suggestions_streaming,
            args=(query, token),
            daemon=True
        ).start()

    def _fetch_suggestions_streaming(self, query, token):
        """
        Lancia yt-dlp con --no-flat-playlist e legge stdout riga per riga:
        ogni risultato viene spedito alla UI appena arriva, senza aspettare
        che finiscano tutti e 10.
        """
        MAX_RESULTS = 10
        try:
            cmd = _find_cmd("yt-dlp") + [
                f"ytsearch{MAX_RESULTS}:{query}",
                "--print", "%(title)s|||%(uploader)s|||%(duration_string)s|||%(webpage_url)s",
                "--no-playlist", "--no-warnings", "--quiet",
                "--extractor-args", "youtube:skip=dash,hls",
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, creationflags=_NO_WINDOW
            )
            for raw_line in proc.stdout:
                # Se la query è cambiata (nuovo token), abbandona
                if getattr(self, "_search_token", 0) != token:
                    proc.terminate()
                    return
                line = raw_line.strip()
                if "|||" not in line:
                    continue
                parts = line.split("|||")
                if len(parts) >= 4:
                    item = {"title": parts[0], "uploader": parts[1],
                            "duration": parts[2], "url": parts[3]}
                    self.after(0, lambda it=item, tk=token: self._append_suggestion(it, tk))
            proc.wait()
        except Exception:
            pass

    def _append_suggestion(self, item, token):
        """Aggiunge un risultato al popup esistente, o lo crea se non c'è ancora."""
        if getattr(self, "_selecting", False):
            return
        if getattr(self, "_search_token", 0) != token:
            return
        # Non aprire il popup se il campo è vuoto o è diventato un URL
        current = self._song_var.get().strip()
        if not self._is_plain_search(current):
            return

        # Crea il popup solo se non esiste — mai ricrearlo se è già aperto
        if self._suggest_popup is None or not self._suggest_popup.winfo_exists():
            self._search_results_data = []
            self._create_popup()

        self._search_results_data.append(item)
        lb = self._suggest_listbox
        lb.insert("end", f"  {item['title']}  —  {item['uploader']}  [{item['duration']}]")

        # Ridimensiona il popup: max 5 righe visibili (scrollabile oltre)
        ROW_H   = 26
        MAX_VIS = 5
        n       = lb.size()
        vis     = min(n, MAX_VIS)
        lb.config(height=vis)

        self._url_entry.update_idletasks()
        x = self._url_entry.winfo_rootx()
        y = self._url_entry.winfo_rooty() + self._url_entry.winfo_height() + 2
        w = self._url_entry.winfo_width()
        # +16 per la scrollbar verticale se presente
        self._suggest_popup.geometry(f"{w}x{vis * ROW_H + 4}+{x}+{y}")

    def _create_popup(self):
        """Crea la finestra popup con listbox + scrollbar, senza dati."""
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.configure(bg=ACCENT3)
        popup.wm_attributes("-topmost", True)
        self._suggest_popup = popup

        frame = tk.Frame(popup, bg=BG2)
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        sb = ttk.Scrollbar(frame, orient="vertical")
        sb.pack(side="right", fill="y")

        lb = tk.Listbox(
            frame,
            font=(SANS, 9), bg=BG2, fg=TEXT,
            selectbackground=BG4, selectforeground=TEXT,
            relief="flat", bd=0, activestyle="none",
            highlightthickness=0, height=1,
            yscrollcommand=sb.set
        )
        lb.pack(side="left", fill="both", expand=True)
        sb.config(command=lb.yview)
        self._suggest_listbox = lb

        # Hover effect
        def on_motion(e, _lb=lb):
            idx = _lb.nearest(e.y)
            for i in range(_lb.size()):
                _lb.itemconfig(i,
                    bg=BG4 if i == idx else BG2,
                    fg=ACCENT if i == idx else TEXT)

        def on_leave(e, _lb=lb):
            for i in range(_lb.size()):
                _lb.itemconfig(i, bg=BG2, fg=TEXT)

        lb.bind("<Motion>", on_motion)
        lb.bind("<Leave>", on_leave)
        lb.bind("<ButtonRelease-1>", self._on_suggest_select)
        lb.bind("<Return>", self._on_suggest_select)
        lb.bind("<Escape>", lambda e: self._close_popup())

        # MouseWheel sul popup: scrolla la listbox e blocca la propagazione al canvas
        def _on_popup_scroll(e, _lb=lb):
            _lb.yview_scroll(int(-1*(e.delta/120)), "units")
            return "break"  # "break" impedisce la propagazione a bind_all
        lb.bind("<MouseWheel>", _on_popup_scroll)
        popup.bind("<MouseWheel>", _on_popup_scroll)

    def _show_suggestions(self, items, query):
        pass  # non usato, tenuto per compatibilità

    def _close_popup(self):
        """Chiude il popup E cancella la ricerca in corso."""
        # Incrementa il token: qualsiasi thread attivo si fermerà al prossimo ciclo
        self._search_token = getattr(self, "_search_token", 0) + 1
        if self._suggest_popup and self._suggest_popup.winfo_exists():
            self._suggest_popup.destroy()
        self._suggest_popup = None

    def _hide_suggestions(self):
        self._close_popup()
        self._search_results_data = []

    def _hide_suggestions_delayed(self, event=None):
        def _maybe_hide():
            # Non nascondere se il focus è finito nel popup (scrollbar, listbox, ecc.)
            focused = self.focus_get()
            popup = getattr(self, "_suggest_popup", None)
            if popup and popup.winfo_exists():
                try:
                    # Controlla se il widget con il focus è dentro il popup
                    w = focused
                    while w is not None:
                        if w == popup:
                            return  # focus è dentro il popup, non chiudere
                        w = w.master
                except Exception:
                    pass
            self._hide_suggestions()
        self.after(200, _maybe_hide)

    def _focus_suggestions(self, event=None):
        if self._suggest_popup and self._suggest_popup.winfo_exists():
            self._suggest_listbox.focus_set()
            self._suggest_listbox.selection_set(0)

    def _on_suggest_select(self, event=None):
        # Leggi i dati PRIMA di qualsiasi modifica allo stato
        data = list(self._search_results_data)
        lb = self._suggest_listbox
        idx = lb.nearest(event.y) if event else None
        if idx is None:
            sel = lb.curselection()
            idx = sel[0] if sel else None
        if idx is None or not (0 <= idx < len(data)):
            return
        chosen_url = data[idx]["url"]

        # Blocca il trace, chiudi popup, imposta URL
        self._selecting = True
        self._close_popup()
        self._search_results_data = []
        if self._search_after_id:
            self.after_cancel(self._search_after_id)
            self._search_after_id = None
        self._song_var.set(chosen_url)
        self._selecting = False
        self._url_entry.focus_set()
        self._url_entry.icursor("end")

    def _start_download(self):
        url = self._song_var.get().strip()
        out = self._dir_var.get().strip()
        csv_songs = getattr(self, "_csv_songs", None)

        if not url and not csv_songs:
            messagebox.showwarning("Missing input", "Enter a URL, a song name, or import a CSV file.")
            return

        is_search     = self._is_plain_search(url) if url else False
        is_spotify    = url and "spotify.com" in url
        is_youtube    = url and ("youtube.com" in url or "youtu.be" in url)
        is_soundcloud = url and "soundcloud.com" in url

        if url and not is_spotify and not is_youtube and not is_soundcloud and not is_search:
            messagebox.showwarning("Invalid input", "Use a Spotify, YouTube or SoundCloud URL, or type a song name.")
            return

        if url and is_spotify:
            if not ("playlist" in url or "track" in url):
                messagebox.showwarning("Invalid Spotify URL", "Use a Spotify track or playlist link.")
                return

        if not out:
            messagebox.showwarning("Missing folder", "Select a destination folder.")
            return

        os.makedirs(out, exist_ok=True)
        _save_config({"last_dest": out})
        self._hide_suggestions()

        # Se è ricerca libera, converti in ytsearch per yt-dlp
        if is_search:
            url = f"ytsearch1:{url}"

        fmt     = self._fmt_var.get()
        quality = self._qual_var.get()

        # Deduplicazione: non accodare lo stesso URL due volte
        url_key = url or "csv"
        if url_key in self._downloaded_urls:
            self._log_write(f"⚠ Already queued or downloaded: {url_key}", "warn")
            return
        self._downloaded_urls.add(url_key)

        if self._running:
            # Download in corso: accoda il batch
            self._pending_batches.append((url, out, quality, csv_songs, fmt))
            # Mostra subito separatore + placeholder nella queue
            label = url if url else "CSV import"
            # Accorcia l'URL per mostrarlo leggibile
            if "spotify.com" in label:
                label = "Spotify: " + label.split("/")[-1].split("?")[0]
            elif "youtube.com" in label or "youtu.be" in label:
                label = "YouTube: " + label.split("v=")[-1].split("&")[0] if "v=" in label else label
            elif "soundcloud.com" in label:
                label = "SoundCloud: " + label.rstrip("/").split("/")[-1]
            elif label.startswith("ytsearch"):
                label = label.replace("ytsearch1:", "🔍 ")
            self._queue_append_placeholder(label)
            return

        # Nessun download in corso: resetta la queue se la sessione precedente è finita
        if not self._queue_session_active:
            self._queue_clear()
            self._downloaded_urls = {url_key}  # ricomincia tracking

        self._queue_session_active = True
        self._running = True
        self._dl_btn.config(state="normal")   # rimane cliccabile per accodare
        self._stop_btn.config(state="normal")
        self._progress.start(12)
        self._set_status("Searching…" if is_search else "Extracting…", WARN_CLR)

        if url:
            if is_search:
                self._log_write(f"🔍 Searching: {url}", "bold")
            elif is_youtube:
                self._log_write(f"URL YouTube: {url}", "bold")
            elif is_soundcloud:
                self._log_write(f"URL SoundCloud: {url}", "bold")
            else:
                self._log_write(f"URL Spotify: {url}", "bold")
        self._log_write(f"Destination: {out}", "dim")

        threading.Thread(target=self._extract_and_download,
                         args=(url, out, quality, csv_songs, fmt),
                         daemon=True).start()

    def _extract_and_download(self, spotify_url, out, quality, csv_songs=None, fmt="mp3"):
        """Extract songs from Spotify/YouTube/SoundCloud and download them"""
        try:
            # Determina il tipo di URL e source
            is_ytsearch   = spotify_url and spotify_url.startswith("ytsearch")
            is_youtube    = is_ytsearch or (self._is_youtube_url(spotify_url) if spotify_url else False)
            is_soundcloud = self._is_soundcloud_url(spotify_url) if spotify_url else False
            if is_youtube:
                source = "youtube"
            elif is_soundcloud:
                source = "soundcloud"
            else:
                source = "spotify"
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

                if is_ytsearch:
                    is_playlist = False
                    self.after(0, lambda: self._log_write("   Search mode (single track)", "dim"))
                    songs = [spotify_url]  # yt-dlp gestisce ytsearch1: direttamente
                elif self._is_youtube_playlist_url(spotify_url):
                    is_playlist = True
                    self.after(0, lambda: self._log_write("   Playlist found", "dim"))
                    playlist_name = self._get_youtube_playlist_name(spotify_url)
                    songs = self._extract_youtube_playlist_songs(spotify_url)
                else:
                    is_playlist = False
                    self.after(0, lambda: self._log_write("   Single video", "dim"))
                    songs = [spotify_url]

            elif is_soundcloud:
                # SoundCloud — yt-dlp gestisce tutto nativamente
                self.after(0, lambda: self._log_write("SoundCloud URL detected", "dim"))
                is_playlist = "/sets/" in spotify_url
                if is_playlist:
                    self.after(0, lambda: self._log_write("   Playlist found", "dim"))
                    playlist_name = self._get_soundcloud_playlist_name(spotify_url)
                    songs = self._extract_soundcloud_playlist_songs(spotify_url)
                else:
                    self.after(0, lambda: self._log_write("   Single track", "dim"))
                    songs = [spotify_url]

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
            already_done = self._sync_done_with_disk(already_done, out)
            # Salva subito il json ripulito
            if already_done is not None:
                self._save_done(done_file, already_done, out)

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
            self._is_youtube_mode = is_youtube
            self._is_soundcloud_mode = is_soundcloud
            # Se c'è un placeholder da batch accodato, sostituiscilo; altrimenti append normale
            if getattr(self, "_placeholder_line", None) is not None:
                self.after(0, lambda s=songs: self._queue_replace_placeholder(s))
            else:
                self.after(0, lambda s=songs: self._queue_append(s))
            self._download_next_song(out, quality, fmt)

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
    
    def _sync_done_with_disk(self, already_done, folder):
        """Rimuove dal set le canzoni il cui file audio non esiste più su disco.
        Strategia: per ogni canzone nel JSON, cerca un file audio nella cartella
        il cui stem contiene almeno una parola significativa del nome canzone.
        Se la cartella è vuota o non esiste, pulisce tutto il set."""
        if not already_done or not os.path.exists(folder):
            return already_done
        try:
            audio_exts = {".mp3", ".flac", ".m4a", ".ogg", ".wav", ".opus"}
            audio_stems = set()
            for fname in os.listdir(folder):
                ext = os.path.splitext(fname)[1].lower()
                if ext in audio_exts:
                    audio_stems.add(os.path.splitext(fname)[0].lower())

            # Se non c'è nessun file audio nella cartella, svuota tutto
            if not audio_stems:
                return set()

            # Per ogni canzone nel JSON, controlla se esiste almeno un file
            # audio il cui stem condivide 2+ parole con il nome canzone
            removed = set()
            for song in list(already_done):
                words = set(w for w in re.split(r"[\s\-_,]", song.lower()) if len(w) > 2)
                if not words:
                    continue
                found = any(
                    sum(1 for w in words if w in stem) >= min(2, len(words))
                    for stem in audio_stems
                )
                if not found:
                    removed.add(song)

            if removed:
                already_done -= removed
            return already_done
        except Exception:
            return already_done

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

    def _download_next_song(self, out, quality, fmt="mp3"):
        """
        Avvia fino a MAX_PARALLEL download contemporaneamente.
        Chiamato all'inizio e ogni volta che un worker finisce.
        """
        MAX_PARALLEL = max(1, min(20, self._parallel_var.get()))

        with self._idx_lock:
            # Avvia worker finché ci sono slot liberi e canzoni da scaricare
            while self._active_workers < MAX_PARALLEL and self._running:
                # Salta le già scaricate
                while self._current_song_idx < len(self._songs_list):
                    song = self._songs_list[self._current_song_idx]
                    if song in self._already_done:
                        self._current_song_idx += 1
                        n = self._current_song_idx
                        self.after(0, lambda n=n, s=song: self._log_write(
                            f"[{n}/{len(self._songs_list)}] Already downloaded", "dim"))
                        self.after(0, lambda s=song: self._queue_set_status(s, "skipped"))
                    else:
                        break

                if self._current_song_idx >= len(self._songs_list):
                    break  # niente più canzoni da avviare

                song = self._songs_list[self._current_song_idx]
                self._current_song_idx += 1
                self._active_workers += 1
                idx = self._current_song_idx
                # Avvia il worker in un thread separato
                threading.Thread(
                    target=self._worker,
                    args=(song, idx, out, quality, fmt),
                    daemon=True
                ).start()

    def _worker(self, song, idx, out, quality, fmt):
        """Esegue il download di una singola canzone e poi chiama _on_worker_done."""
        if not self._running:
            with self._idx_lock:
                self._active_workers -= 1
            return
        is_youtube_mode    = getattr(self, "_is_youtube_mode", False)
        is_soundcloud_mode = getattr(self, "_is_soundcloud_mode", False)
        total = len(self._songs_list)

        display_title = song
        if is_youtube_mode and ("youtube.com" in song or "youtu.be" in song):
            title = self._get_youtube_video_title(song)
            if title:
                display_title = title

        self.after(0, lambda: self._log_write(
            f"[{idx}/{total}] - {display_title}", "bold"))
        self.after(0, lambda s=song: self._queue_set_status(s, "downloading"))
        self.after(0, lambda t=display_title: self._track_lbl.config(
            text=f"⏳ [{idx}/{total}] {t}  -  downloading"))

        retries = 0
        success = False
        while retries <= self._max_retries:
            if not self._running:
                break
            done_event = threading.Event()
            result = [False]
            result_file = [None]

            def on_complete(ok, fpath=None, _ev=done_event, _res=result, _rf=result_file):
                _res[0] = ok
                _rf[0] = fpath
                _ev.set()

            self._download_song_youtube(song, out, quality, on_complete, fmt, track_num=idx)
            done_event.wait()
            success = result[0]

            if success:
                break
            retries += 1
            if retries <= self._max_retries:
                self.after(0, lambda c=retries, m=self._max_retries:
                    self._log_write(f"   Retry ({c}/{m})...", "warn"))
                import time; time.sleep(1)
            else:
                self.after(0, lambda: self._log_write(
                    f"   Skipped after {self._max_retries} retries", "err"))

        self._on_worker_done(song, success, out, quality, fmt, track_num=idx, output_file=result_file[0])

    def _write_track_number_to_untagged(self, out, track_num):
        """Fallback: trova il file audio senza track number e scrivilo."""
        audio_exts = {".mp3", ".flac", ".m4a", ".ogg", ".opus"}
        try:
            from mutagen.id3 import ID3
            from mutagen.mp4 import MP4
            from mutagen.flac import FLAC
            from mutagen.oggvorbis import OggVorbis
            for f in os.listdir(out):
                ext = os.path.splitext(f)[1].lower()
                if ext not in audio_exts:
                    continue
                fpath = os.path.join(out, f)
                try:
                    has_track = False
                    if ext == ".mp3":
                        tags = ID3(fpath)
                        has_track = "TRCK" in tags and str(tags["TRCK"]).strip() not in ("", "0")
                    elif ext == ".flac":
                        tags = FLAC(fpath)
                        has_track = bool(tags.get("tracknumber"))
                    elif ext == ".m4a":
                        tags = MP4(fpath)
                        has_track = bool(tags.get("trkn"))
                    elif ext in (".ogg", ".opus"):
                        tags = OggVorbis(fpath)
                        has_track = bool(tags.get("tracknumber"))
                    if not has_track:
                        self._write_track_number_to_file(fpath, track_num)
                        return  # scrivi solo sul primo file senza numero
                except Exception:
                    continue
        except Exception:
            pass

    def _write_track_number_to_file(self, fpath, track_num):
        """Scrive il track number in un file audio specifico usando mutagen."""
        try:
            from mutagen.id3 import ID3, TRCK
            from mutagen.mp4 import MP4
            from mutagen.flac import FLAC
            from mutagen.oggvorbis import OggVorbis
            ext = os.path.splitext(fpath)[1].lower()
            if ext == ".mp3":
                tags = ID3(fpath)
                tags["TRCK"] = TRCK(encoding=3, text=str(track_num))
                tags.save(fpath)
            elif ext == ".flac":
                tags = FLAC(fpath)
                tags["tracknumber"] = [str(track_num)]
                tags.save()
            elif ext == ".m4a":
                tags = MP4(fpath)
                tags["trkn"] = [(track_num, 0)]
                tags.save()
            elif ext in (".ogg", ".opus"):
                tags = OggVorbis(fpath)
                tags["tracknumber"] = [str(track_num)]
                tags.save()
        except Exception:
            pass

    def _on_worker_done(self, song, success, out, quality, fmt, track_num=None, output_file=None):
        """Chiamato quando un worker finisce — aggiorna stato e avvia il prossimo."""
        if success:
            with self._idx_lock:
                self._already_done.add(song)
            self._save_done(self._done_file, self._already_done, self._done_key)
            self.after(0, lambda: self._log_write("   ✓ Done", "ok"))
            self.after(0, lambda s=song: self._queue_set_status(s, "done"))
            self._retry_count.pop(song, None)
        else:
            self.after(0, lambda s=song: self._queue_set_status(s, "error"))
            self._retry_count.pop(song, None)

        with self._idx_lock:
            self._active_workers -= 1
            all_started  = self._current_song_idx >= len(self._songs_list)
            still_active = self._active_workers
            running      = self._running

        # Prova ad avviare il prossimo slot
        if running:
            self._download_next_song(out, quality, fmt)

        # Controlla se siamo davvero finiti (tutti avviati + nessun worker attivo)
        with self._idx_lock:
            finished = (self._current_song_idx >= len(self._songs_list)
                        and self._active_workers == 0)

        if finished and self._running:
            total = len(self._songs_list)
            self.after(0, lambda: self._log_write(f"✓ Complete! ({total} songs)", "ok"))
            if self._pending_batches:
                next_url, next_out, next_quality, next_csv, next_fmt = self._pending_batches.pop(0)
                self.after(0, lambda u=next_url: self._log_write(f"▶ Starting queued batch: {u}", "bold"))
                threading.Thread(
                    target=self._extract_and_download,
                    args=(next_url, next_out, next_quality, next_csv, next_fmt),
                    daemon=True
                ).start()
            else:
                self.after(0, lambda: self._set_status("Complete", ACCENT))
                self._notify_complete(total)
                self._queue_session_active = False
                self._running = False
                self.after(0, self._on_done)

    def _run_ytdlp(self, song, out, quality):
        # Comando yt-dlp per cercare e scaricare da YouTube
        cmd = _find_cmd("yt-dlp") + [
            f"ytsearch:{song}",
            "-x",
            "-f", "bestaudio",
            "--audio-format", "mp3",
            "--audio-quality", quality,
            "-o", os.path.join(out, "%(artist,uploader)s - %(title)s.%(ext)s"),
            "--no-warnings",
            "--embed-metadata",
            "--add-metadata",
            "--parse-metadata", "title:%(artist)s - %(title)s",
            "--parse-metadata", r"%(title)s:(?P<title>.+?)(?:\s*[\(\[].+?[\)\]])*\s*$",
            "--print", "after_move:PYTHOFY_OUTFILE:%(filepath)s",
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

    def _download_song_youtube(self, song, out, quality, on_complete, fmt="mp3", track_num=None):
        """Download a single song from YouTube (batch version)"""
        import time
        import threading

        # Determine if search or direct URL
        is_youtube_mode    = getattr(self, "_is_youtube_mode", False)
        is_soundcloud_mode = getattr(self, "_is_soundcloud_mode", False)
        is_direct_url = (
            (is_youtube_mode    and ("youtube.com" in song or "youtu.be" in song)) or
            (is_soundcloud_mode and "soundcloud.com" in song)
        )

        if is_direct_url:
            search_query = song
            search_type  = "downloading"
        else:
            search_query = f"ytsearch:{song}"
            search_type  = "searching"

        # flac/wav non supportano bitrate: usa best quality automaticamente
        audio_quality_args = ["--audio-quality", quality] if fmt not in ("flac", "wav") else []
        cmd = _find_cmd("yt-dlp") + [
            search_query,
            "-x",
            "-f", "bestaudio",
            "--audio-format", fmt,
        ] + audio_quality_args + [
            "-o", os.path.join(out, "%(artist,uploader)s - %(title)s.%(ext)s"),
            "--no-warnings",
            "--embed-metadata",
            "--add-metadata",
            "--parse-metadata", "title:%(artist)s - %(title)s",
            "--parse-metadata", r"%(title)s:(?P<title>.+?)(?:\s*[\(\[].+?[\)\]])*\s*$",
        ] + ([
            "--postprocessor-args", f"ffmpeg:-metadata track={track_num}",
        ] if track_num else [])

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._process = proc  # compatibilità
            with self._active_procs_lock:
                self._active_procs.append(proc)
            with self._active_downloads_lock:
                self._active_downloads[proc] = set()

            last_heartbeat = time.time()
            phase = search_type
            process_completed = False

            output_file = [None]

            def read_output():
                nonlocal process_completed, last_heartbeat, phase
                last_progress = 0
                progress_logged = False
                try:
                    for line in proc.stdout:
                        if not self._running:
                            proc.terminate()
                            break

                        line = line.rstrip()
                        if not line:
                            continue

                        l = line.lower()
                        
                        # Only log important lines, filter out noise
                        should_log = False
                        if "pythofy_outfile:" in l:
                            # Path finale del file — sempre presente grazie a --print after_move
                            try:
                                fpath = line.split("PYTHOFY_OUTFILE:", 1)[1].strip()
                                output_file[0] = fpath
                                with self._active_downloads_lock:
                                    if proc in self._active_downloads:
                                        self._active_downloads[proc].add(fpath)
                            except Exception:
                                pass
                            continue  # non loggare questa riga
                        if "[download] destination:" in l:
                            try:
                                fpath = line.split("Destination:", 1)[1].strip()
                                with self._active_downloads_lock:
                                    if proc in self._active_downloads:
                                        self._active_downloads[proc].add(fpath)
                            except Exception:
                                pass
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
                            
                            # Cattura il path esatto del file creato
                            if "[extractaudio]" in l and "destination" in l:
                                try:
                                    fpath = line.split("Destination:", 1)[1].strip()
                                    output_file[0] = fpath
                                    with self._active_downloads_lock:
                                        if proc in self._active_downloads:
                                            self._active_downloads[proc].add(fpath)
                                except Exception:
                                    pass
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

            # Wait for process with timeout (3 min per canzone)
            proc.wait(timeout=180)
            rc = proc.returncode
            with self._active_procs_lock:
                try:
                    self._active_procs.remove(proc)
                except ValueError:
                    pass
            with self._active_downloads_lock:
                self._active_downloads.pop(proc, None)

            # Wait for reader to finish
            reader_thread.join(timeout=5)

            if self._running:
                on_complete(rc == 0, output_file[0])
        except subprocess.TimeoutExpired:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except:
                try:
                    proc.kill()
                except:
                    pass
            with self._active_procs_lock:
                try: self._active_procs.remove(proc)
                except ValueError: pass
            if self._running:
                self.after(0, lambda: self._log_write(
                    f"⚠ Download timeout (> 3 min), saltato", "warn"))
                on_complete(False, None)
        except Exception as e:
            # Assicurati che il processo sia terminato
            try:
                if self._process and self._process.poll() is None:
                    self._process.terminate()
                    self._process.wait(timeout=5)
            except:
                pass
            with self._active_procs_lock:
                try: self._active_procs.remove(proc)
                except (ValueError, UnboundLocalError): pass
            if self._running:
                error_msg = str(e)[:80]
                self.after(0, lambda m=error_msg: self._log_write(
                    f"⚠ Errore nel download: {m}", "warn"))
                on_complete(False, None)

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

        # Raccogli i filepath PRIMA di terminare i processi
        with self._active_downloads_lock:
            partial_sets = list(self._active_downloads.values())
            self._active_downloads.clear()

        # Termina tutti i processi paralleli attivi
        with self._active_procs_lock:
            for proc in self._active_procs:
                try:
                    if proc.poll() is None:
                        proc.terminate()
                except Exception:
                    pass
            self._active_procs.clear()

        # Compatibilità con _process singolo
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass

        # Piccola pausa per dare ai processi il tempo di chiudersi
        import time as _time
        _time.sleep(0.5)

        # Cancella tutti i file parziali tracciati
        deleted = 0
        all_partial = set()
        for fset in partial_sets:
            if fset:
                all_partial.update(fset)

        for fpath in all_partial:
            if not fpath:
                continue
            # Cancella il file principale
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                    deleted += 1
                except Exception:
                    pass
            # Cancella anche file .part/.ytdl/.temp associati
            for ext in (".part", ".ytdl", ".temp"):
                if os.path.exists(fpath + ext):
                    try:
                        os.remove(fpath + ext)
                        deleted += 1
                    except Exception:
                        pass

        # Cerca anche file .part/.ytdl nella cartella di output (fallback)
        try:
            out_dir = self._done_key if hasattr(self, "_done_key") else None
            if out_dir and os.path.isdir(out_dir):
                for f in os.listdir(out_dir):
                    if f.endswith(".part") or f.endswith(".ytdl"):
                        try:
                            os.remove(os.path.join(out_dir, f))
                            deleted += 1
                        except Exception:
                            pass
        except Exception:
            pass

        msg = f"Download stopped — {deleted} partial file(s) removed" if deleted else "Download stopped"
        self._log_write(msg, "warn")
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

        # Se non siamo admin, rilancia come admin e chiudi questa finestra
        if not _is_admin():
            import json as _json
            tmp_assets = tempfile.mktemp(prefix="pythofy_assets_", suffix=".json")
            with open(tmp_assets, "w") as f:
                _json.dump(assets, f)
            ok = _relaunch_as_admin([f"--do-update={tmp_assets}"])
            if ok:
                self.after(0, win.destroy)
                self.after(200, self.destroy)
                import sys as _sys; _sys.exit(0)
            else:
                self.after(0, lambda: self._update_progress_var.set(
                    "❌ Admin privileges required — please run as administrator"))
            return

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
                f'❌ Asset "{ASSET_NAME}" not found in release'))
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

        # Se non siamo admin, rilancia come admin
        if not _is_admin():
            ok = _relaunch_as_admin(["--do-rollback"])
            if ok:
                self.after(200, self.destroy)
                import sys as _sys; _sys.exit(0)
            else:
                self._log_write("❌ Admin privileges required — please run as administrator", "err")
            return

        base = os.path.dirname(sys.executable) if frozen else os.path.dirname(__file__)
        current = os.path.join(base, "Pythofy.exe")
        broken  = current + ".broken"
        try:
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


    # ══════════════════════════════════════════
    #  SOUNDCLOUD
    # ══════════════════════════════════════════

    def _is_soundcloud_url(self, url):
        return "soundcloud.com" in url

    def _get_soundcloud_playlist_name(self, url):
        """Estrae il nome di un set SoundCloud dall'URL"""
        try:
            # URL format: soundcloud.com/artist/sets/playlist-name
            parts = url.rstrip("/").split("/")
            idx = parts.index("sets") if "sets" in parts else -1
            if idx != -1 and idx + 1 < len(parts):
                return parts[idx + 1].replace("-", " ").title()
        except Exception:
            pass
        return "SoundCloud Playlist"

    def _extract_soundcloud_playlist_songs(self, url):
        """Estrae gli URL dei brani da un set SoundCloud tramite yt-dlp"""
        try:
            self.after(0, lambda: self._log_write("   📡 Extracting tracks from SoundCloud…", "dim"))
            cmd = _find_cmd("yt-dlp") + [
                url,
                "--print", "original_url",
                "--flat-playlist",
                "--no-warnings",
                "--quiet",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace", creationflags=_NO_WINDOW,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                urls = [l.strip() for l in lines if "soundcloud.com" in l]
                if urls:
                    self.after(0, lambda n=len(urls): self._log_write(f"   Found {n} tracks", "ok"))
                    return urls
            err = (result.stderr or result.stdout or "")[:80].strip()
            self.after(0, lambda e=err: self._log_write(f"   ⚠ SoundCloud extract error: {e}", "warn"))
            return None
        except Exception as e:
            self.after(0, lambda e=e: self._log_write(f"   ⚠ {str(e)[:60]}", "warn"))
            return None

    # ══════════════════════════════════════════
    #  QUEUE
    # ══════════════════════════════════════════

    def _queue_build(self, songs):
        """Prima chiamata: resetta e costruisce la queue da zero."""
        self._queue_map = {}
        self._queue_total = 0
        self._queue_line_counter = 0
        self._placeholder_line = None
        self._placeholder_line = None
        self._queue_list.configure(state="normal")
        self._queue_list.delete("1.0", "end")
        self._queue_list.configure(state="disabled")
        self._queue_append(songs)

    def _queue_append_placeholder(self, label):
        """Mostra subito separatore + riga pending nella queue, prima che le canzoni siano estratte."""
        if not hasattr(self, "_queue_map"):
            self._queue_map = {}
        if not hasattr(self, "_queue_line_counter"):
            self._queue_line_counter = 0

        self._queue_list.configure(state="normal")
        # Separatore
        if self._queue_line_counter > 0:
            self._queue_list.insert("end", "  " + "─" * 36 + "\n", "skipped")
            self._queue_line_counter += 1
        # Placeholder — verrà sostituito da _queue_replace_placeholder quando le canzoni arrivano
        display = label if len(label) <= 72 else label[:69] + "…"
        self._queue_list.insert("end", f"  ⏳  {display} (loading…)\n", "dim")
        self._queue_line_counter += 1
        self._placeholder_line = self._queue_line_counter  # salva la riga del placeholder
        self._queue_list.configure(state="disabled")

    def _queue_replace_placeholder(self, songs):
        """Sostituisce il placeholder con le canzoni reali, oppure fa _queue_append normale."""
        placeholder_line = getattr(self, "_placeholder_line", None)
        if placeholder_line is None:
            # Nessun placeholder da sostituire, append normale
            self._queue_append(songs)
            return

        self._queue_list.configure(state="normal")
        # Elimina la riga placeholder
        line_start = f"{placeholder_line}.0"
        line_end   = f"{placeholder_line}.end+1c"
        self._queue_list.delete(line_start, line_end)
        # Aggiusta il contatore: la riga placeholder è sparita
        self._queue_line_counter -= 1
        self._placeholder_line = None
        self._queue_list.configure(state="disabled")
        # Inserisci le canzoni reali a partire da placeholder_line
        self._queue_insert_at(songs, placeholder_line)

    def _queue_insert_at(self, songs, start_line):
        """Inserisce canzoni a una riga specifica del Text widget."""
        if not hasattr(self, "_queue_map"):
            self._queue_map = {}
        self._queue_list.configure(state="normal")
        for i, song in enumerate(songs):
            line_no = start_line + i
            label = song if len(song) <= 80 else song[:77] + "…"
            self._queue_list.insert(f"{line_no}.0", f"  ○  {label}\n", "queued")
            self._queue_map[song] = line_no
            self._queue_line_counter += 1
        if not hasattr(self, "_queue_total"):
            self._queue_total = 0
        self._queue_total += len(songs)
        self._queue_list.configure(state="disabled")
        self._queue_count_lbl.config(text=f"  {self._queue_total} tracks")

    def _queue_append(self, songs):
        """Aggiunge un batch di canzoni alla queue, con separatore se non è il primo."""
        if not hasattr(self, "_queue_map"):
            self._queue_map = {}
        if not hasattr(self, "_queue_line_counter"):
            self._queue_line_counter = 0  # numero di righe già nel widget

        self._queue_list.configure(state="normal")

        # Aggiungi separatore se ci sono già righe
        if self._queue_line_counter > 0:
            self._queue_list.insert("end", "  " + "─" * 36 + "\n", "skipped")
            self._queue_line_counter += 1

        # Inserisci le canzoni — ogni riga va a _queue_line_counter+1 (1-based)
        for song in songs:
            self._queue_line_counter += 1
            label = song if len(song) <= 80 else song[:77] + "…"
            self._queue_list.insert("end", f"  ○  {label}\n", "queued")
            self._queue_map[song] = self._queue_line_counter

        if not hasattr(self, "_queue_total"):
            self._queue_total = 0
        self._queue_total += len(songs)
        self._queue_list.configure(state="disabled")
        self._queue_count_lbl.config(text=f"  {self._queue_total} tracks")

    def _queue_set_status(self, song, status):
        """Aggiorna lo stato di una riga nella queue"""
        if not hasattr(self, "_queue_map") or song not in self._queue_map:
            return
        line_no = self._queue_map[song]
        icons = {
            "queued":      "  ○  ",
            "downloading": "  ▶  ",
            "done":        "  ✓  ",
            "error":       "  ✗  ",
            "skipped":     "  Skipped —  ",
        }
        icon = icons.get(status, "  ○  ")
        self._queue_list.configure(state="normal")
        line_start = f"{line_no}.0"
        line_end   = f"{line_no}.end"
        current = self._queue_list.get(line_start, line_end)
        # Sostituisci solo i primi 5 caratteri (l'icona)
        new_line = icon + current[5:]
        self._queue_list.delete(line_start, line_end)
        self._queue_list.insert(line_start, new_line, status)
        self._queue_list.configure(state="disabled")
        # Scrolla per mostrare la riga attiva
        if status == "downloading":
            self._queue_list.see(line_start)

    def _queue_clear(self):
        self._queue_list.configure(state="normal")
        self._queue_list.delete("1.0", "end")
        self._queue_list.configure(state="disabled")
        self._queue_count_lbl.config(text="")
        self._queue_map = {}
        self._queue_total = 0
        self._queue_line_counter = 0

    # ══════════════════════════════════════════
    #  WINDOWS NOTIFICATION
    # ══════════════════════════════════════════

    def _notify_complete(self, total):
        """Mostra notifica Windows al termine del download"""
        try:
            # Usa PowerShell per mostrare una toast notification nativa
            msg = f"Download complete: {total} song{'s' if total != 1 else ''} saved."
            script = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "$n = New-Object System.Windows.Forms.NotifyIcon;"
                "$n.Icon = [System.Drawing.SystemIcons]::Information;"
                "$n.Visible = $true;"
                f'$n.ShowBalloonTip(4000, "Pythofy", "{msg}", '
                "[System.Windows.Forms.ToolTipIcon]::None);"
                "Start-Sleep -Milliseconds 4500;"
                "$n.Visible = $false"
            )
            subprocess.Popen(
                ["powershell", "-WindowStyle", "Hidden", "-Command", script],
                creationflags=_NO_WINDOW,
            )
        except Exception:
            pass  # Notifica opzionale, non blocca nulla

    # ══════════════════════════════════════════
    #  DRAG & DROP
    # ══════════════════════════════════════════


    # ══════════════════════════════════════════
    #  CLEAR CSV
    # ══════════════════════════════════════════

    def _clear_csv(self):
        self._csv_songs = None
        self._csv_file_name = None
        self._csv_var.set("")
        self._log_write("CSV cleared", "dim")

    # ══════════════════════════════════════════
    #  SONGS WINDOW
    # ══════════════════════════════════════════

    def _open_songs_window(self):
        """Apre la finestra Songs con pannello cartelle + canzoni"""
        base_dir = self._dir_var.get().strip()
        if not os.path.exists(base_dir):
            messagebox.showinfo("Songs", "Destination folder does not exist yet.")
            return

        # Scansiona il JSON e la cartella
        done_file = self._done_file_path(base_dir)
        all_data = {}  # folder_path -> list of song names
        audio_exts = {".mp3", ".flac", ".m4a", ".ogg", ".wav", ".opus"}

        try:
            json_data = {}
            if os.path.exists(done_file):
                with open(done_file, "r", encoding="utf-8") as f:
                    json_data = json.load(f)
        except Exception:
            json_data = {}

        # Costruisci struttura: scan disco come fonte primaria (i file audio reali)
        # Il JSON può contenere URL o nomi canzone — usiamo solo i file fisici
        for root_dir, dirs, files in os.walk(base_dir):
            audio_files = [f for f in files if os.path.splitext(f)[1].lower() in audio_exts]
            if not audio_files:
                continue
            stems = [os.path.splitext(f)[0] for f in audio_files]
            all_data[root_dir] = stems

        # Se una cartella è nel JSON ma non ha file audio ancora (download parziale),
        # mostrala comunque con i nomi dal JSON, filtrando gli URL
        for folder_key, songs in json_data.items():
            if folder_key not in all_data and os.path.exists(folder_key):
                # Filtra le voci che sembrano URL
                real_names = [s for s in songs if not s.startswith("http")]
                if real_names:
                    all_data[folder_key] = real_names

        if not all_data:
            messagebox.showinfo("Songs", "No downloaded songs found.")
            return

        # ── Costruisci finestra ──────────────────────────────
        win = tk.Toplevel(self)
        win.title("Songs")
        win.configure(bg=BG)
        win.geometry("900x580")
        win.minsize(700, 400)

        # Header
        hdr = tk.Frame(win, bg=BG2, height=40)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="SONGS", font=(MONO, 9, "bold"), bg=BG2, fg=ACCENT).pack(side="left", padx=14)
        total_songs = sum(len(v) for v in all_data.values())
        tk.Label(hdr, text=f"{total_songs} tracks  ·  {len(all_data)} folders",
                 font=(MONO, 8), bg=BG2, fg=TEXT_SUB).pack(side="left", padx=(0, 0))
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x", side="top")

        # Body: pannello sinistro + separatore + pannello destro
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True)

        # ── LEFT: lista cartelle ──────────────────────────────
        left = tk.Frame(body, bg=BG, width=260)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        tk.Label(left, text="FOLDERS", font=(MONO, 7, "bold"), bg=BG, fg=TEXT_DIM).pack(
            anchor="w", padx=14, pady=(10, 4))

        folder_list_frame = tk.Frame(left, bg=BG)
        folder_list_frame.pack(fill="both", expand=True)

        folder_lb = tk.Listbox(folder_list_frame,
            bg=BG, fg=TEXT_MID, selectbackground=BG4, selectforeground=ACCENT,
            font=(SANS, 9), relief="flat", bd=0, highlightthickness=0,
            activestyle="none", cursor="hand2")
        folder_sb = ttk.Scrollbar(folder_list_frame, orient="vertical", command=folder_lb.yview)
        folder_lb.configure(yscrollcommand=folder_sb.set)
        folder_sb.pack(side="right", fill="y")
        folder_lb.pack(side="left", fill="both", expand=True, padx=(14, 0))

        folder_keys = list(all_data.keys())
        for fk in folder_keys:
            name = os.path.basename(fk) or fk
            count = len(all_data[fk])
            folder_lb.insert("end", f"  {name}  ({count})")

        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        # ── RIGHT: lista canzoni ──────────────────────────────
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        right_hdr = tk.Frame(right, bg=BG2, height=32)
        right_hdr.pack(fill="x", side="top")
        right_hdr.pack_propagate(False)
        self._songs_win_folder_lbl = tk.Label(right_hdr, text="Select a folder",
            font=(MONO, 8), bg=BG2, fg=TEXT_MID)
        self._songs_win_folder_lbl.pack(side="left", padx=14)
        tk.Frame(right, bg=BORDER, height=1).pack(fill="x", side="top")

        songs_frame = tk.Frame(right, bg=BG)
        songs_frame.pack(fill="both", expand=True)

        songs_lb = tk.Listbox(songs_frame,
            bg=BG, fg=TEXT, selectbackground=BG4, selectforeground=ACCENT,
            font=(SANS, 9), relief="flat", bd=0, highlightthickness=0,
            activestyle="none", cursor="hand2")
        songs_sb = ttk.Scrollbar(songs_frame, orient="vertical", command=songs_lb.yview)
        songs_lb.configure(yscrollcommand=songs_sb.set)
        songs_sb.pack(side="right", fill="y")
        songs_lb.pack(side="left", fill="both", expand=True, padx=(14, 0), pady=4)

        # Statusbar / action bar in fondo
        tk.Frame(right, bg=BORDER, height=1).pack(fill="x", side="bottom")
        action_bar = tk.Frame(right, bg=BG2, height=36)
        action_bar.pack(fill="x", side="bottom")
        action_bar.pack_propagate(False)
        self._songs_win_status = tk.Label(action_bar, text="",
            font=(MONO, 8), bg=BG2, fg=TEXT_SUB)
        self._songs_win_status.pack(side="left", padx=14)

        open_folder_btn = self._ghost_btn(action_bar, "OPEN FOLDER", lambda: None)
        open_folder_btn.pack(side="right", padx=(0, 8), pady=4)
        delete_btn = self._ghost_btn(action_bar, "DELETE", lambda: None)
        delete_btn.pack(side="right", padx=(0, 4), pady=4)

        # ── Stato condiviso tra callbacks ────────────────────
        state = {"folder": None, "song_name": None}

        def on_folder_select(e):
            sel = folder_lb.curselection()
            if not sel:
                return
            idx = sel[0]
            fk = folder_keys[idx]
            state["folder"] = fk
            state["song_name"] = None
            name = os.path.basename(fk) or fk
            self._songs_win_folder_lbl.config(text=name)
            songs_lb.delete(0, "end")
            for s in all_data[fk]:
                songs_lb.insert("end", f"  {s}")
            self._songs_win_status.config(text=f"{len(all_data[fk])} tracks")

        def on_song_select(e):
            sel = songs_lb.curselection()
            if not sel:
                return
            idx = sel[0]
            fk = state["folder"]
            if not fk:
                return
            song = all_data[fk][idx]
            state["song_name"] = song
            self._songs_win_status.config(text=song[:80])

        def do_open_folder():
            fk = state["folder"]
            if not fk or not os.path.exists(fk):
                return
            if sys.platform == "win32":
                os.startfile(fk)
            else:
                subprocess.Popen(["xdg-open", fk])

        def do_delete():
            fk = state["folder"]
            sn = state["song_name"]
            if not fk or not sn:
                messagebox.showinfo("Delete", "Select a song first.", parent=win)
                return

            if not messagebox.askyesno("Delete", f'Delete "{sn}" and remove from history?', parent=win):
                return

            # Cerca il file su disco
            audio_exts_list = [".mp3", ".flac", ".m4a", ".ogg", ".wav", ".opus"]
            deleted_file = False
            sn_clean = sn.lstrip("📁 ")
            if os.path.exists(fk):
                for fname in os.listdir(fk):
                    stem = os.path.splitext(fname)[0]
                    if stem.lower() == sn_clean.lower() or stem == sn_clean:
                        fpath = os.path.join(fk, fname)
                        try:
                            os.remove(fpath)
                            deleted_file = True
                        except Exception as ex:
                            messagebox.showerror("Error", f"Could not delete file:\n{ex}", parent=win)
                            return
                        break

            # Rimuovi dal JSON
            try:
                if os.path.exists(done_file):
                    with open(done_file, "r", encoding="utf-8") as f:
                        jdata = json.load(f)
                    if fk in jdata and sn in jdata[fk]:
                        jdata[fk].remove(sn)
                        with open(done_file, "w", encoding="utf-8") as f:
                            json.dump(jdata, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

            # Aggiorna UI
            all_data[fk].remove(sn)
            sel = songs_lb.curselection()
            if sel:
                songs_lb.delete(sel[0])
            state["song_name"] = None
            self._songs_win_status.config(
                text=f"{'Deleted  ·  ' if deleted_file else 'Removed from history  ·  '}{len(all_data[fk])} tracks remaining")

            # Aggiorna contatore cartella nella lista sinistra
            sel_f = folder_lb.curselection()
            if sel_f:
                name = os.path.basename(fk) or fk
                folder_lb.delete(sel_f[0])
                folder_lb.insert(sel_f[0], f"  {name}  ({len(all_data[fk])})")
                folder_lb.selection_set(sel_f[0])

        open_folder_btn.config(command=do_open_folder)
        delete_btn.config(command=do_delete)
        folder_lb.bind("<<ListboxSelect>>", on_folder_select)
        songs_lb.bind("<<ListboxSelect>>", on_song_select)

        # Seleziona prima cartella automaticamente
        if folder_keys:
            folder_lb.selection_set(0)
            folder_lb.event_generate("<<ListboxSelect>>")


    def _on_done(self):
        self._progress.stop()
        self._dl_btn.config(state="normal")
        self._stop_btn.config(state="disabled")
        self._track_lbl.config(text="")
        # Se stoppato manualmente, svuota i pending e chiudi la sessione
        if not self._running:
            self._pending_batches.clear()
            self._queue_session_active = False
            self._downloaded_urls.clear()


# ──────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────
def _handle_cli_admin_actions():
    import sys, os, shutil
    args = sys.argv[1:]
    if not args:
        return False

    for arg in args:
        if arg.startswith("--do-update="):
            import json as _json, tempfile, zipfile, urllib.request, ssl, threading as _th
            import tkinter as tk
            assets_file = arg.split("=", 1)[1]
            try:
                with open(assets_file, "r") as f:
                    assets = _json.load(f)
                os.remove(assets_file)
            except Exception:
                return True

            root = tk.Tk()
            root.title("Pythofy — Updating…")
            root.geometry("420x70")
            root.configure(bg="#0d0d0d")
            root.resizable(False, False)
            progress_var = tk.StringVar(value="Starting update…")
            tk.Label(root, textvariable=progress_var, font=("Arial", 10),
                     bg="#0d0d0d", fg="#a3e635").pack(expand=True)

            def run_update():
                frozen = getattr(sys, "frozen", False)
                base_path = os.path.dirname(sys.executable) if frozen else os.path.dirname(__file__)
                tools_path = os.path.join(base_path, "pythofy_tools")
                ASSET_NAME = "Pythofy.-.Portable.zip"
                url = assets.get(ASSET_NAME)
                if not url:
                    root.after(0, lambda: progress_var.set("❌ Asset not found"))
                    root.after(2000, root.destroy)
                    return
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                tmp_dir = tempfile.mkdtemp(prefix="pythofy_update_")
                zip_path = os.path.join(tmp_dir, "update.zip")
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Pythofy-Updater"})
                    with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
                        total = int(resp.headers.get("Content-Length", 0))
                        done = 0
                        with open(zip_path, "wb") as fp:
                            while True:
                                buf = resp.read(65536)
                                if not buf: break
                                fp.write(buf)
                                done += len(buf)
                                if total:
                                    pct = int(done / total * 100)
                                    root.after(0, lambda p=pct: progress_var.set(f"Downloading… {p}%"))
                    root.after(0, lambda: progress_var.set("Extracting…"))
                    extract_dir = os.path.join(tmp_dir, "extracted")
                    with zipfile.ZipFile(zip_path, "r") as z:
                        z.extractall(extract_dir)
                    src_root = extract_dir
                    for entry in os.listdir(extract_dir):
                        candidate = os.path.join(extract_dir, entry)
                        if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "Pythofy.exe")):
                            src_root = candidate
                            break
                    os.makedirs(tools_path, exist_ok=True)
                    for tool in ("yt-dlp.exe", "ffmpeg.exe"):
                        src = os.path.join(src_root, "pythofy_tools", tool)
                        if os.path.exists(src):
                            root.after(0, lambda t=tool: progress_var.set(f"Installing {t}…"))
                            shutil.copy2(src, os.path.join(tools_path, tool))
                    new_exe_src = os.path.join(src_root, "Pythofy.exe")
                    new_exe_dst = os.path.join(base_path, "Pythofy.exe")
                    if os.path.exists(new_exe_src):
                        root.after(0, lambda: progress_var.set("Installing Pythofy.exe…"))
                        if frozen:
                            try: os.replace(new_exe_dst, new_exe_dst + ".old")
                            except: pass
                        shutil.copy2(new_exe_src, new_exe_dst)
                    root.after(0, lambda: progress_var.set("✓ Done — restarting…"))
                    import subprocess as _sp
                    root.after(1200, lambda dst=new_exe_dst: (
                        _sp.Popen([dst], creationflags=0x08000000),
                        root.destroy()
                    ))
                except Exception as e:
                    root.after(0, lambda err=str(e)[:80]: progress_var.set(f"❌ {err}"))
                    root.after(3000, root.destroy)
                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)

            _th.Thread(target=run_update, daemon=True).start()
            root.mainloop()
            return True

    if "--do-rollback" in args:
        frozen = getattr(sys, "frozen", False)
        base = os.path.dirname(sys.executable) if frozen else os.path.dirname(__file__)
        old_path = os.path.join(base, "Pythofy.exe.old")
        current  = os.path.join(base, "Pythofy.exe")
        if not os.path.exists(old_path):
            return True
        try:
            if frozen:
                try: os.replace(current, current + ".broken")
                except: pass
            shutil.copy2(old_path, current)
            os.remove(old_path)
            import subprocess as _sp
            _sp.Popen([current], creationflags=0x08000000)
        except Exception:
            pass
        return True

    return False


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    if _handle_cli_admin_actions():
        import sys; sys.exit(0)
    app = YouTubeDownloaderApp()
    app.mainloop()