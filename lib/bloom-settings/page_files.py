#!/usr/bin/env python3
"""Bloom Settings — File Search page using plocate/find."""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib
import subprocess, threading, os

from common import make_header, clear_box, sh


_PLOCATE  = bool(sh(["which", "plocate"]))
_LOCATE   = bool(sh(["which", "locate"]))
_HAS_IDX  = _PLOCATE or _LOCATE


class FilesPage(Gtk.Box):
    """File search page. Uses plocate (fast indexed search) or find (live)."""

    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win    = win_ref
        self._cancel = False

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        inner.set_margin_top(32); inner.set_margin_bottom(20)
        inner.set_margin_start(40); inner.set_margin_end(40)
        inner.set_hexpand(True); inner.set_vexpand(True)
        self.append(inner)

        inner.append(make_header("File Search", "Find files by name across your system."))

        # ── Search bar ────────────────────────────────────────────────────────
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.set_margin_bottom(10)

        self._entry = Gtk.SearchEntry()
        self._entry.set_placeholder_text("Search filenames…")
        self._entry.set_hexpand(True)
        self._entry.connect("activate", self._search)
        bar.append(self._entry)

        self._go_btn = Gtk.Button(label="Search")
        self._go_btn.add_css_class("act-btn"); self._go_btn.add_css_class("primary")
        self._go_btn.connect("clicked", self._search)
        bar.append(self._go_btn)

        inner.append(bar)

        # Index status
        if _HAS_IDX:
            idx_tool = "plocate" if _PLOCATE else "locate"
            idx_lbl = Gtk.Label(label=f"Fast search via {idx_tool} (index updated daily by systemd timer)")
        else:
            idx_lbl = Gtk.Label(label="plocate not found — using live find (slower). Install plocate for fast search.")
        idx_lbl.add_css_class("card-desc"); idx_lbl.set_xalign(0); idx_lbl.set_margin_bottom(16)
        inner.append(idx_lbl)

        # Results area
        self._status = Gtk.Label(label="Enter a search term and press Enter or Search.")
        self._status.add_css_class("card-desc"); self._status.set_xalign(0)
        inner.append(self._status)

        sw = Gtk.ScrolledWindow(); sw.set_vexpand(True)
        self._results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sw.set_child(self._results)
        inner.append(sw)

    def _search(self, *_):
        q = self._entry.get_text().strip()
        if not q:
            return
        self._cancel = True  # cancel previous
        clear_box(self._results)
        self._status.set_label("Searching…")
        self._go_btn.set_sensitive(False)
        self._cancel = False
        threading.Thread(target=self._do_search, args=(q,), daemon=True).start()

    def _do_search(self, q):
        results = []
        try:
            if _PLOCATE:
                proc = subprocess.run(
                    ["plocate", "--limit", "500", q],
                    capture_output=True, text=True, timeout=15)
                results = [l for l in proc.stdout.splitlines() if l.strip()]
            elif _LOCATE:
                proc = subprocess.run(
                    ["locate", "-l", "500", q],
                    capture_output=True, text=True, timeout=15)
                results = [l for l in proc.stdout.splitlines() if l.strip()]
            else:
                proc = subprocess.run(
                    ["find", os.path.expanduser("~"), "-iname", f"*{q}*",
                     "-not", "-path", "*/.*", "-maxdepth", "8"],
                    capture_output=True, text=True, timeout=20)
                results = [l for l in proc.stdout.splitlines() if l.strip()]
        except Exception as e:
            GLib.idle_add(self._show_results, [], str(e))
            return
        GLib.idle_add(self._show_results, results, None)

    def _show_results(self, results, err):
        self._go_btn.set_sensitive(True)
        clear_box(self._results)
        if err:
            self._status.set_label(f"Error: {err}")
            return False
        n = len(results)
        self._status.set_label(
            f"{n} result{'s' if n != 1 else ''} found" +
            ("  (showing first 500)" if n == 500 else ""))

        for path in results:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.add_css_class("card"); row.set_margin_bottom(3)

            icon_chr = "" if os.path.isdir(path) else ""
            icon = Gtk.Label(label=icon_chr); icon.set_valign(Gtk.Align.CENTER)
            row.append(icon)

            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            info.set_hexpand(True)
            fname = Gtk.Label(label=os.path.basename(path))
            fname.add_css_class("card-name"); fname.set_xalign(0)
            info.append(fname)
            dirp = Gtk.Label(label=os.path.dirname(path))
            dirp.add_css_class("card-pkg"); dirp.set_xalign(0)
            info.append(dirp)
            row.append(info)

            open_btn = Gtk.Button(label="Open")
            open_btn.add_css_class("act-btn")
            open_btn.set_valign(Gtk.Align.CENTER)
            open_btn.connect("clicked", lambda _, p=path: subprocess.Popen(["xdg-open", p]))
            row.append(open_btn)

            self._results.append(row)
        return False
