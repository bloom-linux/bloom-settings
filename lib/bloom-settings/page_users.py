#!/usr/bin/env python3
"""Bloom Settings — Users page."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
import subprocess, threading, os, re as _re, shutil

from common import (
    make_header, make_section, spinner_row, clear_box, text_entry,
    TermWindow, sh,
)

_AVATAR_DIR = "/var/lib/AccountsService/icons"


def _avatar_path(username):
    return os.path.join(_AVATAR_DIR, username)


def _get_user_groups(username):
    out = sh(["groups", username])
    parts = out.split(":", 1)
    if len(parts) == 2:
        return [g.strip() for g in parts[1].split()]
    return [g.strip() for g in out.split()]


def _get_user_shell(username):
    for line in open("/etc/passwd"):
        parts = line.strip().split(":")
        if parts[0] == username and len(parts) >= 7:
            return parts[6]
    return "/bin/bash"


def _avatar_widget(username, size=52):
    path = _avatar_path(username)
    if os.path.exists(path):
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, True)
            img = Gtk.Image.new_from_pixbuf(pb)
            img.set_size_request(size, size)
            return img
        except Exception:
            pass
    lbl = Gtk.Label(label="󰀄")
    lbl.set_size_request(size, size)
    lbl.set_css_classes(["page-title"])
    lbl.set_valign(Gtk.Align.CENTER)
    return lbl


def _section(lbl):
    l = Gtk.Label(label=lbl)
    l.set_css_classes(["section-head"]); l.set_xalign(0); l.set_margin_top(12)
    return l


def _pw_strength(pw):
    if not pw:
        return "", ""
    s  = (len(pw) >= 8) + (len(pw) >= 12)
    s += bool(_re.search(r"[A-Z]", pw))
    s += bool(_re.search(r"[0-9]", pw))
    s += bool(_re.search(r"[^a-zA-Z0-9]", pw))
    if s <= 1: return "weak",   "Weak"
    if s <= 3: return "medium", "Fair"
    return "strong", "Strong"


_STRENGTH_COLORS = {"weak": "#e08888", "medium": "#E0C060", "strong": "#50C878"}


def _pick_avatar_dialog(parent, on_chosen):
    fc = Gtk.FileChooserDialog(title="Choose Profile Picture", transient_for=parent,
                               action=Gtk.FileChooserAction.OPEN)
    fc.add_button("Cancel", Gtk.ResponseType.CANCEL)
    fc.add_button("Open",   Gtk.ResponseType.ACCEPT)
    fc.set_modal(True)
    filt = Gtk.FileFilter(); filt.set_name("Images")
    filt.add_mime_type("image/png"); filt.add_mime_type("image/jpeg")
    filt.add_mime_type("image/webp"); filt.add_mime_type("image/svg+xml")
    fc.add_filter(filt)
    def on_resp(dlg, resp):
        if resp == Gtk.ResponseType.ACCEPT:
            f = dlg.get_file()
            if f:
                on_chosen(f.get_path())
        dlg.destroy()
    fc.connect("response", on_resp)
    fc.present()


def _apply_avatar(src_path, username):
    os.makedirs(_AVATAR_DIR, exist_ok=True)
    dest = _avatar_path(username)
    try:
        shutil.copy2(src_path, dest)
        os.chmod(dest, 0o644)
    except PermissionError:
        subprocess.run(["pkexec", "cp", src_path, dest], capture_output=True)
        subprocess.run(["pkexec", "chmod", "644", dest], capture_output=True)


# ── Users Page ────────────────────────────────────────────────────────────────

class UsersPage(Gtk.Box):
    def __init__(self, win_ref):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._win = win_ref
        self.set_margin_top(32); self.set_margin_bottom(32)
        self.set_margin_start(40); self.set_margin_end(40)
        self.append(make_header("Users", "Manage user accounts and profiles."))
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
                gecos = parts[4].split(",")
                users.append({
                    "name":     parts[0],
                    "fullname": gecos[0] if gecos else "",
                    "room":     gecos[1] if len(gecos) > 1 else "",
                    "workph":   gecos[2] if len(gecos) > 2 else "",
                    "homeph":   gecos[3] if len(gecos) > 3 else "",
                    "uid":      uid,
                    "home":     parts[5],
                    "shell":    shell,
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
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        card.add_css_class("card")

        card.append(_avatar_widget(u["name"], size=48))

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.set_hexpand(True)
        nl = Gtk.Label(label=u["name"]); nl.add_css_class("card-name"); nl.set_xalign(0)
        info.append(nl)
        if u["fullname"]:
            fl = Gtk.Label(label=u["fullname"]); fl.add_css_class("card-desc"); fl.set_xalign(0)
            info.append(fl)
        detail = f"UID {u['uid']}  ·  {u['shell'].split('/')[-1]}  ·  {u['home']}"
        dl = Gtk.Label(label=detail); dl.add_css_class("card-pkg"); dl.set_xalign(0)
        info.append(dl)
        card.append(info)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.set_valign(Gtk.Align.CENTER)

        edit_btn = Gtk.Button(label=" Manage"); edit_btn.add_css_class("act-btn")
        edit_btn.connect("clicked", lambda _, uu=u: self._manage_dialog(uu))
        btn_box.append(edit_btn)

        del_btn = Gtk.Button(label="Delete"); del_btn.add_css_class("act-btn"); del_btn.add_css_class("rm")
        del_btn.connect("clicked", lambda _, n=u["name"]: self._confirm_delete(n))
        btn_box.append(del_btn)
        card.append(btn_box)
        return card

    # ── Add user dialog ───────────────────────────────────────────────────────

    def _add_user_dialog(self):
        dlg = Gtk.Window(title="Add User")
        dlg.set_transient_for(self._win); dlg.set_modal(True); dlg.set_default_size(500, 620)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_margin_top(24); root.set_margin_bottom(20)
        root.set_margin_start(28); root.set_margin_end(28)
        scroll.set_child(root)

        t = Gtk.Label(label="Add New User"); t.add_css_class("page-title"); t.set_xalign(0)
        t.set_margin_bottom(4)
        root.append(t)

        # ── Avatar picker ────────────────────────────────────────────────────
        root.append(_section("PROFILE PICTURE"))
        av_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        av_row.set_margin_bottom(4)
        self._new_avatar_path = [None]
        self._new_avatar_img  = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._new_avatar_img.set_size_request(64, 64)
        placeholder = Gtk.Label(label="󰀄")
        placeholder.set_css_classes(["page-title"]); placeholder.set_valign(Gtk.Align.CENTER)
        self._new_avatar_img.append(placeholder)
        av_row.append(self._new_avatar_img)

        av_btns = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        av_btns.set_valign(Gtk.Align.CENTER)
        pick_btn = Gtk.Button(label=" Choose Image…"); pick_btn.add_css_class("act-btn")

        def on_avatar_chosen(path):
            self._new_avatar_path[0] = path
            clear_box(self._new_avatar_img)
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 64, 64, True)
                img = Gtk.Image.new_from_pixbuf(pb)
                self._new_avatar_img.append(img)
            except Exception:
                self._new_avatar_img.append(Gtk.Label(label="󰀄", css_classes=["page-title"]))

        pick_btn.connect("clicked", lambda _: _pick_avatar_dialog(dlg, on_avatar_chosen))
        clear_av = Gtk.Button(label="Remove"); clear_av.add_css_class("act-btn")

        def on_clear_av(_):
            self._new_avatar_path[0] = None
            clear_box(self._new_avatar_img)
            self._new_avatar_img.append(Gtk.Label(label="󰀄", css_classes=["page-title"]))

        clear_av.connect("clicked", on_clear_av)
        av_btns.append(pick_btn); av_btns.append(clear_av)
        av_row.append(av_btns)
        root.append(av_row)

        # ── Account info ─────────────────────────────────────────────────────
        root.append(_section("USERNAME"))
        uname_e = text_entry("e.g. alice"); root.append(uname_e)
        uname_err = Gtk.Label(label=""); uname_err.set_css_classes(["card-desc"])
        uname_err.set_xalign(0)
        root.append(uname_err)

        root.append(_section("FULL NAME"))
        fname_e = text_entry("e.g. Alice Smith"); root.append(fname_e)

        root.append(_section("ROOM / LOCATION (OPTIONAL)"))
        room_e = text_entry("e.g. Office 3B"); root.append(room_e)

        root.append(_section("WORK PHONE (OPTIONAL)"))
        wph_e = text_entry("e.g. +1 555 0100"); root.append(wph_e)

        root.append(_section("HOME PHONE (OPTIONAL)"))
        hph_e = text_entry("e.g. +1 555 0200"); root.append(hph_e)

        # ── Shell & Admin ─────────────────────────────────────────────────────
        root.append(_section("SHELL"))
        shells = ["/bin/zsh", "/bin/bash", "/bin/sh", "/usr/bin/fish"]
        shell_combo = Gtk.DropDown()
        shell_combo.set_model(Gtk.StringList.new(shells))
        shell_combo.set_selected(0)
        root.append(shell_combo)

        admin_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        admin_row.set_margin_top(10)
        ainfo = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); ainfo.set_hexpand(True)
        ainfo.append(Gtk.Label(label="Administrator (sudo)", css_classes=["card-name"], xalign=0))
        ainfo.append(Gtk.Label(label="Adds user to the wheel group",
                               css_classes=["card-desc"], xalign=0))
        admin_row.append(ainfo)
        admin_sw = Gtk.Switch(); admin_sw.set_active(True); admin_sw.set_valign(Gtk.Align.CENTER)
        admin_row.append(admin_sw)
        root.append(admin_row)

        # ── Password ──────────────────────────────────────────────────────────
        root.append(_section("PASSWORD"))
        pw1 = Gtk.PasswordEntry(); pw1.set_show_peek_icon(True)
        pw1.set_property("placeholder-text", "Password")
        root.append(pw1)
        pw_str_lbl = Gtk.Label(label=""); pw_str_lbl.set_xalign(0)
        root.append(pw_str_lbl)

        root.append(_section("CONFIRM PASSWORD"))
        pw2 = Gtk.PasswordEntry(); pw2.set_show_peek_icon(True)
        pw2.set_property("placeholder-text", "Confirm password")
        root.append(pw2)
        pw_match_lbl = Gtk.Label(label=""); pw_match_lbl.set_xalign(0)
        root.append(pw_match_lbl)

        def _on_pw(_):
            level, lbl = _pw_strength(pw1.get_text())
            if level:
                pw_str_lbl.set_markup(f'<span color="{_STRENGTH_COLORS[level]}">Strength: {lbl}</span>')
            else:
                pw_str_lbl.set_label("")
            p1 = pw1.get_text(); p2 = pw2.get_text()
            if p2:
                pw_match_lbl.set_markup(
                    '<span color="#e08888">No match</span>' if p1 != p2
                    else '<span color="#50C878">Passwords match</span>')
            else:
                pw_match_lbl.set_label("")

        pw1.connect("changed", _on_pw); pw2.connect("changed", _on_pw)

        err_lbl = Gtk.Label(label=""); err_lbl.set_xalign(0); err_lbl.set_margin_top(8)
        root.append(err_lbl)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END); btn_row.set_margin_top(10)
        cancel = Gtk.Button(label="Cancel"); cancel.add_css_class("act-btn")
        cancel.connect("clicked", lambda _: dlg.close())
        ok = Gtk.Button(label="Create User"); ok.add_css_class("act-btn"); ok.add_css_class("primary")

        def create(_):
            uname = uname_e.get_text().strip()
            if not uname or not _re.match(r"^[a-z][a-z0-9_-]{0,30}$", uname):
                err_lbl.set_markup('<span color="#e08888">Username: lowercase letters, numbers, _ or - only</span>')
                return
            p1 = pw1.get_text(); p2 = pw2.get_text()
            if len(p1) < 6:
                err_lbl.set_markup('<span color="#e08888">Password must be at least 6 characters</span>')
                return
            if p1 != p2:
                err_lbl.set_markup('<span color="#e08888">Passwords do not match</span>')
                return
            gecos_parts = [
                fname_e.get_text().strip(),
                room_e.get_text().strip(),
                wph_e.get_text().strip(),
                hph_e.get_text().strip(),
            ]
            gecos = ",".join(gecos_parts)
            shell  = shells[shell_combo.get_selected()]
            groups = ("wheel,audio,video,storage,optical,network"
                      if admin_sw.get_active() else "audio,video,storage,optical,network")
            avatar = self._new_avatar_path[0]
            dlg.close()

            cmd = ["pkexec", "useradd", "-m", "-G", groups, "-s", shell, "-c", gecos, uname]

            def do_create():
                r = subprocess.run(cmd, capture_output=True)
                if r.returncode == 0:
                    if p1:
                        subprocess.run(["pkexec", "chpasswd"],
                                       input=f"{uname}:{p1}", capture_output=True, text=True)
                    if avatar:
                        _apply_avatar(avatar, uname)
                GLib.idle_add(self._load)

            threading.Thread(target=do_create, daemon=True).start()

        ok.connect("clicked", create)
        btn_row.append(cancel); btn_row.append(ok)
        root.append(btn_row)
        dlg.set_child(scroll); dlg.present()

    # ── Manage user dialog ────────────────────────────────────────────────────

    def _manage_dialog(self, u):
        username = u["name"]
        dlg = Gtk.Window(title=f"Manage — {username}")
        dlg.set_transient_for(self._win); dlg.set_modal(True); dlg.set_default_size(500, 660)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_margin_top(24); root.set_margin_bottom(20)
        root.set_margin_start(28); root.set_margin_end(28)
        scroll.set_child(root)

        t = Gtk.Label(label=f"Manage {username}"); t.add_css_class("page-title")
        t.set_xalign(0); t.set_margin_bottom(4)
        root.append(t)

        # ── Avatar ────────────────────────────────────────────────────────────
        root.append(_section("PROFILE PICTURE"))
        av_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        av_row.set_margin_bottom(4)
        _avatar_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        _avatar_container.set_size_request(64, 64)
        _avatar_container.append(_avatar_widget(username, size=64))
        av_row.append(_avatar_container)
        _pending_avatar = [None]

        av_btns = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        av_btns.set_valign(Gtk.Align.CENTER)
        pick_btn = Gtk.Button(label=" Change Picture…"); pick_btn.add_css_class("act-btn")

        def on_av_chosen(path):
            _pending_avatar[0] = path
            clear_box(_avatar_container)
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 64, 64, True)
                _avatar_container.append(Gtk.Image.new_from_pixbuf(pb))
            except Exception:
                _avatar_container.append(Gtk.Label(label="󰀄", css_classes=["page-title"]))

        pick_btn.connect("clicked", lambda _: _pick_avatar_dialog(dlg, on_av_chosen))
        rm_av = Gtk.Button(label="Remove Picture"); rm_av.add_css_class("act-btn")

        def on_rm_av(_):
            _pending_avatar[0] = "__remove__"
            clear_box(_avatar_container)
            _avatar_container.append(Gtk.Label(label="󰀄", css_classes=["page-title"]))

        rm_av.connect("clicked", on_rm_av)
        av_btns.append(pick_btn); av_btns.append(rm_av)
        av_row.append(av_btns)
        root.append(av_row)

        # ── Profile info ──────────────────────────────────────────────────────
        root.append(_section("FULL NAME"))
        fname_e = text_entry("Full name"); fname_e.set_text(u.get("fullname", ""))
        root.append(fname_e)

        root.append(_section("ROOM / LOCATION"))
        room_e = text_entry("Room or location"); room_e.set_text(u.get("room", ""))
        root.append(room_e)

        root.append(_section("WORK PHONE"))
        wph_e = text_entry("Work phone"); wph_e.set_text(u.get("workph", ""))
        root.append(wph_e)

        root.append(_section("HOME PHONE"))
        hph_e = text_entry("Home phone"); hph_e.set_text(u.get("homeph", ""))
        root.append(hph_e)

        # ── Shell ─────────────────────────────────────────────────────────────
        root.append(_section("SHELL"))
        shells = ["/bin/zsh", "/bin/bash", "/bin/sh", "/usr/bin/fish"]
        cur_shell = u.get("shell", "/bin/bash")
        shell_combo = Gtk.DropDown()
        shell_combo.set_model(Gtk.StringList.new(shells))
        shell_combo.set_selected(shells.index(cur_shell) if cur_shell in shells else 1)
        root.append(shell_combo)

        # ── Groups ────────────────────────────────────────────────────────────
        root.append(_section("GROUPS"))
        groups_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        groups_row.set_margin_bottom(2)
        all_groups_label = Gtk.Label(label="Loading…")
        all_groups_label.add_css_class("card-desc"); all_groups_label.set_xalign(0)
        all_groups_label.set_hexpand(True)
        groups_row.append(all_groups_label)
        edit_groups_btn = Gtk.Button(label="Edit…"); edit_groups_btn.add_css_class("act-btn")
        groups_row.append(edit_groups_btn)
        root.append(groups_row)

        def load_groups():
            grps = _get_user_groups(username)
            GLib.idle_add(lambda: all_groups_label.set_label(", ".join(grps) if grps else "(none)"))

        threading.Thread(target=load_groups, daemon=True).start()

        def open_groups_editor(_):
            grps = _get_user_groups(username)
            self._edit_groups_dialog(dlg, username, grps, lambda: threading.Thread(target=load_groups, daemon=True).start())

        edit_groups_btn.connect("clicked", open_groups_editor)

        # ── Password ──────────────────────────────────────────────────────────
        root.append(_section("CHANGE PASSWORD"))
        pw_new = Gtk.PasswordEntry(); pw_new.set_show_peek_icon(True)
        pw_new.set_property("placeholder-text", "New password (leave blank to keep current)")
        root.append(pw_new)
        pw_new2 = Gtk.PasswordEntry(); pw_new2.set_show_peek_icon(True)
        pw_new2.set_property("placeholder-text", "Confirm new password")
        root.append(pw_new2)
        pw_match_lbl = Gtk.Label(label=""); pw_match_lbl.set_xalign(0)
        root.append(pw_match_lbl)

        def _on_pw_m(_):
            p1 = pw_new.get_text(); p2 = pw_new2.get_text()
            if p1 and p2:
                pw_match_lbl.set_markup(
                    '<span color="#e08888">No match</span>' if p1 != p2
                    else '<span color="#50C878">Passwords match</span>')
            else:
                pw_match_lbl.set_label("")

        pw_new.connect("changed", _on_pw_m); pw_new2.connect("changed", _on_pw_m)

        err_lbl = Gtk.Label(label=""); err_lbl.set_xalign(0); err_lbl.set_margin_top(8)
        root.append(err_lbl)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END); btn_row.set_margin_top(12)
        cancel = Gtk.Button(label="Cancel"); cancel.add_css_class("act-btn")
        cancel.connect("clicked", lambda _: dlg.close())
        ok = Gtk.Button(label="Save Changes"); ok.add_css_class("act-btn"); ok.add_css_class("primary")

        def apply_changes(_):
            p1 = pw_new.get_text(); p2 = pw_new2.get_text()
            if p1 and p1 != p2:
                err_lbl.set_markup('<span color="#e08888">Passwords do not match</span>')
                return
            if p1 and len(p1) < 6:
                err_lbl.set_markup('<span color="#e08888">Password must be at least 6 characters</span>')
                return

            gecos = ",".join([
                fname_e.get_text().strip(),
                room_e.get_text().strip(),
                wph_e.get_text().strip(),
                hph_e.get_text().strip(),
            ])
            shell  = shells[shell_combo.get_selected()]
            avatar = _pending_avatar[0]
            dlg.close()

            def do_apply():
                subprocess.run(["pkexec", "chfn", "-f", fname_e.get_text().strip(),
                                "-r", room_e.get_text().strip(),
                                "-w", wph_e.get_text().strip(),
                                "-h", hph_e.get_text().strip(),
                                username], capture_output=True)
                subprocess.run(["pkexec", "chsh", "-s", shell, username], capture_output=True)
                if p1:
                    subprocess.run(["pkexec", "chpasswd"],
                                   input=f"{username}:{p1}", capture_output=True, text=True)
                if avatar == "__remove__":
                    try:
                        os.remove(_avatar_path(username))
                    except Exception:
                        subprocess.run(["pkexec", "rm", "-f", _avatar_path(username)], capture_output=True)
                elif avatar:
                    _apply_avatar(avatar, username)
                GLib.idle_add(self._load)

            threading.Thread(target=do_apply, daemon=True).start()

        ok.connect("clicked", apply_changes)
        btn_row.append(cancel); btn_row.append(ok)
        root.append(btn_row)
        dlg.set_child(scroll); dlg.present()

    # ── Edit groups dialog ────────────────────────────────────────────────────

    def _edit_groups_dialog(self, parent, username, current_groups, on_done):
        dlg = Gtk.Window(title=f"Edit Groups — {username}")
        dlg.set_transient_for(parent); dlg.set_modal(True); dlg.set_default_size(380, 480)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_top(20); root.set_margin_bottom(16)
        root.set_margin_start(22); root.set_margin_end(22)

        t = Gtk.Label(label="System Groups"); t.add_css_class("card-name"); t.set_xalign(0)
        t.set_margin_bottom(8); root.append(t)

        note = Gtk.Label(label="Toggle membership in system groups. Changes apply immediately.")
        note.add_css_class("card-desc"); note.set_wrap(True); note.set_xalign(0)
        note.set_margin_bottom(10); root.append(note)

        important_groups = [
            ("wheel",    "Administrator (sudo)"),
            ("audio",    "Audio devices"),
            ("video",    "Video devices / GPU"),
            ("storage",  "Storage / USB drives"),
            ("input",    "Input devices"),
            ("optical",  "Optical drives"),
            ("network",  "Network configuration"),
            ("docker",   "Docker (rootless containers)"),
            ("libvirt",  "Virtualisation (libvirt/KVM)"),
            ("lp",       "Printing"),
            ("scanner",  "Scanner access"),
            ("games",    "Games"),
            ("power",    "Power management"),
        ]

        sw = Gtk.ScrolledWindow(); sw.set_vexpand(True)
        grp_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        sw.set_child(grp_box)

        switches = {}
        for grp, desc in important_groups:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.add_css_class("card")
            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); info.set_hexpand(True)
            info.append(Gtk.Label(label=grp,  css_classes=["card-name"], xalign=0))
            info.append(Gtk.Label(label=desc, css_classes=["card-desc"], xalign=0))
            row.append(info)
            gsw = Gtk.Switch(); gsw.set_active(grp in current_groups)
            gsw.set_valign(Gtk.Align.CENTER)
            row.append(gsw)
            switches[grp] = gsw
            grp_box.append(row)

        root.append(sw)

        err_lbl = Gtk.Label(label=""); err_lbl.set_xalign(0); root.append(err_lbl)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END); btn_row.set_margin_top(8)
        cancel = Gtk.Button(label="Cancel"); cancel.add_css_class("act-btn")
        cancel.connect("clicked", lambda _: dlg.close())
        ok = Gtk.Button(label="Apply"); ok.add_css_class("act-btn"); ok.add_css_class("primary")

        def apply_groups(_):
            dlg.close()
            def do_apply():
                for grp, gsw in switches.items():
                    if gsw.get_active():
                        subprocess.run(["pkexec", "usermod", "-aG", grp, username], capture_output=True)
                    else:
                        subprocess.run(["pkexec", "gpasswd", "-d", username, grp], capture_output=True)
                GLib.idle_add(on_done)
            threading.Thread(target=do_apply, daemon=True).start()

        ok.connect("clicked", apply_groups)
        btn_row.append(cancel); btn_row.append(ok)
        root.append(btn_row)
        dlg.set_child(root); dlg.present()

    # ── Delete ────────────────────────────────────────────────────────────────

    def _confirm_delete(self, username):
        dlg = Gtk.Window(title="Delete User")
        dlg.set_transient_for(self._win); dlg.set_modal(True); dlg.set_default_size(380, 180)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(24); root.set_margin_bottom(24)
        root.set_margin_start(24); root.set_margin_end(24)

        t = Gtk.Label(label=f"Delete '{username}'?")
        t.add_css_class("card-name"); t.set_xalign(0); root.append(t)
        s = Gtk.Label(label="This will remove the user and their home directory. This cannot be undone.")
        s.add_css_class("card-desc"); s.set_wrap(True); s.set_xalign(0); root.append(s)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END); btn_row.set_margin_top(8)
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
