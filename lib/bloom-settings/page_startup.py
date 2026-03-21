#!/usr/bin/env python3
"""Bloom Settings — Startup & Session, Privacy & Security pages."""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib
import subprocess, threading, os, glob as glob_mod

from common import make_header, make_section, spinner_row, clear_box, text_entry, sh, gsettings_get


# ── Startup & Session Page ────────────────────────────────────────────────────

class StartupSessionPage(Gtk.Box):
    AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")

    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Startup & Session", "Apps that launch automatically on login."))
        self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.append(self._root)
        self._load()

    def _load(self):
        clear_box(self._root)
        self._root.append(spinner_row("Reading autostart entries…"))
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        entries = []
        os.makedirs(self.AUTOSTART_DIR, exist_ok=True)
        for path in sorted(glob_mod.glob(os.path.join(self.AUTOSTART_DIR, "*.desktop"))):
            name = os.path.basename(path).replace(".desktop", "")
            exec_cmd = ""
            comment = ""
            hidden = False
            try:
                for line in open(path, errors="ignore"):
                    line = line.strip()
                    if line.startswith("Name="):
                        name = line[5:].strip() or name
                    elif line.startswith("Exec="):
                        exec_cmd = line[5:].strip()
                    elif line.startswith("Comment="):
                        comment = line[8:].strip()
                    elif line.lower() == "hidden=true":
                        hidden = True
            except Exception:
                pass
            if not hidden:
                entries.append({"path": path, "name": name,
                                "exec": exec_cmd, "comment": comment})
        GLib.idle_add(self._populate, entries)

    def _populate(self, entries):
        clear_box(self._root)

        add_btn = Gtk.Button(label="  Add Autostart Entry")
        add_btn.add_css_class("act-btn"); add_btn.add_css_class("primary")
        add_btn.set_halign(Gtk.Align.START); add_btn.set_margin_bottom(16)
        add_btn.connect("clicked", lambda _: self._add_dialog())
        self._root.append(add_btn)

        if not entries:
            lbl = Gtk.Label(label="No autostart entries found.")
            lbl.add_css_class("card-desc"); lbl.set_xalign(0)
            self._root.append(lbl)
            return False

        self._root.append(make_section("AUTOSTART APPLICATIONS"))
        for entry in entries:
            self._root.append(self._entry_card(entry))
        return False

    def _entry_card(self, entry):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card.add_css_class("card")
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); info.set_hexpand(True)
        info.append(Gtk.Label(label=entry["name"], css_classes=["card-name"], xalign=0))
        if entry["exec"]:
            info.append(Gtk.Label(label=entry["exec"], css_classes=["card-pkg"], xalign=0))
        if entry["comment"]:
            info.append(Gtk.Label(label=entry["comment"], css_classes=["card-desc"], xalign=0))
        card.append(info)
        rm_btn = Gtk.Button(label="Remove"); rm_btn.add_css_class("act-btn"); rm_btn.add_css_class("rm")
        rm_btn.set_valign(Gtk.Align.CENTER)
        rm_btn.connect("clicked", lambda _, p=entry["path"]: self._remove_entry(p))
        card.append(rm_btn)
        return card

    def _add_dialog(self):
        dlg = Gtk.Window(title="Add Autostart Entry")
        dlg.set_transient_for(self._win); dlg.set_modal(True); dlg.set_default_size(380, 260)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(24); root.set_margin_bottom(24)
        root.set_margin_start(24); root.set_margin_end(24)
        root.append(Gtk.Label(label="Add Autostart Entry", css_classes=["page-title"], xalign=0))
        name_e = text_entry("Application name"); root.append(name_e)
        exec_e = text_entry("Command to run (e.g. /usr/bin/nm-applet)"); root.append(exec_e)
        btn_row = Gtk.Box(spacing=8); btn_row.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel"); cancel.add_css_class("act-btn")
        cancel.connect("clicked", lambda _: dlg.close())
        ok = Gtk.Button(label="Add"); ok.add_css_class("act-btn"); ok.add_css_class("primary")
        def do_add(_):
            name = name_e.get_text().strip()
            cmd  = exec_e.get_text().strip()
            if not name or not cmd:
                return
            dlg.close()
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
            path = os.path.join(self.AUTOSTART_DIR, f"{safe_name}.desktop")
            with open(path, "w") as f:
                f.write(f"[Desktop Entry]\nType=Application\nName={name}\nExec={cmd}\n"
                        f"X-GNOME-Autostart-enabled=true\n")
            self._load()
        ok.connect("clicked", do_add)
        btn_row.append(cancel); btn_row.append(ok)
        root.append(btn_row)
        dlg.set_child(root); dlg.present()

    def _remove_entry(self, path):
        try:
            os.remove(path)
        except Exception:
            pass
        self._load()


# ── Privacy & Security Page ───────────────────────────────────────────────────

class PrivacySecurityPage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Privacy & Security", "Location, file history, and screen lock settings."))
        self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._root.append(spinner_row("Reading privacy settings…"))
        self.append(self._root)
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        recent    = gsettings_get("org.gnome.desktop.privacy", "remember-recent-files",  "true")
        recent_age= gsettings_get("org.gnome.desktop.privacy", "recent-files-max-age",   "30")
        send_stats= gsettings_get("org.gnome.desktop.privacy", "send-software-usage-stats", "false")
        lock_delay= gsettings_get("org.gnome.desktop.screensaver", "lock-delay",          "0")
        lock_susp = gsettings_get("org.gnome.desktop.screensaver", "lock-enabled",        "true")
        GLib.idle_add(self._populate, recent, recent_age, send_stats, lock_delay, lock_susp)

    def _populate(self, recent, recent_age, send_stats, lock_delay, lock_susp):
        clear_box(self._root)

        # ── File History ───────────────────────────────────────────────────────
        self._root.append(make_section("FILE HISTORY"))
        fh_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        fh_card.add_css_class("card")

        rr_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        rrl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); rrl.set_hexpand(True)
        rrl.append(Gtk.Label(label="Remember recent files", css_classes=["card-name"], xalign=0))
        rrl.append(Gtk.Label(label="Apps can access your recently opened files list",
                            css_classes=["card-desc"], xalign=0))
        rr_row.append(rrl)
        rr_sw = Gtk.Switch(); rr_sw.set_active(recent.lower() == "true")
        rr_sw.set_valign(Gtk.Align.CENTER)
        rr_sw.connect("notify::active", lambda s, _: subprocess.Popen([
            "gsettings", "set", "org.gnome.desktop.privacy",
            "remember-recent-files", "true" if s.get_active() else "false"]))
        rr_row.append(rr_sw)
        fh_card.append(rr_row)

        age_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        age_row.append(Gtk.Label(label="Keep history for (days)", css_classes=["info-key"]))
        age_spin = Gtk.SpinButton.new_with_range(1, 365, 1)
        try: age_spin.set_value(int(recent_age))
        except: age_spin.set_value(30)
        age_spin.set_valign(Gtk.Align.CENTER)
        age_spin.connect("value-changed", lambda s: subprocess.Popen([
            "gsettings", "set", "org.gnome.desktop.privacy",
            "recent-files-max-age", str(int(s.get_value()))]))
        age_row.append(age_spin)
        clear_hist = Gtk.Button(label="Clear Now"); clear_hist.add_css_class("act-btn")
        clear_hist.add_css_class("rm"); clear_hist.set_valign(Gtk.Align.CENTER)
        clear_hist.connect("clicked", lambda _: subprocess.Popen(
            ["bash", "-c", "rm -f ~/.local/share/recently-used.xbel"]))
        age_row.append(clear_hist)
        fh_card.append(age_row)
        self._root.append(fh_card)

        # ── Screen Lock ────────────────────────────────────────────────────────
        self._root.append(make_section("SCREEN LOCK"))
        sl_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        sl_card.add_css_class("card")

        le_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        lel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); lel.set_hexpand(True)
        lel.append(Gtk.Label(label="Lock screen", css_classes=["card-name"], xalign=0))
        lel.append(Gtk.Label(label="Require password after screen goes blank",
                            css_classes=["card-desc"], xalign=0))
        le_row.append(lel)
        le_sw = Gtk.Switch(); le_sw.set_active(lock_susp.lower() == "true")
        le_sw.set_valign(Gtk.Align.CENTER)
        le_sw.connect("notify::active", lambda s, _: subprocess.Popen([
            "gsettings", "set", "org.gnome.desktop.screensaver",
            "lock-enabled", "true" if s.get_active() else "false"]))
        le_row.append(le_sw)
        sl_card.append(le_row)

        ld_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        ld_row.append(Gtk.Label(label="Lock delay (seconds)", css_classes=["info-key"]))
        ld_spin = Gtk.SpinButton.new_with_range(0, 3600, 30)
        try: ld_spin.set_value(int(lock_delay))
        except: ld_spin.set_value(0)
        ld_spin.set_valign(Gtk.Align.CENTER)
        ld_spin.connect("value-changed", lambda s: subprocess.Popen([
            "gsettings", "set", "org.gnome.desktop.screensaver",
            "lock-delay", str(int(s.get_value()))]))
        ld_row.append(ld_spin)
        sl_card.append(ld_row)
        self._root.append(sl_card)

        # ── Usage Statistics ───────────────────────────────────────────────────
        self._root.append(make_section("DIAGNOSTICS"))
        stat_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        stat_card.add_css_class("card")
        stl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); stl.set_hexpand(True)
        stl.append(Gtk.Label(label="Software usage statistics", css_classes=["card-name"], xalign=0))
        stl.append(Gtk.Label(label="Share anonymous app usage data to help developers",
                            css_classes=["card-desc"], xalign=0))
        stat_card.append(stl)
        stat_sw = Gtk.Switch(); stat_sw.set_active(send_stats.lower() == "true")
        stat_sw.set_valign(Gtk.Align.CENTER)
        stat_sw.connect("notify::active", lambda s, _: subprocess.Popen([
            "gsettings", "set", "org.gnome.desktop.privacy",
            "send-software-usage-stats", "true" if s.get_active() else "false"]))
        stat_card.append(stat_sw)
        self._root.append(stat_card)
        return False
