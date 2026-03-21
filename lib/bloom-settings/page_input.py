#!/usr/bin/env python3
"""Bloom Settings — Input Device pages: Keyboard, Mouse & Touchpad, Accessibility."""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib
import subprocess, threading, os

from common import make_header, make_section, spinner_row, clear_box, sh, gsettings_get


# ── Keyboard Page ─────────────────────────────────────────────────────────────

class KeyboardPage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Keyboard", "Layout, input method, and key repeat settings."))
        self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._root.append(spinner_row("Reading keyboard settings…"))
        self.append(self._root)
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        locale_raw = sh(["localectl", "status"])
        layout = ""
        variant = ""
        for line in locale_raw.splitlines():
            if "X11 Layout" in line:
                layout = line.split(":", 1)[1].strip()
            elif "X11 Variant" in line:
                variant = line.split(":", 1)[1].strip()
        # Key repeat: xset q shows rates
        xset_raw = sh(["xset", "q"])
        rate = 300; delay = 400
        for line in xset_raw.splitlines():
            if "repeat rate" in line.lower() or "key repeat" in line.lower():
                parts = line.split()
                try:
                    idx = [p.lower() for p in parts].index("rate")
                    rate = int(parts[idx + 1])
                except (ValueError, IndexError):
                    pass
                try:
                    idx = [p.lower() for p in parts].index("delay")
                    delay = int(parts[idx + 1])
                except (ValueError, IndexError):
                    pass
        GLib.idle_add(self._populate, layout, variant, rate, delay)

    def _populate(self, layout, variant, rate, delay):
        clear_box(self._root)

        # Current layout info
        self._root.append(make_section("CURRENT LAYOUT"))
        info_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        info_card.add_css_class("card")
        layout_lbl = Gtk.Label(label=f"Layout: {layout or 'us'}  Variant: {variant or 'default'}")
        layout_lbl.add_css_class("card-desc"); layout_lbl.set_xalign(0)
        info_card.append(layout_lbl)
        self._root.append(info_card)

        # Layout picker
        self._root.append(make_section("CHANGE LAYOUT"))
        layout_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        layout_card.add_css_class("card")
        ll = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); ll.set_hexpand(True)
        ll.append(Gtk.Label(label="Keyboard Layout", css_classes=["card-name"], xalign=0))
        ll.append(Gtk.Label(label="Applies to console and X11", css_classes=["card-desc"], xalign=0))
        layout_card.append(ll)
        layouts = ["us", "gb", "de", "fr", "es", "it", "pl", "ru", "pt", "nl",
                   "se", "no", "fi", "dk", "cz", "hu", "ro", "tr", "jp", "cn",
                   "ar", "he", "ko", "th", "uk", "az", "be", "bg", "ca", "cs"]
        kb_model = Gtk.StringList.new(layouts)
        kb_combo = Gtk.DropDown(model=kb_model); kb_combo.set_valign(Gtk.Align.CENTER)
        cur = layout.split(",")[0].strip() if layout else "us"
        if cur in layouts:
            kb_combo.set_selected(layouts.index(cur))
        apply_btn = Gtk.Button(label="Apply"); apply_btn.add_css_class("act-btn")
        apply_btn.set_valign(Gtk.Align.CENTER)
        apply_btn.connect("clicked", lambda _, c=kb_combo, ls=layouts:
                          subprocess.Popen(["pkexec", "localectl", "set-keymap", ls[c.get_selected()]]))
        layout_card.append(kb_combo); layout_card.append(apply_btn)
        self._root.append(layout_card)

        # Input method
        self._root.append(make_section("INPUT METHOD"))
        im_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        im_card.add_css_class("card")
        iml = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); iml.set_hexpand(True)
        iml.append(Gtk.Label(label="Input Method Framework", css_classes=["card-name"], xalign=0))
        iml.append(Gtk.Label(label="For CJK and special character input",
                             css_classes=["card-desc"], xalign=0))
        im_card.append(iml)
        im_row = Gtk.Box(spacing=6); im_row.set_valign(Gtk.Align.CENTER)
        fcitx_btn = Gtk.Button(label="Fcitx5"); fcitx_btn.add_css_class("act-btn")
        fcitx_btn.connect("clicked", lambda _: subprocess.Popen(["fcitx5-configtool"]))
        ibus_btn = Gtk.Button(label="IBus"); ibus_btn.add_css_class("act-btn")
        ibus_btn.connect("clicked", lambda _: subprocess.Popen(["ibus-setup"]))
        im_row.append(fcitx_btn); im_row.append(ibus_btn)
        im_card.append(im_row)
        self._root.append(im_card)

        # Key repeat
        self._root.append(make_section("KEY REPEAT"))
        repeat_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        repeat_card.add_css_class("card")

        delay_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        delay_row.append(Gtk.Label(label="Repeat delay (ms)", css_classes=["info-key"]))
        self._delay_spin = Gtk.SpinButton.new_with_range(100, 2000, 50)
        self._delay_spin.set_value(delay); delay_row.append(self._delay_spin)
        repeat_card.append(delay_row)

        rate_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        rate_row.append(Gtk.Label(label="Repeat rate (keys/s)", css_classes=["info-key"]))
        self._rate_spin = Gtk.SpinButton.new_with_range(1, 100, 1)
        self._rate_spin.set_value(rate); rate_row.append(self._rate_spin)
        repeat_card.append(rate_row)

        apply_repeat = Gtk.Button(label="Apply Repeat Settings")
        apply_repeat.add_css_class("act-btn"); apply_repeat.set_halign(Gtk.Align.START)
        apply_repeat.connect("clicked", lambda _: self._apply_repeat())
        repeat_card.append(apply_repeat)
        self._root.append(repeat_card)
        return False

    def _apply_repeat(self):
        delay = int(self._delay_spin.get_value())
        rate  = int(self._rate_spin.get_value())
        subprocess.Popen(["xset", "r", "rate", str(delay), str(rate)])
        # Also apply via hyprctl for Wayland
        subprocess.Popen(["hyprctl", "keyword", "input:repeat_delay", str(delay)])
        subprocess.Popen(["hyprctl", "keyword", "input:repeat_rate", str(rate)])


# ── Mouse & Touchpad Page ─────────────────────────────────────────────────────

class MouseTouchpadPage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Mouse & Touchpad", "Pointer speed, scrolling and gesture settings."))
        self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._root.append(spinner_row("Reading pointer settings…"))
        self.append(self._root)
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        speed    = gsettings_get("org.gnome.desktop.peripherals.mouse",     "speed",           "0")
        nat_scroll = gsettings_get("org.gnome.desktop.peripherals.mouse",   "natural-scroll",  "false")
        tp_speed = gsettings_get("org.gnome.desktop.peripherals.touchpad",  "speed",           "0")
        tap      = gsettings_get("org.gnome.desktop.peripherals.touchpad",  "tap-to-click",    "false")
        tp_nat   = gsettings_get("org.gnome.desktop.peripherals.touchpad",  "natural-scroll",  "true")
        two_finger= gsettings_get("org.gnome.desktop.peripherals.touchpad", "two-finger-scrolling-enabled", "true")
        GLib.idle_add(self._populate, speed, nat_scroll, tp_speed, tap, tp_nat, two_finger)

    def _populate(self, speed, nat_scroll, tp_speed, tap, tp_nat, two_finger):
        clear_box(self._root)

        # ── Mouse ─────────────────────────────────────────────────────────────
        self._root.append(make_section("MOUSE"))
        mouse_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        mouse_card.add_css_class("card")

        spd_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        spd_row.append(Gtk.Label(label="Pointer speed", css_classes=["info-key"]))
        spd_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -1.0, 1.0, 0.1)
        try: spd_slider.set_value(float(speed))
        except: spd_slider.set_value(0.0)
        spd_slider.set_hexpand(True); spd_slider.set_draw_value(True)
        spd_slider.connect("value-changed", lambda s: subprocess.Popen([
            "gsettings", "set", "org.gnome.desktop.peripherals.mouse",
            "speed", str(round(s.get_value(), 2))]))
        spd_row.append(spd_slider)
        mouse_card.append(spd_row)

        nat_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        nat_lbl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); nat_lbl.set_hexpand(True)
        nat_lbl.append(Gtk.Label(label="Natural scrolling", css_classes=["card-name"], xalign=0))
        nat_lbl.append(Gtk.Label(label="Scroll content in the same direction as finger movement",
                                css_classes=["card-desc"], xalign=0))
        nat_row.append(nat_lbl)
        nat_sw = Gtk.Switch(); nat_sw.set_active(nat_scroll.lower() == "true")
        nat_sw.set_valign(Gtk.Align.CENTER)
        nat_sw.connect("notify::active", lambda s, _: subprocess.Popen([
            "gsettings", "set", "org.gnome.desktop.peripherals.mouse",
            "natural-scroll", "true" if s.get_active() else "false"]))
        nat_row.append(nat_sw)
        mouse_card.append(nat_row)
        self._root.append(mouse_card)

        # ── Touchpad ──────────────────────────────────────────────────────────
        self._root.append(make_section("TOUCHPAD"))
        tp_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        tp_card.add_css_class("card")

        tp_spd_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        tp_spd_row.append(Gtk.Label(label="Touchpad speed", css_classes=["info-key"]))
        tp_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -1.0, 1.0, 0.1)
        try: tp_slider.set_value(float(tp_speed))
        except: tp_slider.set_value(0.0)
        tp_slider.set_hexpand(True); tp_slider.set_draw_value(True)
        tp_slider.connect("value-changed", lambda s: subprocess.Popen([
            "gsettings", "set", "org.gnome.desktop.peripherals.touchpad",
            "speed", str(round(s.get_value(), 2))]))
        tp_spd_row.append(tp_slider)
        tp_card.append(tp_spd_row)

        for label, desc, key, schema, val in [
            ("Tap to click",         "Click by tapping the touchpad",
             "tap-to-click",         "org.gnome.desktop.peripherals.touchpad", tap),
            ("Natural scrolling",    "Scroll in the same direction as finger movement",
             "natural-scroll",       "org.gnome.desktop.peripherals.touchpad", tp_nat),
            ("Two-finger scrolling", "Use two fingers to scroll",
             "two-finger-scrolling-enabled", "org.gnome.desktop.peripherals.touchpad", two_finger),
        ]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            lbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); lbox.set_hexpand(True)
            lbox.append(Gtk.Label(label=label, css_classes=["card-name"], xalign=0))
            lbox.append(Gtk.Label(label=desc, css_classes=["card-desc"], xalign=0))
            row.append(lbox)
            sw = Gtk.Switch(); sw.set_active(val.lower() == "true")
            sw.set_valign(Gtk.Align.CENTER)
            sw.connect("notify::active", lambda s, _, k=key, sc=schema: subprocess.Popen([
                "gsettings", "set", sc, k, "true" if s.get_active() else "false"]))
            row.append(sw)
            tp_card.append(row)

        self._root.append(tp_card)

        # ── Acceleration ──────────────────────────────────────────────────────
        self._root.append(make_section("ACCELERATION"))
        accel_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        accel_card.add_css_class("card")
        al = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); al.set_hexpand(True)
        al.append(Gtk.Label(label="Acceleration profile", css_classes=["card-name"], xalign=0))
        al.append(Gtk.Label(label="Adaptive adjusts speed based on movement; flat is linear",
                           css_classes=["card-desc"], xalign=0))
        accel_card.append(al)
        profiles = ["adaptive", "flat"]
        accel_model = Gtk.StringList.new(profiles)
        cur_accel = gsettings_get("org.gnome.desktop.peripherals.mouse", "accel-profile", "adaptive")
        accel_combo = Gtk.DropDown(model=accel_model); accel_combo.set_valign(Gtk.Align.CENTER)
        if cur_accel in profiles:
            accel_combo.set_selected(profiles.index(cur_accel))
        accel_combo.connect("notify::selected", lambda c, _: subprocess.Popen([
            "gsettings", "set", "org.gnome.desktop.peripherals.mouse",
            "accel-profile", profiles[c.get_selected()]]))
        accel_card.append(accel_combo)
        self._root.append(accel_card)
        return False


# ── Accessibility Page ────────────────────────────────────────────────────────

class AccessibilityPage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Accessibility", "Visual, motor, and assistive technology settings."))
        self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._root.append(spinner_row("Reading accessibility settings…"))
        self.append(self._root)
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        scale = gsettings_get("org.gnome.desktop.interface", "text-scaling-factor", "1.0")
        theme = gsettings_get("org.gnome.desktop.interface", "gtk-theme", "Adwaita-dark")
        hc    = "high-contrast" in theme.lower()
        sticky_keys  = gsettings_get("org.gnome.desktop.a11y.keyboard", "stickykeys-enable",  "false")
        bounce_keys  = gsettings_get("org.gnome.desktop.a11y.keyboard", "bouncekeys-enable",  "false")
        slow_keys    = gsettings_get("org.gnome.desktop.a11y.keyboard", "slowkeys-enable",    "false")
        mouse_keys   = gsettings_get("org.gnome.desktop.a11y.keyboard", "mousekeys-enable",   "false")
        GLib.idle_add(self._populate, scale, hc, sticky_keys, bounce_keys, slow_keys, mouse_keys)

    def _populate(self, scale, hc, sticky_keys, bounce_keys, slow_keys, mouse_keys):
        clear_box(self._root)

        # ── Visual ────────────────────────────────────────────────────────────
        self._root.append(make_section("VISUAL"))
        vis_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vis_card.add_css_class("card")

        # Large text
        lt_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        ltl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); ltl.set_hexpand(True)
        ltl.append(Gtk.Label(label="Large text", css_classes=["card-name"], xalign=0))
        ltl.append(Gtk.Label(label="Increases text size across the desktop",
                            css_classes=["card-desc"], xalign=0))
        lt_row.append(ltl)
        lt_sw = Gtk.Switch(); lt_sw.set_active(float(scale) > 1.1)
        lt_sw.set_valign(Gtk.Align.CENTER)
        lt_sw.connect("notify::active", lambda s, _: subprocess.Popen([
            "gsettings", "set", "org.gnome.desktop.interface",
            "text-scaling-factor", "1.3" if s.get_active() else "1.0"]))
        lt_row.append(lt_sw)
        vis_card.append(lt_row)

        # High contrast
        hc_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hcl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); hcl.set_hexpand(True)
        hcl.append(Gtk.Label(label="High contrast", css_classes=["card-name"], xalign=0))
        hcl.append(Gtk.Label(label="Increases contrast between UI elements",
                            css_classes=["card-desc"], xalign=0))
        hc_row.append(hcl)
        hc_sw = Gtk.Switch(); hc_sw.set_active(hc)
        hc_sw.set_valign(Gtk.Align.CENTER)
        hc_sw.connect("notify::active", lambda s, _: subprocess.Popen([
            "gsettings", "set", "org.gnome.desktop.interface",
            "gtk-theme", "HighContrast" if s.get_active() else "Adwaita-dark"]))
        hc_row.append(hc_sw)
        vis_card.append(hc_row)
        self._root.append(vis_card)

        # ── Keyboard Accessibility ─────────────────────────────────────────────
        self._root.append(make_section("KEYBOARD ACCESSIBILITY"))
        kb_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        kb_card.add_css_class("card")

        for label, desc, key, val in [
            ("Sticky keys",  "Press modifier keys (Shift, Ctrl) one at a time",
             "stickykeys-enable",  sticky_keys),
            ("Bounce keys",  "Ignore rapid repeated key presses",
             "bouncekeys-enable",  bounce_keys),
            ("Slow keys",    "Add a delay between pressing and registering a key",
             "slowkeys-enable",    slow_keys),
            ("Mouse keys",   "Control the mouse pointer using the numeric keypad",
             "mousekeys-enable",   mouse_keys),
        ]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            lbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); lbox.set_hexpand(True)
            lbox.append(Gtk.Label(label=label, css_classes=["card-name"], xalign=0))
            lbox.append(Gtk.Label(label=desc, css_classes=["card-desc"], xalign=0))
            row.append(lbox)
            sw = Gtk.Switch(); sw.set_active(val.lower() == "true")
            sw.set_valign(Gtk.Align.CENTER)
            sw.connect("notify::active", lambda s, _, k=key: subprocess.Popen([
                "gsettings", "set", "org.gnome.desktop.a11y.keyboard",
                k, "true" if s.get_active() else "false"]))
            row.append(sw)
            kb_card.append(row)

        self._root.append(kb_card)

        # ── Screen Reader ──────────────────────────────────────────────────────
        self._root.append(make_section("SCREEN READER"))
        sr_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        sr_card.add_css_class("card")
        srl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); srl.set_hexpand(True)
        srl.append(Gtk.Label(label="Orca Screen Reader", css_classes=["card-name"], xalign=0))
        srl.append(Gtk.Label(label="Full-featured screen reader. Start with Super+Alt+S",
                            css_classes=["card-desc"], xalign=0))
        sr_card.append(srl)
        orca_btn = Gtk.Button(label="Launch Orca"); orca_btn.add_css_class("act-btn")
        orca_btn.set_valign(Gtk.Align.CENTER)
        orca_btn.connect("clicked", lambda _: subprocess.Popen(["orca"]))
        sr_card.append(orca_btn)
        self._root.append(sr_card)
        return False
