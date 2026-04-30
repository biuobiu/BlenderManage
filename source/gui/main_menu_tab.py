import json
import os
import platform
import re
import subprocess
import threading
import time
import tkinter as tk
import zipfile
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog

from i18n import _

import ttkbootstrap as ttkb
from ttkbootstrap.constants import *

from core import (
    Logger, DataManager, ConfigManager, run_in_background,
    get_blender_executable, get_blender_config_path,
    get_blender_install_dir, get_blender_versions_dir,
    get_blender_manager_dir, get_paths_dir, ensure_dir,
    open_file_with_default_app,
)
from services import VersionService, UpdateService

log = Logger()

BLENDER_PATH = get_blender_install_dir()
BLENDER_ABSOLUTE_PATH = get_blender_executable()
BLENDER_DIR = get_blender_versions_dir()


class MainMenuTab:
    def __init__(self, app, frame):
        self.app = app
        self.frame = frame
        self.frame.configure(padding=10)
        self.config = ConfigManager()
        self.data = DataManager()
        self.version_service = VersionService()
        self.update_service = UpdateService()

        self.cancel_event = threading.Event()
        self.progress_var = tk.DoubleVar()
        self.project_times = {}

        self._build_ui()

    def _build_ui(self):
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(0, weight=1)
        inner = ttkb.Frame(self.frame)
        inner.grid(row=0, column=0, sticky="nsew")
        self.frame.grid_columnconfigure(1, weight=3)
        self.frame.grid_rowconfigure(0, weight=1)

        settings = self.config.get_all()
        bff = settings.get("button_font_family", "Segoe UI")
        bfs = settings.get("button_font_size", 11)

        btn_frame = ttkb.Frame(inner)
        btn_frame.grid(row=0, column=0, sticky="n", padx=(0, 10), pady=(5, 0))

        self.launch_btn = ttkb.Button(
            btn_frame, text=_("Launch Blender"), takefocus=False,
            command=self._launch_blender, bootstyle=SUCCESS, width=15
        )
        self.launch_btn.grid(row=1, column=0, pady=(30, 5), sticky="ew", ipady=5)
        self.app.bind_right_click(self.launch_btn, self._launch_context_menu)

        create_btn = ttkb.Button(
            btn_frame, text=_("Create Project"), takefocus=False,
            command=self.app._open_create_project_window,
            bootstyle=SUCCESS, width=15
        )
        create_btn.grid(row=2, column=0, pady=(10, 5), sticky="ew")

        update_btn = ttkb.Button(
            btn_frame, text=_("Check Updates"), takefocus=False,
            command=self._check_updates, bootstyle=PRIMARY, width=15
        )
        update_btn.grid(row=3, column=0, pady=(10, 5), sticky="ew")

        self.cancel_btn = ttkb.Button(
            btn_frame, text=_("Cancel Download"), takefocus=False,
            command=self._cancel_download, bootstyle=DANGER, width=15
        )
        self.cancel_btn.grid(row=4, column=0, pady=(10, 5), sticky="ew")
        self.cancel_btn.grid_remove()

        self.progress_bar = ttkb.Progressbar(
            btn_frame, orient="horizontal", mode="determinate",
            variable=self.progress_var, bootstyle=WARNING
        )
        self.progress_bar.grid(row=5, column=0, pady=(4, 0), sticky="ew")
        self.progress_bar.grid_remove()

        self.progress_label = ttkb.Label(
            btn_frame, text="", anchor="center",
            font=(bff, 10)
        )
        self.progress_label.grid(row=6, column=0, sticky="ew", pady=(0, 3))
        self.progress_label.grid_remove()

        settings_btn = ttkb.Button(
            btn_frame, text=_("Settings"), takefocus=False,
            command=self.app._open_settings_window, width=15
        )
        settings_btn.grid(row=7, column=0, pady=(10, 5), sticky="ew")

        help_btn = ttkb.Button(
            btn_frame, text=_("Help"), takefocus=False,
            command=self.app._open_help_window, width=15
        )
        help_btn.grid(row=8, column=0, pady=(10, 5), sticky="ew")

        self.bm_version_label = ttkb.Label(
            self.frame,
            text=_(f"BManager v{self.config.get('version', '1.0.2')}"),
            font=(bff, 8)
        )
        self.bm_version_label.place(relx=0.001, rely=0.98, anchor="sw")

        self.blender_version_label = ttkb.Label(
            self.frame, text=_("Blender Not Installed"),
            cursor="hand2", font=(bff, 8)
        )
        self.blender_version_label.place(relx=0.001, rely=0.94, anchor="sw")
        self.blender_version_label.bind("<Button-1>", self._show_blender_release_notes)

        proj_frame = ttkb.Frame(inner)
        proj_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        inner.grid_columnconfigure(1, weight=3)
        inner.grid_rowconfigure(0, weight=1)

        proj_header = ttkb.Frame(proj_frame)
        proj_header.pack(anchor="nw", pady=(0, 5), fill="x")

        ttkb.Label(proj_header, text=_("Recent Projects"),
                   font=(bff, 12, "bold")).pack(side="left")

        self.work_hours_label = ttkb.Label(
            proj_header, text="  ", font=(bff, 12)
        )
        self.work_hours_label.pack(side="left", padx=(10, 0))

        if not self.config.get("show_worktime_label", True):
            self.work_hours_label.pack_forget()

        tree_frame = ttkb.Frame(proj_frame)
        tree_frame.pack(fill="both", expand=True)

        self.projects_tree = ttkb.Treeview(
            tree_frame,
            columns=("Project Name", "Last Opened", "Path"),
            show="headings", height=15
        )
        self.projects_tree.heading("Project Name", text=_("Project Name"))
        self.projects_tree.heading("Last Opened", text=_("Last Opened"))
        self.projects_tree.heading("Path", text=_("Path"))
        self.projects_tree.column("Project Name", anchor="w", width=300, minwidth=200, stretch=True)
        self.projects_tree.column("Last Opened", anchor="center", width=150, minwidth=100, stretch=False)
        self.projects_tree.column("Path", width=0, stretch=False)
        self.projects_tree.grid(row=0, column=0, sticky="nsew")

        self.projects_tree.bind("<<TreeviewSelect>>", self._update_work_hours)
        self.projects_tree.bind("<Double-1>", self._on_project_double_click)
        self.app.bind_right_click(self.projects_tree, self._show_project_context_menu)

        scroll = ttkb.Scrollbar(tree_frame, orient="vertical", command=self.projects_tree.yview)
        self.projects_tree.configure(yscroll=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self._load_recent_projects()
        self._update_blender_version_label()
        self._update_bm_version_label()

    def _load_recent_projects(self):
        try:
            cfg_path = get_blender_config_path()
            ver = self._get_blender_folder()
            if not ver:
                return
            if platform.system() == "Darwin":
                ver = ".".join(ver.split(".")[:2])
            recent_path = os.path.join(cfg_path, ver, "config", "recent-files.txt")
            if not os.path.exists(recent_path):
                return
            with open(recent_path, "r", encoding="utf-8") as f:
                for line in f:
                    p = line.strip()
                    if os.path.exists(p):
                        lm = datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d")
                        self.projects_tree.insert("", "end", values=(
                            os.path.basename(p), lm, p
                        ))
        except Exception as e:
            log.debug(f"Load recent projects: {e}")

    def _get_blender_folder(self):
        base = get_blender_install_dir()
        if not os.path.exists(base):
            return None
        latest = None
        for entry in os.listdir(base):
            ep = os.path.join(base, entry)
            if os.path.isdir(ep):
                m = re.match(r"(\d+\.\d+)", entry)
                if m:
                    ver = m.group(1)
                    if not latest or list(map(int, ver.split("."))) > list(map(int, latest.split("."))):
                        latest = ver
        return latest

    def refresh_projects(self):
        for item in self.projects_tree.get_children():
            self.projects_tree.delete(item)
        self._load_recent_projects()

    def _launch_blender(self):
        exe = get_blender_executable()
        if not os.path.exists(exe):
            self._show_install_dialog()
            return
        def launch():
            self._disable_buttons(_("Running"))
            try:
                si = None
                if os.name == "nt":
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                proc = subprocess.Popen([exe], startupinfo=si)
                def monitor():
                    proc.wait()
                    self.app.after(0, self._enable_buttons)
                    self.app.after(0, self.refresh_projects)
                threading.Thread(target=monitor, daemon=True).start()
            except Exception as e:
                log.error(f"Launch Blender: {e}")
                self._enable_buttons()
        threading.Thread(target=launch, daemon=True).start()

    def _show_install_dialog(self):
        dialog = tk.Toplevel(self.app)
        dialog.title(_("Blender Not Installed"))
        dialog.geometry("320x180")
        dialog.resizable(False, False)
        dialog.transient(self.app)
        dialog.grab_set()
        self.app.center_window(dialog, 320, 180)

        frame = ttkb.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)

        ttkb.Label(frame, text=_("Blender is not installed.\nWould you like to install it?"),
                   font=("Segoe UI", 11, "bold"), anchor="center",
                   justify="center", wraplength=280).pack(pady=(0, 15))

        bf = ttkb.Frame(frame)
        bf.pack(pady=(0, 10))

        def on_yes():
            dialog.destroy()
            self._install_blender()

        ttkb.Button(bf, text=_("Yes"), command=on_yes, width=14).grid(row=0, column=0, padx=5)
        ttkb.Button(bf, text=_("No"), command=dialog.destroy, width=14).grid(row=0, column=1, padx=5)

        ttkb.Button(frame, text=_("Already Installed"),
                     command=lambda: self._handle_existing_blender(dialog),
                     width=30).pack()

    def _install_blender(self):
        def install():
            latest, download_url = self._get_latest_blender_version()
            if not latest or not download_url:
                self.app.after(0, lambda: messagebox.showerror(_("Error"), _("Could not fetch latest version.")))
                return
            try:
                self.app.after(0, self._show_progress)
                self.cancel_event.clear()
                self.app.after(0, lambda: self.cancel_btn.grid())

                file_name = os.path.basename(download_url)
                file_path = os.path.join(get_blender_manager_dir(), file_name)

                import requests
                session = requests.Session()
                response = session.get(download_url, stream=True, timeout=10)
                response.raise_for_status()
                total_length = int(response.headers.get('content-length', 0))
                downloaded = 0

                ensure_dir(os.path.dirname(file_path))
                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if self.cancel_event.is_set():
                            f.close()
                            os.remove(file_path)
                            self.app.after(0, self._hide_progress)
                            return
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_length > 0:
                                pct = downloaded / total_length * 100
                                self.app.after(0, lambda v=pct: self.progress_var.set(v))

                import shutil, zipfile
                target = get_blender_install_dir()
                if os.path.exists(target):
                    shutil.rmtree(target)
                ensure_dir(target)

                if file_name.endswith('.zip'):
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        root_items = zf.namelist()
                        top = set(i.split('/')[0] for i in root_items if i.strip())
                        if len(top) == 1:
                            root = list(top)[0]
                            for member in zf.infolist():
                                mpath = member.filename
                                if mpath.startswith(root + '/'):
                                    rel = mpath[len(root) + 1:]
                                    if rel:
                                        tp = os.path.join(target, rel)
                                        if member.is_dir():
                                            os.makedirs(tp, exist_ok=True)
                                        else:
                                            os.makedirs(os.path.dirname(tp), exist_ok=True)
                                            with zf.open(member) as src, open(tp, 'wb') as dst:
                                                shutil.copyfileobj(src, dst)
                        else:
                            zf.extractall(target)
                elif file_name.endswith('.dmg'):
                    if sys.platform == "darwin":
                        import tempfile as tf2
                        mount = tf2.mkdtemp()
                        subprocess.run(["hdiutil", "attach", file_path, "-mountpoint", mount], check=True)
                        app_src = os.path.join(mount, "Blender.app")
                        if os.path.exists(app_src):
                            shutil.copytree(app_src, os.path.join(target, "Blender.app"))
                        subprocess.run(["hdiutil", "detach", mount], check=True)
                        shutil.rmtree(mount)

                if os.path.exists(file_path):
                    os.remove(file_path)

                self._update_main_version(latest)
                self._update_blender_version_label()
                self.app.after(0, lambda: self.cancel_btn.grid_remove())
                self.app.after(0, lambda: messagebox.showinfo(_("Done"), _("Blender installed.")))
            except Exception as e:
                self.app.after(0, lambda: messagebox.showerror(_("Error"), str(e)))
            finally:
                self.app.after(0, self._hide_progress)

        threading.Thread(target=install, daemon=True).start()

    def _handle_existing_blender(self, dialog):
        dialog.destroy()
        folder = filedialog.askdirectory(title=_("Select Blender Installation Folder"))
        if not folder:
            return
        exe = get_blender_executable()
        exe_name = os.path.basename(exe)
        found_exe = None
        for root, dirs, files in os.walk(folder):
            if exe_name in files:
                found_exe = os.path.join(root, exe_name)
                break
        if not found_exe:
            messagebox.showerror(_("Error"), _("Blender executable not found in selected folder."))
            return
        target = os.path.dirname(exe)
        os.makedirs(target, exist_ok=True)
        def transfer():
            try:
                for item in os.listdir(folder):
                    s = os.path.join(folder, item)
                    d = os.path.join(target, item)
                    if os.path.isdir(s):
                        import shutil
                        if os.path.exists(d):
                            shutil.rmtree(d)
                        shutil.copytree(s, d)
                    else:
                        import shutil
                        shutil.copy2(s, d)
                self.app.after(0, self._update_blender_version_label)
                self.app.after(0, self.refresh_projects)
            except Exception as e:
                log.error(f"Transfer error: {e}")
        threading.Thread(target=transfer, daemon=True).start()

    def _launch_context_menu(self, event):
        menu = tk.Menu(self.launch_btn, tearoff=0)
        menu.add_command(label=_("Launch With Arguments"), command=self._launch_with_args)
        menu.add_command(label=_("Export Blender"), command=self._export_blender)
        menu.add_command(label=_("Delete Blender"), command=self._delete_blender)
        menu.post(event.x_root, event.y_root)

    def _launch_with_args(self):
        exe = get_blender_executable()
        if not os.path.exists(exe):
            messagebox.showwarning(_("Warning"), _("Blender is not installed."))
            return

        dialog = tk.Toplevel(self.app)
        dialog.title(_("Launch Blender with Arguments"))
        dialog.geometry("400x200")
        dialog.resizable(False, False)
        dialog.transient(self.app)
        dialog.grab_set()
        self.app.center_window(dialog, 400, 200)

        tk.Label(dialog, text=_("Enter Blender arguments:"), font=("Segoe UI", 12)).pack(pady=10)
        arg_entry = tk.Entry(dialog, width=50)
        arg_entry.pack(pady=5)

        def validate_and_launch():
            args = arg_entry.get().strip()
            if args and not args.startswith("--"):
                messagebox.showerror(_("Invalid Argument"), _("Arguments should start with '--'"))
                return
            try:
                cmd = [exe] + (args.split() if args else [])
                si = None
                if os.name == "nt":
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                proc = subprocess.Popen(cmd, startupinfo=si)
                def monitor():
                    proc.wait()
                    self.app.after(0, self.refresh_projects)
                threading.Thread(target=monitor, daemon=True).start()
                dialog.destroy()
            except Exception as e:
                messagebox.showerror(_("Error"), str(e))

        launch_btn = tk.Button(dialog, text=_("Launch"), command=validate_and_launch,
                                font=("Segoe UI", 12), fg="green")
        launch_btn.pack(pady=10)

    def _export_blender(self):
        src = get_blender_install_dir()
        if not os.path.exists(src):
            messagebox.showerror(_("Error"), _("Blender directory does not exist."))
            return
        dest = filedialog.askdirectory(title=_("Select Destination Directory"))
        if not dest:
            return
        compress = messagebox.askyesno(_("Compress"), _("Would you like to compress into ZIP?"))
        import shutil
        def do_export():
            try:
                if compress:
                    zip_path = os.path.join(dest, "blender_export.zip")
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                        for root, dirs, files in os.walk(src):
                            for f in files:
                                fp = os.path.join(root, f)
                                zf.write(fp, os.path.relpath(fp, src))
                    self.app.after(0, lambda: messagebox.showinfo(_("Success"), _(f"Exported to {zip_path}")))
                else:
                    target = os.path.join(dest, os.path.basename(src))
                    if os.path.exists(target):
                        shutil.rmtree(target)
                    shutil.copytree(src, target)
                    self.app.after(0, lambda: messagebox.showinfo(_("Success"), _(f"Exported to {target}")))
            except Exception as e:
                self.app.after(0, lambda: messagebox.showerror(_("Error"), str(e)))
        threading.Thread(target=do_export, daemon=True).start()

    def _delete_blender(self):
        src = get_blender_install_dir()
        if not os.path.exists(src):
            messagebox.showerror(_("Error"), _("Blender directory not found."))
            return
        if not messagebox.askyesno(_("Confirm"), _("Delete Blender installation?")):
            return
        import shutil
        def do_delete():
            try:
                shutil.rmtree(src)
                self.app.after(0, self._update_blender_version_label)
                self.app.after(0, lambda: messagebox.showinfo(_("Done"), _("Blender deleted.")))
            except Exception as e:
                self.app.after(0, lambda: messagebox.showerror(_("Error"), str(e)))
        threading.Thread(target=do_delete, daemon=True).start()

    def _check_updates(self):
        exe = get_blender_executable()
        if not os.path.exists(exe):
            self._show_install_dialog()
            return

        def check():
            installed = self._get_installed_blender_version(exe)
            if not installed:
                return
            latest, download_url = self._get_latest_blender_version()
            if not latest:
                self.app.after(0, lambda: messagebox.showerror(_("Error"), _("Could not fetch latest version.")))
                return
            if not self.version_service.is_newer(installed, latest):
                self.app.after(0, lambda v=installed: messagebox.showinfo(_("Up to Date"), _("Blender {0} is the latest.").format(v)))
                return
            self.app.after(0, self._show_progress)
            try:
                file_name = os.path.basename(download_url)
                file_path = os.path.join(get_blender_manager_dir(), file_name)
                import requests
                session = requests.Session()
                resp = session.get(download_url, stream=True, timeout=10)
                resp.raise_for_status()
                total = int(resp.headers.get('content-length', 0))
                downloaded = 0
                ensure_dir(os.path.dirname(file_path))
                with open(file_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                self.app.after(0, lambda v=downloaded/total*100: self.progress_var.set(v))
                import shutil, zipfile
                ver_dir = os.path.join(get_blender_versions_dir(), latest)
                if os.path.exists(ver_dir):
                    shutil.rmtree(ver_dir)
                ensure_dir(ver_dir)
                if file_name.endswith('.zip'):
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        top = set(i.split('/')[0] for i in zf.namelist() if i.strip())
                        if len(top) == 1:
                            root = list(top)[0]
                            for m in zf.infolist():
                                mp = m.filename
                                if mp.startswith(root + '/'):
                                    rel = mp[len(root) + 1:]
                                    if rel:
                                        tp = os.path.join(ver_dir, rel)
                                        if m.is_dir(): os.makedirs(tp, exist_ok=True)
                                        else:
                                            os.makedirs(os.path.dirname(tp), exist_ok=True)
                                            with zf.open(m) as s, open(tp, 'wb') as d:
                                                shutil.copyfileobj(s, d)
                        else:
                            zf.extractall(ver_dir)
                elif file_name.endswith('.dmg'):
                    import tempfile as tf2
                    mount = tf2.mkdtemp()
                    subprocess.run(["hdiutil", "attach", file_path, "-mountpoint", mount], check=True)
                    app_src = os.path.join(mount, "Blender.app")
                    if os.path.exists(app_src):
                        shutil.copytree(app_src, os.path.join(ver_dir, "Blender.app"))
                    subprocess.run(["hdiutil", "detach", mount], check=True)
                    shutil.rmtree(mount)
                if os.path.exists(file_path):
                    os.remove(file_path)
                self._update_main_version(latest)
                self.app.after(0, lambda: messagebox.showinfo(_("Done"), _("Blender updated.")))
            except Exception as e:
                self.app.after(0, lambda: messagebox.showerror(_("Error"), str(e)))
            finally:
                self.app.after(0, self._hide_progress)

        threading.Thread(target=check, daemon=True).start()

    def _get_installed_blender_version(self, exe):
        try:
            si = None
            if os.name == "nt":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0
            result = subprocess.run([exe, "--version"], stdout=subprocess.PIPE,
                                     text=True, startupinfo=si, timeout=15)
            line = result.stdout.splitlines()[0] if result.stdout else ""
            m = re.search(r"(\d+\.\d+(?:\.\d+)?)", line)
            return m.group(1) if m else None
        except Exception:
            return None

    def _get_latest_blender_version(self):
        from bs4 import BeautifulSoup
        import requests
        base = "https://download.blender.org/release/"
        try:
            resp = requests.get(base, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            majors = []
            for link in soup.find_all("a", href=True):
                href = link["href"].strip("/")
                m = re.match(r"Blender(\d+)\.(\d+)", href)
                if m:
                    majors.append((int(m.group(1)), int(m.group(2))))
            if not majors:
                return None, None
            mx, my = max(majors, key=lambda v: (v[0], v[1]))
            mv_url = f"{base}Blender{mx}.{my}/"
            resp = requests.get(mv_url, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            sys_name = platform.system()
            if sys_name == "Windows":
                suffix = "windows-x64.zip"
            elif sys_name == "Darwin":
                machine = platform.machine()
                suffix = "macos-arm64.dmg" if "arm" in machine.lower() else "macos-x64.dmg"
            else:
                suffix = "linux-x64.tar.xz"
            minors = []
            dl_url = None
            for link in soup.find_all("a", href=True):
                href = link["href"].strip("/")
                m = re.match(rf"blender-(\d+)\.(\d+)\.(\d+)-{suffix}", href)
                if m and int(m.group(1)) == mx and int(m.group(2)) == my:
                    minors.append(int(m.group(3)))
                    dl_url = mv_url + href
            if not minors:
                return None, None
            latest = max(minors)
            ver = f"{mx}.{my}.{latest}"
            dl_url = f"{mv_url}blender-{ver}-{suffix}"
            return ver, dl_url
        except Exception as e:
            log.error(f"Latest version fetch: {e}")
            return None, None

    def _extract_blender(self, temp_file):
        import shutil
        target = get_blender_install_dir()
        if not target or target == get_blender_versions_dir():
            log.error("Cannot extract: no main version selected")
            return
        if os.path.exists(target):
            shutil.rmtree(target)
        ext = os.path.splitext(temp_file)[1].lower()
        if ext == ".zip":
            import zipfile, tempfile
            td = tempfile.mkdtemp()
            with zipfile.ZipFile(temp_file, "r") as zf:
                zf.extractall(td)
            items = os.listdir(td)
            src = os.path.join(td, items[0]) if len(items) == 1 and os.path.isdir(os.path.join(td, items[0])) else td
            os.makedirs(target, exist_ok=True)
            for item in os.listdir(src):
                s = os.path.join(src, item)
                d = os.path.join(target, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d)
                else:
                    shutil.copy2(s, d)
            shutil.rmtree(td)
        elif ext == ".dmg":
            import tempfile as tf
            mount = tf.mkdtemp()
            subprocess.run(["hdiutil", "attach", temp_file, "-mountpoint", mount], check=True)
            app_src = os.path.join(mount, "Blender.app")
            if os.path.exists(app_src):
                os.makedirs(target, exist_ok=True)
                shutil.copytree(app_src, os.path.join(target, "Blender.app"))
            subprocess.run(["hdiutil", "detach", mount], check=True)
            shutil.rmtree(mount)
        if os.path.exists(temp_file):
            os.remove(temp_file)

    def _cancel_download(self):
        self.cancel_event.set()
        messagebox.showinfo(_("Cancelled"), _("Download cancelled."))

    def _show_progress(self):
        self.progress_bar.grid()
        self.progress_label.config(text=_("Downloading..."))
        self.progress_label.grid()
        self.launch_btn.config(state="disabled")
        self.cancel_btn.grid()

    def _hide_progress(self):
        self.progress_bar.grid_remove()
        self.progress_label.grid_remove()
        self.cancel_btn.grid_remove()
        self.launch_btn.config(state="normal")

    def _disable_buttons(self, text=None):
        if text is None:
            text = _("Please wait...")
        self.launch_btn.config(text=text, state="disabled")

    def _enable_buttons(self):
        self.launch_btn.config(text=_("Launch Blender"), state="normal")

    def _update_work_hours(self, event):
        if not self.config.get("show_worktime_label", True):
            return
        sel = self.projects_tree.selection()
        if sel:
            name = self.projects_tree.item(sel[0], "values")[0]
            hours = self.project_times.get(name, "")
            self.work_hours_label.config(text=_(f"Work Time: {hours}"))
        else:
            self.work_hours_label.config(text=_("Work Time: "))

    def _on_project_double_click(self, event):
        sel = self.projects_tree.focus()
        if not sel:
            return
        vals = self.projects_tree.item(sel, "values")
        if len(vals) < 3:
            return
        proj_path = vals[2]
        exe = get_blender_executable()
        if not os.path.exists(proj_path) or not os.path.exists(exe):
            return
        try:
            si = None
            if os.name == "nt":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.Popen([exe, proj_path], startupinfo=si)
        except Exception as e:
            log.error(f"Open project: {e}")

    def _show_project_context_menu(self, event):
        item = self.projects_tree.identify_row(event.y)
        if not item:
            return
        self.projects_tree.selection_set(item)
        self.projects_tree.focus(item)
        menu = tk.Menu(self.projects_tree, tearoff=0)
        menu.add_command(label=_("Delete Project"), command=self._delete_selected_project)
        menu.post(event.x_root, event.y_root)

    def _delete_selected_project(self):
        sel = self.projects_tree.focus()
        if not sel:
            return
        vals = self.projects_tree.item(sel, "values")
        name = vals[0]
        path = vals[2] if len(vals) > 2 else ""
        if not path or not os.path.exists(path):
            messagebox.showwarning(_("Not Found"), _("Project file not found."))
            return
        if messagebox.askyesno(_("Confirm"), _(f"Delete '{name}'?")):
            try:
                os.remove(path)
                self.projects_tree.delete(sel)
                messagebox.showinfo(_("Deleted"), _(f"{name} deleted."))
            except Exception as e:
                messagebox.showerror(_("Error"), str(e))

    def _update_main_version(self, version):
        cfg_path = os.path.join(get_blender_manager_dir(), "config.json")
        try:
            with open(cfg_path, "r") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        cfg["selected_main_version"] = version
        with open(cfg_path, "w") as f:
            json.dump(cfg, f, indent=4)

    def _update_blender_version_label(self):
        exe = get_blender_executable()
        ver = self._get_installed_blender_version(exe) if os.path.exists(exe) else None
        text = _(f"Blender {ver}") if ver else _("Blender Not Installed")
        self.blender_version_label.config(text=text)

    def _update_bm_version_label(self):
        cv = self.config.get("version", "0.0.0")
        lv = self.update_service.check_bm_latest_version()
        text = _(f"BManager v{cv}")
        if lv and self.version_service.is_newer(cv, lv):
            text += " !"
            self.bm_version_label.config(text=text, foreground="orange", cursor="hand2")
            self.bm_version_label.bind("<Button-1>", lambda e: self.app._open_settings_window())
        else:
            self.bm_version_label.config(text=text, foreground="green", cursor="arrow")
            self.bm_version_label.unbind("<Button-1>")

    def _show_blender_release_notes(self, event):
        exe = get_blender_executable()
        if not os.path.exists(exe):
            return
        ver = self._get_installed_blender_version(exe)
        if not ver:
            return
        parts = ver.split(".")
        url = f"https://www.blender.org/download/releases/{parts[0]}.{parts[1]}/"
        import webbrowser
        webbrowser.open(url)
