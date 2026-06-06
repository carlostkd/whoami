#!/usr/bin/env python3

import os
import sys
import json
import time
import hashlib
import threading
import re
from datetime import datetime, timezone
from pathlib import Path
from tkinter import *
from tkinter import ttk, scrolledtext, messagebox, filedialog

from osint_profiler import (
    fetch_reddit, fetch_github, fetch_hackernews, fetch_bluesky,
    fetch_mastodon, fetch_gravatar, fetch_intelx, fetch_ahmia,
    fetch_telegram, fetch_youtube, fetch_twitter, fetch_instagram, fetch_threads,
    fetch_pixelfed, fetch_peertube, fetch_lemmy,
    fetch_devto, fetch_medium, fetch_pinterest,
    generate_ai_profile, save_json, LLM_PROVIDERS,
)

ANSI_RE = re.compile(r'\033\[[0-9;]*m')

def strip_ansi(text):
    return ANSI_RE.sub("", text)

CONFIG_DIR = Path.home() / ".osint_profiler"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_gui_config():
    defaults = {
        "llm_provider": "anthropic",
        "llm_model": "",
        "llm_key": "",
        "intelx_key": "",
        "intelx_user": "",
        "reddit_client_id": "",
        "reddit_client_secret": "",
        "mastodon_instance": "mastodon.social",
        "youtube_api_key": "",
        "twitter_bearer_token": "",
        "pixelfed_instance": "pixelfed.social",
        "peertube_instance": "peertube.tv",
        "lemmy_instance": "lemmy.world",
        "window_geometry": "",
    }
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            if isinstance(data, dict):
                defaults.update(data)
        except Exception:
            pass
    return defaults


def save_gui_config(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


class TextRedirector:
    def __init__(self, text_widget, parent=None):
        self.text = text_widget
        self.parent = parent
        self.buf = ""
        self._poll()

    def write(self, msg):
        self.buf += msg

    def _poll(self):
        if self.buf:
            self.text.configure(state="normal")
            self._write_colored(self.buf)
            if self.parent is None or self.parent.auto_scroll.get():
                self.text.see(END)
            self.text.configure(state="disabled")
            self.buf = ""
        self.text.after(50, self._poll)

    def _write_colored(self, msg):
        idx = 0
        cur_tag = None
        for m in ANSI_RE.finditer(msg):
            start, end = m.start(), m.end()
            if start > idx:
                txt = msg[idx:start]
                if cur_tag:
                    self.text.insert(END, txt, cur_tag)
                else:
                    self.text.insert(END, txt)
            code = m.group(0).lstrip("\033[").rstrip("m")
            cur_tag = ANSI_TO_TAG.get(code)
            if cur_tag == "white":
                cur_tag = None
            idx = end
        if idx < len(msg):
            txt = msg[idx:]
            if cur_tag:
                self.text.insert(END, txt, cur_tag)
            else:
                self.text.insert(END, txt)

    def flush(self):
        pass


class OSINTProfilerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("OSINT Profiler")
        self.root.minsize(1000, 750)

        cfg = load_gui_config()
        if cfg.get("window_geometry"):
            self.root.geometry(cfg["window_geometry"])

        self.running = False
        self.all_data = []
        self.intelx_data = []
        self.darkweb_data = []
        self.source_vars = {}
        self.auto_scroll = BooleanVar(value=True)

        self._build_ui()
        self._load_config_to_ui(cfg)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill=BOTH, expand=True)

        # --- PanedWindow: top (inputs) | bottom (results + output) ---
        pw = PanedWindow(main, orient=VERTICAL, sashrelief=RAISED, sashwidth=6)
        pw.pack(fill=BOTH, expand=True)

        # Top pane: Notebook
        top_frame = ttk.Frame(pw, padding=(0, 0, 0, 4))
        pw.add(top_frame)

        nb = ttk.Notebook(top_frame)
        nb.pack(fill=BOTH, expand=True)

        sources_tab = ttk.Frame(nb, padding=10)
        llm_tab = ttk.Frame(nb, padding=10)
        nb.add(sources_tab, text="Sources")
        nb.add(llm_tab, text="AI Profile")

        self._build_sources_tab(sources_tab)
        self._build_llm_tab(llm_tab)

        # Bottom pane: Output area
        bottom_frame = ttk.Frame(pw)
        pw.add(bottom_frame)
        self.root.after(100, lambda: pw.sash_place(0, 0, 380))

        # Toolbar
        btn_frame = ttk.Frame(bottom_frame)
        btn_frame.pack(fill=X, pady=(0, 4))

        self.run_btn = ttk.Button(btn_frame, text="▶ Run", command=self._run)
        self.run_btn.pack(side=LEFT, padx=1)
        ttk.Button(btn_frame, text="Clear", command=self._clear_output).pack(side=LEFT, padx=1)
        ttk.Button(btn_frame, text="Save JSON", command=self._save_results).pack(side=LEFT, padx=1)
        ttk.Button(btn_frame, text="Copy Output", command=self._copy_output).pack(side=LEFT, padx=1)

        self.autoscroll_btn = ttk.Checkbutton(
            btn_frame, text="📜 Auto-scroll", variable=self.auto_scroll,
            style="Toolbutton",
        )
        self.autoscroll_btn.pack(side=LEFT, padx=1)

        # Progress bar
        self.progress = ttk.Progressbar(btn_frame, mode="indeterminate", length=120)
        self.progress.pack(side=RIGHT, padx=(5, 0))

        # Results panel (collapsible)
        self.results_frame = ttk.LabelFrame(bottom_frame, text="Results", padding=4)
        self.results_frame.pack(fill=X, pady=(0, 4))
        self.results_panel = ttk.Frame(self.results_frame)
        self.results_panel.pack(fill=X)
        self.results_label = ttk.Label(self.results_panel, text="No results yet", foreground="#888")
        self.results_label.pack(anchor=W)

        # Output text
        out_frame = ttk.LabelFrame(bottom_frame, text="Output", padding=3)
        out_frame.pack(fill=BOTH, expand=True)

        self.output_text = scrolledtext.ScrolledText(
            out_frame, wrap=WORD, font=("Consolas", 10), height=18,
            state="disabled", bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white",
            relief=FLAT, borderwidth=0,
        )
        self.output_text.pack(fill=BOTH, expand=True)
        self._setup_output_tags()

        # Redirect stdout to output widget with color support
        self.stdout_redirect = TextRedirector(self.output_text, parent=self)

        # Status bar
        self.status_var = StringVar(value="Ready")
        status_bar = ttk.Label(
            main, textvariable=self.status_var, relief=SUNKEN, anchor=W,
            padding=(6, 2), font=("", 9),
        )
        status_bar.pack(fill=X, pady=(4, 0))

    def _setup_output_tags(self):
        t = self.output_text
        t.tag_configure("ok", foreground="#4ec94e")
        t.tag_configure("warn", foreground="#e6c84a")
        t.tag_configure("fail", foreground="#e64a4a")
        t.tag_configure("info", foreground="#888888")
        t.tag_configure("section", foreground="#56b6c2", font=("Consolas", 10, "bold"))
        t.tag_configure("white", foreground="#ffffff")

    def _build_sources_tab(self, parent):
        # Scrollable left panel
        left_canvas = Canvas(parent, highlightthickness=0, borderwidth=0)
        left_scroll = ttk.Scrollbar(parent, orient=VERTICAL, command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left = ttk.LabelFrame(left_canvas, text="Social Media", padding=10)
        left_canvas.create_window((0, 0), window=left, anchor=NW, tags="inner")
        left_canvas.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 2))
        left_scroll.pack(side=LEFT, fill=Y)

        def _configure_left(event):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"), width=left.winfo_reqwidth())
            left_canvas.itemconfigure("inner", width=left_canvas.winfo_width())
        left.bind("<Configure>", _configure_left)
        left_canvas.bind("<Configure>", lambda e: left_canvas.itemconfigure("inner", width=e.width))
        _on_mousewheel = lambda e: left_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        left_canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")

        right = ttk.Frame(parent)
        right.pack(side=LEFT, fill=BOTH, expand=True, padx=(5, 0))

        # Quick Scan bar
        scan_frame = ttk.LabelFrame(left, text="Quick Scan", padding=6)
        scan_frame.pack(fill=X, pady=(0, 8))
        scan_inner = ttk.Frame(scan_frame)
        scan_inner.pack(fill=X)
        self.source_vars["scan_query"] = StringVar()
        scan_entry = ttk.Entry(scan_inner, textvariable=self.source_vars["scan_query"],
                               font=("", 10))
        scan_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 4))
        ttk.Button(scan_inner, text="Scan All",
                   command=self._scan_all).pack(side=LEFT)
        ttk.Label(scan_frame, text="Fills all fields below with this value and runs",
                  foreground="#888", font=("", 8)).pack(anchor=W, pady=(2, 0))

        fields = [
            ("reddit", "Reddit Username"),
            ("github", "GitHub Username"),
            ("hackernews", "Hacker News Username"),
            ("bluesky", "Bluesky Handle"),
            ("mastodon", "Mastodon Username"),
            ("email", "Email (Gravatar)"),
            ("telegram", "Telegram Username"),
            ("youtube", "YouTube Handle (@channel)"),
            ("twitter", "Twitter/X Username"),
            ("pixelfed", "Pixelfed Username"),
            ("peertube", "PeerTube Username"),
            ("lemmy", "Lemmy Username"),
            ("devto", "Dev.to Username"),
            ("medium", "Medium Username"),
        ]

        for key, label in fields:
            f = ttk.Frame(left)
            f.pack(fill=X, pady=2)
            ttk.Label(f, text=label, width=22, anchor=W).pack(side=LEFT)
            var = StringVar()
            ent = ttk.Entry(f, textvariable=var)
            ent.pack(side=LEFT, fill=X, expand=True, padx=(5, 0))
            self.source_vars[key] = var

        self.source_vars["mastodon_instance"] = StringVar(value="mastodon.social")
        f_inst = ttk.Frame(left)
        f_inst.pack(fill=X, pady=2)
        ttk.Label(f_inst, text="Mastodon Instance", width=22, anchor=W).pack(side=LEFT)
        ttk.Entry(f_inst, textvariable=self.source_vars["mastodon_instance"]).pack(side=LEFT, fill=X, expand=True, padx=(5, 0))

        self.source_vars["pixelfed_instance"] = StringVar(value="pixelfed.social")
        f_pi = ttk.Frame(left)
        f_pi.pack(fill=X, pady=2)
        ttk.Label(f_pi, text="Pixelfed Instance", width=22, anchor=W).pack(side=LEFT)
        ttk.Entry(f_pi, textvariable=self.source_vars["pixelfed_instance"]).pack(side=LEFT, fill=X, expand=True, padx=(5, 0))

        self.source_vars["peertube_instance"] = StringVar(value="peertube.tv")
        f_pt = ttk.Frame(left)
        f_pt.pack(fill=X, pady=2)
        ttk.Label(f_pt, text="PeerTube Instance", width=22, anchor=W).pack(side=LEFT)
        ttk.Entry(f_pt, textvariable=self.source_vars["peertube_instance"]).pack(side=LEFT, fill=X, expand=True, padx=(5, 0))

        self.source_vars["lemmy_instance"] = StringVar(value="lemmy.world")
        f_lm = ttk.Frame(left)
        f_lm.pack(fill=X, pady=2)
        ttk.Label(f_lm, text="Lemmy Instance", width=22, anchor=W).pack(side=LEFT)
        ttk.Entry(f_lm, textvariable=self.source_vars["lemmy_instance"]).pack(side=LEFT, fill=X, expand=True, padx=(5, 0))

        # Fragile platforms
        sep = ttk.Separator(left, orient=HORIZONTAL)
        sep.pack(fill=X, pady=8)
        ttk.Label(left, text="Instagram / Threads / Pinterest (web scrape — breaks often)", font=("", 9, "italic")).pack(anchor=W)
        for key, label in (("instagram", "Instagram Username"), ("threads", "Threads Username"), ("pinterest", "Pinterest Username")):
            f = ttk.Frame(left)
            f.pack(fill=X, pady=1)
            ttk.Label(f, text=label, width=22, anchor=W).pack(side=LEFT)
            var = StringVar()
            ttk.Entry(f, textvariable=var).pack(side=LEFT, fill=X, expand=True, padx=(5, 0))
            self.source_vars[key] = var

        # API keys section
        sep2 = ttk.Separator(left, orient=HORIZONTAL)
        sep2.pack(fill=X, pady=8)
        ttk.Label(left, text="API Keys (required for some platforms)", font=("", 9, "italic")).pack(anchor=W)

        self.source_vars["reddit_client_id"] = StringVar()
        self.source_vars["reddit_client_secret"] = StringVar()
        f_r1 = ttk.Frame(left)
        f_r1.pack(fill=X, pady=1)
        ttk.Label(f_r1, text="Reddit Client ID", width=22, anchor=W).pack(side=LEFT)
        ttk.Entry(f_r1, textvariable=self.source_vars["reddit_client_id"]).pack(side=LEFT, fill=X, expand=True, padx=(5, 0))
        f_r2 = ttk.Frame(left)
        f_r2.pack(fill=X, pady=1)
        ttk.Label(f_r2, text="Reddit Client Secret", width=22, anchor=W).pack(side=LEFT)
        ttk.Entry(f_r2, textvariable=self.source_vars["reddit_client_secret"], show="*").pack(side=LEFT, fill=X, expand=True, padx=(5, 0))

        self.source_vars["youtube_api_key"] = StringVar()
        f_yt = ttk.Frame(left)
        f_yt.pack(fill=X, pady=1)
        ttk.Label(f_yt, text="YouTube API Key", width=22, anchor=W).pack(side=LEFT)
        ttk.Entry(f_yt, textvariable=self.source_vars["youtube_api_key"]).pack(side=LEFT, fill=X, expand=True, padx=(5, 0))
        ttk.Label(f_yt, text="optional", foreground="#666", font=("", 8)).pack(side=LEFT)

        self.source_vars["twitter_bearer_token"] = StringVar()
        f_tw = ttk.Frame(left)
        f_tw.pack(fill=X, pady=1)
        ttk.Label(f_tw, text="Twitter Bearer Token", width=22, anchor=W).pack(side=LEFT)
        ttk.Entry(f_tw, textvariable=self.source_vars["twitter_bearer_token"], show="*").pack(side=LEFT, fill=X, expand=True, padx=(5, 0))

        # --- Right panel: additional sources ---
        right_top = ttk.LabelFrame(right, text="Deep Web Search", padding=10)
        right_top.pack(fill=X, pady=(0, 5))

        self.source_vars["intelx_enabled"] = BooleanVar(value=False)
        cb = ttk.Checkbutton(right_top, text="IntelX", variable=self.source_vars["intelx_enabled"])
        cb.pack(anchor=W)
        ttk.Label(right_top, text="Searches leak databases, pastes, darknet", foreground="#888", font=("", 9)).pack(anchor=W, padx=(20, 0))

        self.source_vars["darkweb_enabled"] = BooleanVar(value=False)
        cb = ttk.Checkbutton(right_top, text="Dark Web (Ahmia)", variable=self.source_vars["darkweb_enabled"])
        cb.pack(anchor=W)
        ttk.Label(right_top, text="Searches .onion sites via clearnet proxy", foreground="#888", font=("", 9)).pack(anchor=W, padx=(20, 0))

        sep_dw = ttk.Separator(right_top, orient=HORIZONTAL)
        sep_dw.pack(fill=X, pady=6)
        ttk.Label(right_top, text="Query (optional — defaults to first social-media field above)", foreground="#888", font=("", 9)).pack(anchor=W)
        f_dwq = ttk.Frame(right_top)
        f_dwq.pack(fill=X, pady=(3, 0))
        self.source_vars["deepweb_query"] = StringVar()
        ttk.Entry(f_dwq, textvariable=self.source_vars["deepweb_query"]).pack(fill=X)

        # IntelX credentials
        right_mid = ttk.LabelFrame(right, text="IntelX Credentials", padding=10)
        right_mid.pack(fill=X, pady=5)

        self.source_vars["intelx_key"] = StringVar()
        self.source_vars["intelx_user"] = StringVar()
        ttk.Label(right_mid, text="API Key").pack(anchor=W)
        ttk.Entry(right_mid, textvariable=self.source_vars["intelx_key"], show="*").pack(fill=X, pady=2)
        ttk.Label(right_mid, text="User Email").pack(anchor=W)
        ttk.Entry(right_mid, textvariable=self.source_vars["intelx_user"]).pack(fill=X, pady=2)

        # Summary
        right_bot = ttk.LabelFrame(right, text="Notes", padding=10)
        right_bot.pack(fill=BOTH, expand=True, pady=5)
        ttk.Label(right_bot, text="IntelX and Dark Web searches use the\noptional query field above, or fall back\nto the first social-media field.",
                  foreground="#888", font=("", 9), justify=LEFT).pack(anchor=W)

    def _build_llm_tab(self, parent):
        f = ttk.LabelFrame(parent, text="AI Profile Generation", padding=10)
        f.pack(fill=X, pady=5)

        ttk.Label(f, text="Enable AI Profile").grid(row=0, column=0, sticky=W, pady=2)
        self.source_vars["ai_enabled"] = BooleanVar(value=True)
        ttk.Checkbutton(f, variable=self.source_vars["ai_enabled"]).grid(row=0, column=1, sticky=W, padx=5)

        ttk.Label(f, text="LLM Provider").grid(row=1, column=0, sticky=W, pady=2)
        self.source_vars["llm_provider"] = StringVar()
        providers = list(LLM_PROVIDERS.keys())
        cb = ttk.Combobox(f, textvariable=self.source_vars["llm_provider"],
                          values=providers, state="readonly", width=25)
        cb.grid(row=1, column=1, sticky=W, pady=2, padx=5)
        cb.set("anthropic")

        ttk.Label(f, text="Model (optional)").grid(row=2, column=0, sticky=W, pady=2)
        self.source_vars["llm_model"] = StringVar()
        ttk.Entry(f, textvariable=self.source_vars["llm_model"], width=30).grid(row=2, column=1, sticky=W, pady=2, padx=5)
        ttk.Label(f, text="Leave empty for default").grid(row=2, column=2, sticky=W)

        ttk.Label(f, text="API Key (or set env var)").grid(row=3, column=0, sticky=W, pady=2)
        self.source_vars["llm_key"] = StringVar()
        ttk.Entry(f, textvariable=self.source_vars["llm_key"], show="*", width=50).grid(row=3, column=1, columnspan=2, sticky=EW, pady=2, padx=5)
        ttk.Label(f, text="If blank, uses env var for this provider.",
                  foreground="#888").grid(row=4, column=1, columnspan=2, sticky=W, padx=5)
        f.columnconfigure(1, weight=1)

    def _load_config_to_ui(self, cfg):
        for key in ("llm_provider", "llm_model", "llm_key", "intelx_key", "intelx_user", "reddit_client_id", "reddit_client_secret", "mastodon_instance", "youtube_api_key", "twitter_bearer_token", "pixelfed_instance", "peertube_instance", "lemmy_instance"):
            if cfg.get(key) and key in self.source_vars:
                self.source_vars[key].set(cfg[key])

    def _get_identity(self):
        dwq = self.source_vars["deepweb_query"].get().strip()
        if dwq:
            return dwq
        for key in ("email", "reddit", "github", "hackernews", "bluesky", "mastodon",
                     "telegram", "youtube", "twitter", "instagram", "threads",
                     "pixelfed", "peertube", "lemmy", "devto", "medium", "pinterest"):
            val = self.source_vars[key].get().strip()
            if val:
                return val
        return ""

    def _run_task(self):
        self.running = True
        self.all_data = []
        self.intelx_data = []
        self.darkweb_data = []

        identity = self._get_identity()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = self.stdout_redirect
        sys.stderr = self.stdout_redirect

        try:
            from osint_profiler import banner
            banner()

            reddit_user = self.source_vars["reddit"].get().strip()
            github_user = self.source_vars["github"].get().strip()
            hn_user = self.source_vars["hackernews"].get().strip()
            bsky_handle = self.source_vars["bluesky"].get().strip()
            masto_user = self.source_vars["mastodon"].get().strip()
            email_val = self.source_vars["email"].get().strip()
            telegram_user = self.source_vars["telegram"].get().strip()
            youtube_user = self.source_vars["youtube"].get().strip()
            twitter_user = self.source_vars["twitter"].get().strip()
            instagram_user = self.source_vars["instagram"].get().strip()
            threads_user = self.source_vars["threads"].get().strip()
            pixelfed_user = self.source_vars["pixelfed"].get().strip()
            peertube_user = self.source_vars["peertube"].get().strip()
            lemmy_user = self.source_vars["lemmy"].get().strip()
            devto_user = self.source_vars["devto"].get().strip()
            medium_user = self.source_vars["medium"].get().strip()
            pinterest_user = self.source_vars["pinterest"].get().strip()

            if reddit_user:
                cid = self.source_vars["reddit_client_id"].get().strip() or None
                cs = self.source_vars["reddit_client_secret"].get().strip() or None
                if cid:
                    os.environ["REDDIT_CLIENT_ID"] = cid
                if cs:
                    os.environ["REDDIT_CLIENT_SECRET"] = cs
                d = fetch_reddit(reddit_user, client_id=cid, client_secret=cs)
                if d:
                    self.all_data.append(d)

            if github_user:
                d = fetch_github(github_user)
                if d:
                    self.all_data.append(d)

            if hn_user:
                d = fetch_hackernews(hn_user)
                if d:
                    self.all_data.append(d)

            if bsky_handle:
                d = fetch_bluesky(bsky_handle)
                if d:
                    self.all_data.append(d)

            if masto_user:
                inst = self.source_vars["mastodon_instance"].get().strip() or "mastodon.social"
                d = fetch_mastodon(masto_user, inst)
                if d:
                    self.all_data.append(d)

            if email_val:
                d = fetch_gravatar(email_val)
                if d:
                    self.all_data.append(d)

            if telegram_user:
                d = fetch_telegram(telegram_user)
                if d:
                    self.all_data.append(d)

            if youtube_user:
                yk = self.source_vars["youtube_api_key"].get().strip() or None
                d = fetch_youtube(youtube_user, api_key=yk)
                if d:
                    self.all_data.append(d)

            if twitter_user:
                bt = self.source_vars["twitter_bearer_token"].get().strip() or None
                d = fetch_twitter(twitter_user, bearer_token=bt)
                if d:
                    self.all_data.append(d)

            if instagram_user:
                d = fetch_instagram(instagram_user)
                if d:
                    self.all_data.append(d)

            if threads_user:
                d = fetch_threads(threads_user)
                if d:
                    self.all_data.append(d)

            if pixelfed_user:
                inst = self.source_vars["pixelfed_instance"].get().strip() or "pixelfed.social"
                d = fetch_pixelfed(pixelfed_user, instance=inst)
                if d:
                    self.all_data.append(d)

            if peertube_user:
                inst = self.source_vars["peertube_instance"].get().strip() or "peertube.tv"
                d = fetch_peertube(peertube_user, instance=inst)
                if d:
                    self.all_data.append(d)

            if lemmy_user:
                inst = self.source_vars["lemmy_instance"].get().strip() or "lemmy.world"
                d = fetch_lemmy(lemmy_user, instance=inst)
                if d:
                    self.all_data.append(d)

            if devto_user:
                d = fetch_devto(devto_user)
                if d:
                    self.all_data.append(d)

            if medium_user:
                d = fetch_medium(medium_user)
                if d:
                    self.all_data.append(d)

            if pinterest_user:
                d = fetch_pinterest(pinterest_user)
                if d:
                    self.all_data.append(d)

            if self.source_vars["intelx_enabled"].get() and identity:
                os.environ["INTELX_API_KEY"] = self.source_vars["intelx_key"].get().strip() or os.environ.get("INTELX_API_KEY", "")
                os.environ["INTELX_USER"] = self.source_vars["intelx_user"].get().strip() or os.environ.get("INTELX_USER", "")
                idata = fetch_intelx(identity)
                if idata:
                    self.intelx_data = idata
                    self.all_data.append({"platform": "intelx", "results": idata, "query": identity})

            if self.source_vars["darkweb_enabled"].get() and identity:
                ddata = fetch_ahmia(identity)
                if ddata:
                    self.darkweb_data = ddata
                    self.all_data.append({"platform": "darkweb", "results": ddata, "query": identity})

            if not self.all_data:
                print("\n  \033[33m\u26a0\033[0m No data collected. Check usernames exist on the selected platforms.")
            else:
                ident = identity.replace("@", "_").replace(".", "_") or "profile"
                fn = f"osint_{ident}_{int(time.time())}.json"
                with open(fn, "w", encoding="utf-8") as f:
                    json.dump(self.all_data, f, indent=2, ensure_ascii=False)
                print(f"\n  \033[90mJSON saved: {fn}\033[0m")

            if self.source_vars["ai_enabled"].get() and self.all_data:
                provider = self.source_vars["llm_provider"].get()
                model = self.source_vars["llm_model"].get().strip() or None
                key = self.source_vars["llm_key"].get().strip() or None
                if key:
                    env_var = LLM_PROVIDERS.get(provider, {}).get("env_key")
                    if env_var:
                        os.environ[env_var] = key
                generate_ai_profile(
                    self.all_data,
                    intelx_data=self.intelx_data,
                    darkweb_data=self.darkweb_data,
                    llm_provider=provider,
                    llm_model=model,
                    llm_key=key,
                )

        except Exception as e:
            print(f"\n  \033[31m\u2717\033[0m Error: {e}")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            self.root.after(0, self._on_task_done)

    def _update_results_panel(self):
        for w in self.results_panel.winfo_children():
            w.destroy()
        if not self.all_data:
            self.results_label = ttk.Label(self.results_panel, text="No results", foreground="#888")
            self.results_label.pack(anchor=W)
            return
        platforms = []
        for d in self.all_data:
            plat = d.get("platform", "?")
            name = d.get("username") or d.get("handle") or d.get("email") or d.get("display_name") or plat
            platforms.append((plat, str(name)[:25]))
        plat_counts = {}
        for p, n in platforms:
            plat_counts.setdefault(p, []).append(n)
        frames = []
        for p, names in sorted(plat_counts.items()):
            label_text = f"{p}: {', '.join(names)}"
            lbl = ttk.Label(self.results_panel, text=f"● {label_text}",
                            foreground="#56b6c2", font=("", 9))
            lbl.pack(side=LEFT, padx=4)

    def _on_task_done(self):
        self.running = False
        self.progress.stop()
        self.run_btn.configure(state="normal")
        count = len(self.all_data)
        if count:
            self.status_var.set(f"Done — {count} platform(s)")
        else:
            self.status_var.set("Done — no results")
        self._update_results_panel()

    def _scan_all(self):
        query = self.source_vars["scan_query"].get().strip()
        if not query:
            messagebox.showinfo("No Input", "Enter a username or email to scan.")
            return
        for key in ("reddit", "github", "hackernews", "bluesky", "mastodon",
                     "email", "telegram", "youtube", "twitter", "instagram", "threads",
                     "pixelfed", "peertube", "lemmy", "devto", "medium", "pinterest"):
            self.source_vars[key].set(query)
        self.status_var.set(f"Scanning '{query}' across all platforms...")
        self._run()

    def _run(self):
        if self.running:
            return
        self._clear_output()
        self.run_btn.configure(state="disabled")

        if not self._get_identity():
            messagebox.showinfo("No Input", "Enter a username or email in the Sources tab.")
            self.run_btn.configure(state="normal")
            return

        self.status_var.set("Searching...")
        self.progress.start()
        t = threading.Thread(target=self._run_task, daemon=True)
        t.start()

    def _clear_output(self):
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", END)
        self.output_text.configure(state="disabled")
        self.all_data = []
        self.intelx_data = []
        self.darkweb_data = []
        self.results_label.configure(text="No results yet")
        for w in self.results_panel.winfo_children():
            w.destroy()
        self.results_label = ttk.Label(self.results_panel, text="No results yet", foreground="#888")
        self.results_label.pack(anchor=W)

    def _copy_output(self):
        text = self.output_text.get("1.0", END).strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.status_var.set("Output copied to clipboard")
            self.root.after(2000, lambda: self.status_var.set("Ready"))

    def _save_results(self):
        if not self.all_data:
            messagebox.showinfo("No Data", "Run a profile first before saving.")
            return
        fn = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All Files", "*.*")],
            initialfile=f"osint_profile_{int(time.time())}.json",
        )
        if fn:
            combined = {
                "profiles": self.all_data,
                "intelx": self.intelx_data,
                "darkweb": self.darkweb_data,
                "exported_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(fn, "w") as f:
                json.dump(combined, f, indent=2, default=str)
            messagebox.showinfo("Saved", f"Results saved to:\n{fn}")

    def _on_close(self):
        cfg = {
            "llm_provider": self.source_vars["llm_provider"].get(),
            "llm_model": self.source_vars["llm_model"].get(),
            "llm_key": self.source_vars["llm_key"].get(),
            "intelx_key": self.source_vars["intelx_key"].get(),
            "intelx_user": self.source_vars["intelx_user"].get(),
            "reddit_client_id": self.source_vars["reddit_client_id"].get(),
            "reddit_client_secret": self.source_vars["reddit_client_secret"].get(),
            "mastodon_instance": self.source_vars["mastodon_instance"].get(),
            "youtube_api_key": self.source_vars["youtube_api_key"].get(),
            "twitter_bearer_token": self.source_vars["twitter_bearer_token"].get(),
            "pixelfed_instance": self.source_vars["pixelfed_instance"].get(),
            "peertube_instance": self.source_vars["peertube_instance"].get(),
            "lemmy_instance": self.source_vars["lemmy_instance"].get(),
            "window_geometry": self.root.geometry(),
        }
        try:
            save_gui_config(cfg)
        except Exception:
            pass
        self.root.destroy()


def main():
    root = Tk()
    style = ttk.Style()
    style.theme_use("clam")
    app = OSINTProfilerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
