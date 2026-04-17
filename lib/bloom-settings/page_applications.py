#!/usr/bin/env python3
"""Bloom Settings — Applications pages: DefaultAppsPage."""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib
import subprocess, threading, os

from common import (
    make_header, make_section, spinner_row, clear_box,
    sh, get_default_app, desktop_name, apps_for_mime, MIME_APPS,
)


# ── Default Apps Page ─────────────────────────────────────────────────────────

class DefaultAppsPage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Default Apps", "Choose which app opens each file type."))
        self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._root.append(spinner_row("Loading applications…"))
        self.append(self._root)
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        data = []
        for label, mime in MIME_APPS:
            current_id = get_default_app(mime)
            current_name = desktop_name(current_id) if current_id else "None"
            apps = apps_for_mime(mime)
            data.append((label, mime, current_id, current_name, apps))
        GLib.idle_add(self._populate, data)

    def _populate(self, data):
        clear_box(self._root)
        for label, mime, cur_id, cur_name, apps in data:
            self._root.append(self._app_row(label, mime, cur_id, cur_name, apps))
        return False

    def _app_row(self, label, mime, cur_id, cur_name, apps):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card.add_css_class("card")

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.set_hexpand(True)
        info.append(Gtk.Label(label=label, css_classes=["card-name"], xalign=0))
        current_lbl = Gtk.Label(label=f"Current: {cur_name}",
                                css_classes=["card-desc"], xalign=0)
        info.append(current_lbl)
        card.append(info)

        if apps:
            names = [n for n, _ in apps]
            ids   = [i for _, i in apps]
            model = Gtk.StringList.new(names)
            combo = Gtk.DropDown(model=model); combo.set_valign(Gtk.Align.CENTER)
            if cur_id in ids:
                combo.set_selected(ids.index(cur_id))

            apply_btn = Gtk.Button(label="Set"); apply_btn.add_css_class("act-btn")
            apply_btn.set_valign(Gtk.Align.CENTER)
            apply_btn.connect("clicked", self._on_set_clicked,
                              combo, names, ids, mime, current_lbl, apply_btn)
            card.append(combo); card.append(apply_btn)
        else:
            card.append(Gtk.Label(label="No apps found — install one from Software",
                                  css_classes=["card-desc"]))
        return card

    def _on_set_clicked(self, _btn, combo, names, ids, mime, current_lbl, apply_btn):
        idx = combo.get_selected()
        if idx < 0 or idx >= len(ids):
            return
        chosen_id   = ids[idx]
        chosen_name = names[idx]
        apply_btn.set_sensitive(False)
        apply_btn.set_label("Setting…")

        def worker():
            result = subprocess.run(["xdg-mime", "default", chosen_id, mime],
                                    capture_output=True, text=True)
            GLib.idle_add(self._on_set_done, result, chosen_name,
                          current_lbl, apply_btn)

        threading.Thread(target=worker, daemon=True).start()

    def _on_set_done(self, result, chosen_name, current_lbl, apply_btn):
        apply_btn.set_sensitive(True)
        if result.returncode == 0:
            current_lbl.set_label(f"Current: {chosen_name}")
            apply_btn.set_label("✓")
            GLib.timeout_add(1200, lambda: (apply_btn.set_label("Set"), False)[1])
        else:
            apply_btn.set_label("Failed")
            GLib.timeout_add(1800, lambda: (apply_btn.set_label("Set"), False)[1])
        return False
