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
        info.append(Gtk.Label(label=f"Current: {cur_name}", css_classes=["card-desc"], xalign=0))
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
            apply_btn.connect("clicked",
                              lambda _, c=combo, is_=ids, m=mime:
                              subprocess.Popen(["xdg-mime", "default", is_[c.get_selected()], m]))
            card.append(combo); card.append(apply_btn)
        else:
            card.append(Gtk.Label(label="No apps found", css_classes=["card-desc"]))
        return card
