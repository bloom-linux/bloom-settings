#!/usr/bin/env python3
"""Bloom Settings — Users page."""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib
import subprocess, threading, os

from common import (
    make_header, make_section, spinner_row, clear_box, text_entry,
    TermWindow, sh,
)


# ── Users Page ────────────────────────────────────────────────────────────────

class UsersPage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Users", "Manage user accounts."))
        self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.append(self._root)
        self._load()

    def _load(self):
        clear_box(self._root)
        self._root.append(spinner_row("Loading users…"))
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        users = []
        try:
            for line in open("/etc/passwd"):
                parts = line.strip().split(":")
                if len(parts) < 7:
                    continue
                uid = int(parts[2])
                if uid < 1000 or uid > 60000:
                    continue
                shell = parts[6]
                if "nologin" in shell or "false" in shell:
                    continue
                users.append({
                    "name": parts[0], "gecos": parts[4].split(",")[0],
                    "uid": uid, "home": parts[5],
                })
        except Exception:
            pass
        GLib.idle_add(self._populate, users)

    def _populate(self, users):
        clear_box(self._root)

        add_btn = Gtk.Button(label="  Add User")
        add_btn.add_css_class("act-btn"); add_btn.add_css_class("primary")
        add_btn.set_halign(Gtk.Align.START); add_btn.set_margin_bottom(16)
        add_btn.connect("clicked", lambda _: self._add_user_dialog())
        self._root.append(add_btn)

        if not users:
            self._root.append(Gtk.Label(label="No regular users found."))
            return False

        for u in users:
            self._root.append(self._user_card(u))
        return False

    def _user_card(self, u):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card.add_css_class("card")

        icon = Gtk.Label(label="󰀄"); icon.set_css_classes(["page-title"])
        icon.set_valign(Gtk.Align.CENTER)
        card.append(icon)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.set_hexpand(True)
        nl = Gtk.Label(label=u["name"]); nl.add_css_class("card-name"); nl.set_xalign(0); info.append(nl)
        if u["gecos"]:
            gl = Gtk.Label(label=u["gecos"]); gl.add_css_class("card-desc"); gl.set_xalign(0); info.append(gl)
        hl = Gtk.Label(label=u["home"]); hl.add_css_class("card-pkg"); hl.set_xalign(0); info.append(hl)
        card.append(info)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.set_valign(Gtk.Align.CENTER)

        pw_btn = Gtk.Button(label="Password"); pw_btn.add_css_class("act-btn")
        pw_btn.connect("clicked", lambda _, n=u["name"]: self._change_password(n))
        btn_box.append(pw_btn)

        del_btn = Gtk.Button(label="Delete"); del_btn.add_css_class("act-btn"); del_btn.add_css_class("rm")
        del_btn.connect("clicked", lambda _, n=u["name"]: self._confirm_delete(n))
        btn_box.append(del_btn)
        card.append(btn_box)
        return card

    def _add_user_dialog(self):
        dlg = Gtk.Window(title="Add User")
        dlg.set_transient_for(self._win); dlg.set_modal(True); dlg.set_default_size(360, 280)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(24); root.set_margin_bottom(24)
        root.set_margin_start(24); root.set_margin_end(24)

        t = Gtk.Label(label="Add New User"); t.add_css_class("page-title"); t.set_xalign(0)
        root.append(t)

        uname_e = text_entry("Username"); root.append(uname_e)
        fname_e = text_entry("Full Name (optional)"); root.append(fname_e)
        pass_e  = text_entry("Password", password=True); root.append(pass_e)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel"); cancel.add_css_class("act-btn")
        cancel.connect("clicked", lambda _: dlg.close())
        ok = Gtk.Button(label="Create"); ok.add_css_class("act-btn"); ok.add_css_class("primary")

        def create(_):
            uname = uname_e.get_text().strip()
            fname = fname_e.get_text().strip()
            passwd = pass_e.get_text()
            if not uname:
                return
            dlg.close()
            cmd = ["pkexec", "useradd", "-m", "-G", "wheel,audio,video,storage,optical,network"]
            if fname:
                cmd += ["-c", fname]
            cmd.append(uname)
            def do_create():
                r = subprocess.run(cmd, capture_output=True)
                if r.returncode == 0 and passwd:
                    subprocess.run(["pkexec", "chpasswd"],
                                   input=f"{uname}:{passwd}", capture_output=True, text=True)
                GLib.idle_add(self._load)
            threading.Thread(target=do_create, daemon=True).start()

        ok.connect("clicked", create)
        btn_row.append(cancel); btn_row.append(ok)
        root.append(btn_row)
        dlg.set_child(root); dlg.present()

    def _change_password(self, username):
        dlg = Gtk.Window(title=f"Change Password — {username}")
        dlg.set_transient_for(self._win); dlg.set_modal(True); dlg.set_default_size(340, 200)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(24); root.set_margin_bottom(24)
        root.set_margin_start(24); root.set_margin_end(24)

        t = Gtk.Label(label=f"New password for {username}")
        t.add_css_class("card-name"); t.set_xalign(0); root.append(t)
        pass_e = text_entry("New password", password=True); root.append(pass_e)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel"); cancel.add_css_class("act-btn")
        cancel.connect("clicked", lambda _: dlg.close())
        ok = Gtk.Button(label="Apply"); ok.add_css_class("act-btn"); ok.add_css_class("primary")

        def apply(_):
            passwd = pass_e.get_text()
            if not passwd:
                return
            dlg.close()
            threading.Thread(target=lambda: subprocess.run(
                ["pkexec", "chpasswd"], input=f"{username}:{passwd}",
                capture_output=True, text=True), daemon=True).start()

        ok.connect("clicked", apply)
        btn_row.append(cancel); btn_row.append(ok)
        root.append(btn_row)
        dlg.set_child(root); dlg.present()

    def _confirm_delete(self, username):
        dlg = Gtk.Window(title="Delete User")
        dlg.set_transient_for(self._win); dlg.set_modal(True); dlg.set_default_size(340, 160)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(24); root.set_margin_bottom(24)
        root.set_margin_start(24); root.set_margin_end(24)
        t = Gtk.Label(label=f"Delete user '{username}' and their home directory?")
        t.set_wrap(True); t.set_xalign(0); root.append(t)
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel"); cancel.add_css_class("act-btn")
        cancel.connect("clicked", lambda _: dlg.close())
        ok = Gtk.Button(label="Delete"); ok.add_css_class("act-btn"); ok.add_css_class("rm")
        def do_del(_):
            dlg.close()
            TermWindow(self._win, f"Deleting user {username}",
                       ["pkexec", "userdel", "-r", username], on_done=self._load)
        ok.connect("clicked", do_del)
        btn_row.append(cancel); btn_row.append(ok)
        root.append(btn_row)
        dlg.set_child(root); dlg.present()
