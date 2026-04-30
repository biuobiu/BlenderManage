import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, simpledialog

import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from PIL import Image, ImageTk

from core import (
    ConfigManager, Logger, DataManager,
    get_blender_config_path, get_blender_manager_dir,
    get_blender_install_dir, get_blender_versions_dir,
    get_blender_executable, get_selected_main_version,
    get_paths_dir, get_user_data_dir, get_assets_dir,
    set_path_overrides, save_path_overrides, ensure_dir,
)
from i18n import _, get_available_languages, set_language

log = Logger()


class SettingsWindow:
    def __init__(self, app):
        self.app = app
        self.config = ConfigManager()
        self.data = DataManager()
        self._window = None
        self._build()

    def _build(self):
        w = tk.Toplevel(self.app)
        w.title(_("Settings"))
        w.geometry("750x550")
        w.resizable(False, False)
        w.transient(self.app)
        w.grab_set()
        self._window = w

        nb = ttkb.Notebook(w)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        self._paths_tab(nb)
        self._appearance_tab(nb)
        self._general_tab(nb)
        self._blender_settings_tab(nb)
        nb.select(0)

        ttkb.Button(w, text=_("Close"), command=w.destroy, bootstyle=SECONDARY).pack(pady=(0, 10))

    def _paths_tab(self, notebook):
        tab = ttkb.Frame(notebook, padding=20)
        notebook.add(tab, text=_("Default Paths"))
        tab.columnconfigure(1, weight=1)

        self._path_vars = {}
        path_keys = [
            ("blender_manager_dir", _("Blender Manager Root")),
            ("blender_versions_dir", _("Blender Versions")),
            ("user_data_dir", _("Data (mngaddon)")),
            ("paths_dir", _("Paths Config")),
            ("logs", _("Logs")),
        ]
        default_values = {
            "blender_manager_dir": get_blender_manager_dir(),
            "blender_versions_dir": get_blender_versions_dir(),
            "user_data_dir": get_user_data_dir(),
            "paths_dir": get_paths_dir(),
            "logs": os.path.join(get_blender_manager_dir(), "logs"),
        }
        for i, (key, label) in enumerate(path_keys):
            ttkb.Label(tab, text=label, font=("Segoe UI", 10, "bold")).grid(
                row=i, column=0, sticky="w", pady=(6 if i > 0 else 0, 0)
            )
            var = tk.StringVar(value=default_values[key])
            entry = ttkb.Entry(tab, width=70, font=("Consolas", 9), textvariable=var)
            entry.grid(row=i, column=1, sticky="ew", padx=(10, 0), pady=(6 if i > 0 else 0, 0))
            self._path_vars[key] = var

        def _update_derived_paths(*_):
            root = self._path_vars["blender_manager_dir"].get().strip().strip('"')
            for key, sub in [("blender_versions_dir", "BlenderVersions"),
                             ("user_data_dir", "mngaddon"),
                             ("paths_dir", "paths"),
                             ("logs", "logs")]:
                if key in self._path_vars:
                    self._path_vars[key].set(os.path.join(root, sub))
            for key in ["assets", "addons", "Projects", "renders"]:
                if key in self._path_vars:
                    self._path_vars[key].set(os.path.join(root, key))

        self._path_vars["blender_manager_dir"].trace("w", _update_derived_paths)

        sep = ttkb.Separator(tab, orient="horizontal")
        sep.grid(row=len(path_keys), column=0, columnspan=2, sticky="ew", pady=12)

        extra_keys = ["assets", "addons", "Projects", "renders"]
        extra_labels = {
            "assets": _("Assets"), "addons": _("Addons"),
            "Projects": _("Projects"), "renders": _("Renders"),
        }
        for i, key in enumerate(extra_keys):
            erow = len(path_keys) + 1 + i
            ttkb.Label(tab, text=extra_labels[key], font=("Segoe UI", 10)).grid(
                row=erow, column=0, sticky="w", pady=(3, 0)
            )
            var = tk.StringVar(value=os.path.join(get_blender_manager_dir(), key))
            entry = ttkb.Entry(tab, width=70, font=("Consolas", 9), textvariable=var)
            entry.grid(row=erow, column=1, sticky="ew", padx=(10, 0), pady=(3, 0))
            self._path_vars[key] = var

        # Default Version dropdown
        ver_row = len(path_keys) + 1 + len(extra_keys)
        ttkb.Separator(tab, orient="horizontal").grid(
            row=ver_row, column=0, columnspan=2, sticky="ew", pady=12)
        self._version_var = tk.StringVar()
        ttkb.Label(tab, text=_("Default Version"), font=("Segoe UI", 10, "bold")).grid(
            row=ver_row + 1, column=0, sticky="w"
        )
        vdir = get_blender_versions_dir()
        available = sorted([d for d in os.listdir(vdir)
                           if os.path.isdir(os.path.join(vdir, d))], reverse=True) if os.path.exists(vdir) else []
        self._version_cb = ttkb.Combobox(tab, textvariable=self._version_var,
                                          values=available, state="readonly", width=50)
        current = get_selected_main_version()
        self._version_var.set(current if current else "")
        self._version_cb.grid(row=ver_row + 1, column=1, sticky="ew", padx=(10, 0))

        sep2 = ttkb.Separator(tab, orient="horizontal")
        sep2.grid(row=ver_row + 2, column=0, columnspan=2, sticky="ew", pady=12)

        def _save_paths():
            cfg_path = os.path.join(os.path.expanduser("~"), ".BlenderManager", "config.json")
            overrides = {k: v.get().strip().strip('"') for k, v in self._path_vars.items()}
            set_path_overrides(overrides)
            save_path_overrides(cfg_path)
            v = self._version_var.get()
            if v:
                try:
                    with open(cfg_path, "r") as f:
                        cfg = json.load(f)
                except Exception:
                    cfg = {}
                cfg["selected_main_version"] = v
                with open(cfg_path, "w") as f:
                    json.dump(cfg, f, indent=4)
            messagebox.showinfo(_("Saved"), _("Paths updated. Restart to apply."))

        tk.Button(tab, text=_("Save Settings"),
                  command=_save_paths,
                  font=("Segoe UI", 11, "bold"),
                  bg="#28a745", fg="white", relief="flat",
                  padx=20, pady=8, cursor="hand2", width=20).grid(
            row=ver_row + 3, column=0, columnspan=2, pady=12)

    def _appearance_tab(self, notebook):
        tab = ttkb.Frame(notebook, padding=20)
        notebook.add(tab, text=_("Appearance"))

        ttkb.Label(tab, text=_("Theme"), font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tf = ttkb.Frame(tab)
        tf.pack(fill="x", pady=5)
        theme_var = tk.StringVar(value=self.config.get("selected_theme", "darkly"))
        theme_cb = ttkb.Combobox(tf, textvariable=theme_var, state="readonly", width=30)
        theme_cb["values"] = sorted(self.app.available_themes.values())
        theme_cb.pack(side="left")
        tk.Button(tf, text=_("Apply"), command=lambda: self._apply_theme(theme_var.get()),
                  font=("Segoe UI", 10), bg="#0d6efd", fg="white",
                  relief="flat", padx=15, pady=4, cursor="hand2").pack(side="left", padx=(10, 0))

        ttkb.Label(tab, text=_("Window Opacity"), font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(15, 5))
        alpha_var = tk.DoubleVar(value=self.config.get("window_alpha", 0.98))
        ttkb.Scale(tab, from_=0.5, to=1.0, variable=alpha_var, orient="horizontal",
                    command=lambda v: self.app.attributes("-alpha", float(v))).pack(fill="x")

        ttkb.Label(tab, text=_("Treeview Font Family"), font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(15, 5))
        tff = tk.StringVar(value=self.config.get("treeview_font_family", "Segoe UI"))
        fonts = ["Segoe UI", "Arial", "Helvetica", "Times New Roman", "Courier New", "Consolas"]
        ttf_cb = ttkb.Combobox(tab, textvariable=tff, values=fonts, state="readonly", width=30)
        ttf_cb.pack(anchor="w")

        ttkb.Label(tab, text=_("Treeview Font Size"), font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(15, 5))
        tfs_var = tk.IntVar(value=self.config.get("treeview_font_size", 12))
        ttkb.Scale(tab, from_=8, to=24, variable=tfs_var, orient="horizontal").pack(fill="x")

        ttkb.Label(tab, text=_("Button Font Family"), font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(15, 5))
        bff = tk.StringVar(value=self.config.get("button_font_family", "Segoe UI"))
        bff_cb = ttkb.Combobox(tab, textvariable=bff, values=fonts, state="readonly", width=30)
        bff_cb.pack(anchor="w")

        ttkb.Label(tab, text=_("Button Font Size"), font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(15, 5))
        bfs_var = tk.IntVar(value=self.config.get("button_font_size", 11))
        ttkb.Scale(tab, from_=8, to=24, variable=bfs_var, orient="horizontal").pack(fill="x")

        save_btn = tk.Button(tab, text=_("Save Settings"),
                             command=lambda: self._save_appearance(theme_var.get(), alpha_var.get(),
                                                                    tfs_var.get(), tff.get(), bff.get(), bfs_var.get()),
                             font=("Segoe UI", 11, "bold"),
                             bg="#28a745", fg="white", relief="flat",
                             padx=20, pady=8, cursor="hand2", width=20)
        save_btn.pack(pady=20)
        save_btn.bind("<Enter>", lambda e: save_btn.configure(bg="#34d058"))
        save_btn.bind("<Leave>", lambda e: save_btn.configure(bg="#28a745"))

    def _apply_theme(self, name):
        self.app.style.theme_use(name)
        self.config.save_setting("selected_theme", name)
        self.app._apply_custom_styles()

    def _save_appearance(self, theme, alpha, tfs, tff, bff, bfs):
        self.config.save_setting("selected_theme", theme)
        self.config.save_setting("window_alpha", alpha)
        self.config.save_setting("treeview_font_size", tfs)
        self.config.save_setting("treeview_font_family", tff)
        self.config.save_setting("button_font_family", bff)
        self.config.save_setting("button_font_size", bfs)
        self.app.attributes("-alpha", alpha)
        self.app._apply_custom_styles()

    def _general_tab(self, notebook):
        tab = ttkb.Frame(notebook, padding=20)
        notebook.add(tab, text=_("General"))

        auto_update = tk.BooleanVar(value=self.config.get("auto_update_checkbox", True))
        ttkb.Checkbutton(tab, text=_("Auto-update Blender"), variable=auto_update,
                          command=lambda: self.config.save_setting("auto_update_checkbox", auto_update.get())
                          ).pack(anchor="w", pady=3)

        bm_auto = tk.BooleanVar(value=self.config.get("bm_auto_update_checkbox", False))
        ttkb.Checkbutton(tab, text=_("Auto-update Blender Manager"), variable=bm_auto,
                          command=lambda: self.config.save_setting("bm_auto_update_checkbox", bm_auto.get())
                          ).pack(anchor="w", pady=3)

        run_bg = tk.BooleanVar(value=self.config.get("run_in_background", True))
        ttkb.Checkbutton(tab, text=_("Run in background (minimize to tray)"), variable=run_bg,
                          command=lambda: self.config.save_setting("run_in_background", run_bg.get())
                          ).pack(anchor="w", pady=3)

        launch_startup = tk.BooleanVar(value=self.config.get("launch_on_startup", False))
        ttkb.Checkbutton(tab, text=_("Launch on startup"), variable=launch_startup,
                          command=lambda: self._toggle_startup(launch_startup.get())
                          ).pack(anchor="w", pady=3)

        show_work = tk.BooleanVar(value=self.config.get("show_worktime_label", True))
        ttkb.Checkbutton(tab, text=_("Show work time label"), variable=show_work,
                          command=lambda: self.config.save_setting("show_worktime_label", show_work.get())
                          ).pack(anchor="w", pady=3)

        auto_activate = tk.BooleanVar(value=self.config.get("auto_activate_plugin", True))
        ttkb.Checkbutton(tab, text=_("Auto-activate addon after adding"), variable=auto_activate,
                          command=lambda: self.config.save_setting("auto_activate_plugin", auto_activate.get())
                          ).pack(anchor="w", pady=3)

        ttkb.Label(tab, text=_("Download Chunk Size Multiplier"),
                   font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(15, 5))
        chunk = tk.IntVar(value=self.config.get("chunk_size_multiplier", 3))
        chunk_frame = ttkb.Frame(tab)
        chunk_frame.pack(fill="x")
        ttkb.Scale(chunk_frame, from_=1, to=10, variable=chunk, orient="horizontal",
                    command=lambda v: self.config.save_setting("chunk_size_multiplier", int(float(v)))).pack(fill="x")
        ttkb.Label(chunk_frame, textvariable=tk.StringVar(value=f"{chunk.get()}x")).pack()

        ttkb.Label(tab, text=_("Tab Visibility"), font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(15, 5))
        for tab_name in ["Addon Management", "Project Management", "Render Management", "Version Management"]:
            key = f"show_{tab_name.lower().replace(' ', '_')}"
            var = tk.BooleanVar(value=self.config.get(key, True))
            ttkb.Checkbutton(tab, text=_(f"Show {tab_name} Tab"), variable=var,
                              command=lambda k=key, v=var: self.config.save_setting(k, v.get())
                              ).pack(anchor="w")

        ttkb.Label(tab, text=_("Restart needed for tab visibility changes."),
                   font=("Segoe UI", 8, "italic"), foreground="gray").pack(anchor="w", pady=(5, 0))

        ttkb.Label(tab, text=_("Language:"), font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(15, 5))
        lang_frame = ttkb.Frame(tab)
        lang_frame.pack(fill="x")
        self.lang_var = tk.StringVar()
        lang_map = {"zh_CN": _("Chinese"), "en": _("English")}
        available = get_available_languages()
        display_names = [lang_map.get(c, c) for c in available]
        self.lang_cb = ttkb.Combobox(lang_frame, textvariable=self.lang_var,
                                      values=display_names, state="readonly", width=30)
        self.lang_cb.pack(side="left")
        current_lang = self.config.get("language", "zh_CN")
        if current_lang in lang_map:
            self.lang_var.set(lang_map[current_lang])
        elif display_names:
            self.lang_cb.current(0)
        tk.Button(lang_frame, text=_("Apply"),
                  command=self._apply_language,
                  font=("Segoe UI", 10), bg="#0d6efd", fg="white",
                  relief="flat", padx=15, pady=4, cursor="hand2").pack(side="left", padx=(10, 0))

        ttkb.Button(tab, text=_("Reset All Settings to Default"), bootstyle=DANGER,
                     command=self._reset_defaults).pack(pady=20, anchor="w")

    def _apply_language(self):
        display = self.lang_var.get()
        if not display:
            return
        rev = {"Chinese": "zh_CN", "English": "en"}
        code = rev.get(display, display)
        set_language(code)
        self.config.save_setting("language", code)
        messagebox.showinfo(_("Language"), _("Language will be applied after restart."))

    def _toggle_startup(self, enabled):
        self.config.save_setting("launch_on_startup", enabled)
        try:
            if platform.system() == "Windows":
                startup = os.path.join(os.getenv("APPDATA"), "Microsoft", "Windows",
                                       "Start Menu", "Programs", "Startup", "BlenderManager.lnk")
                if enabled:
                    from win32com.client import Dispatch
                    shell = Dispatch("WScript.Shell")
                    shortcut = shell.CreateShortcut(startup)
                    shortcut.TargetPath = sys.argv[0]
                    shortcut.WorkingDirectory = os.path.dirname(sys.argv[0])
                    shortcut.save()
                elif os.path.exists(startup):
                    os.remove(startup)
        except Exception as e:
            log.error(f"Startup toggle: {e}")

    def _reset_defaults(self):
        if messagebox.askyesno(_("Confirm"), _("Reset all settings to defaults?")):
            self.config.reset_to_defaults()
            messagebox.showinfo(_("Done"), _("Settings reset. You may need to restart."))

    def _blender_settings_tab(self, notebook):
        tab = ttkb.Frame(notebook, padding=20)
        notebook.add(tab, text=_("Blender Settings"))

        install_path = get_blender_install_dir()
        ttkb.Label(tab, text=_("Blender Path"), font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttkb.Label(tab, text=install_path, font=("Segoe UI", 9)).pack(anchor="w", pady=5)

        btn_frame = ttkb.Frame(tab)
        btn_frame.pack(anchor="w", pady=10)

        ttkb.Button(btn_frame, text=_("Setup Addon"), bootstyle=INFO,
                     command=self._setup_addon).pack(side="left", padx=5)
        ttkb.Button(btn_frame, text=_("Reset All Data"), bootstyle=DANGER,
                     command=self._reset_all_data).pack(side="left", padx=5)

        ttkb.Label(tab, text=_("Transfer Settings Between Versions"),
                   font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(20, 5))

        transfer_frame = ttkb.Frame(tab)
        transfer_frame.pack(fill="x")

        left = ttkb.Frame(transfer_frame)
        left.pack(side="left", fill="y", padx=(0, 20))

        ttkb.Label(left, text=_("Source Version:"), font=("Segoe UI", 9)).pack(anchor="w")
        self.src_var = tk.StringVar()
        self.src_cb = ttkb.Combobox(left, textvariable=self.src_var, state="readonly", width=25)
        self.src_cb.pack(anchor="w", pady=2)
        ttkb.Label(left, text="↓", font=("Segoe UI", 14)).pack(anchor="center", pady=2)
        ttkb.Label(left, text=_("Destination Version:"), font=("Segoe UI", 9)).pack(anchor="w")
        self.dst_var = tk.StringVar()
        self.dst_cb = ttkb.Combobox(left, textvariable=self.dst_var, state="readonly", width=25)
        self.dst_cb.pack(anchor="w", pady=2)
        ttkb.Button(left, text=_("Transfer Settings"), bootstyle=PRIMARY,
                     command=self._transfer_settings).pack(anchor="w", pady=5)

        right = ttkb.Frame(transfer_frame)
        right.pack(side="left", fill="y")

        ttkb.Label(right, text=_("Export/Import"), font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.exp_var = tk.StringVar()
        ttkb.Label(right, text=_("Select Version:"), font=("Segoe UI", 9)).pack(anchor="w")
        self.exp_cb = ttkb.Combobox(right, textvariable=self.exp_var, state="readonly", width=25)
        self.exp_cb.pack(anchor="w", pady=2)
        ttkb.Button(right, text=_("Export Config"), bootstyle=PRIMARY,
                     command=self._export_config).pack(anchor="w", pady=5)
        ttkb.Button(right, text=_("Import Config"), bootstyle=PRIMARY,
                     command=self._import_config).pack(anchor="w", pady=5)

        ttkb.Label(tab, text=_("Reset Blender Config"),
                   font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(20, 5))
        reset_frame = ttkb.Frame(tab)
        reset_frame.pack(anchor="w")
        self.cfg_ver_var = tk.StringVar()
        cfg_versions = self._get_config_versions()
        self.cfg_cb = ttkb.Combobox(reset_frame, textvariable=self.cfg_ver_var,
                                     values=cfg_versions, state="readonly", width=25)
        self.cfg_cb.set(_("Select Version"))
        self.cfg_cb.pack(side="left", padx=5)
        ttkb.Button(reset_frame, text=_("Reset Config"), bootstyle=DANGER,
                     command=self._reset_blender_config).pack(side="left", padx=5)

        self._populate_versions()

    def _get_config_versions(self):
        try:
            cfg = get_blender_config_path()
            if os.path.exists(cfg):
                return sorted([d for d in os.listdir(cfg) if os.path.isdir(os.path.join(cfg, d))])
        except Exception:
            pass
        return []

    def _populate_versions(self):
        versions = self._get_config_versions()
        for cb in [self.src_cb, self.dst_cb, self.exp_cb]:
            cb["values"] = versions

    def _setup_addon(self):
        addon_zips = ["BlenderManager.zip", "Blender Manager.zip",
                      "Blender_Manager.zip", "Blender Manager Addon.zip",
                      "Blender_Manager_Addon.zip"]
        zip_path = None
        assets_override = get_assets_dir()
        search_dirs = [assets_override] if assets_override else []
        search_dirs.append(os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.dirname(os.path.dirname(__file__))))
        search_dirs.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "Assets"))
        for d in search_dirs:
            for name in addon_zips:
                p = os.path.join(d, name)
                if os.path.exists(p):
                    zip_path = p
                    break
            if zip_path:
                break
        if not zip_path:
            messagebox.showerror(_("Error"), _("Addon zip file not found."))
            return

        cfg = get_blender_config_path()
        if not os.path.exists(cfg):
            messagebox.showerror(_("Error"), _("Blender config path not found."))
            return

        exe = get_blender_executable()
        if not os.path.exists(exe):
            messagebox.showerror(_("Error"), _("Blender not installed."))
            return

        import re, zipfile
        try:
            si = None
            if os.name == "nt":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0
            result = subprocess.run([exe, "--version"], stdout=subprocess.PIPE,
                                     text=True, startupinfo=si, timeout=15)
            line = result.stdout.splitlines()[0] if result.stdout else ""
            m = re.search(r"(\d+\.\d+)", line)
            if not m:
                messagebox.showerror(_("Error"), _("Could not detect Blender version."))
                return
            ver = m.group(1)
            addons_dir = os.path.join(cfg, ver, "scripts", "addons")
            os.makedirs(addons_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(addons_dir)
            messagebox.showinfo(_("Success"), _("Addon installed to Blender {}.").format(ver))
        except Exception as e:
            messagebox.showerror(_("Error"), str(e))

    def _reset_all_data(self):
        if not messagebox.askyesno(_("Confirm"), _("Delete all Blender Manager data?")):
            return
        try:
            d = get_blender_manager_dir()
            if os.path.exists(d):
                shutil.rmtree(d)
            self.config.reset_to_defaults()
            messagebox.showinfo(_("Done"), _("All data reset. Restart the app."))
        except Exception as e:
            messagebox.showerror(_("Error"), str(e))

    def _transfer_settings(self):
        src = self.src_var.get()
        dst = self.dst_var.get()
        if not src or not dst:
            messagebox.showerror(_("Error"), _("Select source and destination versions."))
            return
        base = get_blender_config_path()
        src_path = os.path.join(base, src)
        dst_path = os.path.join(base, dst)
        if not os.path.exists(src_path) or not os.path.exists(dst_path):
            messagebox.showerror(_("Error"), _("Version path not found."))
            return
        include = messagebox.askyesno(_("Include Addons?"), _("Include addons in transfer?"))
        try:
            sc = os.path.join(src_path, "config")
            dc = os.path.join(dst_path, "config")
            if os.path.exists(sc):
                if os.path.exists(dc):
                    shutil.rmtree(dc)
                shutil.copytree(sc, dc)
            if include:
                ss = os.path.join(src_path, "scripts")
                ds = os.path.join(dst_path, "scripts")
                if os.path.exists(ss):
                    if os.path.exists(ds):
                        shutil.rmtree(ds)
                    shutil.copytree(ss, ds)
            messagebox.showinfo(_("Done"), _("Settings transferred: {} -> {}").format(src, dst))
        except Exception as e:
            messagebox.showerror(_("Error"), str(e))

    def _export_config(self):
        ver = self.exp_var.get()
        if not ver:
            messagebox.showerror(_("Error"), _("Select a version."))
            return
        base = get_blender_config_path()
        vp = os.path.join(base, ver)
        if not os.path.exists(vp):
            messagebox.showerror(_("Error"), _("Version not found."))
            return
        dest = filedialog.askdirectory(title=_("Export To"))
        if not dest:
            return
        export_dir = os.path.join(dest, ver)
        if os.path.exists(export_dir):
            shutil.rmtree(export_dir)
        os.makedirs(export_dir)
        include = messagebox.askyesno(_("Include Addons?"), _("Include addons?"))
        try:
            sc = os.path.join(vp, "config")
            if os.path.exists(sc):
                shutil.copytree(sc, os.path.join(export_dir, "config"))
            if include:
                ss = os.path.join(vp, "scripts")
                if os.path.exists(ss):
                    shutil.copytree(ss, os.path.join(export_dir, "scripts"))
            messagebox.showinfo(_("Done"), _("Exported to {}").format(export_dir))
        except Exception as e:
            messagebox.showerror(_("Error"), str(e))

    def _import_config(self):
        ver = self.exp_var.get()
        if not ver:
            messagebox.showerror(_("Error"), _("Select a version."))
            return
        base = get_blender_config_path()
        vp = os.path.join(base, ver)
        if not os.path.exists(vp):
            messagebox.showerror(_("Error"), _("Version not found."))
            return
        src = filedialog.askdirectory(title=_("Import From"))
        if not src:
            return
        include = messagebox.askyesno(_("Include Addons?"), _("Include addons?"))
        try:
            sc = os.path.join(src, "config")
            dc = os.path.join(vp, "config")
            if os.path.exists(sc):
                if os.path.exists(dc):
                    shutil.rmtree(dc)
                shutil.copytree(sc, dc)
            if include:
                ss = os.path.join(src, "scripts")
                ds = os.path.join(vp, "scripts")
                if os.path.exists(ss):
                    if os.path.exists(ds):
                        shutil.rmtree(ds)
                    shutil.copytree(ss, ds)
            messagebox.showinfo(_("Done"), _("Imported to {}").format(ver))
        except Exception as e:
            messagebox.showerror(_("Error"), str(e))

    def _reset_blender_config(self):
        ver = self.cfg_ver_var.get()
        if not ver or ver == _("Select Version"):
            messagebox.showerror(_("Error"), _("Select a version."))
            return
        base = get_blender_config_path()
        vp = os.path.join(base, ver)
        if os.path.exists(vp):
            if messagebox.askyesno(_("Confirm"), _("Reset config for Blender {}?").format(ver)):
                shutil.rmtree(vp)
                messagebox.showinfo(_("Done"), _("Config reset for {}.").format(ver))
                versions = self._get_config_versions()
                self.cfg_cb["values"] = versions
                self.cfg_cb.set(_("Select Version"))


class HelpWindow:
    def __init__(self, app):
        self.app = app
        self._window = None
        self._build()

    def _build(self):
        w = tk.Toplevel(self.app)
        w.title(_("Help"))
        w.geometry("600x400")
        w.resizable(False, False)
        w.transient(self.app)
        w.grab_set()
        self._window = w

        nb = ttkb.Notebook(w)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        doc = ttkb.Frame(nb)
        nb.add(doc, text=_("Documentation"))
        txt = tk.Text(doc, wrap="word", padx=10, pady=10, font=("Segoe UI", 9))
        txt.insert("1.0", _("Blender Manager v1.0.2\n\n"
                   "Manage Blender versions, projects, addons and renders.\n"
                   "See the GitHub repo for full documentation:\n"
                   "https://github.com/verlorengest/BlenderManager\n\n"
                   "For feedback: majinkaji@proton.me\n"))
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)

        cred = ttkb.Frame(nb)
        nb.add(cred, text=_("Credits"))
        ttkb.Label(cred, text=_("Developed by verlorengest"),
                   font=("Segoe UI", 12)).pack(pady=100)

        donate = ttkb.Frame(nb)
        nb.add(donate, text=_("Donate"))
        ttkb.Label(donate, text=_("Support the project:"),
                   font=("Segoe UI", 12)).pack(pady=50)
        ttkb.Label(donate, text="https://verlorengest.gumroad.com/l/blendermanager",
                   foreground="blue", cursor="hand2",
                   font=("Segoe UI", 9, "underline")).pack()

        ttkb.Button(w, text=_("Close"), command=w.destroy, bootstyle=SECONDARY).pack(pady=(0, 10))


class ProjectWindow:
    def __init__(self, app):
        self.app = app
        self.config = ConfigManager()
        self.data = DataManager()
        self._window = None
        self.reference_images = {}
        self._build()

    def _build(self):
        w = tk.Toplevel(self.app)
        w.title(_("Create Project"))
        w.geometry("700x550")
        w.resizable(False, False)
        w.transient(self.app)
        w.grab_set()
        self._window = w

        nb = ttkb.Notebook(w)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        self._ref_tab(nb)
        self._mesh_tab(nb)
        self._settings_tab(nb)

        ttkb.Button(w, text=_("Create Project"), bootstyle=SUCCESS,
                     command=self._create).pack(pady=10)

    def _ref_tab(self, notebook):
        tab = ttkb.Frame(notebook, padding=20)
        notebook.add(tab, text=_("Reference Images"))
        ttkb.Label(tab, text=_("Reference Images (same size recommended)"),
                   font=("Segoe UI", 14, "bold")).pack(pady=(0, 10))
        img_frame = ttkb.Frame(tab)
        img_frame.pack(fill="both", expand=True)

        for pos in ["Front", "Back", "Right", "Left", "Top", "Bottom"]:
            k = pos.lower()
            f = ttkb.Frame(img_frame)
            f.pack(fill="x", pady=2)
            ttkb.Label(f, text=_(f"{pos}:"), width=10, anchor="e").pack(side="left")
            e = ttkb.Entry(f)
            e.pack(side="left", fill="x", expand=True, padx=5)
            ttkb.Button(f, text=_("Browse"), command=lambda p=k, entry=e: self._browse_img(p, entry)).pack(side="left")
            self.reference_images[k] = e

    def _mesh_tab(self, notebook):
        tab = ttkb.Frame(notebook, padding=20)
        notebook.add(tab, text=_("Base Mesh"))
        ttkb.Label(tab, text=_("Base Mesh"), font=("Segoe UI", 14, "bold")).pack(pady=(0, 10))

        meshes = self.data.load_base_meshes()
        self.mesh_var = tk.StringVar()
        cb = ttkb.Combobox(tab, textvariable=self.mesh_var, state="readonly", width=40)
        cb["values"] = list(meshes.keys())
        cb.pack(pady=10)
        ttkb.Button(tab, text=_("Add Base Mesh"), command=self._add_mesh).pack()

    def _settings_tab(self, notebook):
        tab = ttkb.Frame(notebook, padding=20)
        notebook.add(tab, text=_("Settings"))
        user = self.data.load_user_input()

        self.name_var = tk.StringVar(value=user.get("project_name", ""))
        ttkb.Label(tab, text=_("Project Name:")).pack(anchor="w")
        ttkb.Entry(tab, textvariable=self.name_var, width=40).pack(anchor="w", pady=5)

        self.dir_var = tk.StringVar(value=user.get("project_dir", ""))
        ttkb.Label(tab, text=_("Project Directory:")).pack(anchor="w")
        df = ttkb.Frame(tab)
        df.pack(fill="x", pady=5)
        ttkb.Entry(df, textvariable=self.dir_var, width=35, state="readonly").pack(side="left")
        ttkb.Button(df, text=_("Browse"), command=self._browse_dir).pack(side="left", padx=5)

        self.light_var = tk.BooleanVar(value=user.get("add_light", False))
        ttkb.Checkbutton(tab, text=_("Add Light"), variable=self.light_var).pack(anchor="w", pady=2)
        self.cam_var = tk.BooleanVar(value=user.get("add_camera", False))
        ttkb.Checkbutton(tab, text=_("Add Camera"), variable=self.cam_var).pack(anchor="w", pady=2)
        self.auto_save_var = tk.BooleanVar(value=user.get("auto_save_project", False))
        ttkb.Checkbutton(tab, text=_("Auto Save"), variable=self.auto_save_var).pack(anchor="w", pady=2)

        saved_int = user.get("auto_save_interval", "5 minutes")
        self.interval_var = tk.StringVar(value=saved_int)
        ttkb.Label(tab, text=_("Auto Save Interval:")).pack(anchor="w", pady=(10, 0))
        ttkb.Combobox(tab, textvariable=self.interval_var,
                       values=["5 minutes", "15 minutes", "30 minutes", "1 hour",
                               "2 hours", "3 hours", "6 hours", "12 hours", "24 hours"],
                       state="readonly", width=20).pack(anchor="w", pady=5)

    def _browse_img(self, pos, entry):
        fp = filedialog.askopenfilename(filetypes=[(_("Images"), "*.png;*.jpg;*.jpeg;*.bmp")])
        if fp:
            entry.delete(0, tk.END)
            entry.insert(0, fp)

    def _browse_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.dir_var.set(d)

    def _add_mesh(self):
        name = simpledialog.askstring(_("Name"), _("Mesh name:"), parent=self._window)
        if not name:
            return
        path = filedialog.askopenfilename(filetypes=[(_("Mesh"), "*.obj;*.fbx;*.stl")])
        if not path:
            return
        meshes = self.data.load_base_meshes()
        meshes[name] = path
        self.data.save_base_meshes(meshes)
        self.mesh_var.set(name)

    def _create(self):
        import time
        settings = {
            "reference_images": {k: e.get() for k, e in self.reference_images.items() if e.get()},
            "base_mesh": {"name": self.mesh_var.get(), "path": ""},
            "add_light": self.light_var.get(),
            "add_camera": self.cam_var.get(),
            "project_name": self.name_var.get(),
            "project_dir": self.dir_var.get(),
            "auto_save_project": self.auto_save_var.get(),
            "auto_save_interval": self.interval_var.get(),
            "auto_save_style": "overwrite",
        }
        ud = os.path.join(get_user_data_dir(), "settings.json")
        ensure_dir(os.path.dirname(ud))
        with open(ud, "w") as f:
            json.dump(settings, f, indent=4)
        self.data.save_user_input({
            "project_name": self.name_var.get(),
            "project_dir": self.dir_var.get(),
            "add_light": self.light_var.get(),
            "add_camera": self.cam_var.get(),
            "auto_save_project": self.auto_save_var.get(),
            "auto_save_interval": self.interval_var.get(),
        })
        messagebox.showinfo(_("Created"), _("Project settings saved."))
        self._window.destroy()
