#!/usr/bin/env python3
"""Bloom Settings — Personalization pages: Appearance, Display, Sound."""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib
import subprocess, threading, os, sys, re

from common import (
    make_header, make_section, spinner_row, clear_box, text_entry,
    TermWindow, sh, installed, CSS, _reload_app_css,
    gsettings_get, get_volume, get_mute, get_mic_volume, get_sink_inputs,
    list_gtk_themes, list_icon_themes, list_cursor_themes,
    read_bloom_colors, BLOOM_COLORS_CONF, THEME_PRESETS,
    _write_gtk_ini_all, _write_cursor_default,
)


# ── Appearance Page ───────────────────────────────────────────────────────────

class AppearancePage(Gtk.Box):
    """Appearance page with unified Apply/Discard bar for all theme settings."""

    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win         = win_ref
        self._saved       = {}
        self._pending     = {}
        self._combos      = {}   # key → (combo_widget, themes_list)
        self._color_btns  = {}   # palette key → Gtk.ColorButton
        self._scheme_btns = {}   # "dark"/"light" → Gtk.Button
        self._preset_btns = {}   # preset name → Gtk.Button
        self._font_btn    = None

        # ── Scrollable settings area ──────────────────────────────────────────
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self._inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._inner.set_margin_top(32); self._inner.set_margin_bottom(16)
        self._inner.set_margin_start(40); self._inner.set_margin_end(40)
        self._inner.append(make_header("Appearance", "Wallpaper, colors, themes and visual style."))
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._content.append(spinner_row("Loading themes…"))
        self._inner.append(self._content)
        scroll.set_child(self._inner)
        self.append(scroll)

        # ── Apply / Discard bar — only visible when there are pending changes ─
        self._action_sep = Gtk.Separator()
        self._action_sep.set_visible(False)
        self.append(self._action_sep)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bar.add_css_class("action-bar")
        bar.set_visible(False)
        self._action_bar = bar

        info = Gtk.Label(label="You have unsaved changes")
        info.add_css_class("action-bar-info")
        info.set_hexpand(True); info.set_xalign(0)
        bar.append(info)

        discard_btn = Gtk.Button(label="Discard")
        discard_btn.add_css_class("act-btn")
        discard_btn.connect("clicked", lambda _: self._discard())
        bar.append(discard_btn)

        apply_btn = Gtk.Button(label="Apply")
        apply_btn.add_css_class("act-btn"); apply_btn.add_css_class("primary")
        apply_btn.connect("clicked", lambda _: self._apply_all())
        bar.append(apply_btn)

        self.append(bar)
        threading.Thread(target=self._do_load, daemon=True).start()

    # ── Loading ───────────────────────────────────────────────────────────────

    def _do_load(self):
        wallpaper     = self._find_wallpaper()
        cur_gtk       = gsettings_get("org.gnome.desktop.interface", "gtk-theme",    "Adwaita-dark")
        cur_icon      = gsettings_get("org.gnome.desktop.interface", "icon-theme",   "")
        cur_cursor    = gsettings_get("org.gnome.desktop.interface", "cursor-theme", "")
        cur_font      = gsettings_get("org.gnome.desktop.interface", "font-name",    "")
        cur_scheme    = gsettings_get("org.gnome.desktop.interface", "color-scheme", "prefer-dark")
        gtk_themes    = list_gtk_themes()
        icon_themes   = list_icon_themes()
        cursor_themes = list_cursor_themes()
        bloom_colors  = read_bloom_colors()
        GLib.idle_add(self._populate, wallpaper, cur_gtk, cur_icon, cur_cursor,
                      cur_font, cur_scheme, gtk_themes, icon_themes, cursor_themes,
                      bloom_colors)

    def _find_wallpaper(self):
        cfg = os.path.expanduser("~/.config/bloom/wallpaper")
        if os.path.exists(cfg):
            path = open(cfg).read().strip()
            if os.path.exists(path):
                return path
        out = sh(["pgrep", "-a", "swaybg"])
        for line in out.splitlines():
            if "-i" in line:
                parts = line.split()
                try:
                    idx = parts.index("-i"); return parts[idx + 1]
                except (ValueError, IndexError): pass
        return "/usr/share/wallpapers/bloom/bloom-wallpaper.png"

    def _populate(self, wallpaper, cur_gtk, cur_icon, cur_cursor,
                  cur_font, cur_scheme, gtk_themes, icon_themes, cursor_themes,
                  bloom_colors):
        clear_box(self._content)
        self._combos      = {}
        self._color_btns  = {}
        self._scheme_btns = {}
        self._preset_btns = {}
        self._font_btn    = None

        scheme     = "dark" if "dark" in cur_scheme else "light"
        cur_preset = bloom_colors.get("preset", "Bloom")

        # Full saved state covers every knob on this page
        self._saved = {
            "scheme":   scheme,
            "preset":   cur_preset,
            "accent":   bloom_colors.get("accent",   "#B01828"),
            "bg":       bloom_colors.get("bg",       "#0D0618"),
            "surface":  bloom_colors.get("surface",  "#080312"),
            "overlay":  bloom_colors.get("overlay",  "#120920"),
            "text":     bloom_colors.get("text",     "#F0EEF4"),
            "text_dim": bloom_colors.get("text_dim", "#88809A"),
            "gtk":      cur_gtk,
            "icon":     cur_icon,
            "cursor":   cur_cursor,
            "font":     cur_font,
        }
        self._pending = self._saved.copy()

        # ── Wallpaper ─────────────────────────────────────────────────────────
        self._content.append(make_section("WALLPAPER"))
        wp_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        wp_card.add_css_class("card")

        self._wp_pic = Gtk.Picture()
        self._wp_pic.set_can_shrink(True)
        self._wp_pic.set_content_fit(Gtk.ContentFit.COVER)
        self._wp_pic.add_css_class("wallpaper-box")
        self._wp_pic.set_size_request(160, 90)
        if wallpaper and os.path.exists(wallpaper):
            self._wp_pic.set_filename(wallpaper)
        wp_card.append(self._wp_pic)

        wp_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        wp_info.set_hexpand(True); wp_info.set_valign(Gtk.Align.CENTER)
        self._wp_lbl = Gtk.Label(label=os.path.basename(wallpaper) if wallpaper else "Default")
        self._wp_lbl.add_css_class("card-desc"); self._wp_lbl.set_xalign(0)
        wp_info.append(self._wp_lbl)
        btn = Gtk.Button(label="  Choose Wallpaper")
        btn.add_css_class("act-btn"); btn.set_halign(Gtk.Align.START)
        btn.connect("clicked", lambda _: self._pick_wallpaper())
        wp_info.append(btn)
        wp_card.append(wp_info)
        self._content.append(wp_card)

        # ── Color Scheme ──────────────────────────────────────────────────────
        self._content.append(make_section("COLOR SCHEME"))
        scheme_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        scheme_card.add_css_class("card")
        sl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); sl.set_hexpand(True)
        sl.append(Gtk.Label(label="Dark / Light Mode", css_classes=["card-name"], xalign=0))
        sl.append(Gtk.Label(label="Affects GTK apps, Qt apps, bloom popups and the bar",
                            css_classes=["card-desc"], xalign=0))
        scheme_card.append(sl)
        dark_btn  = Gtk.Button(label="  Dark");  dark_btn.add_css_class("act-btn")
        light_btn = Gtk.Button(label="  Light"); light_btn.add_css_class("act-btn")
        if scheme == "dark":  dark_btn.add_css_class("primary")
        else:                 light_btn.add_css_class("primary")
        dark_btn.set_valign(Gtk.Align.CENTER)
        light_btn.set_valign(Gtk.Align.CENTER)
        dark_btn.connect("clicked",  lambda _: self._set_pending("scheme", "dark"))
        light_btn.connect("clicked", lambda _: self._set_pending("scheme", "light"))
        self._scheme_btns = {"dark": dark_btn, "light": light_btn}
        scheme_card.append(dark_btn); scheme_card.append(light_btn)
        self._content.append(scheme_card)

        # ── Theme Presets ─────────────────────────────────────────────────────
        self._content.append(make_section("THEME PRESETS"))
        presets_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        presets_card.add_css_class("card")
        presets_card.append(Gtk.Label(
            label="Full color palette presets — select to preview, then click Apply to save.",
            css_classes=["card-desc"], xalign=0))
        swatches_flow = Gtk.FlowBox()
        swatches_flow.set_max_children_per_line(5)
        swatches_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        swatches_flow.set_column_spacing(8)
        swatches_flow.set_row_spacing(8)
        swatches_flow.set_margin_top(10)
        self._preset_btns = {}
        for pname, pdata in THEME_PRESETS.items():
            variant = pdata.get(scheme, pdata.get("dark", {}))
            btn = self._make_swatch_btn(pname, variant, pname == cur_preset)
            btn.connect("clicked", lambda _, n=pname: self._set_pending_preset(n))
            swatches_flow.append(btn)
            self._preset_btns[pname] = btn
        presets_card.append(swatches_flow)
        self._content.append(presets_card)

        # ── Custom Palette ────────────────────────────────────────────────────
        self._content.append(make_section("CUSTOM PALETTE"))
        palette_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        palette_card.add_css_class("card")
        palette_card.append(Gtk.Label(
            label="Fine-tune individual colors — changes are staged until you click Apply.",
            css_classes=["card-desc"], xalign=0))
        palette_card.set_margin_top(2)
        for color_key, color_label in [
            ("accent",   "Accent"),
            ("bg",       "Background"),
            ("surface",  "Surface / Sidebar"),
            ("overlay",  "Overlay / Popups"),
            ("text",     "Text"),
            ("text_dim", "Dim Text"),
        ]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.set_margin_top(4)
            lbl = Gtk.Label(label=color_label)
            lbl.add_css_class("card-desc"); lbl.set_hexpand(True); lbl.set_xalign(0)
            row.append(lbl)
            cb = Gtk.ColorButton()
            cb.set_valign(Gtk.Align.CENTER)
            try:
                rv = Gdk.RGBA()
                rv.parse(bloom_colors.get(color_key, "#000000"))
                cb.set_rgba(rv)
            except Exception: pass
            cb.connect("color-set", lambda btn, k=color_key:
                       self._set_pending(k, self._rgba_to_hex(btn.get_rgba())))
            self._color_btns[color_key] = cb
            row.append(cb)
            palette_card.append(row)

        reset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        reset_row.set_margin_top(8)
        reset_btn = Gtk.Button(label="Reset to scheme defaults")
        reset_btn.add_css_class("act-btn")
        reset_btn.connect("clicked", lambda _: self._pending_reset_palette())
        reset_row.append(reset_btn)
        palette_card.append(reset_row)
        self._content.append(palette_card)

        # ── Style (themes) ────────────────────────────────────────────────────
        self._content.append(make_section("STYLE"))
        self._content.append(self._theme_row("gtk",    "Application Theme", gtk_themes,    cur_gtk))
        self._content.append(self._theme_row("icon",   "Icon Theme",        icon_themes,   cur_icon))
        self._content.append(self._theme_row("cursor", "Cursor Theme",      cursor_themes, cur_cursor))

        # ── Font ──────────────────────────────────────────────────────────────
        self._content.append(make_section("FONT"))
        font_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        font_card.add_css_class("card")
        fl = Gtk.Label(label="Interface Font"); fl.add_css_class("card-name")
        fl.set_hexpand(True); fl.set_xalign(0); font_card.append(fl)
        font_btn = Gtk.FontButton()
        font_btn.set_valign(Gtk.Align.CENTER)
        if cur_font:
            font_btn.set_font(cur_font)
        font_btn.connect("font-set", lambda b: self._set_pending("font", b.get_font()))
        self._font_btn = font_btn
        font_card.append(font_btn)
        self._content.append(font_card)
        return False

    # ── Theme rows ────────────────────────────────────────────────────────────

    def _theme_row(self, key, label, themes, current):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card.add_css_class("card")
        lbl = Gtk.Label(label=label); lbl.add_css_class("card-name")
        lbl.set_hexpand(True); lbl.set_xalign(0); card.append(lbl)
        if themes:
            model = Gtk.StringList.new(themes)
            combo = Gtk.DropDown(model=model); combo.set_valign(Gtk.Align.CENTER)
            if current in themes:
                combo.set_selected(themes.index(current))
            self._combos[key] = (combo, themes)
            combo.connect("notify::selected",
                          lambda c, _, k=key, ts=themes: self._set_pending(k, ts[c.get_selected()]))
            card.append(combo)
        else:
            card.append(Gtk.Label(label="No themes found", css_classes=["card-desc"]))
        return card

    # ── Pending state management ──────────────────────────────────────────────

    def _set_pending(self, key, value):
        self._pending[key] = value
        if key == "scheme":
            # Update scheme button highlight immediately
            for s, b in self._scheme_btns.items():
                if s == value: b.add_css_class("primary")
                else:          b.remove_css_class("primary")
            # Auto-stage the active preset's palette for the new scheme so the
            # palette colours actually switch (not just the scheme label)
            preset = THEME_PRESETS.get(self._pending.get("preset", "Bloom"))
            if preset:
                variant = preset.get(value, preset.get("dark", {}))
                for k in ("bg", "surface", "overlay", "text", "text_dim"):
                    if k in variant:
                        self._pending[k] = variant[k]
                        if k in self._color_btns:
                            try:
                                rv = Gdk.RGBA(); rv.parse(variant[k])
                                self._color_btns[k].set_rgba(rv)
                            except Exception: pass
        self._mark_dirty()

    def _set_pending_preset(self, preset_name):
        """Stage a preset: marks all palette colors from the preset variant as pending."""
        scheme  = self._pending.get("scheme", "dark")
        preset  = THEME_PRESETS.get(preset_name)
        if not preset:
            return
        variant = preset.get(scheme, preset.get("dark", {}))
        self._pending["preset"] = preset_name
        for k in ("accent", "bg", "surface", "overlay", "text", "text_dim"):
            if k in variant:
                self._pending[k] = variant[k]
                # Update color button so user sees the palette preview immediately
                if k in self._color_btns:
                    try:
                        rv = Gdk.RGBA(); rv.parse(variant[k])
                        self._color_btns[k].set_rgba(rv)
                    except Exception: pass
        # Highlight the selected preset button
        for n, b in self._preset_btns.items():
            if n == preset_name: b.add_css_class("primary")
            else:                b.remove_css_class("primary")
        self._mark_dirty()

    def _pending_reset_palette(self):
        """Stage a reset of all palette colors to scheme defaults."""
        dark = self._pending.get("scheme", "dark") == "dark"
        defs = {
            "bg":       "#0D0618" if dark else "#F5F3F7",
            "surface":  "#080312" if dark else "#FFFEFF",
            "overlay":  "#120920" if dark else "#EDE9F0",
            "text":     "#F0EEF4" if dark else "#1A1420",
            "text_dim": "#88809A" if dark else "#6B6378",
        }
        for k, v in defs.items():
            self._pending[k] = v
            if k in self._color_btns:
                try:
                    rv = Gdk.RGBA(); rv.parse(v)
                    self._color_btns[k].set_rgba(rv)
                except Exception: pass
        self._mark_dirty()

    def _mark_dirty(self):
        dirty = self._pending != self._saved
        self._action_bar.set_visible(dirty)
        self._action_sep.set_visible(dirty)

    # ── Apply / Discard ───────────────────────────────────────────────────────

    def _apply_all(self):
        p = self._pending
        s = self._saved

        # ── Bloom colors (scheme, preset, palette) ────────────────────────────
        color_keys    = ("scheme", "preset", "accent", "bg", "surface", "overlay", "text", "text_dim")
        bloom_changes = {k: p[k] for k in color_keys if p.get(k) != s.get(k)}
        if bloom_changes:
            self._update_bloom_colors(bloom_changes)

        scheme_changed = p.get("scheme") != s.get("scheme")
        scheme         = p.get("scheme", "dark")

        if scheme_changed:
            val = "prefer-dark" if scheme == "dark" else "prefer-light"
            subprocess.Popen(["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", val])
            # Auto-switch GTK theme dark/light variant if one exists
            cur_gtk = p.get("gtk", "")
            try:
                themes = list_gtk_themes()
                if scheme == "dark" and not cur_gtk.endswith("-dark") and cur_gtk + "-dark" in themes:
                    self._pending["gtk"] = cur_gtk + "-dark"
                    subprocess.Popen(["gsettings", "set", "org.gnome.desktop.interface",
                                       "gtk-theme", cur_gtk + "-dark"])
                elif scheme == "light" and cur_gtk.endswith("-dark"):
                    light = cur_gtk[:-5]
                    if light in themes:
                        self._pending["gtk"] = light
                        subprocess.Popen(["gsettings", "set", "org.gnome.desktop.interface",
                                           "gtk-theme", light])
            except Exception: pass
            self._write_qt_scheme(scheme)
            GLib.idle_add(_reload_app_css)

        # ── GTK theme / icon / cursor / font ──────────────────────────────────
        gtk    = p.get("gtk",    "")
        icon   = p.get("icon",   "")
        cursor = p.get("cursor", "")
        font   = p.get("font",   "")

        _write_gtk_ini_all(
            gtk    = gtk    if gtk    != s.get("gtk")    else None,
            icon   = icon   if icon   != s.get("icon")   else None,
            cursor = cursor if cursor != s.get("cursor") else None,
            font   = font   if font   != s.get("font")   else None,
            scheme = scheme if scheme_changed             else None,
        )

        if gtk and gtk != s.get("gtk"):
            subprocess.Popen(["gsettings", "set", "org.gnome.desktop.interface", "gtk-theme", gtk])

        if icon and icon != s.get("icon"):
            subprocess.Popen(["gsettings", "set", "org.gnome.desktop.interface", "icon-theme", icon])
            self._write_qt_icon_theme(icon)
            self._write_rofi_icon_theme(icon)
            subprocess.Popen(["bloom-generate-icons"])

        if cursor and cursor != s.get("cursor"):
            subprocess.Popen(["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", cursor])
            subprocess.Popen(["gsettings", "set", "org.gnome.desktop.interface", "cursor-size", "24"])
            subprocess.Popen(["hyprctl", "setcursor", cursor, "24"])
            _write_cursor_default(cursor)
            subprocess.Popen(["bloom-generate-cursors"])

        if font and font != s.get("font"):
            subprocess.Popen(["gsettings", "set", "org.gnome.desktop.interface", "font-name", font])
            subprocess.Popen(["gsettings", "set", "org.gnome.desktop.interface",
                               "monospace-font-name", font])
            self._update_bloom_colors({"font": font})

        # Regenerate colors + restart the bar in one shot
        subprocess.Popen(["bloom-generate-colors"])

        self._saved = self._pending.copy()
        self._mark_dirty()

    def _discard(self):
        self._pending = self._saved.copy()
        s = self._saved

        # Restore scheme buttons
        for sv, btn in self._scheme_btns.items():
            if sv == s.get("scheme"): btn.add_css_class("primary")
            else:                     btn.remove_css_class("primary")

        # Restore preset buttons
        for name, btn in self._preset_btns.items():
            if name == s.get("preset"): btn.add_css_class("primary")
            else:                       btn.remove_css_class("primary")

        # Restore color pickers
        for k, cb in self._color_btns.items():
            val = s.get(k, "")
            if val:
                try:
                    rv = Gdk.RGBA(); rv.parse(val); cb.set_rgba(rv)
                except Exception: pass

        # Restore theme combo dropdowns
        for key, (combo, themes) in self._combos.items():
            val = s.get(key, "")
            if val in themes:
                combo.set_selected(themes.index(val))

        # Restore font button
        if self._font_btn and s.get("font"):
            self._font_btn.set_font(s["font"])

        self._mark_dirty()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_swatch_btn(self, name, variant, selected):
        """Create a visual color swatch button for a theme preset."""
        def _hex2rgb(h):
            h = h.lstrip("#")
            return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))

        bg_c  = variant.get("bg",      "#0D0618")
        sur_c = variant.get("surface", "#080312")
        acc_c = variant.get("accent",  "#B01828")
        txt_c = variant.get("text",    "#F0EEF4")

        btn = Gtk.Button()
        btn.add_css_class("act-btn")
        if selected: btn.add_css_class("primary")

        vbox   = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        swatch = Gtk.DrawingArea()
        swatch.set_content_width(96)
        swatch.set_content_height(54)

        def make_draw(bg, sur, acc, txt):
            def draw(area, cr, w, h):
                r, g, b = _hex2rgb(bg);  cr.set_source_rgb(r, g, b);  cr.paint()
                r, g, b = _hex2rgb(sur); cr.set_source_rgb(r, g, b)
                cr.rectangle(0, 0, w * 0.22, h); cr.fill()
                r, g, b = _hex2rgb(acc); cr.set_source_rgb(r, g, b)
                cr.rectangle(0, h - 7, w, 7); cr.fill()
                r, g, b = _hex2rgb(txt); cr.set_source_rgba(r, g, b, 0.35)
                for yi in [0.28, 0.48, 0.68]:
                    cr.rectangle(w * 0.28, h * yi, w * 0.55, 4); cr.fill()
            return draw

        swatch.set_draw_func(make_draw(bg_c, sur_c, acc_c, txt_c))
        vbox.append(swatch)
        lbl = Gtk.Label(label=name); lbl.add_css_class("card-desc")
        vbox.append(lbl)
        btn.set_child(vbox)
        return btn

    def _rgba_to_hex(self, rgba):
        return "#{:02X}{:02X}{:02X}".format(
            int(rgba.red * 255), int(rgba.green * 255), int(rgba.blue * 255))

    # ── Wallpaper (immediate — live preview is good UX) ───────────────────────

    def _pick_wallpaper(self):
        from gi.repository import Gio
        native = Gtk.FileChooserNative(
            title="Choose Wallpaper", transient_for=self._win,
            action=Gtk.FileChooserAction.OPEN,
            accept_label="_Open", cancel_label="_Cancel",
        )
        f = Gtk.FileFilter(); f.set_name("Images")
        for m in ["image/jpeg", "image/png", "image/webp", "image/bmp"]: f.add_mime_type(m)
        native.set_filter(f)
        wp_dir = "/usr/share/wallpapers/bloom"
        if os.path.isdir(wp_dir):
            native.set_current_folder(Gio.File.new_for_path(wp_dir))
        native.connect("response", self._on_wp_chosen)
        native.show()
        self._file_dlg = native

    def _on_wp_chosen(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            self._apply_wallpaper(dialog.get_file().get_path())

    def _apply_wallpaper(self, path):
        subprocess.Popen(["bash", "-c", f"pkill swaybg; sleep 0.2; swaybg -i '{path}' -m fill"])
        if os.path.exists(path): self._wp_pic.set_filename(path)
        self._wp_lbl.set_text(os.path.basename(path))
        cfg = os.path.expanduser("~/.config/bloom")
        os.makedirs(cfg, exist_ok=True)
        open(os.path.join(cfg, "wallpaper"), "w").write(path)

    # ── Qt / Rofi / Colors helpers ────────────────────────────────────────────

    def _write_qt_scheme(self, scheme):
        """Update qt5ct/qt6ct style for dark/light."""
        import configparser as _cp
        style         = "kvantum-dark" if scheme == "dark" else "kvantum"
        kvantum_theme = "KvDark"       if scheme == "dark" else "KvFlat"
        for path in [os.path.expanduser("~/.config/qt5ct/qt5ct.conf"),
                     os.path.expanduser("~/.config/qt6ct/qt6ct.conf")]:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            cp = _cp.RawConfigParser(); cp.optionxform = str
            if os.path.exists(path):
                try: cp.read(path)
                except Exception: pass
            if not cp.has_section("Appearance"): cp.add_section("Appearance")
            cp.set("Appearance", "style", style)
            try:
                with open(path, "w") as f: cp.write(f, space_around_delimiters=False)
            except Exception: pass
        kv_path = os.path.expanduser("~/.config/Kvantum/kvantum.kvconfig")
        os.makedirs(os.path.dirname(kv_path), exist_ok=True)
        kv = _cp.RawConfigParser(); kv.optionxform = str
        if os.path.exists(kv_path):
            try: kv.read(kv_path)
            except Exception: pass
        if not kv.has_section("General"): kv.add_section("General")
        kv.set("General", "theme", kvantum_theme)
        try:
            with open(kv_path, "w") as f: kv.write(f, space_around_delimiters=False)
        except Exception: pass

    def _write_qt_icon_theme(self, theme):
        """Write icon theme into qt5ct and qt6ct config."""
        import configparser as _cp
        for path in [os.path.expanduser("~/.config/qt5ct/qt5ct.conf"),
                     os.path.expanduser("~/.config/qt6ct/qt6ct.conf")]:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            cp = _cp.RawConfigParser(); cp.optionxform = str
            if os.path.exists(path):
                try: cp.read(path)
                except Exception: pass
            if not cp.has_section("Appearance"): cp.add_section("Appearance")
            cp.set("Appearance", "icon_theme", theme)
            try:
                with open(path, "w") as f: cp.write(f, space_around_delimiters=False)
            except Exception: pass

    def _write_rofi_icon_theme(self, theme):
        """Update icon-theme in rofi config.rasi."""
        path = os.path.expanduser("~/.config/rofi/config.rasi")
        if not os.path.exists(path):
            return
        try:
            content = open(path).read()
            new = re.sub(r'icon-theme:\s*"[^"]*"', f'icon-theme: "{theme}"', content)
            open(path, "w").write(new)
        except Exception: pass

    def _update_bloom_colors(self, overrides):
        """Merge overrides into ~/.config/bloom/colors.conf."""
        import configparser as _cp
        cp = _cp.ConfigParser()
        if os.path.exists(BLOOM_COLORS_CONF):
            try: cp.read(BLOOM_COLORS_CONF)
            except: pass
        if not cp.has_section("Colors"):
            cp.add_section("Colors")
        for k, v in overrides.items():
            cp.set("Colors", k, v)
        os.makedirs(os.path.dirname(BLOOM_COLORS_CONF), exist_ok=True)
        with open(BLOOM_COLORS_CONF, "w") as f:
            cp.write(f)


# ── Display Page ──────────────────────────────────────────────────────────────

class DisplayPage(Gtk.Box):
    _NL_CONF = os.path.expanduser("~/.config/bloom/night-light.conf")

    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Display", "Monitor configuration, scaling, and night light."))
        self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._root.append(spinner_row("Reading monitors…"))
        self.append(self._root)
        self._nl_tid = None
        threading.Thread(target=self._do_load, daemon=True).start()

    def _parse_modes(self, modes_raw):
        result = {}
        for m in (modes_raw or []):
            m2 = re.match(r"(\d+x\d+)@([\d.]+)", m)
            if m2:
                res = m2.group(1)
                hz  = float(m2.group(2))
                result.setdefault(res, []).append(hz)
        return {r: sorted(set(hzs), reverse=True) for r, hzs in result.items()}

    def _do_load(self):
        import json
        raw = sh(["hyprctl", "monitors", "-j"])
        try:
            monitors = json.loads(raw) if raw else []
        except Exception:
            monitors = []
        nl_enabled = False; nl_temp = 4000
        try:
            import configparser as _cp
            cfg = _cp.ConfigParser()
            cfg.read(self._NL_CONF)
            nl_enabled = cfg.getboolean("NightLight", "enabled", fallback=False)
            nl_temp    = cfg.getint("NightLight", "temperature", fallback=4000)
        except Exception:
            pass
        GLib.idle_add(self._populate, monitors, nl_enabled, nl_temp)

    def _populate(self, monitors, nl_enabled, nl_temp):
        clear_box(self._root)

        # ── Visual monitor arrangement canvas ─────────────────────────────────
        if len(monitors) >= 2:
            canvas = self._make_monitor_canvas(monitors)
            if canvas:
                self._root.append(make_section("MONITOR LAYOUT"))
                self._root.append(canvas)

        for mon in monitors:
            self._root.append(make_section(f"MONITOR — {mon.get('name', '?')}"))
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            card.add_css_class("card")

            name  = mon.get("name", "unknown")
            w     = mon.get("width",  0); h = mon.get("height", 0)
            hz    = mon.get("refreshRate", 60.0)
            scale = mon.get("scale", 1.0)
            desc  = mon.get("description", "")

            if desc:
                dl = Gtk.Label(label=desc); dl.add_css_class("card-desc"); dl.set_xalign(0)
                card.append(dl)

            modes    = self._parse_modes(mon.get("availableModes", []))
            cur_res  = f"{w}x{h}"
            res_combo = None; hz_combo = None; res_list = []

            if modes:
                res_list = sorted(modes.keys(),
                                  key=lambda r: tuple(int(x) for x in r.split("x")),
                                  reverse=True)
                res_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                res_row.append(Gtk.Label(label="Resolution", css_classes=["info-key"]))
                res_combo = Gtk.DropDown(model=Gtk.StringList.new(res_list))
                res_combo.set_hexpand(True); res_combo.set_valign(Gtk.Align.CENTER)
                try:
                    res_combo.set_selected(res_list.index(cur_res))
                except ValueError:
                    pass
                res_row.append(res_combo)
                card.append(res_row)

                init_hzs = modes.get(cur_res, [hz])
                hz_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                hz_row.append(Gtk.Label(label="Refresh rate", css_classes=["info-key"]))
                hz_combo = Gtk.DropDown(
                    model=Gtk.StringList.new([f"{r:.0f} Hz" for r in init_hzs]))
                hz_combo.set_valign(Gtk.Align.CENTER)
                hz_row.append(hz_combo)
                card.append(hz_row)

                def on_res_change(c, _, rc=res_combo, hc=hz_combo, rl=res_list, m=modes):
                    hzs = m.get(rl[rc.get_selected()], [])
                    hc.set_model(Gtk.StringList.new([f"{r:.0f} Hz" for r in hzs]))
                res_combo.connect("notify::selected", on_res_change)
            else:
                lbl = Gtk.Label(label=f"Resolution: {w}×{h} @ {hz:.0f} Hz")
                lbl.add_css_class("card-desc"); lbl.set_xalign(0)
                card.append(lbl)

            # Scale
            scales    = ["0.5", "0.75", "1", "1.25", "1.5", "1.75", "2"]
            scale_str = f"{scale:.2f}".rstrip("0").rstrip(".")
            if scale_str not in scales:
                scales.append(scale_str); scales.sort(key=float)
            sc_combo = Gtk.DropDown(model=Gtk.StringList.new(scales))
            sc_combo.set_valign(Gtk.Align.CENTER)
            try:
                sc_combo.set_selected(scales.index(scale_str))
            except ValueError:
                pass
            scale_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            scale_row.append(Gtk.Label(label="Scale", css_classes=["info-key"]))
            scale_row.append(sc_combo)
            card.append(scale_row)

            # Rotation
            rotations = ["Normal (0°)", "90° CW", "180°", "270° CW (90° CCW)",
                         "Flipped", "Flipped + 90°", "Flipped + 180°", "Flipped + 270°"]
            cur_transform = mon.get("transform", 0)
            rot_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            rot_row.append(Gtk.Label(label="Rotation", css_classes=["info-key"]))
            rot_combo = Gtk.DropDown(model=Gtk.StringList.new(rotations))
            rot_combo.set_valign(Gtk.Align.CENTER)
            rot_combo.set_selected(cur_transform if 0 <= cur_transform < len(rotations) else 0)
            rot_row.append(rot_combo)
            card.append(rot_row)

            # Position (for multi-monitor layout)
            pos_x = mon.get("x", 0); pos_y = mon.get("y", 0)
            pos_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            pos_row.append(Gtk.Label(label="Position", css_classes=["info-key"]))
            px_spin = Gtk.SpinButton.new_with_range(-7680, 7680, 1)
            px_spin.set_value(pos_x); px_spin.set_size_request(90, -1)
            py_spin = Gtk.SpinButton.new_with_range(-4320, 4320, 1)
            py_spin.set_value(pos_y); py_spin.set_size_request(90, -1)
            pos_row.append(Gtk.Label(label="X:"))
            pos_row.append(px_spin)
            pos_row.append(Gtk.Label(label="Y:"))
            pos_row.append(py_spin)
            card.append(pos_row)

            _rl = res_list
            apply_btn = Gtk.Button(label="Apply")
            apply_btn.add_css_class("act-btn"); apply_btn.add_css_class("primary")
            apply_btn.set_halign(Gtk.Align.START)
            apply_btn.connect("clicked",
                lambda _, n=name, rc=res_combo, hc=hz_combo, sc=sc_combo,
                       ss=scales, rl=_rl, m=modes, rc2=rot_combo, px=px_spin, py=py_spin:
                self._apply_monitor(n, rc, hc, sc, ss, rl, m, rc2, px, py))
            card.append(apply_btn)

            if mon.get("focused"):
                fb = Gtk.Label(label="PRIMARY"); fb.add_css_class("badge"); fb.add_css_class("ok")
                fb.set_halign(Gtk.Align.START); card.append(fb)

            self._root.append(card)

        if not monitors:
            msg = Gtk.Label(label="Hyprland not running — monitor settings unavailable.")
            msg.add_css_class("card-desc"); msg.set_xalign(0)
            self._root.append(msg)

        # ── Night Light ───────────────────────────────────────────────────────
        self._root.append(make_section("NIGHT LIGHT"))
        nl_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        nl_card.add_css_class("card")

        nl_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        nl_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); nl_info.set_hexpand(True)
        nl_info.append(Gtk.Label(label="Night Light", css_classes=["card-name"], xalign=0))
        nl_info.append(Gtk.Label(label="Reduce blue light to ease eye strain in low-light environments",
                                 css_classes=["card-desc"], xalign=0))
        nl_hdr.append(nl_info)
        self._nl_sw = Gtk.Switch(); self._nl_sw.set_active(nl_enabled)
        self._nl_sw.set_valign(Gtk.Align.CENTER)
        self._nl_sw.connect("notify::active", lambda s, _: self._toggle_nl(s.get_active()))
        nl_hdr.append(self._nl_sw)
        nl_card.append(nl_hdr)

        temp_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        temp_row.append(Gtk.Label(label="Color temperature", css_classes=["info-key"]))
        self._nl_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1000, 6500, 100)
        self._nl_slider.set_value(nl_temp); self._nl_slider.set_hexpand(True)
        self._nl_slider.set_draw_value(True)
        self._nl_slider.set_format_value_func(lambda _, v: f"{int(v)} K")
        for mark, lbl in [(2700, "Warm"), (4000, "Neutral"), (6500, "Cool")]:
            self._nl_slider.add_mark(mark, Gtk.PositionType.BOTTOM, lbl)
        self._nl_slider.connect("value-changed", self._on_nl_temp)
        temp_row.append(self._nl_slider)
        nl_card.append(temp_row)
        self._root.append(nl_card)
        return False

    def _apply_monitor(self, name, res_combo, hz_combo, sc_combo, scales, res_list, modes,
                       rot_combo=None, px_spin=None, py_spin=None):
        scale     = scales[sc_combo.get_selected()]
        transform = rot_combo.get_selected() if rot_combo is not None else 0
        px        = int(px_spin.get_value()) if px_spin is not None else 0
        py        = int(py_spin.get_value()) if py_spin is not None else 0
        pos       = f"{px}x{py}"
        if res_combo is not None and res_list:
            res    = res_list[res_combo.get_selected()]
            hzs    = modes.get(res, [])
            hz_idx = hz_combo.get_selected() if hz_combo is not None else 0
            hz     = hzs[hz_idx] if hz_idx < len(hzs) else 60.0
            cmd    = f"hyprctl keyword monitor {name},{res}@{hz:.0f},{pos},{scale},transform,{transform}"
        else:
            cmd    = f"hyprctl keyword monitor {name},preferred,{pos},{scale},transform,{transform}"
        subprocess.Popen(["bash", "-c", cmd])

    def _make_monitor_canvas(self, monitors):
        """Render a proportional top-down view of all connected monitors."""
        def _hex2rgb(h):
            h = h.lstrip("#")
            return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))

        min_x = min(m.get("x", 0) for m in monitors)
        min_y = min(m.get("y", 0) for m in monitors)
        max_x = max(m.get("x", 0) + m.get("width",  1920) for m in monitors)
        max_y = max(m.get("y", 0) + m.get("height", 1080) for m in monitors)
        total_w = max(max_x - min_x, 1)
        total_h = max(max_y - min_y, 1)

        mons = [(m.get("name", "?"),
                 m.get("x", 0) - min_x,
                 m.get("y", 0) - min_y,
                 m.get("width", 1920),
                 m.get("height", 1080),
                 bool(m.get("focused", False)))
                for m in monitors]

        da = Gtk.DrawingArea()
        da.set_size_request(-1, 130)
        da.add_css_class("card")

        def draw(area, cr, w, h):
            pad = 14
            aw = w - 2 * pad
            ah = h - 2 * pad
            scale = min(aw / total_w, ah / total_h)
            ox = pad + (aw - total_w * scale) / 2
            oy = pad + (ah - total_h * scale) / 2

            for name, mx, my, mw, mh, focused in mons:
                rx = ox + mx * scale
                ry = oy + my * scale
                rw = mw * scale
                rh = mh * scale

                # Fill
                if focused:
                    cr.set_source_rgb(0.20, 0.09, 0.33)
                else:
                    cr.set_source_rgb(0.10, 0.05, 0.18)
                cr.rectangle(rx, ry, rw, rh)
                cr.fill()

                # Border
                cr.set_source_rgb(0.50, 0.22, 0.75)
                cr.set_line_width(1.5)
                cr.rectangle(rx + 0.75, ry + 0.75, rw - 1.5, rh - 1.5)
                cr.stroke()

                # Monitor name label
                cr.set_source_rgb(0.90, 0.88, 0.95)
                cr.select_font_face("monospace", 0, 0)
                font_sz = max(9.0, min(14.0, rh * 0.18))
                cr.set_font_size(font_sz)
                ext = cr.text_extents(name)
                cr.move_to(rx + (rw - ext.width) / 2, ry + (rh + ext.height) / 2)
                cr.show_text(name)

        da.set_draw_func(draw)
        return da

    def _toggle_nl(self, enable):
        temp = int(self._nl_slider.get_value())
        if enable:
            subprocess.Popen(["gammastep", "-O", str(temp)])
        else:
            subprocess.Popen(["gammastep", "-x"])
        self._save_nl(enable, temp)

    def _on_nl_temp(self, slider):
        if self._nl_tid:
            GLib.source_remove(self._nl_tid)
        temp = int(slider.get_value())
        def apply():
            if self._nl_sw.get_active():
                subprocess.Popen(["gammastep", "-O", str(temp)])
            self._save_nl(self._nl_sw.get_active(), temp)
            return False
        self._nl_tid = GLib.timeout_add(300, apply)

    def _save_nl(self, enabled, temp):
        os.makedirs(os.path.dirname(self._NL_CONF), exist_ok=True)
        with open(self._NL_CONF, "w") as f:
            f.write(f"[NightLight]\nenabled = {'true' if enabled else 'false'}\n"
                    f"temperature = {temp}\n")


# ── Sound Page ────────────────────────────────────────────────────────────────

class SoundPage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Sound", "Output, input, and per-application volume."))
        self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._root.append(spinner_row("Loading audio…"))
        self.append(self._root)
        self._vol_tid = None
        self._mic_tid = None
        self._app_tids = {}
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        vol = get_volume(); muted = get_mute()
        mic = get_mic_volume()
        sinks   = sh(["pactl", "list", "sinks",   "short"])
        sources = sh(["pactl", "list", "sources",  "short"])
        inputs  = get_sink_inputs()
        GLib.idle_add(self._populate, vol, muted, mic, sinks, sources, inputs)

    def _populate(self, vol, muted, mic, sinks_raw, sources_raw, sink_inputs):
        clear_box(self._root)

        def sink_names(raw):
            names = []
            for line in raw.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    names.append(parts[1])
            return names

        out_names = sink_names(sinks_raw)
        in_names  = sink_names(sources_raw)

        # ── Output ────────────────────────────────────────────────────────────
        self._root.append(make_section("OUTPUT"))
        out_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        out_card.add_css_class("card")

        if out_names:
            out_model = Gtk.StringList.new(out_names)
            out_combo = Gtk.DropDown(model=out_model)
            out_combo.connect("notify::selected", lambda c, _:
                subprocess.Popen(["pactl", "set-default-sink", out_names[c.get_selected()]]))
            out_card.append(out_combo)

        vol_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vol_lbl = Gtk.Label(label="󰕾  Volume"); vol_lbl.add_css_class("info-key"); vol_row.append(vol_lbl)
        self._vol_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150, 1)
        self._vol_slider.set_value(vol); self._vol_slider.set_hexpand(True)
        self._vol_slider.set_draw_value(True)
        self._vol_slider.connect("value-changed", self._on_vol_changed)
        vol_row.append(self._vol_slider)
        mute_btn = Gtk.Button(label="Mute" if not muted else "Unmute")
        mute_btn.add_css_class("act-btn")
        mute_btn.connect("clicked", lambda b: self._toggle_mute(b))
        self._mute_btn = mute_btn
        vol_row.append(mute_btn)
        out_card.append(vol_row)
        self._root.append(out_card)

        # ── Input ─────────────────────────────────────────────────────────────
        self._root.append(make_section("INPUT"))
        in_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        in_card.add_css_class("card")

        if in_names:
            in_model = Gtk.StringList.new(in_names)
            in_combo = Gtk.DropDown(model=in_model)
            in_combo.connect("notify::selected", lambda c, _:
                subprocess.Popen(["pactl", "set-default-source", in_names[c.get_selected()]]))
            in_card.append(in_combo)

        mic_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        mic_lbl = Gtk.Label(label="  Mic"); mic_lbl.add_css_class("info-key"); mic_row.append(mic_lbl)
        self._mic_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150, 1)
        self._mic_slider.set_value(mic); self._mic_slider.set_hexpand(True)
        self._mic_slider.set_draw_value(True)
        self._mic_slider.connect("value-changed", self._on_mic_changed)
        mic_row.append(self._mic_slider)
        in_card.append(mic_row)
        self._root.append(in_card)

        # ── Per-application volume ─────────────────────────────────────────────
        self._root.append(make_section("APPLICATIONS"))
        refresh_btn = Gtk.Button(label="󰑐  Refresh")
        refresh_btn.add_css_class("act-btn"); refresh_btn.set_halign(Gtk.Align.START)
        refresh_btn.set_margin_bottom(6)
        refresh_btn.connect("clicked", lambda _:
            threading.Thread(target=lambda: GLib.idle_add(
                self._refresh_apps), daemon=True).start())
        self._root.append(refresh_btn)

        self._apps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._root.append(self._apps_box)
        self._render_apps(sink_inputs)

        # ── Advanced ──────────────────────────────────────────────────────────
        self._root.append(make_section("ADVANCED"))
        adv_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        pw_btn = Gtk.Button(label="PipeWire Mixer (qpwgraph)")
        pw_btn.add_css_class("act-btn")
        pw_btn.connect("clicked", lambda _: subprocess.Popen(["qpwgraph"]))
        pav_btn = Gtk.Button(label="Volume Control (pavucontrol)")
        pav_btn.add_css_class("act-btn")
        pav_btn.connect("clicked", lambda _: subprocess.Popen(["pavucontrol"]))
        adv_row.append(pw_btn); adv_row.append(pav_btn)
        self._root.append(adv_row)
        return False

    def _render_apps(self, inputs):
        clear_box(self._apps_box)
        if not inputs:
            lbl = Gtk.Label(label="No applications currently playing audio.")
            lbl.add_css_class("card-desc"); lbl.set_xalign(0)
            self._apps_box.append(lbl)
            return
        for inp in inputs:
            card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            card.add_css_class("card")
            lbl = Gtk.Label(label=inp["name"]); lbl.add_css_class("info-key")
            lbl.set_xalign(0); lbl.set_size_request(140, -1); card.append(lbl)
            slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150, 1)
            slider.set_value(inp["volume"]); slider.set_hexpand(True)
            slider.set_draw_value(True)
            slider.connect("value-changed", lambda s, idx=inp["index"]:
                           self._on_app_vol(idx, int(s.get_value())))
            card.append(slider)
            self._apps_box.append(card)

    def _refresh_apps(self):
        inputs = get_sink_inputs()
        self._render_apps(inputs)
        return False

    def _on_app_vol(self, sink_index, vol):
        tid_key = f"app_{sink_index}"
        if self._app_tids.get(tid_key):
            GLib.source_remove(self._app_tids[tid_key])
        self._app_tids[tid_key] = GLib.timeout_add(80, lambda: (
            subprocess.Popen(["pactl", "set-sink-input-volume", str(sink_index), f"{vol}%"]),
            False)[-1])

    def _on_vol_changed(self, slider):
        if self._vol_tid:
            GLib.source_remove(self._vol_tid)
        v = int(slider.get_value())
        self._vol_tid = GLib.timeout_add(80, lambda: (
            subprocess.Popen(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{v}%"]), False)[-1])

    def _on_mic_changed(self, slider):
        if self._mic_tid:
            GLib.source_remove(self._mic_tid)
        v = int(slider.get_value())
        self._mic_tid = GLib.timeout_add(80, lambda: (
            subprocess.Popen(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", f"{v}%"]), False)[-1])

    def _toggle_mute(self, btn):
        subprocess.Popen(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
        muted = get_mute()
        btn.set_label("Unmute" if muted else "Mute")
