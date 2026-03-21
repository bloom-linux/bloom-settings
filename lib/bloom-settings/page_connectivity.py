#!/usr/bin/env python3
"""Bloom Settings — Connectivity pages: Network, Bluetooth."""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib
import subprocess, threading, os

from common import (
    make_header, make_section, spinner_row, clear_box, text_entry,
    TermWindow, sh,
)


# ── Network Page ──────────────────────────────────────────────────────────────

class NetworkPage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Network", "Wireless and wired connections."))
        self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.append(self._root)
        self._load()

    def _load(self):
        clear_box(self._root)
        self._root.append(spinner_row("Scanning networks…"))
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        wifi_enabled = "enabled" in sh(["nmcli", "radio", "wifi"]).lower()
        sh(["nmcli", "dev", "wifi", "rescan"])
        wifi_raw = sh(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE", "dev", "wifi", "list"])
        wired_raw = sh(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev", "status"])
        GLib.idle_add(self._populate, wifi_enabled, wifi_raw, wired_raw)

    def _parse_wifi(self, raw):
        nets = {}
        for line in raw.splitlines():
            # rsplit on last 3 colons to handle SSIDs with colons
            parts = line.rsplit(":", 3)
            if len(parts) < 4:
                continue
            ssid = parts[0]
            if not ssid:
                continue
            try:
                signal = int(parts[1])
            except ValueError:
                signal = 0
            security = parts[2]
            in_use = parts[3].strip() == "*"
            # Deduplicate, keep strongest signal or connected
            if ssid not in nets or in_use or signal > nets[ssid]["signal"]:
                nets[ssid] = {"ssid": ssid, "signal": signal,
                              "security": security, "in_use": in_use}
        return sorted(nets.values(), key=lambda x: (not x["in_use"], -x["signal"]))

    def _populate(self, wifi_enabled, wifi_raw, wired_raw):
        clear_box(self._root)

        # ── WiFi toggle ───────────────────────────────────────────────────────
        wifi_ctrl = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        wifi_ctrl.add_css_class("card")
        wl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); wl.set_hexpand(True)
        wl.append(Gtk.Label(label="Wi-Fi", css_classes=["card-name"], xalign=0))
        self._wifi_status = Gtk.Label(label="Enabled" if wifi_enabled else "Disabled")
        self._wifi_status.add_css_class("card-desc"); self._wifi_status.set_xalign(0)
        wl.append(self._wifi_status)
        wifi_ctrl.append(wl)
        wifi_sw = Gtk.Switch(); wifi_sw.set_active(wifi_enabled); wifi_sw.set_valign(Gtk.Align.CENTER)
        wifi_sw.connect("notify::active", lambda s, _: self._toggle_wifi(s.get_active()))
        wifi_ctrl.append(wifi_sw)
        scan_btn = Gtk.Button(label="󰑐  Scan"); scan_btn.add_css_class("act-btn")
        scan_btn.set_valign(Gtk.Align.CENTER)
        scan_btn.connect("clicked", lambda _: self._load())
        wifi_ctrl.append(scan_btn)
        self._root.append(wifi_ctrl)

        # ── Networks ──────────────────────────────────────────────────────────
        if wifi_enabled:
            self._root.append(make_section("AVAILABLE NETWORKS"))
            networks = self._parse_wifi(wifi_raw)
            if not networks:
                self._root.append(Gtk.Label(label="No networks found.", css_classes=["card-desc"]))
            for net in networks:
                self._root.append(self._net_row(net))

        # ── Wired ─────────────────────────────────────────────────────────────
        self._root.append(make_section("WIRED"))
        for line in wired_raw.splitlines():
            parts = line.split(":")
            if len(parts) < 4:
                continue
            dev, typ, state, con = parts[:4]
            if typ not in ("ethernet",):
                continue
            card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            card.add_css_class("card")
            il = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); il.set_hexpand(True)
            il.append(Gtk.Label(label=dev, css_classes=["card-name"], xalign=0))
            il.append(Gtk.Label(label=f"State: {state}  Connection: {con}", css_classes=["card-desc"], xalign=0))
            card.append(il)
            if "connected" in state:
                badge = Gtk.Label(label="CONNECTED"); badge.add_css_class("badge"); badge.add_css_class("ok")
                card.append(badge)
            self._root.append(card)
        return False

    def _net_row(self, net):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        card.add_css_class("card")

        sig = net["signal"]
        if sig >= 70:   sig_class = "sig-strong"
        elif sig >= 40: sig_class = "sig-medium"
        else:           sig_class = "sig-weak"

        sig_lbl = Gtk.Label(label="▂▄▆█" if sig >= 70 else "▂▄▆ " if sig >= 40 else "▂▄  ")
        sig_lbl.add_css_class(sig_class); card.append(sig_lbl)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); info.set_hexpand(True)
        ssid_lbl = Gtk.Label(label=net["ssid"])
        ssid_lbl.add_css_class("net-active" if net["in_use"] else "card-name")
        ssid_lbl.set_xalign(0); info.append(ssid_lbl)

        details = []
        if net["in_use"]:
            details.append("● Connected")
        if net["security"]:
            details.append("🔒 " + net["security"])
        details.append(f"{sig}%")
        dl = Gtk.Label(label="  ".join(details)); dl.add_css_class("card-desc"); dl.set_xalign(0)
        info.append(dl)
        card.append(info)

        if net["in_use"]:
            dc_btn = Gtk.Button(label="Disconnect"); dc_btn.add_css_class("act-btn"); dc_btn.add_css_class("rm")
            dc_btn.set_valign(Gtk.Align.CENTER)
            dc_btn.connect("clicked", lambda _, s=net["ssid"]: self._disconnect(s))
            card.append(dc_btn)
        else:
            conn_btn = Gtk.Button(label="Connect"); conn_btn.add_css_class("act-btn")
            conn_btn.set_valign(Gtk.Align.CENTER)
            conn_btn.connect("clicked", lambda _, n=net: self._connect_dialog(n))
            card.append(conn_btn)
        return card

    def _toggle_wifi(self, enable):
        state = "on" if enable else "off"
        threading.Thread(target=lambda: (
            subprocess.run(["nmcli", "radio", "wifi", state]),
            GLib.idle_add(self._load)
        ), daemon=True).start()

    def _disconnect(self, ssid):
        threading.Thread(target=lambda: (
            subprocess.run(["nmcli", "con", "down", "id", ssid]),
            GLib.idle_add(self._load)
        ), daemon=True).start()

    def _connect_dialog(self, net):
        if not net["security"]:
            self._do_connect(net["ssid"], "")
            return
        dlg = Gtk.Window(title=f"Connect to {net['ssid']}")
        dlg.set_transient_for(self._win); dlg.set_modal(True); dlg.set_default_size(340, 180)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(24); root.set_margin_bottom(24)
        root.set_margin_start(24); root.set_margin_end(24)
        root.append(Gtk.Label(label=f"Password for \"{net['ssid']}\"",
                              css_classes=["card-name"], xalign=0))
        pass_e = text_entry("Password", password=True); root.append(pass_e)
        btn_row = Gtk.Box(spacing=8); btn_row.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel"); cancel.add_css_class("act-btn")
        cancel.connect("clicked", lambda _: dlg.close())
        ok = Gtk.Button(label="Connect"); ok.add_css_class("act-btn"); ok.add_css_class("primary")
        def do_conn(_):
            passwd = pass_e.get_text()
            dlg.close()
            self._do_connect(net["ssid"], passwd)
        ok.connect("clicked", do_conn)
        btn_row.append(cancel); btn_row.append(ok)
        root.append(btn_row)
        dlg.set_child(root); dlg.present()

    def _do_connect(self, ssid, password):
        cmd = ["nmcli", "dev", "wifi", "connect", ssid]
        if password:
            cmd += ["password", password]
        TermWindow(self._win, f"Connecting to {ssid}", cmd, on_done=self._load)


# ── Bluetooth Page ────────────────────────────────────────────────────────────

class BluetoothPage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Bluetooth", "Paired devices and connections."))
        self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.append(self._root)
        self._load()

    def _load(self):
        clear_box(self._root)
        self._root.append(spinner_row("Reading Bluetooth status…"))
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        controller = sh(["bluetoothctl", "show"])
        powered = "Powered: yes" in controller
        devices_raw = sh(["bluetoothctl", "devices"])
        devices = []
        for line in devices_raw.splitlines():
            # Format: Device AA:BB:CC:DD:EE:FF Name
            parts = line.split(" ", 2)
            if len(parts) == 3 and parts[0] == "Device":
                mac = parts[1]; name = parts[2]
                info = sh(["bluetoothctl", "info", mac])
                connected = "Connected: yes" in info
                paired = "Paired: yes" in info
                devices.append({"mac": mac, "name": name, "connected": connected, "paired": paired})
        GLib.idle_add(self._populate, powered, devices)

    def _populate(self, powered, devices):
        clear_box(self._root)

        if "No default controller available" in sh(["bluetoothctl", "show"]):
            self._root.append(Gtk.Label(label="No Bluetooth adapter found.",
                                        css_classes=["card-desc"]))
            return False

        ctrl_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        ctrl_card.add_css_class("card")
        cl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); cl.set_hexpand(True)
        cl.append(Gtk.Label(label="Bluetooth", css_classes=["card-name"], xalign=0))
        cl.append(Gtk.Label(label="Enabled" if powered else "Disabled",
                            css_classes=["card-desc"], xalign=0))
        ctrl_card.append(cl)
        bt_sw = Gtk.Switch(); bt_sw.set_active(powered); bt_sw.set_valign(Gtk.Align.CENTER)
        bt_sw.connect("notify::active", lambda s, _: self._toggle_bt(s.get_active()))
        ctrl_card.append(bt_sw)
        scan_btn = Gtk.Button(label="Scan (5s)"); scan_btn.add_css_class("act-btn")
        scan_btn.set_valign(Gtk.Align.CENTER)
        scan_btn.connect("clicked", lambda _: self._scan())
        ctrl_card.append(scan_btn)
        self._root.append(ctrl_card)

        if powered and devices:
            self._root.append(make_section("DEVICES"))
            for dev in devices:
                self._root.append(self._dev_card(dev))
        elif powered:
            self._root.append(Gtk.Label(label="No paired devices found. Click Scan to discover.",
                                        css_classes=["card-desc"]))
        return False

    def _dev_card(self, dev):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card.add_css_class("card")
        icon = Gtk.Label(label="󰂯"); icon.add_css_class("page-sub")
        icon.set_valign(Gtk.Align.CENTER); card.append(icon)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); info.set_hexpand(True)
        info.append(Gtk.Label(label=dev["name"], css_classes=["card-name"], xalign=0))
        info.append(Gtk.Label(label=dev["mac"], css_classes=["card-pkg"], xalign=0))
        card.append(info)
        if dev["connected"]:
            badge = Gtk.Label(label="CONNECTED"); badge.add_css_class("badge"); badge.add_css_class("ok")
            badge.set_valign(Gtk.Align.CENTER); card.append(badge)
            dc = Gtk.Button(label="Disconnect"); dc.add_css_class("act-btn"); dc.add_css_class("rm")
            dc.set_valign(Gtk.Align.CENTER)
            dc.connect("clicked", lambda _, m=dev["mac"]: self._bt_action("disconnect", m))
            card.append(dc)
        else:
            co = Gtk.Button(label="Connect"); co.add_css_class("act-btn")
            co.set_valign(Gtk.Align.CENTER)
            co.connect("clicked", lambda _, m=dev["mac"]: self._bt_action("connect", m))
            rm = Gtk.Button(label="Remove"); rm.add_css_class("act-btn"); rm.add_css_class("rm")
            rm.set_valign(Gtk.Align.CENTER)
            rm.connect("clicked", lambda _, m=dev["mac"]: self._bt_action("remove", m))
            card.append(co); card.append(rm)
        return card

    def _toggle_bt(self, enable):
        state = "on" if enable else "off"
        threading.Thread(target=lambda: (
            subprocess.run(["bluetoothctl", "power", state]),
            GLib.idle_add(self._load)
        ), daemon=True).start()

    def _scan(self):
        clear_box(self._root)
        self._root.append(spinner_row("Scanning for 5 seconds…"))
        def do_scan():
            subprocess.run(["bluetoothctl", "--timeout", "5", "scan", "on"])
            GLib.idle_add(self._load)
        threading.Thread(target=do_scan, daemon=True).start()

    def _bt_action(self, action, mac):
        threading.Thread(target=lambda: (
            subprocess.run(["bluetoothctl", action, mac]),
            GLib.idle_add(self._load)
        ), daemon=True).start()
