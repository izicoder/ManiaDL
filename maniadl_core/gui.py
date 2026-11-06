"""Dark tkinter desktop UI for ManiaDL.

Layout follows the spec: every setting lives in the scrollable left panel, all
run status (progress, stats, transfers, log, failed sets) lives on the right.
Downloads run in a worker thread; widgets are only touched from the Tk thread.
"""

from __future__ import annotations

import asyncio
import os
import queue
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import api, app, config, reports, runtime, ui, util
from .constants import ADVANCED_KEYS, DEFAULT_OUT, NEW_DEFAULTS, SORT_LABELS, SORTS
from .progress import TaskBoard

BG = "#111318"
PANEL = "#191c23"
PANEL_ALT = "#232834"
FG = "#e5e9f0"
MUTED = "#8f98a8"
ACCENT = "#7aa2f7"
GREEN = "#9ece6a"
RED = "#f7768e"
YELLOW = "#e0af68"
BORDER = "#2b303b"
FIELD = "#1e222b"

STATUS_ORDER = ["ranked", "loved", "qualified", "pending", "graveyard"]
STATUS_LABELS = {
    "ranked": "Ranked",
    "loved": "Loved",
    "qualified": "Qualified",
    "pending": "Pending",
    "graveyard": "Graveyard",
    "any": "Any",
}
ADVANCED_FIELDS = [
    ("query", "Search query"),
    ("title", "Title contains"),
    ("artist", "Artist contains"),
    ("creator", "Mapper contains"),
    ("source", "Source contains"),
    ("exclude", "Exclude terms"),
    ("genre", "Genres"),
    ("language", "Languages"),
    ("bpm_range", "BPM range"),
    ("length_range", "Length range (s)"),
    ("notes_range", "Notes range"),
    ("min_plays", "Min play count"),
    ("ranked_range", "Ranked dates"),
]
ADVANCED_HINTS = {
    "bpm_range": "e.g. 150-220",
    "length_range": "e.g. 60-300",
    "notes_range": "e.g. 1000-5000",
    "ranked_range": "e.g. 2020-01-01..2024-12-31",
    "exclude": "comma-separated",
    "genre": "comma-separated, partial ok",
    "language": "comma-separated, partial ok",
}
SORT_BY_LABEL = {label: key for key, label in SORT_LABELS.items()}


class ManiaDLApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ManiaDL")
        self.geometry("1200x820")
        self.minsize(1000, 680)
        self.configure(bg=BG)
        self.option_add("*tearOff", False)

        self.saved = self._load_saved()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.event_queue: queue.Queue[tuple] = queue.Queue()
        self.progress = TaskBoard()
        self.overall = TaskBoard()
        self.worker: threading.Thread | None = None
        self.running = False
        self.closing = False
        self.started = 0.0
        self.cfg: dict | None = None
        self.failed_entries: list[dict] = []
        self._free_at = 0.0
        self._free_text = "?"

        self._apply_theme()
        self._build()
        self._load_settings()
        self._sync_advanced_state()

        runtime.set_log_listener(self.log_queue.put)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind_all("<MouseWheel>", self._on_wheel)
        self.after(120, self._tick)
        self.after(80, self._dark_titlebar)
        runtime.log("ManiaDL ready.")

    # ---- settings load/save ---------------------------------------------

    def _load_saved(self) -> dict:
        saved = config.load_saved()
        saved, changed = config.migrate_saved(saved)
        if changed and (saved.get("client_id") or saved.get("client_secret")):
            config.save_saved(saved)
        return saved

    def _load_settings(self) -> None:
        saved = self.saved
        cid = os.environ.get("OSU_CLIENT_ID") or saved.get("client_id") or ""
        secret = (
            os.environ.get("OSU_CLIENT_SECRET") or saved.get("client_secret") or ""
        )
        self.cid_var.set(str(cid))
        self.secret_var.set(str(secret))

        self.out_var.set(str(saved.get("out") or DEFAULT_OUT))
        try:
            self._free_text = f"{util.free_gb(Path(self.out_var.get())):,.1f} GB"
            self.stat_vars["free"].set(self._free_text)
        except OSError:
            self._free_text = "?"
            self.stat_vars["free"].set("?")

        statuses = [
            part.strip().lower()
            for part in str(saved.get("statuses") or "ranked").split(",")
            if part.strip()
        ]
        if not statuses or "any" in statuses:
            self.status_vars["any"].set(True)
        else:
            for name in STATUS_ORDER:
                self.status_vars[name].set(name in statuses)
            if not any(
                self.status_vars[name].get() for name in STATUS_ORDER
            ):
                self.status_vars["ranked"].set(True)

        self.keys_var.set(str(saved.get("keys") or "all"))
        self.min_sr_var.set(str(saved.get("min_sr", 0)))
        self.max_sr_var.set(str(saved.get("max_sr", 99)))
        self.min_favs_var.set(str(saved.get("min_favs", 0)))
        self.sort_var.set(
            SORT_LABELS.get(
                saved.get("sort") if saved.get("sort") in SORTS else SORTS[0],
                SORT_LABELS[SORTS[0]],
            )
        )
        self.limit_var.set(str(saved.get("limit", 500)))
        self.workers_var.set(str(saved.get("workers", 4)))
        self.batch_var.set(str(saved.get("batch", 20)))

        advanced = util.as_bool(saved.get("advanced", False))
        try:
            min_plays = int(saved.get("min_plays") or 0)
        except (TypeError, ValueError):
            min_plays = 0
        if not advanced:
            advanced = any(
                str(saved.get(key) or "").strip()
                for key in ADVANCED_KEYS
                if key not in ("include_nsfw", "min_plays")
            ) or min_plays > 0 or util.as_bool(
                saved.get("include_nsfw", False)
            )
        self.adv_var.set(advanced)
        for key, var in self.adv_vars.items():
            if key == "include_nsfw":
                var.set(util.as_bool(saved.get(key, False)))
            else:
                var.set(str(saved.get(key, NEW_DEFAULTS.get(key, ""))))

        if os.environ.get("OSU_CLIENT_ID") or os.environ.get(
            "OSU_CLIENT_SECRET"
        ):
            self.env_note_var.set("Environment credentials override saved keys.")

    def _collect_raw(self) -> dict:
        statuses = [name for name in STATUS_ORDER if self.status_vars[name].get()]
        if self.status_vars["any"].get():
            statuses = ["any"]
        if not statuses:
            raise ValueError("Pick at least one status (or tick Any).")

        raw: dict = {
            "out": self.out_var.get().strip() or str(DEFAULT_OUT),
            "statuses": ",".join(statuses),
            "keys": self.keys_var.get().strip() or "all",
            "min_sr": self.min_sr_var.get().strip() or "0",
            "max_sr": self.max_sr_var.get().strip() or "99",
            "min_favs": self.min_favs_var.get().strip() or "0",
            "sort": SORT_BY_LABEL.get(self.sort_var.get(), SORTS[0]),
            "limit": self.limit_var.get().strip() or "500",
            "workers": self.workers_var.get().strip() or "4",
            "batch": self.batch_var.get().strip() or "20",
            "advanced": bool(self.adv_var.get()),
        }
        for key, var in self.adv_vars.items():
            if key == "include_nsfw":
                raw[key] = bool(var.get())
            else:
                raw[key] = str(var.get()).strip()
        raw["min_plays"] = raw.get("min_plays") or "0"
        return raw

    # ---- theme ----------------------------------------------------------

    def _apply_theme(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        base = ("Segoe UI", 10)
        bold = ("Segoe UI Semibold", 10)
        small = ("Segoe UI", 9)
        tiny_bold = ("Segoe UI Semibold", 9)
        value = ("Segoe UI Semibold", 17)
        self.option_add("*Font", base)

        style.configure(
            ".",
            background=BG,
            foreground=FG,
            fieldbackground=FIELD,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            troughcolor=PANEL,
            focuscolor=ACCENT,
            selectbackground=ACCENT,
            selectforeground="#10131a",
            font=base,
        )

        # ---- text ------------------------------------------------------
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=small)
        style.configure(
            "Title.TLabel",
            background=BG,
            foreground=FG,
            font=("Segoe UI Semibold", 21),
        )
        style.configure(
            "Subtitle.TLabel", background=BG, foreground=MUTED, font=small
        )

        # ---- cards -----------------------------------------------------
        style.configure("Card.TFrame", background=PANEL)
        style.configure(
            "CardTitle.TLabel", background=PANEL, foreground=MUTED, font=small
        )
        style.configure(
            "CardValue.TLabel", background=PANEL, foreground=FG, font=value
        )
        style.configure(
            "CardValueGreen.TLabel", background=PANEL, foreground=GREEN, font=value
        )
        style.configure(
            "CardValueRed.TLabel", background=PANEL, foreground=RED, font=value
        )
        style.configure(
            "CardValueAccent.TLabel", background=PANEL, foreground=ACCENT, font=value
        )
        style.configure(
            "CardMeta.TLabel", background=PANEL, foreground=MUTED, font=small
        )

        # ---- buttons ---------------------------------------------------
        style.configure(
            "TButton",
            background=PANEL_ALT,
            foreground=FG,
            borderwidth=0,
            padding=(12, 6),
            focusthickness=0,
            font=bold,
        )
        style.map(
            "TButton",
            background=[("active", BORDER), ("pressed", BORDER), ("disabled", PANEL)],
            foreground=[("disabled", MUTED)],
        )
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#0d1117",
            font=("Segoe UI Semibold", 10),
            padding=(26, 8),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#9bb8fa"), ("pressed", "#9bb8fa"), ("disabled", "#374151")],
            foreground=[("disabled", MUTED)],
        )
        style.configure(
            "Stop.TButton",
            background=PANEL_ALT,
            foreground=RED,
            font=("Segoe UI Semibold", 10),
            padding=(20, 8),
        )
        style.map(
            "Stop.TButton",
            background=[("active", BORDER), ("pressed", BORDER), ("disabled", PANEL)],
            foreground=[("disabled", MUTED)],
        )

        # ---- containers ------------------------------------------------
        style.configure(
            "TLabelframe",
            background=BG,
            bordercolor=BORDER,
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "TLabelframe.Label",
            background=BG,
            foreground=MUTED,
            font=tiny_bold,
        )
        style.configure("TSeparator", background=BORDER)

        # ---- inputs ----------------------------------------------------
        style.configure(
            "TEntry",
            fieldbackground=FIELD,
            foreground=FG,
            insertcolor=FG,
            bordercolor=BORDER,
            padding=7,
        )
        style.map(
            "TEntry",
            fieldbackground=[("disabled", PANEL), ("focus", FIELD)],
            bordercolor=[("focus", ACCENT)],
        )
        style.configure(
            "TCombobox",
            fieldbackground=FIELD,
            background=FIELD,
            foreground=FG,
            arrowcolor=MUTED,
            bordercolor=BORDER,
            padding=7,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", FIELD), ("disabled", PANEL)],
            foreground=[("readonly", FG)],
            selectbackground=[("readonly", FIELD)],
            selectforeground=[("readonly", FG)],
        )
        style.configure(
            "TSpinbox",
            fieldbackground=FIELD,
            foreground=FG,
            arrowcolor=MUTED,
            bordercolor=BORDER,
            padding=7,
        )
        style.map(
            "TSpinbox",
            fieldbackground=[("disabled", PANEL)],
            foreground=[("disabled", MUTED)],
        )
        style.configure("TCheckbutton", background=BG, foreground=FG, font=small)
        style.map(
            "TCheckbutton",
            background=[("active", BG)],
            foreground=[("disabled", MUTED)],
            indicatorbackground=[("selected", ACCENT), ("!selected", FIELD)],
            indicatorforeground=[("selected", "#0d1117"), ("!selected", MUTED)],
            upperbordercolor=[("!selected", BORDER)],
            lowerbordercolor=[("!selected", BORDER)],
        )

        # ---- data views ------------------------------------------------
        style.configure(
            "Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=FG,
            bordercolor=BORDER,
            rowheight=27,
            font=base,
        )
        style.configure(
            "Treeview.Heading",
            background=PANEL,
            foreground=MUTED,
            relief="flat",
            font=tiny_bold,
            padding=(6, 6),
        )
        style.map(
            "Treeview",
            background=[("selected", "#2f4368")],
            foreground=[("selected", FG)],
        )
        style.map("Treeview.Heading", background=[("active", PANEL_ALT)])

        style.configure(
            "TNotebook",
            background=BG,
            bordercolor=BORDER,
            tabmargins=(0, 6, 0, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=PANEL,
            foreground=MUTED,
            padding=(14, 6),
            borderwidth=0,
            font=tiny_bold,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", PANEL_ALT)],
            foreground=[("selected", FG)],
        )
        style.configure(
            "TProgressbar",
            troughcolor=PANEL_ALT,
            background=ACCENT,
            bordercolor=PANEL_ALT,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=16,
        )
        style.configure(
            "TScrollbar",
            background=PANEL_ALT,
            troughcolor=BG,
            bordercolor=BG,
            arrowcolor=MUTED,
            width=10,
        )
        style.map("TScrollbar", background=[("active", BORDER)])

    # ---- layout ---------------------------------------------------------

    def _build(self) -> None:
        main = ttk.Frame(self, padding=(16, 14))
        main.pack(fill="both", expand=True)

        head = ttk.Frame(main)
        head.pack(fill="x", pady=(0, 10))
        ttk.Label(head, text="ManiaDL", style="Title.TLabel").pack(side="left")
        ttk.Label(
            head,
            text="bulk osu!mania beatmap downloader for osu!lazer",
            style="Subtitle.TLabel",
        ).pack(side="left", padx=(14, 0), pady=(10, 0))
        tk.Frame(main, bg=BORDER, height=1).pack(fill="x", pady=(0, 12))

        footer = ttk.Frame(main)
        footer.pack(side="bottom", fill="x", pady=(12, 0))
        tk.Frame(footer, bg=BORDER, height=1).pack(fill="x", pady=(0, 10))
        bar = ttk.Frame(footer)
        bar.pack(fill="x")
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(
            bar,
            textvariable=self.status_var,
            style="Muted.TLabel",
            wraplength=640,
            justify="left",
        ).pack(side="left")
        self.stop_btn = ttk.Button(
            bar, text="Stop", style="Stop.TButton", command=self._stop
        )
        self.stop_btn.pack(side="right")
        self.stop_btn.state(["disabled"])
        self.start_btn = ttk.Button(
            bar, text="Start", style="Accent.TButton", command=self._start
        )
        self.start_btn.pack(side="right", padx=(0, 10))

        paned = ttk.Panedwindow(main, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned)
        right = ttk.Frame(paned, padding=(14, 0, 0, 0))
        paned.add(left, weight=0)
        paned.add(right, weight=1)

        self._build_settings(left)
        self._build_status(right)

    def _build_settings(self, parent) -> None:
        holder = ttk.Frame(parent)
        holder.pack(fill="both", expand=True)
        self.left_canvas = tk.Canvas(
            holder,
            bg=BG,
            highlightthickness=0,
            width=440,
            bd=0,
        )
        bar = ttk.Scrollbar(
            holder, orient="vertical", command=self.left_canvas.yview
        )
        self.left_canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.left_canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(self.left_canvas, padding=(0, 0, 8, 8))
        self.left_inner = inner
        window = self.left_canvas.create_window(
            (0, 0), window=inner, anchor="nw"
        )
        inner.bind(
            "<Configure>",
            lambda _event: self.left_canvas.configure(
                scrollregion=self.left_canvas.bbox("all")
            ),
        )
        self.left_canvas.bind(
            "<Configure>",
            lambda event: self.left_canvas.itemconfigure(
                window, width=event.width
            ),
        )

        self.cid_var = tk.StringVar()
        self.secret_var = tk.StringVar()
        self.env_note_var = tk.StringVar()
        self.show_secret_var = tk.BooleanVar(value=False)
        self.out_var = tk.StringVar()
        self.status_vars = {
            name: tk.BooleanVar(value=False)
            for name in STATUS_ORDER + ["any"]
        }
        self.keys_var = tk.StringVar()
        self.min_sr_var = tk.StringVar()
        self.max_sr_var = tk.StringVar()
        self.min_favs_var = tk.StringVar()
        self.sort_var = tk.StringVar(value=SORT_LABELS[SORTS[0]])
        self.limit_var = tk.StringVar()
        self.workers_var = tk.StringVar()
        self.batch_var = tk.StringVar()
        self.adv_var = tk.BooleanVar(value=False)
        self.adv_vars: dict[str, tk.Variable] = {}
        for key, _label in ADVANCED_FIELDS:
            self.adv_vars[key] = tk.StringVar()
        self.adv_vars["include_nsfw"] = tk.BooleanVar(value=False)

        self._api_section(inner)
        self._folder_section(inner)
        self._filter_section(inner)
        self._download_section(inner)
        self._advanced_section(inner)
        self._wheel_safe(inner)

    def _api_section(self, parent) -> None:
        box = ttk.Labelframe(parent, text="osu! API", padding=(10, 8))
        box.pack(fill="x", pady=(0, 10))
        box.columnconfigure(0, minsize=112)
        box.columnconfigure(1, weight=1)

        self._labeled(box, 0, "Client ID", ttk.Entry(box, textvariable=self.cid_var))
        secret = ttk.Entry(box, textvariable=self.secret_var, show="•")
        self._labeled(box, 1, "Client secret", secret)
        ttk.Checkbutton(
            box,
            text="Show",
            variable=self.show_secret_var,
            command=lambda: secret.configure(
                show="" if self.show_secret_var.get() else "•"
            ),
        ).grid(row=1, column=2, sticky="w", padx=(6, 0))

        ttk.Button(
            box, text="How to get keys", command=self._show_key_guide
        ).grid(row=2, column=1, sticky="w", pady=(6, 0))
        ttk.Label(
            box,
            textvariable=self.env_note_var,
            style="Muted.TLabel",
            wraplength=280,
        ).grid(row=2, column=2, sticky="w", pady=(6, 0))

    def _folder_section(self, parent) -> None:
        box = ttk.Labelframe(parent, text="Download folder", padding=(10, 8))
        box.pack(fill="x", pady=(0, 10))
        box.columnconfigure(0, weight=1)

        ttk.Entry(box, textvariable=self.out_var).grid(
            row=0, column=0, sticky="ew", pady=3
        )
        ttk.Button(box, text="Browse", command=self._browse).grid(
            row=0, column=1, padx=(6, 0), pady=3
        )
        ttk.Button(box, text="Open", command=self._open_folder).grid(
            row=0, column=2, padx=(6, 0), pady=3
        )

    def _filter_section(self, parent) -> None:
        box = ttk.Labelframe(parent, text="Filters", padding=(10, 8))
        box.pack(fill="x", pady=(0, 10))
        box.columnconfigure(0, minsize=112)
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="Statuses").grid(
            row=0, column=0, sticky="nw", padx=(0, 8), pady=3
        )
        status_box = ttk.Frame(box)
        status_box.grid(row=0, column=1, columnspan=2, sticky="ew", pady=3)
        for index, name in enumerate(STATUS_ORDER + ["any"]):
            ttk.Checkbutton(
                status_box,
                text=STATUS_LABELS[name],
                variable=self.status_vars[name],
                command=lambda key=name: self._status_toggled(key),
            ).grid(
                row=index // 3,
                column=index % 3,
                sticky="w",
                padx=(0, 10),
                pady=1,
            )

        self._labeled(
            box,
            1,
            "Key counts",
            ttk.Entry(box, textvariable=self.keys_var),
        )
        ttk.Label(
            box, text="all or 4,7", style="Muted.TLabel"
        ).grid(row=2, column=1, sticky="w", pady=(0, 3))

        stars = ttk.Frame(box)
        stars.columnconfigure(0, weight=1)
        stars.columnconfigure(2, weight=1)
        ttk.Entry(stars, textvariable=self.min_sr_var).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Label(stars, text="to", style="Muted.TLabel").grid(
            row=0, column=1, padx=6
        )
        ttk.Entry(stars, textvariable=self.max_sr_var).grid(
            row=0, column=2, sticky="ew"
        )
        self._labeled(box, 3, "Star rating", stars)

        self._labeled(
            box,
            4,
            "Min favourites",
            ttk.Entry(box, textvariable=self.min_favs_var),
        )

        sort = ttk.Combobox(
            box,
            textvariable=self.sort_var,
            values=[SORT_LABELS[key] for key in SORTS],
            state="readonly",
        )
        self._labeled(box, 5, "Sort by", sort)

        self._labeled(
            box,
            6,
            "Max sets",
            ttk.Spinbox(
                box, textvariable=self.limit_var, from_=1, to=100000, width=10
            ),
        )

    def _download_section(self, parent) -> None:
        box = ttk.Labelframe(parent, text="Download behaviour", padding=(10, 8))
        box.pack(fill="x", pady=(0, 10))
        box.columnconfigure(0, minsize=112)
        box.columnconfigure(1, weight=1)

        self._labeled(
            box,
            0,
            "Parallel downloads",
            ttk.Spinbox(
                box, textvariable=self.workers_var, from_=1, to=32, width=10
            ),
        )
        self._labeled(
            box,
            1,
            "Batch size",
            ttk.Spinbox(
                box, textvariable=self.batch_var, from_=1, to=500, width=10
            ),
        )

    def _advanced_section(self, parent) -> None:
        box = ttk.Labelframe(parent, text="Advanced filters", padding=(10, 8))
        box.pack(fill="x", pady=(0, 10))
        box.columnconfigure(0, minsize=112)
        box.columnconfigure(1, weight=1)

        head = ttk.Frame(box)
        head.grid(row=0, column=0, columnspan=2, sticky="ew")
        head.columnconfigure(0, weight=1)
        ttk.Checkbutton(
            head,
            text="Enable advanced filters",
            variable=self.adv_var,
            command=self._sync_advanced_state,
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(head, text="Reset", command=self._reset_advanced).grid(
            row=0, column=1, sticky="e"
        )

        self.adv_frame = ttk.Frame(box)
        self.adv_frame.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        self.adv_frame.columnconfigure(0, minsize=112)
        self.adv_frame.columnconfigure(1, weight=1)
        self.adv_inputs: list[tk.Widget] = []

        for row, (key, label) in enumerate(ADVANCED_FIELDS, start=0):
            entry = ttk.Entry(self.adv_frame, textvariable=self.adv_vars[key])
            ttk.Label(self.adv_frame, text=label).grid(
                row=row * 2, column=0, sticky="w", padx=(0, 8), pady=(3, 0)
            )
            entry.grid(row=row * 2, column=1, sticky="ew", pady=(3, 0))
            self.adv_inputs.append(entry)
            hint = ADVANCED_HINTS.get(key)
            if hint:
                ttk.Label(
                    self.adv_frame, text=hint, style="Muted.TLabel"
                ).grid(row=row * 2 + 1, column=1, sticky="w")

        nsfw = ttk.Checkbutton(
            self.adv_frame,
            text="Include NSFW sets",
            variable=self.adv_vars["include_nsfw"],
        )
        nsfw.grid(
            row=len(ADVANCED_FIELDS) * 2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 0),
        )
        self.adv_inputs.append(nsfw)

    def _labeled(self, box, row: int, text: str, widget) -> None:
        ttk.Label(box, text=text).grid(
            row=row, column=0, sticky="w", padx=(0, 8), pady=3
        )
        widget.grid(row=row, column=1, sticky="ew", pady=3)

    def _build_status(self, parent) -> None:
        head = ttk.Frame(parent, style="Card.TFrame", padding=(16, 14))
        head.pack(fill="x")
        head.columnconfigure(0, weight=1)

        topline = ttk.Frame(head, style="Card.TFrame")
        topline.pack(fill="x")
        ttk.Label(topline, text="RUN STATUS", style="CardTitle.TLabel").pack(
            side="left"
        )
        self.run_state_var = tk.StringVar(value="Idle")
        self.state_chip = tk.Label(
            topline,
            textvariable=self.run_state_var,
            bg=PANEL_ALT,
            fg=MUTED,
            padx=12,
            pady=3,
            font=("Segoe UI Semibold", 9),
            borderwidth=0,
        )
        self.state_chip.pack(side="right")

        self.summary_var = tk.StringVar(
            value="Set your filters on the left, then press Start."
        )
        ttk.Label(
            head,
            textvariable=self.summary_var,
            style="CardMeta.TLabel",
            justify="left",
            wraplength=640,
        ).pack(fill="x", pady=(8, 0))

        progress = ttk.Frame(parent, style="Card.TFrame", padding=(16, 14))
        progress.pack(fill="x", pady=(10, 0))
        prow = ttk.Frame(progress, style="Card.TFrame")
        prow.pack(fill="x")
        ttk.Label(prow, text="OVERALL PROGRESS", style="CardTitle.TLabel").pack(
            side="left", pady=(4, 0)
        )
        self.overall_pct_var = tk.StringVar(value="0%")
        ttk.Label(
            prow, textvariable=self.overall_pct_var, style="CardValueAccent.TLabel"
        ).pack(side="right")
        self.overall_bar = ttk.Progressbar(
            progress, mode="determinate", maximum=100
        )
        self.overall_bar.pack(fill="x", pady=(10, 6))
        self.overall_label = ttk.Label(
            progress, text="0 / 0", style="CardMeta.TLabel", anchor="w"
        )
        self.overall_label.pack(fill="x")

        stats = ttk.Frame(parent)
        stats.pack(fill="x", pady=(10, 0))
        for column in range(6):
            stats.columnconfigure(column, weight=1, uniform="stat")
        self.stat_vars: dict[str, tk.StringVar] = {}
        stat_specs = [
            ("ok", "DOWNLOADED", "CardValueGreen.TLabel", "0"),
            ("fail", "FAILED", "CardValueRed.TLabel", "0"),
            ("active", "ACTIVE", "CardValueAccent.TLabel", "0"),
            ("mb", "DATA", "CardValue.TLabel", "0.0 MB"),
            ("rate", "SPEED", "CardValue.TLabel", "0.00 MB/s"),
            ("free", "FREE DISK", "CardValue.TLabel", "?"),
        ]
        for index, (key, title, value_style, initial) in enumerate(stat_specs):
            card = ttk.Frame(stats, style="Card.TFrame", padding=(12, 10))
            card.grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 6, 0),
            )
            var = tk.StringVar(value=initial)
            self.stat_vars[key] = var
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(card, textvariable=var, style=value_style).pack(
                anchor="w", pady=(4, 0)
            )

        transfers = ttk.Frame(parent, style="Card.TFrame", padding=(16, 12))
        transfers.pack(fill="x", pady=(10, 0))
        ttk.Label(
            transfers, text="ACTIVE DOWNLOADS", style="CardTitle.TLabel"
        ).pack(anchor="w", pady=(0, 8))
        self.transfers = ttk.Treeview(
            transfers,
            columns=("set", "pct"),
            show="headings",
            height=3,
            selectmode="none",
        )
        self.transfers.heading("set", text="Set")
        self.transfers.heading("pct", text="Progress")
        self.transfers.column("set", width=430, anchor="w")
        self.transfers.column("pct", width=200, anchor="e")
        tbar = ttk.Scrollbar(
            transfers, orient="vertical", command=self.transfers.yview
        )
        self.transfers.configure(yscrollcommand=tbar.set)
        tbar.pack(side="right", fill="y")
        self.transfers.pack(side="left", fill="x", expand=True)

        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True, pady=(10, 0))

        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="Log")
        self.log = tk.Text(
            log_tab,
            bg=PANEL,
            fg=FG,
            insertbackground=FG,
            selectbackground="#2d4a68",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            wrap="word",
            padx=12,
            pady=10,
            font=("Consolas", 9),
            state="disabled",
        )
        log_bar = ttk.Scrollbar(
            log_tab, orient="vertical", command=self.log.yview
        )
        self.log.configure(yscrollcommand=log_bar.set)
        log_bar.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        self.log.tag_configure("ok", foreground=GREEN)
        self.log.tag_configure("bad", foreground=RED)
        self.log.tag_configure("warn", foreground=YELLOW)
        self.log.tag_configure("dim", foreground=MUTED)
        self.log.tag_configure("info", foreground=ACCENT)

        failed_tab = ttk.Frame(notebook)
        notebook.add(failed_tab, text="Failed downloads")
        self.failed_tree = ttk.Treeview(
            failed_tab,
            columns=("id", "title"),
            show="headings",
            selectmode="extended",
        )
        self.failed_tree.heading("id", text="ID")
        self.failed_tree.heading("title", text="Title")
        self.failed_tree.column("id", width=90, anchor="w")
        self.failed_tree.column("title", width=520, anchor="w")
        fbar = ttk.Scrollbar(
            failed_tab, orient="vertical", command=self.failed_tree.yview
        )
        self.failed_tree.configure(yscrollcommand=fbar.set)
        buttons = ttk.Frame(failed_tab)
        buttons.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(
            buttons, text="Open osu! page", command=self._open_selected_failed
        ).pack(side="left", padx=(2, 6))
        ttk.Button(
            buttons, text="Copy links", command=self._copy_failed_links
        ).pack(side="left")
        fbar.pack(side="right", fill="y")
        self.failed_tree.pack(side="left", fill="both", expand=True)
        self.failed_tree.bind(
            "<Double-1>", lambda _event: self._open_selected_failed()
        )

    # ---- small actions --------------------------------------------------

    def _set_state(self, text: str, kind: str = "idle") -> None:
        """Update the run-state chip text and colour."""
        palette = {
            "idle": (PANEL_ALT, MUTED),
            "running": ("#1e2c44", ACCENT),
            "done": ("#202e22", GREEN),
            "stopped": ("#382f1c", YELLOW),
            "error": ("#3a2028", RED),
        }
        bg, fg = palette.get(kind, palette["idle"])
        self.run_state_var.set(text)
        self.state_chip.configure(bg=bg, fg=fg)

    def _dark_titlebar(self) -> None:
        """Ask DWM for a dark title bar on Windows 10/11."""
        try:
            from ctypes import byref, c_int, sizeof, windll

            hwnd = windll.user32.GetParent(self.winfo_id())
            enabled = c_int(1)
            for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE
                result = windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, byref(enabled), sizeof(enabled)
                )
                if result == 0:
                    break
        except Exception:
            pass

    def _wheel_safe(self, widget) -> None:
        """Keep the wheel scrolling the panel instead of editing values.

        ttk comboboxes and spinboxes edit their value on the wheel by default,
        which is easy to trigger by accident while scrolling the settings list.
        The widget-level binding runs before those class bindings, so breaking
        the event there disables the value change.
        """
        if isinstance(widget, (ttk.Combobox, ttk.Spinbox, ttk.Scale)):
            widget.bind("<MouseWheel>", self._scroll_panel)
        for child in widget.winfo_children():
            self._wheel_safe(child)

    def _scroll_panel(self, event) -> str:
        """Scroll the settings list one notch (or more for fast wheels)."""
        delta = int(event.delta)
        if delta:
            steps = (1 if delta < 0 else -1) * max(1, abs(delta) // 120)
            self.left_canvas.yview_scroll(steps, "units")
        return "break"

    def _on_wheel(self, event) -> None:
        widget = self.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if widget is self.left_canvas or widget is self.left_inner:
                self._scroll_panel(event)
                return
            widget = getattr(widget, "master", None)

    def _status_toggled(self, name: str) -> None:
        if name == "any" and self.status_vars["any"].get():
            for other in STATUS_ORDER:
                self.status_vars[other].set(False)
        elif name != "any" and self.status_vars[name].get():
            self.status_vars["any"].set(False)

    def _sync_advanced_state(self) -> None:
        enabled = bool(self.adv_var.get())
        for widget in getattr(self, "adv_inputs", []):
            widget.state(["!disabled"] if enabled else ["disabled"])

    def _reset_advanced(self) -> None:
        for key, var in self.adv_vars.items():
            if key == "include_nsfw":
                var.set(False)
            else:
                var.set(str(NEW_DEFAULTS.get(key, "")))
        self.status_var.set("Advanced filters reset.")
        runtime.log("Advanced filters reset.")

    def _browse(self) -> None:
        current = self.out_var.get().strip() or str(DEFAULT_OUT)
        chosen = filedialog.askdirectory(parent=self, initialdir=current)
        if chosen:
            self.out_var.set(chosen)

    def _open_folder(self) -> None:
        folder = Path(self.out_var.get().strip() or str(DEFAULT_OUT))
        try:
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(folder)  # type: ignore[attr-defined]
        except (OSError, AttributeError):
            webbrowser.open(folder.as_uri())

    def _show_key_guide(self) -> None:
        if messagebox.askyesno(
            "osu! API keys",
            api.GUIDE + "\nOpen your osu! account settings now?",
            parent=self,
        ):
            webbrowser.open("https://osu.ppy.sh/home/account/edit")

    def _open_selected_failed(self) -> None:
        selection = self.failed_tree.selection()
        if not selection:
            self.status_var.set("Select a failed set first.")
            return
        webbrowser.open(
            f"https://osu.ppy.sh/beatmapsets/{selection[0]}"
        )

    def _copy_failed_links(self) -> None:
        selection = set(self.failed_tree.selection())
        entries = [
            entry
            for entry in self.failed_entries
            if str(entry["id"]) in selection
        ]
        if not entries:
            entries = list(self.failed_entries)
        if not entries:
            self.status_var.set("No failed downloads to copy.")
            return
        self.clipboard_clear()
        self.clipboard_append(reports.links_text(entries))
        self.status_var.set(f"Copied links for {len(entries)} set(s).")

    # ---- run lifecycle --------------------------------------------------

    def _start(self) -> None:
        if self.running:
            return
        try:
            raw = self._collect_raw()
            cfg = config.cfg_from_raw(raw)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Check your settings", str(exc), parent=self)
            return

        cid = self.cid_var.get().strip()
        secret = self.secret_var.get().strip()
        if not cid or not secret:
            messagebox.showerror(
                "API keys needed",
                "Enter your osu! client ID and secret.\n\n" + api.GUIDE,
                parent=self,
            )
            return
        if not cid.isdigit():
            messagebox.showerror(
                "API keys needed",
                "The osu! client ID must be a number.",
                parent=self,
            )
            return

        self.saved.update(raw)
        self.saved["client_id"] = cid
        self.saved["client_secret"] = secret
        config.save_saved(self.saved)

        self.cfg = cfg
        self._clear_log()
        self._clear_failed()
        self.summary_var.set("Starting...")
        self._set_state("Running", "running")
        self.status_var.set("Signing in...")
        self.started = time.time()
        self._free_at = 0.0
        self.running = True
        self._set_running_ui(True)
        self.transfers.delete(*self.transfers.get_children())
        self.overall_bar.configure(value=0)
        self.overall_pct_var.set("0%")
        self.overall_label.configure(text="0 / 0 sets")

        self.worker = threading.Thread(
            target=self._worker, args=(cfg, cid, secret), daemon=True
        )
        self.worker.start()

    def _worker(self, cfg: dict, cid: str, secret: str) -> None:
        try:
            result = asyncio.run(
                app.run(cfg, cid, secret, self.progress, self.overall)
            )
            self.event_queue.put(("done", result))
        except SystemExit as exc:
            self.event_queue.put(("error", str(exc) or "osu! request failed."))
        except BaseException as exc:  # noqa: BLE001 - shown in the GUI
            self.event_queue.put(
                ("error", f"{type(exc).__name__}: {exc}")
            )

    def _stop(self) -> None:
        if not self.running:
            return
        runtime.request_stop()
        self.stop_btn.state(["disabled"])
        self.status_var.set("Stopping after the current files...")
        runtime.log("Stop requested; finishing in-flight files.")

    def _set_running_ui(self, running: bool) -> None:
        if running:
            self.start_btn.state(["disabled"])
            self.stop_btn.state(["!disabled"])
        else:
            self.start_btn.state(["!disabled"])
            self.stop_btn.state(["disabled"])

    def _on_done(self, result: dict) -> None:
        self.running = False
        self._set_running_ui(False)
        self._refresh_live()
        stopped = result.get("stopped")
        self._set_state("Stopped" if stopped else "Done", "stopped" if stopped else "done")

        rows = ui.search_rows(
            result["matched"], result["todo"], self.cfg or config.cfg_from_raw({})
        )
        self.summary_var.set("   ·   ".join(f"{key}: {value}" for key, value in rows))

        self.failed_entries = reports.failed_entries(
            result["failed"].keys(), result["titles"]
        )
        for entry in self.failed_entries:
            self.failed_tree.insert(
                "",
                "end",
                iid=str(entry["id"]),
                values=(entry["id"], entry["title"]),
            )

        failed_now = len(result.get("new_failed") or {})
        old_failed = len(result.get("failed") or {})
        if stopped:
            self.status_var.set(
                f"Stopped. {runtime.stats['ok']} downloaded this run; "
                "finished sets are recorded."
            )
        elif not result.get("todo"):
            self.status_var.set("Nothing new to download.")
        elif failed_now:
            self.status_var.set(
                f"Done. {runtime.stats['ok']} downloaded, {failed_now} failed. "
                "See the Failed downloads tab."
            )
        elif old_failed:
            self.status_var.set(
                f"Done. {runtime.stats['ok']} downloaded; "
                f"{old_failed} earlier failure(s) remain in the Failed tab."
            )
        else:
            self.status_var.set(
                f"Done. {runtime.stats['ok']} downloaded, nothing failed."
            )

        if result.get("mirrors_exhausted"):
            self._set_state("Paused safely", "stopped")
            self.status_var.set(
                "Stopped early: the mirrors rate-limited this IP. "
                "Re-run later; finished sets are already recorded."
            )
            runtime.log(
                "Stopped early: mirrors rate-limited this IP. Nothing was "
                "hammered; re-run later."
            )

    def _on_error(self, message: str) -> None:
        self.running = False
        self._set_running_ui(False)
        self._refresh_live()
        self._set_state("Error", "error")
        self.status_var.set("Stopped with an error; see the log.")
        runtime.log(f"Error: {message}")
        messagebox.showerror("ManiaDL", message, parent=self)

    # ---- polling --------------------------------------------------------

    def _tick(self) -> None:
        self._drain_log()
        self._drain_events()
        if self.running:
            self._refresh_live()
        self.after(120, self._tick)

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self.event_queue.get_nowait()
            except queue.Empty:
                return
            if kind == "done":
                self._on_done(payload)
            elif kind == "error":
                self._on_error(payload)

    def _drain_log(self) -> None:
        lines = []
        while True:
            try:
                lines.append(self.log_queue.get_nowait())
            except queue.Empty:
                break
        if not lines:
            return
        self.log.configure(state="normal")
        for line in lines:
            body = line.split("  ", 1)[-1]
            tag = "info"
            if " + " in f" {body} " or " via " in body:
                tag = "ok"
            elif " x " in f" {body} " or "gave up" in body or "Stopping" in body:
                tag = "bad"
            elif "!" in body or "cooling" in body or "(try " in body:
                tag = "warn"
            elif "…" in body or "already on disk" in body:
                tag = "dim"
            self.log.insert("end", line + "\n", tag)
        excess = int(self.log.index("end-1c").split(".")[0]) - 3000
        if excess > 0:
            self.log.delete("1.0", f"{excess + 1}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _refresh_live(self) -> None:
        now = time.time()
        elapsed = max(now - self.started, 1.0)

        overall = self.overall.snapshot()["tasks"]
        if overall:
            total = overall[0].get("total") or 0
            done = overall[0].get("completed") or 0
            pct = (done / total * 100) if total else 0
            self.overall_bar.configure(value=pct)
            self.overall_pct_var.set(f"{pct:.0f}%")
            self.overall_label.configure(
                text=f"{int(done)} / {int(total)} sets" if total else "searching..."
            )

        tasks = self.progress.snapshot()["tasks"]
        seen = set()
        for task in tasks:
            iid = str(task["id"])
            seen.add(iid)
            done = task["completed"]
            total = task["total"]
            if total:
                text = f"{min(100, done / total * 100):4.0f}%   {done / 1e6:,.1f} / {total / 1e6:,.1f} MB"
            else:
                text = f"{done / 1e6:,.1f} MB"
            values = (task["description"], text)
            if self.transfers.exists(iid):
                self.transfers.item(iid, values=values)
            else:
                self.transfers.insert("", "end", iid=iid, values=values)
        for iid in self.transfers.get_children():
            if iid not in seen:
                self.transfers.delete(iid)

        megabytes = runtime.stats["bytes"] / 1e6
        self.stat_vars["ok"].set(str(runtime.stats["ok"]))
        self.stat_vars["fail"].set(str(runtime.stats["fail"]))
        self.stat_vars["active"].set(str(runtime.stats["active"]))
        self.stat_vars["mb"].set(f"{megabytes:,.1f} MB")
        self.stat_vars["rate"].set(f"{megabytes / elapsed:,.2f} MB/s")
        if now - self._free_at >= 2.0 and self.cfg:
            try:
                self._free_text = f"{util.free_gb(self.cfg['out']):,.1f} GB"
            except OSError:
                self._free_text = "?"
            self._free_at = now
        self.stat_vars["free"].set(self._free_text)

        message = self.progress.snapshot()["message"]
        if message:
            self.status_var.set(message)

    # ---- log/failed helpers --------------------------------------------

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _clear_failed(self) -> None:
        self.failed_tree.delete(*self.failed_tree.get_children())
        self.failed_entries = []

    def _on_close(self) -> None:
        if self.running and not self.closing:
            if not messagebox.askyesno(
                "Quit ManiaDL",
                "A download is running. Stop it and quit?",
                parent=self,
            ):
                return
            self.closing = True
            runtime.request_stop()
            self.status_var.set("Stopping before quit...")
            self.after(200, self._close_when_idle)
            return
        runtime.set_log_listener(None)
        self.destroy()

    def _close_when_idle(self) -> None:
        if self.running:
            self.after(200, self._close_when_idle)
            return
        runtime.set_log_listener(None)
        self.destroy()


def main() -> None:
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    window = ManiaDLApp()
    window.mainloop()


__all__ = ["ManiaDLApp", "main"]
