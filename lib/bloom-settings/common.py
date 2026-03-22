#!/usr/bin/env python3
"""Bloom Settings — common CSS, helpers, shared widgets, TermWindow, theme data."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango
import subprocess, threading, os, sys, json, re, glob as glob_mod

# ── CSS (theme-aware) ──────────────────────────────────────────────────────────

def _c2rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(x * 2 for x in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def _load_theme_colors():
    import configparser as _cp
    p = os.path.expanduser("~/.config/bloom/colors.conf")
    cp = _cp.ConfigParser()
    if os.path.exists(p):
        try:
            cp.read(p)
        except Exception:
            pass
    def g(k, d):
        try:
            return cp.get("Colors", k).strip()
        except Exception:
            return d
    scheme = g("scheme", "dark")
    dark = scheme == "dark"
    return {
        "accent":   g("accent",   "#B01828"),
        "bg":       g("bg",       "#0D0618" if dark else "#F5F3F7"),
        "surface":  g("surface",  "#080312" if dark else "#FFFEFF"),
        "overlay":  g("overlay",  "#120920" if dark else "#EDE9F0"),
        "text":     g("text",     "#F0EEF4" if dark else "#1A1420"),
        "text_dim": g("text_dim", "#88809A" if dark else "#6B6378"),
        "scheme":   scheme,
        "font":     g("font",     "JetBrainsMono Nerd Font 11"),
    }

def _make_css(c):
    acc  = c["accent"]
    bg   = c["bg"]
    sur  = c["surface"]
    ovr  = c["overlay"]
    txt  = c["text"]
    dim  = c["text_dim"]
    dark = c.get("scheme", "dark") == "dark"
    ar, ag, ab = _c2rgb(acc)
    tr, tg, tb = _c2rgb(txt)
    # Neutral tints — white-based on dark themes, black-based on light themes
    nr, ng, nb = (255, 255, 255) if dark else (0, 0, 0)
    def A(a):  return f"rgba({ar},{ag},{ab},{a})"
    def T(a):  return f"rgba({tr},{tg},{tb},{a})"
    def N(a):  return f"rgba({nr},{ng},{nb},{a})"
    return f"""
window {{ background-color: {bg}; }}

.sidebar {{
    background-color: {sur};
    border-right: 1px solid {N(0.06)};
    min-width: 210px;
}}
.sidebar-title {{
    font-size: 18px; font-weight: 800; color: {acc};
    font-family: "JetBrainsMono Nerd Font", monospace;
    padding: 24px 18px 14px 18px;
}}
.sidebar-cat {{
    font-size: 9px; font-weight: 800; color: {T(0.25)};
    font-family: "JetBrainsMono Nerd Font", monospace;
    letter-spacing: 1.5px; padding: 12px 20px 3px 20px;
}}
.nav-btn {{
    background: transparent; border: none; border-radius: 10px;
    color: {T(0.5)}; font-size: 13px; font-weight: 600;
    font-family: "JetBrainsMono Nerd Font", monospace;
    padding: 9px 14px; margin: 1px 8px; min-height: 0;
}}
.nav-btn:hover  {{ background: {A(0.15)}; color: {txt}; }}
.nav-btn.active {{ background: {A(0.25)}; color: {txt}; }}
.nav-btn label  {{ color: inherit; }}

.page-title {{
    font-size: 20px; font-weight: 800; color: {txt};
    font-family: "JetBrainsMono Nerd Font", monospace;
}}
.page-sub {{ font-size: 12px; color: {dim}; margin-bottom: 20px; }}
.section-head {{
    font-size: 10px; font-weight: 800; color: {T(0.3)};
    font-family: "JetBrainsMono Nerd Font", monospace;
    letter-spacing: 1.5px; margin-top: 18px; margin-bottom: 6px;
}}
.card {{
    background: {N(0.035)};
    border: 1px solid {N(0.08)};
    border-radius: 14px; padding: 14px 16px; margin-bottom: 8px;
}}
.card-name {{
    font-size: 14px; font-weight: 700; color: {txt};
    font-family: "JetBrainsMono Nerd Font", monospace;
}}
.card-pkg  {{ font-size: 11px; color: {dim}; margin-top: 1px; }}
.card-desc {{ font-size: 12px; color: {dim}; margin-top: 2px; }}

.badge {{
    background: {A(0.22)}; border-radius: 5px; color: {acc};
    font-size: 10px; font-weight: 800; padding: 2px 7px;
    font-family: "JetBrainsMono Nerd Font", monospace;
}}
.badge.ok   {{ background: rgba(163,190,140,0.18); color: #A3BE8C; }}
.badge.warn {{ background: rgba(235,203,139,0.15); color: #EBCF8B; }}

.act-btn {{
    background: {A(0.18)}; border: 1px solid {A(0.4)};
    border-radius: 8px; color: {txt};
    font-size: 12px; font-weight: 600; padding: 6px 14px; min-height: 0;
}}
.act-btn:hover       {{ background: {A(0.38)}; }}
.act-btn label       {{ color: {txt}; }}
.act-btn.rm          {{ background: rgba(191,97,106,0.12); border-color: rgba(191,97,106,0.3); }}
.act-btn.rm:hover    {{ background: rgba(191,97,106,0.28); }}
.act-btn.primary     {{ background: {A(0.35)}; border-color: {A(0.7)}; }}
.act-btn.primary:hover {{ background: {A(0.55)}; }}
.act-btn.ok          {{ background: rgba(163,190,140,0.15); border-color: rgba(163,190,140,0.35); color: #A3BE8C; }}
.act-btn.ok:hover    {{ background: rgba(163,190,140,0.28); }}

.info-key {{
    font-size: 12px; color: {dim};
    font-family: "JetBrainsMono Nerd Font", monospace; min-width: 160px;
}}
.info-val {{ font-size: 12px; color: {txt}; font-weight: 600; }}
.info-row {{ padding: 9px 0; border-bottom: 1px solid {N(0.05)}; }}
.loading  {{ font-size: 13px; color: {dim}; padding: 32px; }}

.search-entry {{
    background: {N(0.05)}; border: 1px solid {N(0.10)};
    border-radius: 10px; color: {txt}; font-size: 13px;
    padding: 6px 12px; margin-bottom: 12px;
}}
.search-entry:focus {{ border-color: {A(0.5)}; }}

.input-field {{
    background: {N(0.05)}; border: 1px solid {N(0.12)};
    border-radius: 8px; color: {txt}; font-size: 13px; padding: 6px 10px;
}}
.input-field:focus {{ border-color: {A(0.5)}; }}

.term-view {{
    background: {ovr}; color: {T(0.85)};
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-size: 12px; padding: 10px; border-radius: 8px;
}}
.term-title {{
    font-size: 14px; font-weight: 700; color: {txt};
    font-family: "JetBrainsMono Nerd Font", monospace; margin-bottom: 8px;
}}
.update-item {{ font-size: 12px; color: {txt}; font-family: "JetBrainsMono Nerd Font", monospace; }}
.update-ver  {{ font-size: 11px; color: {dim}; font-family: "JetBrainsMono Nerd Font", monospace; }}

scale trough    {{ background: {N(0.10)}; border-radius: 4px; min-height: 6px; }}
scale highlight {{ background: {acc}; border-radius: 4px; }}
scale slider    {{ background: {txt}; border-radius: 50%; min-width: 16px; min-height: 16px; }}

.wallpaper-box {{
    border-radius: 10px; overflow: hidden;
    border: 2px solid {N(0.12)}; min-width: 160px; min-height: 90px;
}}

.sig-strong {{ color: #A3BE8C; }}
.sig-medium {{ color: #EBCF8B; }}
.sig-weak   {{ color: #BF616A; }}
.net-active  {{ color: #A3BE8C; font-weight: 800; }}

.action-bar {{
    background: {sur};
    border-top: 1px solid {A(0.35)};
    padding: 12px 24px;
}}
.action-bar-info {{ font-size: 12px; color: {T(0.5)}; }}
"""

CSS = _make_css(_load_theme_colors())

# Global CSS provider — reloaded when theme changes
_CSS_PROVIDER = None

def _reload_app_css():
    """Rebuild CSS from current colors.conf and reload the global provider."""
    global CSS, _CSS_PROVIDER
    CSS = _make_css(_load_theme_colors())
    if _CSS_PROVIDER is not None:
        try:
            _CSS_PROVIDER.load_from_string(CSS)
        except AttributeError:
            _CSS_PROVIDER.load_from_data(CSS.encode())

# ── Data ──────────────────────────────────────────────────────────────────────

KERNELS = [
    ("linux",          "Linux",           "Latest mainline kernel"),
    ("linux-lts",      "Linux LTS",       "Long-term support, ultra stable"),
    ("linux-zen",      "Linux Zen",       "Optimized for desktop & gaming"),
    ("linux-hardened", "Linux Hardened",  "Security-hardened kernel"),
    ("linux-rt",       "Linux RT",        "Real-time kernel for audio/pro use"),
    ("linux-rt-lts",   "Linux RT LTS",    "Real-time + LTS"),
]

GPU_PACKAGES = {
    "nvidia": [
        ("nvidia-dkms",        "Proprietary driver — works with all kernels incl. linux-zen (recommended)"),
        ("nvidia-open-dkms",   "Open-source kernel module (Turing+ / RTX 20xx+), DKMS variant"),
        ("xf86-video-nouveau", "Nouveau — open-source, no reclocking"),
    ],
    "amd": [
        ("mesa",               "Mesa — open-source, always recommended"),
        ("vulkan-radeon",      "Vulkan support for AMD GPUs"),
        ("libva-mesa-driver",  "VA-API hardware video acceleration"),
        ("xf86-video-amdgpu",  "X.Org AMDGPU driver"),
    ],
    "intel": [
        ("mesa",               "Mesa — open-source, always recommended"),
        ("vulkan-intel",       "Intel Vulkan (ANV) support"),
        ("intel-media-driver", "Intel VA-API / QuickSync (Broadwell+)"),
        ("xf86-video-intel",   "X.Org Intel driver (legacy, usually not needed)"),
    ],
}

MIME_APPS = [
    ("Web Browser",     "x-scheme-handler/http"),
    ("File Manager",    "inode/directory"),
    ("Image Viewer",    "image/jpeg"),
    ("Video Player",    "video/mp4"),
    ("Music Player",    "audio/mpeg"),
    ("Text Editor",     "text/plain"),
    ("PDF Viewer",      "application/pdf"),
    ("Email Client",    "x-scheme-handler/mailto"),
    ("Archive Manager", "application/zip"),
    ("Terminal",        "application/x-terminal-emulator"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def sh(cmd, **kw):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, **kw).stdout.strip()
    except Exception:
        return ""

def installed(pkg):
    return subprocess.run(["pacman", "-Q", pkg], capture_output=True).returncode == 0

def running_kernel():
    return sh(["uname", "-r"])

def detect_gpu():
    out = sh(["lspci"])
    for line in out.splitlines():
        ll = line.upper()
        if any(x in ll for x in ["VGA", "DISPLAY", "3D", "GPU"]):
            if "NVIDIA" in ll:
                return "nvidia", line.strip()
            if "AMD" in ll or "RADEON" in ll or "ADVANCED MICRO" in ll:
                return "amd", line.strip()
            if "INTEL" in ll:
                return "intel", line.strip()
    return None, "No GPU detected"

def is_running_kernel(pkg, kver):
    v = kver.lower()
    if pkg == "linux":
        return not any(x in v for x in ["lts", "zen", "hardened", "rt"])
    return pkg.replace("linux-", "") in v

def pkg_version(pkg, query_installed=True):
    """Return installed or latest-available version string, or None."""
    flag = "-Qi" if query_installed else "-Si"
    out = sh(["pacman", flag, pkg])
    for line in out.splitlines():
        if line.lower().startswith("version"):
            return line.split(":", 1)[1].strip()
    return None

def fetch_ala_versions(pkg):
    """Fetch available versions from the Arch Linux Archive.
    Returns list of (version_str, url) sorted newest-first."""
    import urllib.request, re
    arch = sh(["uname", "-m"]) or "x86_64"
    url  = f"https://archive.archlinux.org/packages/{pkg[0]}/{pkg}/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "bloom-settings/1.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read().decode(errors="replace")
        pat = rf'href="({re.escape(pkg)}-[^"]+?-{re.escape(arch)}\.pkg\.tar\.(?:zst|xz))"'
        names = re.findall(pat, html)
        results = []
        for name in names:
            # strip  pkg-  prefix and  -{arch}.pkg.tar.{ext}  suffix
            ver = re.sub(rf'^{re.escape(pkg)}-', '', name)
            ver = re.sub(rf'-{re.escape(arch)}\.pkg\.tar\.[^.]+$', '', ver)
            file_url = url + name
            results.append((ver, file_url))
        # deduplicate and sort newest first (lexicographic is fine for pkgver)
        seen = set()
        out  = []
        for v, u in reversed(results):
            if v not in seen:
                seen.add(v)
                out.append((v, u))
        return out
    except Exception:
        return []

def list_gtk_themes():
    themes = set()
    for base in ["/usr/share/themes", os.path.expanduser("~/.local/share/themes")]:
        if os.path.isdir(base):
            for d in os.listdir(base):
                p = os.path.join(base, d)
                if os.path.isdir(p) and (
                    os.path.isdir(os.path.join(p, "gtk-4.0")) or
                    os.path.isdir(os.path.join(p, "gtk-3.0"))
                ):
                    themes.add(d)
    return sorted(themes)

def list_icon_themes():
    themes = set()
    skip = {"hicolor", "default", "locolor", "gnome"}
    for base in ["/usr/share/icons", os.path.expanduser("~/.local/share/icons")]:
        if os.path.isdir(base):
            for d in os.listdir(base):
                if d.lower() in skip:
                    continue
                p = os.path.join(base, d)
                if os.path.isdir(p) and os.path.exists(os.path.join(p, "index.theme")):
                    themes.add(d)
    return sorted(themes)

def list_cursor_themes():
    themes = set()
    for base in ["/usr/share/icons", os.path.expanduser("~/.local/share/icons")]:
        if os.path.isdir(base):
            for d in os.listdir(base):
                p = os.path.join(base, d)
                if os.path.isdir(p) and os.path.isdir(os.path.join(p, "cursors")):
                    themes.add(d)
    return sorted(themes)

def gsettings_get(schema, key, fallback=""):
    val = sh(["gsettings", "get", schema, key])
    return val.strip("'\"") if val else fallback

def get_volume(sink="@DEFAULT_SINK@"):
    out = sh(["pactl", "get-sink-volume", sink])
    m = re.search(r"(\d+)%", out)
    return int(m.group(1)) if m else 50

def get_mute(sink="@DEFAULT_SINK@"):
    out = sh(["pactl", "get-sink-mute", sink])
    return "yes" in out.lower()

def get_mic_volume():
    out = sh(["pactl", "get-source-volume", "@DEFAULT_SOURCE@"])
    m = re.search(r"(\d+)%", out)
    return int(m.group(1)) if m else 50

def get_default_app(mime):
    return sh(["xdg-mime", "query", "default", mime])

def desktop_name(desktop_id):
    if not desktop_id:
        return "None"
    for d in ["/usr/share/applications", os.path.expanduser("~/.local/share/applications")]:
        p = os.path.join(d, desktop_id)
        if os.path.exists(p):
            for line in open(p, errors="ignore"):
                if line.startswith("Name="):
                    return line[5:].strip()
    return desktop_id.replace(".desktop", "")

def apps_for_mime(mime):
    """Return [(name, desktop_id)] for apps that claim to handle mime."""
    result = []
    seen = set()
    base_mime = mime.split("/")[0]
    dirs = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications")]
    for d in dirs:
        for path in glob_mod.glob(os.path.join(d, "*.desktop")):
            try:
                content = open(path, errors="ignore").read()
                in_mime = False
                name = ""
                for line in content.splitlines():
                    if line.startswith("Name=") and not name:
                        name = line[5:].strip()
                    if line.startswith("MimeType="):
                        mimes = line[9:].split(";")
                        if mime in mimes or f"{base_mime}/*" in mimes or "*" in mimes:
                            in_mime = True
                if in_mime and name:
                    did = os.path.basename(path)
                    if did not in seen:
                        seen.add(did)
                        result.append((name, did))
            except Exception:
                pass
    return sorted(result)

def read_hypridle_timeouts(path):
    """Return [timeout_secs, ...] from hypridle.conf listener blocks."""
    timeouts = []
    try:
        for line in open(path):
            m = re.match(r"\s*timeout\s*=\s*(\d+)", line)
            if m:
                timeouts.append(int(m.group(1)))
    except Exception:
        pass
    return timeouts

def write_hypridle_timeout(path, index, new_val):
    """Replace the n-th timeout value in hypridle.conf."""
    try:
        lines = open(path).readlines()
        count = 0
        for i, line in enumerate(lines):
            if re.match(r"\s*timeout\s*=\s*\d+", line):
                if count == index:
                    lines[i] = re.sub(r"(\s*timeout\s*=\s*)\d+", rf"\g<1>{new_val}", line)
                count += 1
        open(path, "w").writelines(lines)
    except Exception:
        pass

def get_sink_inputs():
    """Return list of {index, name, volume} for active audio sink inputs."""
    raw = sh(["pactl", "list", "sink-inputs"])
    inputs = []
    cur = {}
    for line in raw.splitlines():
        m = re.match(r"^Sink Input #(\d+)", line)
        if m:
            if cur.get("index") is not None:
                inputs.append(cur)
            cur = {"index": int(m.group(1)), "name": "Unknown", "volume": 100}
        elif "application.name" in line:
            m2 = re.search(r'application\.name = "([^"]+)"', line)
            if m2:
                cur["name"] = m2.group(1)
        elif line.strip().startswith("Volume:") and "%" in line:
            m2 = re.search(r"(\d+)%", line)
            if m2:
                cur["volume"] = int(m2.group(1))
    if cur.get("index") is not None:
        inputs.append(cur)
    return inputs

# ── Shared widgets ────────────────────────────────────────────────────────────

def make_header(title, sub):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    t = Gtk.Label(label=title); t.add_css_class("page-title"); t.set_xalign(0)
    s = Gtk.Label(label=sub);   s.add_css_class("page-sub");   s.set_xalign(0)
    box.append(t); box.append(s)
    return box

def make_section(label):
    l = Gtk.Label(label=label)
    l.add_css_class("section-head")
    l.set_xalign(0)
    return l

def spinner_row(text="Loading…"):
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    box.add_css_class("loading")
    box.set_halign(Gtk.Align.CENTER)
    sp = Gtk.Spinner(); sp.start(); box.append(sp)
    box.append(Gtk.Label(label=text))
    return box

def clear_box(box):
    while (c := box.get_first_child()):
        box.remove(c)

def text_entry(placeholder="", password=False, css="input-field"):
    if password:
        e = Gtk.PasswordEntry()
        e.set_show_peek_icon(True)
        if placeholder:
            e.set_property("placeholder-text", placeholder)
    else:
        e = Gtk.Entry()
        if placeholder:
            e.set_placeholder_text(placeholder)
    e.add_css_class(css)
    return e

# ── Progress terminal window ──────────────────────────────────────────────────

class TermWindow(Gtk.Window):
    def __init__(self, parent, title, cmd, on_done=None):
        super().__init__()
        self.set_title(title)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(620, 400)
        self._on_done = on_done

        provider = Gtk.CssProvider()
        try:
            provider.load_from_string(CSS)
        except AttributeError:
            provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.set_margin_top(16); root.set_margin_bottom(16)
        root.set_margin_start(16); root.set_margin_end(16)

        lbl = Gtk.Label(label=title)
        lbl.add_css_class("term-title"); lbl.set_xalign(0)
        root.append(lbl)

        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._buf = Gtk.TextBuffer()
        self._tv  = Gtk.TextView(buffer=self._buf)
        self._tv.add_css_class("term-view")
        self._tv.set_editable(False); self._tv.set_cursor_visible(False)
        self._tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        sw.set_child(self._tv)
        root.append(sw)

        self._close_btn = Gtk.Button(label="Close")
        self._close_btn.add_css_class("act-btn")
        self._close_btn.set_sensitive(False)
        self._close_btn.set_margin_top(12)
        self._close_btn.set_halign(Gtk.Align.END)
        self._close_btn.connect("clicked", lambda _: self.close())
        root.append(self._close_btn)

        self.set_child(root)
        self.present()
        threading.Thread(target=self._run, args=(cmd,), daemon=True).start()

    def _append(self, text):
        self._buf.insert(self._buf.get_end_iter(), text)
        adj = self._tv.get_vadjustment()
        adj.set_value(adj.get_upper())
        return False

    def _run(self, cmd):
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in proc.stdout:
                GLib.idle_add(self._append, line)
            proc.wait()
            rc = proc.returncode
            GLib.idle_add(self._append, f"\n{'✓ Done.' if rc == 0 else f'✗ Exited with code {rc}.'}\n")
        except Exception as e:
            GLib.idle_add(self._append, f"\nError: {e}\n")
        GLib.idle_add(self._finish)

    def _finish(self):
        self._close_btn.set_sensitive(True)
        if self._on_done:
            self._on_done()
        return False


# ── Theme presets ─────────────────────────────────────────────────────────────

# Full theme presets — each has dark and light palette
THEME_PRESETS = {
    "Bloom":      {
        "dark":  {"accent": "#B01828", "bg": "#0D0618", "surface": "#080312", "overlay": "#120920", "text": "#F0EEF4", "text_dim": "#88809A"},
        "light": {"accent": "#B01828", "bg": "#F5F0F2", "surface": "#FDF8F9", "overlay": "#F0E8EB", "text": "#1A0A0C", "text_dim": "#6B5358"},
    },
    "Ocean":      {
        "dark":  {"accent": "#1E6FBF", "bg": "#060E18", "surface": "#030A12", "overlay": "#0A1525", "text": "#E8F0F8", "text_dim": "#7090A8"},
        "light": {"accent": "#1E6FBF", "bg": "#F0F4F8", "surface": "#F8FAFC", "overlay": "#E5EDF5", "text": "#0A1520", "text_dim": "#506070"},
    },
    "Forest":     {
        "dark":  {"accent": "#2D7A3E", "bg": "#060E08", "surface": "#030A05", "overlay": "#0A1510", "text": "#E8F2EA", "text_dim": "#70906A"},
        "light": {"accent": "#2D7A3E", "bg": "#F2F6F0", "surface": "#FAFCF8", "overlay": "#E8F0E5", "text": "#0A1A0C", "text_dim": "#506845"},
    },
    "Sunset":     {
        "dark":  {"accent": "#C2651A", "bg": "#130A04", "surface": "#0D0602", "overlay": "#1E1008", "text": "#F5EDE4", "text_dim": "#9A8070"},
        "light": {"accent": "#C2651A", "bg": "#FAF3EC", "surface": "#FDFAF5", "overlay": "#F5EAD8", "text": "#1E0E06", "text_dim": "#7A6050"},
    },
    "Amethyst":   {
        "dark":  {"accent": "#7B44C2", "bg": "#0A0615", "surface": "#070310", "overlay": "#100A20", "text": "#F0ECF8", "text_dim": "#8878A8"},
        "light": {"accent": "#7B44C2", "bg": "#F3F0FA", "surface": "#FAF8FE", "overlay": "#EBE5F8", "text": "#14083A", "text_dim": "#625888"},
    },
    "Rose":       {
        "dark":  {"accent": "#C2447B", "bg": "#130610", "surface": "#0D040A", "overlay": "#1E0A18", "text": "#F5ECF3", "text_dim": "#9A7090"},
        "light": {"accent": "#C2447B", "bg": "#FAF0F5", "surface": "#FDF8FB", "overlay": "#F5E5EF", "text": "#1E0614", "text_dim": "#7A5068"},
    },
    "Nord":       {
        "dark":  {"accent": "#81A1C1", "bg": "#0F1117", "surface": "#0A0D12", "overlay": "#161B22", "text": "#ECEFF4", "text_dim": "#8898A8"},
        "light": {"accent": "#5E81AC", "bg": "#ECEFF4", "surface": "#F8F9FC", "overlay": "#E5EAF0", "text": "#2E3440", "text_dim": "#5A6470"},
    },
    "Dracula":    {
        "dark":  {"accent": "#BD93F9", "bg": "#0D0D14", "surface": "#080810", "overlay": "#14141F", "text": "#F8F8F2", "text_dim": "#8880A8"},
        "light": {"accent": "#7C6FCF", "bg": "#F5F4FC", "surface": "#FDFCFE", "overlay": "#EAE8F5", "text": "#1A1830", "text_dim": "#6A6090"},
    },
    "Catppuccin": {
        "dark":  {"accent": "#CBA6F7", "bg": "#0C0C1A", "surface": "#060610", "overlay": "#131322", "text": "#CDD6F4", "text_dim": "#8892A0"},
        "light": {"accent": "#8839EF", "bg": "#EFF1F5", "surface": "#FAFAFA", "overlay": "#E6E9EF", "text": "#4C4F69", "text_dim": "#7C7F93"},
    },
    "Gruvbox":    {
        "dark":  {"accent": "#D79921", "bg": "#111008", "surface": "#0D0C05", "overlay": "#1A1810", "text": "#EBDBB2", "text_dim": "#A89870"},
        "light": {"accent": "#B57614", "bg": "#FBF1C7", "surface": "#F9F5D7", "overlay": "#EBDBB2", "text": "#3C3836", "text_dim": "#7C6840"},
    },
}

BLOOM_COLORS_CONF = os.path.expanduser("~/.config/bloom/colors.conf")


def read_bloom_colors():
    """Read current bloom color config (full palette)."""
    import configparser as _cp
    cp = _cp.ConfigParser()
    if os.path.exists(BLOOM_COLORS_CONF):
        try:
            cp.read(BLOOM_COLORS_CONF)
        except Exception:
            pass
    def g(k, d):
        try: return cp.get("Colors", k).strip()
        except: return d
    scheme = g("scheme", "dark")
    dark = scheme == "dark"
    return {
        "accent":   g("accent",   "#B01828"),
        "bg":       g("bg",       "#0D0618" if dark else "#F5F3F7"),
        "surface":  g("surface",  "#080312" if dark else "#FFFEFF"),
        "overlay":  g("overlay",  "#120920" if dark else "#EDE9F0"),
        "text":     g("text",     "#F0EEF4" if dark else "#1A1420"),
        "text_dim": g("text_dim", "#88809A" if dark else "#6B6378"),
        "scheme":   scheme,
        "font":     g("font",     ""),
        "preset":   g("preset",   "Bloom"),
    }


def _write_gtk_ini_all(gtk=None, icon=None, cursor=None, font=None, scheme=None):
    """Write GTK 3 + 4 settings.ini with provided overrides (None = skip)."""
    import configparser as _cp
    for path in [
        os.path.expanduser("~/.config/gtk-3.0/settings.ini"),
        os.path.expanduser("~/.config/gtk-4.0/settings.ini"),
    ]:
        cp = _cp.RawConfigParser()
        cp.optionxform = str
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            try: cp.read(path)
            except: pass
        if not cp.has_section("Settings"):
            cp.add_section("Settings")
        if gtk    is not None: cp.set("Settings", "gtk-theme-name",       gtk)
        if icon   is not None: cp.set("Settings", "gtk-icon-theme-name",  icon)
        if cursor is not None:
            cp.set("Settings", "gtk-cursor-theme-name", cursor)
            cp.set("Settings", "gtk-cursor-theme-size", "24")
        if font   is not None: cp.set("Settings", "gtk-font-name",        font)
        if scheme is not None:
            prefer_dark = "1" if scheme == "dark" else "0"
            cp.set("Settings", "gtk-application-prefer-dark-theme", prefer_dark)
        with open(path, "w") as f:
            cp.write(f, space_around_delimiters=False)


def _write_cursor_default(theme):
    """Write ~/.icons/default/index.theme so X11 apps pick up the cursor."""
    path = os.path.expanduser("~/.icons/default/index.theme")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(f"[Icon Theme]\nName=Default\nComment=Default Cursor Theme\nInherits={theme}\n")
