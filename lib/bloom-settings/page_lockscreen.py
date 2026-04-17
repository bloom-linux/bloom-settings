#!/usr/bin/env python3
"""Bloom Settings — Lock Screen page (hyprlock configuration)"""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib
import os, threading, configparser

from common import (
    make_header, make_section, spinner_row, clear_box,
    read_bloom_colors,
)

HYPRLOCK_CONF  = os.path.expanduser("~/.config/hypr/hyprlock.conf")
BLOOM_LOCK_INI = os.path.expanduser("~/.config/bloom/hyprlock.ini")
WALLPAPER_DIR  = "/usr/share/wallpapers/bloom"
PIXMAPS_DIR    = "/usr/share/pixmaps"

LOGO_OPTIONS = [
    ("White",     f"{PIXMAPS_DIR}/bloom-white.png"),
    ("Colorful",  f"{PIXMAPS_DIR}/bloom-color.png"),
    ("Icon",      f"{PIXMAPS_DIR}/bloom-icon.png"),
    ("None",      ""),
]


# ── Config I/O ────────────────────────────────────────────────────────────────

def _read_lock_cfg():
    cp = configparser.ConfigParser()
    if os.path.exists(BLOOM_LOCK_INI):
        try:
            cp.read(BLOOM_LOCK_INI)
        except Exception:
            pass

    def g(sec, key, default):
        try:
            return cp.get(sec, key).strip()
        except Exception:
            return default

    return {
        "bg_type":       g("Background", "type",          "wallpaper"),
        "wallpaper":     g("Background", "wallpaper",
                           f"{WALLPAPER_DIR}/bloom-wallpaper.png"),
        "blur_passes":   int(g("Background", "blur_passes",   "4")),
        "blur_size":     int(g("Background", "blur_size",     "6")),
        "brightness":    float(g("Background", "brightness",  "0.7")),
        "overlay_alpha": int(g("Background", "overlay_alpha", "47")),
        "logo":          g("Elements", "logo",          "White"),
        "show_clock":    g("Clock",    "show",          "true") == "true",
        "clock_size":    int(g("Clock",      "font_size",     "88")),
        "show_date":     g("Elements", "show_date",     "true") == "true",
        "show_username": g("Elements", "show_username", "true") == "true",
    }


def _write_lock_cfg(cfg):
    cp = configparser.ConfigParser()
    cp["Background"] = {
        "type":          cfg["bg_type"],
        "wallpaper":     cfg["wallpaper"],
        "blur_passes":   str(cfg["blur_passes"]),
        "blur_size":     str(cfg["blur_size"]),
        "brightness":    str(cfg["brightness"]),
        "overlay_alpha": str(cfg["overlay_alpha"]),
    }
    cp["Clock"] = {
        "font_size": str(cfg["clock_size"]),
        "show":      "true" if cfg["show_clock"] else "false",
    }
    cp["Elements"] = {
        "logo":          cfg["logo"],
        "show_date":     "true" if cfg["show_date"] else "false",
        "show_username": "true" if cfg["show_username"] else "false",
    }
    os.makedirs(os.path.dirname(BLOOM_LOCK_INI), exist_ok=True)
    with open(BLOOM_LOCK_INI, "w") as f:
        cp.write(f)


def _generate_hyprlock_conf(cfg):
    """Regenerate ~/.config/hypr/hyprlock.conf from current settings."""
    colors  = read_bloom_colors()
    bg_hex  = colors["bg"].lstrip("#")
    acc_hex = colors["accent"].lstrip("#")
    txt_hex = colors["text"].lstrip("#")
    dim_hex = colors["text_dim"].lstrip("#")

    bg_path     = "screenshot" if cfg["bg_type"] == "screenshot" else cfg["wallpaper"]
    ov_alpha    = format(round(cfg["overlay_alpha"] * 255 / 100), "02x")
    blur_passes = max(0, cfg["blur_passes"])

    # Resolve logo path from style name
    logo_path = ""
    for name, path in LOGO_OPTIONS:
        if name == cfg["logo"]:
            logo_path = path
            break

    L = []

    L += [
        "general {",
        "    hide_cursor = true",
        "}",
        "",
        "background {",
        "    monitor =",
        f"    path = {bg_path}",
        f"    blur_passes = {blur_passes}",
    ]
    if blur_passes > 0:
        L += [
            f"    blur_size = {cfg['blur_size']}",
            "    noise = 0.015",
            "    contrast = 0.9",
            f"    brightness = {cfg['brightness']:.1f}",
            "    vibrancy = 0.1",
            "    vibrancy_darkness = 0.0",
        ]
    L += ["}", ""]

    L += [
        "shape {",
        "    monitor =",
        "    size = 3840, 2160",
        f"    color = rgba({bg_hex}{ov_alpha})",
        "    rounding = 0",
        "    border_size = 0",
        "    position = 0, 0",
        "    halign = center",
        "    valign = center",
        "}",
        "",
    ]

    if logo_path and os.path.exists(logo_path):
        L += [
            "image {",
            "    monitor =",
            f"    path = {logo_path}",
            "    size = 100",
            "    rounding = -1",
            "    position = 0, 230",
            "    halign = center",
            "    valign = center",
            "    shadow_passes = 2",
            "    shadow_size = 8",
            "    shadow_color = rgba(00000055)",
            "}",
            "",
        ]

    if cfg["show_clock"]:
        L += [
            "label {",
            "    monitor =",
            '    text = cmd[update:1000] echo "<b>$(date +"%-H:%M")</b>"',
            f"    color = rgba({txt_hex}ff)",
            f"    font_size = {cfg['clock_size']}",
            "    font_family = JetBrainsMono Nerd Font Mono",
            "    position = 0, 90",
            "    halign = center",
            "    valign = center",
            "    shadow_passes = 2",
            "    shadow_size = 4",
            "    shadow_color = rgba(00000055)",
            "}",
            "",
        ]

    if cfg["show_date"]:
        L += [
            "label {",
            "    monitor =",
            '    text = cmd[update:60000] echo "$(date +"%A, %B %-d")"',
            f"    color = rgba({txt_hex}bb)",
            "    font_size = 18",
            "    font_family = JetBrainsMono Nerd Font",
            "    position = 0, 20",
            "    halign = center",
            "    valign = center",
            "    shadow_passes = 1",
            "    shadow_size = 3",
            "    shadow_color = rgba(00000044)",
            "}",
            "",
        ]

    L += [
        "input-field {",
        "    monitor =",
        "    size = 320, 52",
        "    outline_thickness = 2",
        "    dots_size = 0.27",
        "    dots_spacing = 0.31",
        "    dots_center = true",
        "    dots_rounding = -1",
        f"    outer_color = rgba({acc_hex}55)",
        f"    inner_color = rgba({bg_hex}dd)",
        f"    font_color = rgba({txt_hex}ff)",
        "    font_family = JetBrainsMono Nerd Font",
        "    fade_on_empty = true",
        "    fade_timeout = 1200",
        f'    placeholder_text = <span foreground="##{dim_hex}">  Enter password</span>',
        "    hide_input = false",
        "    rounding = 14",
        f"    check_color = rgba({acc_hex}ff)",
        "    fail_color = rgba(ff5555ff)",
        '    fail_text = <i>$FAIL <b>($ATTEMPTS)</b></i>',
        "    capslock_color = rgba(ffaa00ff)",
        "    position = 0, -90",
        "    halign = center",
        "    valign = center",
        "}",
    ]

    if cfg["show_username"]:
        L += [
            "",
            "label {",
            "    monitor =",
            "    text =   $USER",
            f"    color = rgba({dim_hex}cc)",
            "    font_size = 13",
            "    font_family = JetBrainsMono Nerd Font",
            "    position = 0, -158",
            "    halign = center",
            "    valign = center",
            "}",
        ]

    os.makedirs(os.path.dirname(HYPRLOCK_CONF), exist_ok=True)
    with open(HYPRLOCK_CONF, "w") as f:
        f.write("\n".join(L) + "\n")


def _list_wallpapers():
    result = []
    if os.path.isdir(WALLPAPER_DIR):
        for name in sorted(os.listdir(WALLPAPER_DIR)):
            if name.lower().endswith(".png"):
                display = name.replace("-", " ").replace(".png", "").title()
                result.append((display, os.path.join(WALLPAPER_DIR, name)))
    return result


# ── Page ──────────────────────────────────────────────────────────────────────

class LockScreenPage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._win     = win_ref
        self._cfg     = {}
        self._pending = {}

        # Scrollable content area
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self._inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._inner.set_margin_top(32)
        self._inner.set_margin_bottom(16)
        self._inner.set_margin_start(40)
        self._inner.set_margin_end(40)
        self._inner.append(make_header(
            "Lock Screen",
            "Customize hyprlock — background, blur, clock, and visible elements.",
        ))
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._content.append(spinner_row("Loading lock screen settings…"))
        self._inner.append(self._content)
        scroll.set_child(self._inner)
        self.append(scroll)

        # Action bar — hidden until there are unsaved changes
        self._action_sep = Gtk.Separator()
        self._action_sep.set_visible(False)
        self.append(self._action_sep)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bar.add_css_class("action-bar")
        bar.set_visible(False)
        self._action_bar = bar

        info = Gtk.Label(label="You have unsaved changes")
        info.add_css_class("action-bar-info")
        info.set_hexpand(True)
        info.set_xalign(0)
        bar.append(info)

        discard_btn = Gtk.Button(label="Discard")
        discard_btn.add_css_class("act-btn")
        discard_btn.connect("clicked", lambda _: self._discard())
        bar.append(discard_btn)

        apply_btn = Gtk.Button(label="Apply")
        apply_btn.add_css_class("act-btn")
        apply_btn.add_css_class("primary")
        apply_btn.connect("clicked", lambda _: self._apply_all())
        bar.append(apply_btn)

        self.append(bar)
        threading.Thread(target=self._do_load, daemon=True).start()

    # ── Load ──────────────────────────────────────────────────────────────────

    def _do_load(self):
        cfg        = _read_lock_cfg()
        wallpapers = _list_wallpapers()
        GLib.idle_add(self._populate, cfg, wallpapers)

    def _populate(self, cfg, wallpapers):
        self._cfg     = cfg.copy()
        self._pending = cfg.copy()
        clear_box(self._content)

        # ── Background ───────────────────────────────────────────────────────
        self._content.append(make_section("BACKGROUND"))

        type_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        type_box.set_margin_bottom(8)
        wp_btn = Gtk.ToggleButton(label="Wallpaper")
        wp_btn.add_css_class("act-btn")
        sc_btn = Gtk.ToggleButton(label="Screenshot")
        sc_btn.add_css_class("act-btn")
        sc_btn.set_group(wp_btn)
        if cfg["bg_type"] == "screenshot":
            sc_btn.set_active(True)
        else:
            wp_btn.set_active(True)
        type_box.append(wp_btn)
        type_box.append(sc_btn)
        self._content.append(type_box)

        wp_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        wp_row.add_css_class("card")
        wp_row.set_margin_bottom(4)
        wp_lbl = Gtk.Label(label="Wallpaper")
        wp_lbl.add_css_class("card-name")
        wp_lbl.set_xalign(0)
        wp_lbl.set_hexpand(True)

        wp_paths = [w[1] for w in wallpapers]
        wp_store = Gtk.StringList.new([w[0] for w in wallpapers])
        wp_combo = Gtk.DropDown.new(wp_store, None)
        wp_combo.set_size_request(220, -1)
        if cfg["wallpaper"] in wp_paths:
            wp_combo.set_selected(wp_paths.index(cfg["wallpaper"]))

        wp_row.append(wp_lbl)
        wp_row.append(wp_combo)
        self._content.append(wp_row)
        wp_row.set_visible(cfg["bg_type"] != "screenshot")

        def _on_type(btn):
            is_wp = wp_btn.get_active()
            wp_row.set_visible(is_wp)
            self._set_pending("bg_type", "wallpaper" if is_wp else "screenshot")

        wp_btn.connect("toggled", _on_type)

        def _on_wp(combo, _):
            idx = combo.get_selected()
            if 0 <= idx < len(wp_paths):
                self._set_pending("wallpaper", wp_paths[idx])

        wp_combo.connect("notify::selected", _on_wp)

        # ── Blur ─────────────────────────────────────────────────────────────
        self._content.append(make_section("BLUR"))
        self._content.append(self._slider_row(
            "Blur Passes", "Number of blur passes — 0 disables blur",
            0, 5, cfg["blur_passes"],
            lambda v: self._set_pending("blur_passes", round(v)),
        ))
        self._content.append(self._slider_row(
            "Blur Size", "Radius of each blur pass",
            2, 12, cfg["blur_size"],
            lambda v: self._set_pending("blur_size", round(v)),
        ))
        self._content.append(self._slider_row(
            "Brightness", "Background brightness",
            1, 10, round(cfg["brightness"] * 10),
            lambda v: self._set_pending("brightness", round(v / 10, 1)),
            fmt=lambda v: f"{v / 10:.1f}",
        ))
        self._content.append(self._slider_row(
            "Overlay Darkness", "Dark tint over background",
            0, 100, cfg["overlay_alpha"],
            lambda v: self._set_pending("overlay_alpha", round(v)),
            fmt=lambda v: f"{int(v)}%",
        ))

        # ── Clock ─────────────────────────────────────────────────────────────
        self._content.append(make_section("CLOCK & DATE"))
        self._content.append(self._toggle_row(
            "Show Clock", cfg["show_clock"],
            lambda v: self._set_pending("show_clock", v),
        ))
        self._content.append(self._slider_row(
            "Clock Size", "Font size for the clock",
            40, 120, cfg["clock_size"],
            lambda v: self._set_pending("clock_size", round(v)),
        ))
        self._content.append(self._toggle_row(
            "Show Date", cfg["show_date"],
            lambda v: self._set_pending("show_date", v),
        ))

        # ── Elements ─────────────────────────────────────────────────────────
        self._content.append(make_section("ELEMENTS"))

        # Logo style dropdown
        logo_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        logo_row.add_css_class("card")
        logo_row.set_margin_bottom(4)
        logo_lbl = Gtk.Label(label="Logo Style")
        logo_lbl.add_css_class("card-name")
        logo_lbl.set_xalign(0)
        logo_lbl.set_hexpand(True)
        logo_desc = Gtk.Label(label="White · Colorful · Icon · None")
        logo_desc.add_css_class("card-desc")

        logo_names  = [o[0] for o in LOGO_OPTIONS]
        # Only show options where the file exists (or "None")
        avail_names = [
            n for n, p in LOGO_OPTIONS
            if not p or os.path.exists(p)
        ]
        logo_store = Gtk.StringList.new(avail_names)
        logo_combo = Gtk.DropDown.new(logo_store, None)
        logo_combo.set_size_request(140, -1)
        cur_logo = cfg["logo"] if cfg["logo"] in avail_names else avail_names[0]
        logo_combo.set_selected(avail_names.index(cur_logo))

        logo_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        logo_col.set_hexpand(True)
        logo_col.append(logo_lbl)
        logo_col.append(logo_desc)
        logo_row.append(logo_col)
        logo_row.append(logo_combo)
        self._content.append(logo_row)

        def _on_logo(combo, _):
            idx = combo.get_selected()
            if 0 <= idx < len(avail_names):
                self._set_pending("logo", avail_names[idx])

        logo_combo.connect("notify::selected", _on_logo)

        self._content.append(self._toggle_row(
            "Show Username", cfg["show_username"],
            lambda v: self._set_pending("show_username", v),
        ))

    # ── Widgets ───────────────────────────────────────────────────────────────

    def _slider_row(self, label, desc, min_val, max_val, value, on_change, fmt=None):
        if fmt is None:
            fmt = lambda v: str(int(v))

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class("card")
        card.set_margin_bottom(4)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        lbl = Gtk.Label(label=label)
        lbl.add_css_class("card-name")
        lbl.set_xalign(0)
        lbl.set_hexpand(True)
        val_lbl = Gtk.Label(label=fmt(value))
        val_lbl.add_css_class("badge")
        top.append(lbl)
        top.append(val_lbl)

        desc_lbl = Gtk.Label(label=desc)
        desc_lbl.add_css_class("card-desc")
        desc_lbl.set_xalign(0)

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, min_val, max_val, 1)
        scale.set_value(value)
        scale.set_hexpand(True)
        scale.set_draw_value(False)

        def _changed(s, _v=val_lbl, _cb=on_change, _fmt=fmt):
            v = s.get_value()
            _v.set_label(_fmt(v))
            _cb(v)

        scale.connect("value-changed", _changed)
        card.append(top)
        card.append(desc_lbl)
        card.append(scale)
        return card

    def _toggle_row(self, label, value, on_change):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.add_css_class("card")
        row.set_margin_bottom(4)

        lbl = Gtk.Label(label=label)
        lbl.add_css_class("card-name")
        lbl.set_xalign(0)
        lbl.set_hexpand(True)

        sw = Gtk.Switch()
        sw.set_active(value)
        sw.set_valign(Gtk.Align.CENTER)

        def _toggled(s, _):
            on_change(s.get_active())
            self._mark_dirty()

        sw.connect("notify::active", _toggled)
        row.append(lbl)
        row.append(sw)
        return row

    # ── State ─────────────────────────────────────────────────────────────────

    def _set_pending(self, key, value):
        self._pending[key] = value
        self._mark_dirty()

    def _mark_dirty(self):
        self._action_bar.set_visible(True)
        self._action_sep.set_visible(True)

    def _apply_all(self):
        _write_lock_cfg(self._pending)
        _generate_hyprlock_conf(self._pending)
        self._cfg = self._pending.copy()
        self._action_bar.set_visible(False)
        self._action_sep.set_visible(False)

    def _discard(self):
        self._pending = self._cfg.copy()
        self._action_bar.set_visible(False)
        self._action_sep.set_visible(False)
        threading.Thread(target=self._do_load, daemon=True).start()
