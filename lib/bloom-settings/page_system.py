#!/usr/bin/env python3
"""Bloom Settings — System pages: Kernels, Drivers, Locale, Power, Notifications, Updates, About."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango
import subprocess, threading, os, re, glob as glob_mod

from common import (
    make_header, make_section, spinner_row, clear_box, text_entry,
    TermWindow, sh, installed, CSS,
    KERNELS, GPU_PACKAGES,
    running_kernel, is_running_kernel, pkg_version, fetch_ala_versions,
    detect_gpu, read_hypridle_timeouts, write_hypridle_timeout,
)


# ── Power page helpers ────────────────────────────────────────────────────────

def _sysfs_brightness():
    """Return (current_pct, sysfs_dir) or (-1, None) if no backlight."""
    for d in glob_mod.glob("/sys/class/backlight/*/"):
        try:
            cur = int(open(d + "brightness").read().strip())
            mx  = int(open(d + "max_brightness").read().strip())
            return max(0, min(100, cur * 100 // max(mx, 1))), d
        except Exception:
            pass
    try:
        out = sh(["brightnessctl", "-m"])
        if out:
            parts = out.split(",")
            if len(parts) >= 5:
                return int(parts[4].rstrip("%")), None
    except Exception:
        pass
    return -1, None


def _apply_brightness(pct, sysfs_dir):
    pct = max(5, min(100, pct))
    if sysfs_dir:
        try:
            mx  = int(open(sysfs_dir + "max_brightness").read().strip())
            val = mx * pct // 100
            try:
                open(sysfs_dir + "brightness", "w").write(str(val))
                return
            except PermissionError:
                subprocess.Popen(["pkexec", "bash", "-c",
                                  f"echo {val} > {sysfs_dir}brightness"])
                return
        except Exception:
            pass
    subprocess.Popen(["brightnessctl", "set", f"{pct}%"])


# ── Drivers page helpers ──────────────────────────────────────────────────────

def _gpu_vram():
    """Return VRAM string or empty string."""
    try:
        out = sh(["nvidia-smi","--query-gpu=memory.total","--format=csv,noheader,nounits"])
        if out:
            mb = int(out.strip().split()[0])
            return f"{mb // 1024} GB" if mb >= 1024 else f"{mb} MB"
    except Exception:
        pass
    for path in glob_mod.glob("/sys/class/drm/card*/device/mem_info_vram_total"):
        try:
            b = int(open(path).read().strip())
            return f"{b // (1024**3)} GB" if b >= 1024**3 else f"{b // (1024**2)} MB"
        except Exception:
            pass
    return ""

def _pkg_ver_installed(pkg):
    """Return installed version string or '' if not installed."""
    out = sh(["pacman", "-Qi", pkg])
    for line in out.splitlines():
        if line.lower().startswith("version"):
            return line.split(":", 1)[1].strip()
    return ""

def _cpu_microcode():
    """Return (vendor, ucode_pkg) for the running CPU."""
    vendor = sh(["grep", "-m1", "vendor_id", "/proc/cpuinfo"])
    if "AMD" in vendor:
        return "AMD", "amd-ucode"
    if "Intel" in vendor:
        return "Intel", "intel-ucode"
    return "Unknown", ""

def _firmware_pkgs():
    """Return list of (pkg, desc) firmware recommendations."""
    pkgs = [("linux-firmware", "Generic firmware — WiFi, Bluetooth, storage controllers")]
    vendor, ucode = _cpu_microcode()
    if ucode:
        pkgs.append((ucode, f"{vendor} CPU microcode updates (security + stability)"))
    return pkgs


# ── Kernel version chooser dialog ─────────────────────────────────────────────

class KernelVersionDialog(Gtk.Window):
    """Fetches ALA version list and lets the user install a specific release."""
    PAGE_SIZE = 20

    def __init__(self, parent, pkg, on_install):
        super().__init__()
        self.set_title(f"Choose version — {pkg}")
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(540, 520)
        self.set_decorated(False)
        self._pkg        = pkg
        self._on_install = on_install
        self._all        = []   # full list (newest first)
        self._filtered   = []   # after search
        self._page       = 0

        provider = Gtk.CssProvider()
        try:
            provider.load_from_string(CSS)
        except AttributeError:
            provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.add_css_class("card")

        # Header
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hdr.set_margin_top(16); hdr.set_margin_bottom(6)
        hdr.set_margin_start(20); hdr.set_margin_end(14)
        title = Gtk.Label(label=f"Version history — {pkg}")
        title.add_css_class("card-name"); title.set_hexpand(True); title.set_xalign(0)
        hdr.append(title)
        close = Gtk.Button(label="✕"); close.add_css_class("close-btn")
        close.connect("clicked", lambda _: self.close())
        hdr.append(close)
        outer.append(hdr)

        note = Gtk.Label(label="From the Arch Linux Archive — newest releases first")
        note.add_css_class("card-desc"); note.set_xalign(0)
        note.set_margin_start(20); note.set_margin_bottom(8)
        outer.append(note)

        # Search
        self._search = Gtk.SearchEntry()
        self._search.set_placeholder_text("Search versions…")
        self._search.set_margin_start(12); self._search.set_margin_end(12)
        self._search.set_margin_bottom(8)
        self._search.connect("search-changed", self._on_search)
        outer.append(self._search)

        # List
        self._list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._list_box.set_margin_start(12); self._list_box.set_margin_end(12)
        spinner = Gtk.Spinner(); spinner.set_spinning(True)
        spinner.set_margin_top(40); spinner.set_margin_bottom(40)
        spinner.set_halign(Gtk.Align.CENTER)
        self._list_box.append(spinner)

        sw = Gtk.ScrolledWindow(); sw.set_vexpand(True)
        sw.set_child(self._list_box)
        outer.append(sw)

        # Pagination bar
        pager = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        pager.set_margin_top(8); pager.set_margin_bottom(12)
        pager.set_margin_start(12); pager.set_margin_end(12)
        pager.set_halign(Gtk.Align.CENTER)
        self._prev_btn = Gtk.Button(label="← Prev"); self._prev_btn.add_css_class("act-btn")
        self._prev_btn.connect("clicked", lambda _: self._change_page(-1))
        self._next_btn = Gtk.Button(label="Next →"); self._next_btn.add_css_class("act-btn")
        self._next_btn.connect("clicked", lambda _: self._change_page(1))
        self._page_lbl = Gtk.Label(label=""); self._page_lbl.set_hexpand(True)
        self._page_lbl.add_css_class("card-desc")
        pager.append(self._prev_btn); pager.append(self._page_lbl); pager.append(self._next_btn)
        outer.append(pager)

        self.set_child(outer)
        self.present()
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        versions = fetch_ala_versions(self._pkg)
        GLib.idle_add(self._populate_all, versions)

    def _populate_all(self, versions):
        self._all = versions  # already newest-first from fetch_ala_versions
        self._filtered = list(self._all)
        self._page = 0
        self._render()
        return False

    def _on_search(self, entry):
        q = entry.get_text().lower().strip()
        self._filtered = [(v, u) for v, u in self._all if q in v.lower()] if q else list(self._all)
        self._page = 0
        self._render()

    def _change_page(self, delta):
        max_page = max(0, (len(self._filtered) - 1) // self.PAGE_SIZE)
        self._page = max(0, min(self._page + delta, max_page))
        self._render()

    def _render(self):
        clear_box(self._list_box)
        total = len(self._filtered)
        if total == 0:
            lbl = Gtk.Label(label="No versions match — try a different search term.")
            lbl.add_css_class("card-desc")
            lbl.set_margin_top(30); lbl.set_halign(Gtk.Align.CENTER)
            self._list_box.append(lbl)
            self._prev_btn.set_sensitive(False); self._next_btn.set_sensitive(False)
            self._page_lbl.set_label("")
            return

        inst_ver  = pkg_version(self._pkg, query_installed=True)
        start     = self._page * self.PAGE_SIZE
        page_vers = self._filtered[start: start + self.PAGE_SIZE]
        max_page  = max(0, (total - 1) // self.PAGE_SIZE)

        for ver, url in page_vers:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.add_css_class("card"); row.set_margin_bottom(4)
            left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); left.set_hexpand(True)
            top  = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            vl   = Gtk.Label(label=ver); vl.add_css_class("card-name"); vl.set_xalign(0)
            top.append(vl)
            if inst_ver and ver == inst_ver:
                b = Gtk.Label(label="INSTALLED"); b.add_css_class("badge"); b.add_css_class("ok")
                top.append(b)
            left.append(top)
            ul = Gtk.Label(label=url); ul.add_css_class("card-pkg"); ul.set_xalign(0)
            ul.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            left.append(ul); row.append(left)
            btn = Gtk.Button(label="Install"); btn.add_css_class("act-btn")
            btn.set_valign(Gtk.Align.CENTER)
            btn.connect("clicked", lambda _, v=ver, u=url: self._install(v, u))
            row.append(btn)
            self._list_box.append(row)

        self._prev_btn.set_sensitive(self._page > 0)
        self._next_btn.set_sensitive(self._page < max_page)
        p1 = start + 1; p2 = min(start + self.PAGE_SIZE, total)
        self._page_lbl.set_label(f"{p1}–{p2} of {total}")

    def _install(self, ver, url):
        self.close()
        self._on_install(ver, url)


# ── Kernels Page ──────────────────────────────────────────────────────────────

class KernelsPage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Kernels", "Install or remove kernels. Reboot to switch."))
        self._lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._lst.append(spinner_row())
        self.append(self._lst)
        self._load()

    def _load(self):
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        kv   = running_kernel()
        rows = []
        for p, n, d in KERNELS:
            inst     = installed(p)
            run      = is_running_kernel(p, kv)
            inst_ver = pkg_version(p, query_installed=True) if inst else None
            avail_ver= pkg_version(p, query_installed=False)
            rows.append((p, n, d, inst, run, inst_ver, avail_ver))
        GLib.idle_add(self._populate, rows)

    def _populate(self, rows):
        clear_box(self._lst)
        for p, n, d, inst, run, iv, av in rows:
            self._lst.append(self._row(p, n, d, inst, run, iv, av))
        return False

    def _row(self, pkg, name, desc, inst, run, inst_ver, avail_ver):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card.add_css_class("card")

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        left.set_hexpand(True)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        nl  = Gtk.Label(label=name); nl.add_css_class("card-name"); nl.set_xalign(0)
        top.append(nl)
        if run:
            b = Gtk.Label(label="RUNNING"); b.add_css_class("badge"); b.add_css_class("ok")
            top.append(b)
        elif inst:
            b = Gtk.Label(label="INSTALLED"); b.add_css_class("badge")
            top.append(b)
        left.append(top)

        left.append(Gtk.Label(label=pkg,  css_classes=["card-pkg"],  xalign=0))
        left.append(Gtk.Label(label=desc, css_classes=["card-desc"], xalign=0))

        ver_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        ver_row.set_margin_top(4)
        if inst_ver:
            iv_lbl = Gtk.Label(label=f"Installed: {inst_ver}")
            iv_lbl.add_css_class("card-desc"); ver_row.append(iv_lbl)
        if avail_ver:
            color = "ok" if (inst_ver and avail_ver == inst_ver) else "warn"
            prefix = "Up to date" if (inst_ver and avail_ver == inst_ver) else "Latest"
            av_lbl = Gtk.Label(label=f"{prefix}: {avail_ver}")
            av_lbl.add_css_class("card-desc")
            if color == "warn" and inst_ver:
                av_lbl.set_markup(
                    f'<span color="#e0c060">Update available: {avail_ver}</span>')
            ver_row.append(av_lbl)
        left.append(ver_row)
        card.append(left)

        btn_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        btn_col.set_valign(Gtk.Align.CENTER)

        if run:
            lbl = Gtk.Label(label="Active"); lbl.add_css_class("badge"); lbl.add_css_class("ok")
            btn_col.append(lbl)
        elif inst:
            rm = Gtk.Button(label="Remove"); rm.add_css_class("act-btn"); rm.add_css_class("rm")
            rm.connect("clicked", lambda _, p=pkg: self._action("remove", p))
            btn_col.append(rm)
        else:
            ins = Gtk.Button(label="Install"); ins.add_css_class("act-btn")
            ins.connect("clicked", lambda _, p=pkg: self._action("install", p))
            btn_col.append(ins)

        ver_btn = Gtk.Button(label="Version…")
        ver_btn.add_css_class("act-btn")
        ver_btn.connect("clicked", lambda _, p=pkg: self._open_version_picker(p))
        btn_col.append(ver_btn)

        card.append(btn_col)
        return card

    def _open_version_picker(self, pkg):
        def on_install(ver, url):
            title = f"Installing {pkg} {ver}"
            dest  = f"/tmp/{pkg}-{ver}-x86_64.pkg.tar.zst"
            cmd   = ["bash", "-c",
                     f"curl -fL --retry 3 '{url}' -o '{dest}' && "
                     f"pkexec pacman -U --noconfirm '{dest}'"]
            TermWindow(self._win, title, cmd, on_done=self._load)
        KernelVersionDialog(self._win, pkg, on_install)

    def _action(self, action, pkg):
        headers = f"{pkg}-headers"
        if action == "install":
            cmd   = ["pkexec", "pacman", "-S", "--noconfirm", pkg, headers]
            title = f"Installing {pkg}"
        else:
            cmd   = ["pkexec", "pacman", "-Rns", "--noconfirm", pkg, headers]
            title = f"Removing {pkg}"
        TermWindow(self._win, title, cmd, on_done=self._load)


# ── Drivers Page ──────────────────────────────────────────────────────────────

class DriversPage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Drivers", "Detected hardware and recommended drivers."))
        self._lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._lst.append(spinner_row("Detecting hardware…"))
        self.append(self._lst)
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        gpu_type, gpu_desc = detect_gpu()
        vram   = _gpu_vram()
        fw     = _firmware_pkgs()
        GLib.idle_add(self._populate, gpu_type, gpu_desc, vram, fw)

    def _populate(self, gpu_type, gpu_desc, vram, fw_pkgs):
        clear_box(self._lst)

        self._lst.append(make_section("GRAPHICS"))

        hw_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        hw_box.set_margin_bottom(10)
        hw_lbl = Gtk.Label(label=f"  {gpu_desc}"); hw_lbl.add_css_class("card-desc")
        hw_lbl.set_xalign(0); hw_lbl.set_hexpand(True)
        hw_box.append(hw_lbl)
        if vram:
            vram_lbl = Gtk.Label(label=f"VRAM: {vram}")
            vram_lbl.add_css_class("badge"); hw_box.append(vram_lbl)
        self._lst.append(hw_box)

        pkgs = GPU_PACKAGES.get(gpu_type, [])
        if not pkgs:
            self._lst.append(Gtk.Label(
                label="No specific driver needed for detected hardware — mesa is sufficient.",
                css_classes=["card-desc"], xalign=0))
        else:
            for pkg, desc in pkgs:
                self._lst.append(self._row(pkg, desc))

        self._lst.append(make_section("AUDIO"))
        for pkg, desc in [
            ("pipewire",       "PipeWire — modern audio/video server"),
            ("pipewire-pulse", "PulseAudio compatibility layer"),
            ("wireplumber",    "PipeWire session manager"),
            ("pipewire-jack",  "JACK compatibility for pro audio"),
        ]:
            self._lst.append(self._row(pkg, desc))

        self._lst.append(make_section("FIRMWARE"))
        for pkg, desc in fw_pkgs:
            self._lst.append(self._row(pkg, desc))

        self._lst.append(make_section("ACCESSIBILITY"))
        for pkg, desc in [
            ("orca",          "Orca screen reader — start with Super+Alt+S"),
            ("at-spi2-core",  "Assistive Technology Service Provider Interface"),
            ("brltty",        "Braille display support"),
        ]:
            self._lst.append(self._row(pkg, desc))

        return False

    def _row(self, pkg, desc):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card.add_css_class("card")
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); left.set_hexpand(True)
        inst = installed(pkg)
        ver  = _pkg_ver_installed(pkg) if inst else ""
        top  = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        top.append(Gtk.Label(label=pkg, css_classes=["card-name"], xalign=0))
        if inst:
            b = Gtk.Label(label="INSTALLED"); b.add_css_class("badge"); b.add_css_class("ok")
            top.append(b)
        left.append(top)
        sub_text = desc + (f"  •  {ver}" if ver else "")
        left.append(Gtk.Label(label=sub_text, css_classes=["card-desc"], xalign=0))
        card.append(left)
        if inst:
            btn = Gtk.Button(label="Remove"); btn.add_css_class("act-btn"); btn.add_css_class("rm")
            btn.connect("clicked", lambda _, p=pkg: self._action("remove", p))
        else:
            btn = Gtk.Button(label="Install"); btn.add_css_class("act-btn")
            btn.connect("clicked", lambda _, p=pkg: self._action("install", p))
        btn.set_valign(Gtk.Align.CENTER); card.append(btn)
        return card

    def _action(self, action, pkg):
        if action == "install":
            cmd = ["pkexec", "pacman", "-S", "--noconfirm", pkg]; title = f"Installing {pkg}"
        else:
            cmd = ["pkexec", "pacman", "-Rns", "--noconfirm", pkg]; title = f"Removing {pkg}"
        TermWindow(self._win, title, cmd,
                   on_done=lambda: threading.Thread(target=self._do_load, daemon=True).start())


# ── Locale Page ───────────────────────────────────────────────────────────────

class LocalePage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Locale & Time", "Timezone, language and keyboard layout."))
        self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._root.append(spinner_row("Reading locale settings…"))
        self.append(self._root)
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        tz     = sh(["timedatectl", "show", "-p", "Timezone", "--value"]) or "UTC"
        locale = sh(["localectl", "status"])
        kb_line = ""
        for line in locale.splitlines():
            if "X11 Layout" in line or "VC Keymap" in line:
                kb_line = line.strip(); break
        lang   = os.environ.get("LANG", "en_US.UTF-8")
        all_tz = sh(["timedatectl", "list-timezones"]).splitlines()
        GLib.idle_add(self._populate, tz, lang, kb_line, all_tz)

    def _populate(self, tz, lang, kb_line, all_tz):
        clear_box(self._root)

        self._root.append(make_section("TIMEZONE"))
        tz_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        tz_card.add_css_class("card")
        ti = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); ti.set_hexpand(True)
        ti.append(Gtk.Label(label="Current timezone", css_classes=["card-name"], xalign=0))
        self._tz_val = Gtk.Label(label=tz); self._tz_val.add_css_class("card-desc"); self._tz_val.set_xalign(0)
        ti.append(self._tz_val)
        tz_card.append(ti)
        tz_btn = Gtk.Button(label="Change"); tz_btn.add_css_class("act-btn")
        tz_btn.set_valign(Gtk.Align.CENTER)
        tz_btn.connect("clicked", lambda _, a=all_tz, cur=tz: self._show_tz_picker(a, cur))
        tz_card.append(tz_btn)
        self._root.append(tz_card)

        self._root.append(make_section("LANGUAGE"))
        lang_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        lang_card.add_css_class("card")
        li = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); li.set_hexpand(True)
        li.append(Gtk.Label(label="System locale", css_classes=["card-name"], xalign=0))
        li.append(Gtk.Label(label=lang, css_classes=["card-desc"], xalign=0))
        lang_card.append(li)
        self._root.append(lang_card)

        self._root.append(make_section("KEYBOARD"))
        kb_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        kb_card.add_css_class("card")
        ki = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); ki.set_hexpand(True)
        ki.append(Gtk.Label(label="Keyboard layout", css_classes=["card-name"], xalign=0))
        ki.append(Gtk.Label(label=kb_line or "—", css_classes=["card-desc"], xalign=0))
        kb_card.append(ki)
        layouts = ["us", "gb", "de", "fr", "es", "it", "pl", "ru", "pt", "nl",
                   "se", "no", "fi", "dk", "cz", "hu", "ro", "tr", "jp", "cn"]
        kb_model = Gtk.StringList.new(layouts)
        kb_combo = Gtk.DropDown(); kb_combo.set_model(kb_model); kb_combo.set_valign(Gtk.Align.CENTER)
        kb_apply = Gtk.Button(label="Apply"); kb_apply.add_css_class("act-btn"); kb_apply.set_valign(Gtk.Align.CENTER)
        kb_apply.connect("clicked", lambda _, c=kb_combo, ls=layouts: self._set_keyboard(ls[c.get_selected()]))
        kb_row = Gtk.Box(spacing=8); kb_row.append(kb_combo); kb_row.append(kb_apply)
        kb_card.append(kb_row)
        self._root.append(kb_card)

        self._root.append(make_section("CLOCK"))
        ntp_on = "yes" in sh(["timedatectl", "show", "-p", "NTP", "--value"]).lower()
        ntp_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        ntp_card.add_css_class("card")
        ni = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); ni.set_hexpand(True)
        ni.append(Gtk.Label(label="Network Time (NTP)", css_classes=["card-name"], xalign=0))
        ni.append(Gtk.Label(label="Enabled" if ntp_on else "Disabled", css_classes=["card-desc"], xalign=0))
        ntp_card.append(ni)
        sw = Gtk.Switch(); sw.set_active(ntp_on); sw.set_valign(Gtk.Align.CENTER)
        sw.connect("notify::active", lambda s, _: self._set_ntp(s.get_active()))
        ntp_card.append(sw)
        self._root.append(ntp_card)
        return False

    def _show_tz_picker(self, all_tz, current):
        dlg = Gtk.Window(title="Choose Timezone")
        dlg.set_transient_for(self._win); dlg.set_modal(True); dlg.set_default_size(400, 540)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.set_margin_top(16); root.set_margin_bottom(16)
        root.set_margin_start(16); root.set_margin_end(16)
        search = Gtk.SearchEntry(); search.add_css_class("search-entry")
        search.set_placeholder_text("Search timezone…"); root.append(search)
        model = Gtk.StringList.new(all_tz)
        filter_model = Gtk.FilterListModel.new(model, None)
        sf = Gtk.CustomFilter.new(None, None, None)
        filter_model.set_filter(sf)
        def do_filter(e):
            q = e.get_text().lower()
            sf.set_filter_func((lambda item: q in item.get_string().lower()) if q else None)
        search.connect("search-changed", do_filter)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", lambda _, item: item.set_child(Gtk.Label(xalign=0)))
        def bind(_, item):
            lbl = item.get_child(); lbl.set_text(item.get_item().get_string())
            lbl.set_margin_top(5); lbl.set_margin_bottom(5); lbl.set_margin_start(8)
            lbl.add_css_class("update-item")
        factory.connect("bind", bind)
        sel = Gtk.SingleSelection.new(filter_model)
        lv = Gtk.ListView(model=sel, factory=factory); lv.set_vexpand(True)
        sw = Gtk.ScrolledWindow(); sw.set_child(lv); sw.set_vexpand(True); root.append(sw)
        btn_row = Gtk.Box(spacing=8); btn_row.set_margin_top(12); btn_row.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel"); cancel.add_css_class("act-btn")
        cancel.connect("clicked", lambda _: dlg.close())
        ok = Gtk.Button(label="Apply"); ok.add_css_class("act-btn"); ok.add_css_class("primary")
        def apply_tz(_):
            item = filter_model.get_item(sel.get_selected())
            if item:
                new_tz = item.get_string(); dlg.close()
                TermWindow(self._win, f"Setting timezone to {new_tz}",
                           ["pkexec", "timedatectl", "set-timezone", new_tz],
                           on_done=lambda: self._tz_val.set_text(new_tz))
        ok.connect("clicked", apply_tz)
        btn_row.append(cancel); btn_row.append(ok); root.append(btn_row)
        dlg.set_child(root); dlg.present()

    def _set_keyboard(self, layout):
        TermWindow(self._win, f"Setting keyboard layout: {layout}",
                   ["pkexec", "localectl", "set-keymap", layout])

    def _set_ntp(self, enable):
        subprocess.Popen(["pkexec", "timedatectl", "set-ntp", "true" if enable else "false"])


# ── Power Page ────────────────────────────────────────────────────────────────

class PowerPage(Gtk.Box):
    IDLE_CONF = os.path.expanduser("~/.config/hypr/hypridle.conf")

    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Power", "Brightness, screen timeout, sleep and power profiles."))
        self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._root.append(spinner_row())
        self.append(self._root)
        self._bright_tid = None
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        timeouts = read_hypridle_timeouts(self.IDLE_CONF)
        while len(timeouts) < 3:
            timeouts.append(0)
        profile = sh(["powerprofilesctl", "get"]) if installed("power-profiles-daemon") else ""
        profiles = sh(["powerprofilesctl", "list"]).splitlines() if profile else []
        profile_list = [l.strip().lstrip("*").strip() for l in profiles
                        if l.strip() and not l.startswith(" ")]
        bright_pct, bright_dev = _sysfs_brightness()
        GLib.idle_add(self._populate, timeouts, profile, profile_list, bright_pct, bright_dev)

    def _populate(self, timeouts, profile, profile_list, bright_pct, bright_dev):
        clear_box(self._root)

        if bright_pct >= 0:
            self._root.append(make_section("BRIGHTNESS"))
            b_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            b_card.add_css_class("card")
            b_icon = Gtk.Label(label="󰃟"); b_icon.add_css_class("info-key")
            b_card.append(b_icon)
            b_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 5, 100, 1)
            b_slider.set_value(bright_pct); b_slider.set_hexpand(True)
            b_slider.set_draw_value(True)
            b_slider.set_format_value_func(lambda _, v: f"{int(v)}%")
            b_slider.connect("value-changed",
                             lambda s, d=bright_dev: self._on_bright(int(s.get_value()), d))
            b_card.append(b_slider)
            self._root.append(b_card)

        self._root.append(make_section("IDLE SETTINGS"))
        labels = ["Dim screen after (seconds)", "Lock screen after (seconds)", "Screen off after (seconds)"]
        self._spins = []
        for i, (lbl, val) in enumerate(zip(labels, timeouts)):
            card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            card.add_css_class("card")
            cl = Gtk.Label(label=lbl); cl.add_css_class("card-name")
            cl.set_hexpand(True); cl.set_xalign(0); card.append(cl)
            spin = Gtk.SpinButton.new_with_range(0, 7200, 30)
            spin.set_value(val); spin.set_valign(Gtk.Align.CENTER)
            self._spins.append(spin); card.append(spin)
            apply_btn = Gtk.Button(label="Apply"); apply_btn.add_css_class("act-btn")
            apply_btn.set_valign(Gtk.Align.CENTER)
            apply_btn.connect("clicked", lambda _, idx=i, s=spin:
                              self._apply_timeout(idx, int(s.get_value())))
            card.append(apply_btn)
            self._root.append(card)

        if profile_list:
            self._root.append(make_section("POWER PROFILE"))
            card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            card.add_css_class("card")
            pl = Gtk.Label(label="Active profile"); pl.add_css_class("card-name")
            pl.set_hexpand(True); pl.set_xalign(0); card.append(pl)
            model = Gtk.StringList.new(profile_list)
            combo = Gtk.DropDown(model=model); combo.set_valign(Gtk.Align.CENTER)
            if profile in profile_list:
                combo.set_selected(profile_list.index(profile))
            apply_btn = Gtk.Button(label="Apply"); apply_btn.add_css_class("act-btn")
            apply_btn.set_valign(Gtk.Align.CENTER)
            apply_btn.connect("clicked", lambda _, c=combo, pl=profile_list:
                              subprocess.Popen(["powerprofilesctl", "set", pl[c.get_selected()]]))
            card.append(combo); card.append(apply_btn)
            self._root.append(card)

        self._root.append(make_section("ACTIONS"))
        suspend_btn = Gtk.Button(label="Suspend Now"); suspend_btn.add_css_class("act-btn")
        suspend_btn.connect("clicked", lambda _: subprocess.Popen(["systemctl", "suspend"]))
        lock_btn = Gtk.Button(label="Lock Screen"); lock_btn.add_css_class("act-btn")
        lock_btn.connect("clicked", lambda _: subprocess.Popen(["hyprlock"]))
        btn_row = Gtk.Box(spacing=8)
        btn_row.append(suspend_btn); btn_row.append(lock_btn)
        self._root.append(btn_row)
        return False

    def _on_bright(self, pct, sysfs_dir):
        if self._bright_tid:
            GLib.source_remove(self._bright_tid)
        self._bright_tid = GLib.timeout_add(
            80, lambda: (_apply_brightness(pct, sysfs_dir), False)[-1])

    def _apply_timeout(self, index, value):
        write_hypridle_timeout(self.IDLE_CONF, index, value)
        subprocess.Popen(["pkill", "hypridle"])
        subprocess.Popen(["hypridle"])


# ── Notifications Page ────────────────────────────────────────────────────────

class NotificationsPage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Notifications", "Do-not-disturb and notification control."))
        self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.append(self._root)
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        dnd = "true" in sh(["swaync-client", "--get-dnd"]).lower()
        count = sh(["swaync-client", "--count"])
        GLib.idle_add(self._populate, dnd, count)

    def _populate(self, dnd, count):
        clear_box(self._root)

        self._root.append(make_section("DO NOT DISTURB"))
        dnd_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        dnd_card.add_css_class("card")
        dl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); dl.set_hexpand(True)
        dl.append(Gtk.Label(label="Do Not Disturb", css_classes=["card-name"], xalign=0))
        dl.append(Gtk.Label(label="Silence all notifications", css_classes=["card-desc"], xalign=0))
        dnd_card.append(dl)
        dnd_sw = Gtk.Switch(); dnd_sw.set_active(dnd); dnd_sw.set_valign(Gtk.Align.CENTER)
        dnd_sw.connect("notify::active", lambda s, _: subprocess.Popen(
            ["swaync-client", "--dnd-on" if s.get_active() else "--dnd-off"]))
        dnd_card.append(dnd_sw)
        self._root.append(dnd_card)

        self._root.append(make_section("NOTIFICATION CENTER"))
        nc_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        nc_card.add_css_class("card")
        nl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); nl.set_hexpand(True)
        nl.append(Gtk.Label(label="Notification History", css_classes=["card-name"], xalign=0))
        try:
            c = int(count)
            nl.append(Gtk.Label(label=f"{c} notification{'s' if c != 1 else ''} stored",
                                css_classes=["card-desc"], xalign=0))
        except Exception:
            pass
        nc_card.append(nl)
        open_btn = Gtk.Button(label="Open Panel"); open_btn.add_css_class("act-btn")
        open_btn.set_valign(Gtk.Align.CENTER)
        open_btn.connect("clicked", lambda _: subprocess.Popen(["swaync-client", "-t"]))
        nc_card.append(open_btn)
        clear_btn = Gtk.Button(label="Clear All"); clear_btn.add_css_class("act-btn"); clear_btn.add_css_class("rm")
        clear_btn.set_valign(Gtk.Align.CENTER)
        clear_btn.connect("clicked", lambda _: (
            subprocess.Popen(["swaync-client", "-C"]),
            threading.Thread(target=self._do_load, daemon=True).start()
        ))
        nc_card.append(clear_btn)
        self._root.append(nc_card)
        return False


# ── Updates Page ──────────────────────────────────────────────────────────────

class UpdatesPage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Updates", "Check for and apply system updates."))
        self._lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.append(self._lst)
        self._pending = []
        self._build_controls()

    def _build_controls(self):
        btn_row = Gtk.Box(spacing=12); btn_row.set_margin_bottom(16)
        self._check_btn = Gtk.Button(label="󰑐  Check for Updates")
        self._check_btn.add_css_class("act-btn")
        self._check_btn.connect("clicked", lambda _: self._check())
        btn_row.append(self._check_btn)
        self._update_btn = Gtk.Button(label="  Update All")
        self._update_btn.add_css_class("act-btn"); self._update_btn.add_css_class("primary")
        self._update_btn.set_sensitive(False)
        self._update_btn.connect("clicked", lambda _: self._update_all())
        btn_row.append(self._update_btn)
        self._lst.append(btn_row)
        self._status = Gtk.Label(label="Press 'Check for Updates' to scan.")
        self._status.add_css_class("card-desc"); self._status.set_xalign(0); self._status.set_wrap(True)
        self._lst.append(self._status)
        self._pkg_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._lst.append(self._pkg_list)

    def _check(self):
        self._check_btn.set_sensitive(False); self._update_btn.set_sensitive(False)
        self._status.set_text("Syncing databases…"); clear_box(self._pkg_list)
        threading.Thread(target=self._do_check, daemon=True).start()

    def _do_check(self):
        subprocess.run(["pkexec", "pacman", "-Sy"], capture_output=True)
        out = sh(["pacman", "-Qu"])
        GLib.idle_add(self._show_updates, out)

    def _show_updates(self, raw):
        clear_box(self._pkg_list)
        lines = [l for l in raw.splitlines() if l.strip()]
        if not lines:
            self._status.set_text("✓ System is up to date.")
            self._check_btn.set_sensitive(True); return False
        self._status.set_text(f"{len(lines)} update{'s' if len(lines) != 1 else ''} available")
        self._pending = lines
        for line in lines:
            parts = line.split()
            pkg = parts[0] if parts else line
            ver = " → ".join(parts[1:]) if len(parts) > 1 else ""
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("card")
            left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); left.set_hexpand(True)
            left.append(Gtk.Label(label=pkg, css_classes=["update-item"], xalign=0))
            if ver:
                left.append(Gtk.Label(label=ver, css_classes=["update-ver"], xalign=0))
            row.append(left); self._pkg_list.append(row)
        self._update_btn.set_sensitive(True); self._check_btn.set_sensitive(True)
        return False

    def _update_all(self):
        TermWindow(self._win, "System Update", ["pkexec", "pacman", "-Su", "--noconfirm"],
                   on_done=self._check)


# ── About Page ────────────────────────────────────────────────────────────────

class AboutPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("About", "System information."))
        gpu_type, gpu_desc = detect_gpu()
        rows = [
            ("OS",           "Bloom Linux"),
            ("Kernel",       sh(["uname", "-r"])),
            ("Architecture", sh(["uname", "-m"])),
            ("Hostname",     sh(["hostname"])),
            ("Desktop",      "Hyprland (Wayland)"),
            ("Shell",        os.environ.get("SHELL", "—")),
            ("CPU",          self._cpu()),
            ("GPU",          gpu_desc),
            ("Memory",       self._mem()),
            ("Disk",         self._disk()),
            ("Uptime",       sh(["uptime", "-p"])),
        ]
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("card")
        for key, val in rows:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.add_css_class("info-row")
            k = Gtk.Label(label=key); k.add_css_class("info-key"); k.set_xalign(0)
            v = Gtk.Label(label=val or "—"); v.add_css_class("info-val")
            v.set_xalign(0); v.set_hexpand(True); v.set_wrap(True)
            row.append(k); row.append(v); card.append(row)
        self.append(card)

    def _cpu(self):
        try:
            for line in open("/proc/cpuinfo"):
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return "—"

    def _mem(self):
        try:
            total = avail = 0
            for line in open("/proc/meminfo"):
                if line.startswith("MemTotal"):
                    total = int(line.split()[1])
                elif line.startswith("MemAvailable"):
                    avail = int(line.split()[1])
            return f"{(total-avail)/1048576:.1f} GB used / {total/1048576:.1f} GB total"
        except Exception:
            return "—"

    def _disk(self):
        try:
            lines = sh(["df", "-h", "/"]).splitlines()
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    return f"{parts[2]} used / {parts[1]} total ({parts[4]} full)"
        except Exception:
            pass
        return "—"
