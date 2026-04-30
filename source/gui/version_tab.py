import os
import platform
import queue
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import tkinter as tk
import webbrowser
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import re
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
import requests
from bs4 import BeautifulSoup

from core import (
    Logger, DataManager, ConfigManager, run_in_background,
    get_blender_manager_dir, get_blender_versions_dir,
    get_blender_install_dir, get_blender_executable,
    normalize_path, ensure_dir
)
from i18n import _

log = Logger()


class VersionManagementTab:
    def __init__(self, app, notebook):
        self.app = app
        self.notebook = notebook
        self.config = ConfigManager()
        self.data = DataManager()

        self.frame = ttkb.Frame(self.notebook, padding=(10, 0, 0, 0))

        self.download_links = {}
        self.is_installing = False
        self.cancel_event = threading.Event()
        self.showing_install = True
        self.version_queue = queue.Queue()

        self._build_ui()
        self._process_queue()

    def _build_ui(self):
        self.versions_parent_frame = ttkb.Frame(self.frame)
        self.versions_parent_frame.pack(expand=True, fill='both')

        self._create_install_view()
        self._create_installed_view()

        self.toggle_button_frame = ttkb.Frame(self.frame)
        self.toggle_button_frame.place(relx=0.0, rely=1.0, anchor='sw')

        self.toggle_button = ttkb.Button(
            self.toggle_button_frame,
            text=_("Show Installed Versions"),
            takefocus=False,
            command=self.toggle_views,
            bootstyle="secondary"
        )
        self.toggle_button.pack(padx=10, pady=10)

        self.show_install_view()

    # -----------------------------------------------------------
    # Queue processing (thread-safe UI updates)
    # -----------------------------------------------------------

    def _process_queue(self):
        try:
            while True:
                msg = self.version_queue.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass
        self.frame.after(100, self._process_queue)

    def _handle_message(self, msg):
        if isinstance(msg, float):
            self.install_progress_var.set(msg)
        elif msg == 'DOWNLOAD_COMPLETE':
            self.install_progress_var.set(100)
            self.install_progress_frame.pack_forget()
            self.cancel_button.pack_forget()
            self.install_btn.configure(text=_('Install'), state='normal')
            self.is_installing = False
            sel = self.tree.selection()
            if sel:
                version = self.tree.item(sel, "values")[0]
                link = self.download_links.get(version)
                if link:
                    fname = os.path.basename(link)
                    fpath = os.path.join(get_blender_manager_dir(), fname)
                    if os.path.exists(fpath):
                        try:
                            time.sleep(5)
                            os.remove(fpath)
                        except Exception as e:
                            log.error(f"Error removing archive: {e}")
        elif msg == 'INSTALLATION_CANCELED':
            self.install_progress_frame.pack_forget()
            self.cancel_button.pack_forget()
            self.is_installing = False
            self.install_btn.configure(text=_('Install'), state='normal')
            self.cancel_event.clear()
            self.install_progress_var.set(0)
            self._cleanup_incomplete_download()
            self.frame.after(0, lambda: self._safe_messagebox("info", _("Canceled"), _("Installation has been canceled.")))
        elif msg == 'INSTALLATION_FAILED':
            self.install_progress_frame.pack_forget()
            self.cancel_button.pack_forget()
            self.is_installing = False
            self.cancel_event.clear()
            self.install_btn.configure(text=_('Install'), state='normal')
            self.install_progress_var.set(0)
            self._cleanup_incomplete_download()
            self.frame.after(0, lambda: self._safe_messagebox("error", _("Error"), _("Installation failed.")))
        elif isinstance(msg, tuple):
            if msg[0] == 'INSTALLATION_SUCCESS':
                version = msg[1]
                self.install_progress_frame.pack_forget()
                self.cancel_button.pack_forget()
                self.is_installing = False
                self.install_btn.configure(text=_('Install'), state='normal')
                self.cancel_event.clear()
                self.install_progress_var.set(0)
                self.frame.after(0, lambda: self._safe_messagebox("info", _("Success"), _("Successfully installed Blender {0}.").format(version)))
            elif msg[0] == 'UPDATE_TREEVIEW':
                versions = msg[1]
                links = msg[2]
                dates = msg[3]

                def parse_version(v):
                    try:
                        vn = v.split(" ")[1]
                        if all(part.isdigit() for part in vn.split(".")):
                            return list(map(int, vn.split(".")))
                        return [0]
                    except (IndexError, ValueError):
                        return [0]

                sorted_versions = sorted(versions, key=parse_version, reverse=True)
                self.tree.delete(*self.tree.get_children())
                for version in sorted_versions:
                    rd = dates.get(version, _("Unknown Date"))
                    self.tree.insert("", "end", values=(version, rd))
                    self.download_links[version] = links[version]
            elif msg[0] == 'ERROR':
                self.frame.after(0, lambda e=msg[1]: self._safe_messagebox("error", _("Error"), e))
                self._reset_fetch_buttons()

    def _reset_fetch_buttons(self):
        self.get_stable_btn.config(text=_("Get Stable Versions"), state='normal')
        self.get_unstable_btn.config(text=_("Get Unstable Versions"), state='normal')

    def _cleanup_incomplete_download(self):
        sel = self.tree.selection()
        if sel:
            version = self.tree.item(sel, "values")[0]
            link = self.download_links.get(version)
            if link:
                fname = os.path.basename(link)
                fpath = os.path.join(get_blender_manager_dir(), fname)
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception as e:
                        log.error(f"Error removing incomplete download: {e}")

    def _safe_messagebox(self, kind, title, message):
        from tkinter import messagebox
        try:
            if kind == "error":
                messagebox.showerror(title, message)
            else:
                messagebox.showinfo(title, message)
        except Exception as e:
            log.error(f"Messagebox error: {e}")

    # -----------------------------------------------------------
    # Toggle views
    # -----------------------------------------------------------

    def show_install_view(self):
        self.installed_frame.pack_forget()
        self.install_frame.pack(expand=True, fill='both')
        self.toggle_button.configure(text=_("Show Installed Versions"))
        self.showing_install = True

    def show_installed_view(self):
        self.install_frame.pack_forget()
        self.installed_frame.pack(expand=True, fill='both')
        self.toggle_button.configure(text=_("Install a Version"))
        self.showing_install = False

    def toggle_views(self):
        if self.showing_install:
            self.show_installed_view()
        else:
            self.show_install_view()

    # -----------------------------------------------------------
    # Install View
    # -----------------------------------------------------------

    def _create_install_view(self):
        self.install_frame = ttkb.Frame(self.versions_parent_frame, padding=(0, 0, 0, 0))

        left_frame = ttkb.Frame(self.install_frame)
        left_frame.pack(side='left', fill='y', padx=(0, 10), pady=(0, 10))

        right_frame = ttkb.Frame(self.install_frame)
        right_frame.pack(side='right', expand=True, fill='both')

        settings = self.config.get_all()
        bff = settings.get("button_font_family", "Segoe UI")
        tff = settings.get("treeview_font_family", "Segoe UI")
        tfs = settings.get("treeview_font_size", 12)

        os_frame = ttkb.Frame(left_frame)
        os_frame.pack(fill='x', pady=(0, 10))

        ttkb.Label(os_frame, text=_("Select Operating System:"), font=(bff, 10, 'bold')).pack(side='top', padx=(10, 10))

        self.os_combobox = ttkb.Combobox(
            os_frame, values=["Windows", "macOS", "Linux"],
            state='readonly', font=(bff, 10), bootstyle="primary"
        )
        self.os_combobox.set(_("Select OS"))
        self.os_combobox.pack(fill='x', padx=(10, 10))
        self.os_combobox.bind("<<ComboboxSelected>>", self._on_os_selected)

        self.win_arch_combobox = ttkb.Combobox(
            os_frame, values=["32-bit", "64-bit"],
            state='readonly', font=(bff, 10), bootstyle="primary"
        )
        self.win_arch_combobox.set(_("Select Architecture"))
        self.win_arch_combobox.pack(fill='x', padx=(10, 10))
        self.win_arch_combobox.pack_forget()

        self.arch_combobox = ttkb.Combobox(
            os_frame, values=["Intel", "Apple Silicon"],
            state='readonly', font=(bff, 10), bootstyle="primary"
        )
        self.arch_combobox.set(_("Select Architecture"))
        self.arch_combobox.pack(fill='x', padx=(10, 10))
        self.arch_combobox.pack_forget()

        buttons_frame = ttkb.Frame(left_frame)
        buttons_frame.pack(fill='x', pady=(0, 10))

        self.get_stable_btn = ttkb.Button(
            buttons_frame, text=_("Get Stable Versions"), takefocus=False,
            command=self._get_stable_versions, bootstyle="primary"
        )
        self.get_stable_btn.pack(fill='x', pady=(5, 5), padx=(10, 10))

        self.get_unstable_btn = ttkb.Button(
            buttons_frame, text=_("Get Unstable Versions"), takefocus=False,
            command=self._get_unstable_versions, bootstyle="primary"
        )
        self.get_unstable_btn.pack(fill='x', pady=(5, 5), padx=(10, 10))

        self.install_btn = ttkb.Button(
            left_frame, text=_("Install"), takefocus=False,
            command=self._install_version, bootstyle="primary"
        )
        self.install_btn.pack(fill='x', pady=(5, 10), padx=(10, 10))

        self.install_progress_frame = ttkb.Frame(left_frame)
        self.install_progress_label = ttkb.Label(
            self.install_progress_frame, text=_("Download Progress:"), font=('Helvetica', 10)
        )
        self.install_progress_label.pack(side='top', padx=(10, 10))

        self.install_progress_var = tk.DoubleVar()
        self.install_progress_bar = ttkb.Progressbar(
            self.install_progress_frame, variable=self.install_progress_var,
            maximum=100, bootstyle="primary-striped"
        )
        self.install_progress_bar.pack(fill='x', expand=True)
        self.install_progress_frame.pack(fill='x', pady=(5, 10), padx=(10, 10))
        self.install_progress_frame.pack_forget()

        self.cancel_button = ttkb.Button(
            left_frame, text=_("Cancel"), takefocus=False,
            command=self._cancel_installation, bootstyle="danger"
        )
        self.cancel_button.pack(fill='x', pady=(5, 10), padx=(10, 10))
        self.cancel_button.pack_forget()

        self.release_notes_btn = ttkb.Button(
            left_frame, text=_("Release Notes"), takefocus=False,
            command=self._show_release_notes, bootstyle="info"
        )
        self.release_notes_btn.pack(fill='x', pady=(5, 10), padx=(10, 10))
        self.release_notes_btn.config(state='disabled')

        style = ttkb.Style()
        style.configure("InstallVersions.Treeview", font=(tff, tfs), rowheight=30)
        style.configure("InstallVersions.Treeview.Heading", font=('Segoe UI', 14, 'bold'))

        self.tree = ttkb.Treeview(
            right_frame, columns=("Version", "Release Date"),
            show="headings", height=20, style="InstallVersions.Treeview"
        )
        self.tree.heading("Version", text=_("Blender Version"),
                          command=lambda: self._sort_treeview_column("Version"))
        self.tree.heading("Release Date", text=_("Release Date"),
                          command=lambda: self._sort_treeview_column("Release Date"))
        self.tree.column("Version", anchor="center")
        self.tree.column("Release Date", anchor="center")
        self.tree.pack(expand=True, fill='both', padx=0, pady=0)
        self.tree.bind("<<TreeviewSelect>>", self._on_treeview_select)

        current_os = platform.system()
        if current_os == "Windows":
            self.os_combobox.set("Windows")
            arch = platform.architecture()[0]
            self.win_arch_combobox.set("64-bit" if arch == "64bit" else "32-bit")
            self._on_os_selected(None)
        elif current_os == "Darwin":
            self.os_combobox.set("macOS")
            machine = platform.machine().lower()
            if "arm" in machine or "aarch64" in machine:
                self.arch_combobox.set("Apple Silicon")
            else:
                self.arch_combobox.set("Intel")
            self._on_os_selected(None)
        elif current_os == "Linux":
            self.os_combobox.set("Linux")
            self._on_os_selected(None)

    def _on_os_selected(self, event):
        selected_os = self.os_combobox.get()

        if sys.platform.startswith('win') and selected_os != "Windows":
            from tkinter import messagebox
            messagebox.showwarning(
                _("Warning"),
                _("You are running Windows. Selecting another OS may not work properly.")
            )

        if selected_os == "Windows":
            self.win_arch_combobox.pack(fill='x', padx=(10, 10))
            self.arch_combobox.pack_forget()
        elif selected_os == "macOS":
            self.win_arch_combobox.pack_forget()
            self.arch_combobox.pack(fill='x', padx=(10, 10))
        else:
            self.win_arch_combobox.pack_forget()
            self.arch_combobox.pack_forget()

    def _get_stable_versions(self):
        self.get_stable_btn.config(text=_("Loading..."), state='disabled')
        run_in_background(self._fetch_stable_versions_sync, name="fetch-stable")

    def _fetch_stable_versions_sync(self):
        os_map = {"Windows": "windows", "macOS": "darwin", "Linux": "linux"}
        selected_os = self.os_combobox.get()
        if selected_os not in os_map:
            self.version_queue.put(('ERROR', _("Please select a valid OS.")))
            return

        plat = os_map[selected_os]
        architecture = None

        if plat == "windows":
            arch_selection = self.win_arch_combobox.get()
            if arch_selection == "64-bit":
                architecture = "x64"
            elif arch_selection == "32-bit":
                architecture = "x86"
            else:
                self.version_queue.put(('ERROR', _("Please select 32-bit or 64-bit for Windows.")))
                return
        elif plat == "darwin":
            arch_selection = self.arch_combobox.get()
            if arch_selection == "Intel":
                architecture = "x64"
            elif arch_selection == "Apple Silicon":
                architecture = "arm64"
            else:
                self.version_queue.put(('ERROR', _("Please select a valid architecture for macOS.")))
                return

        base_url = "https://download.blender.org/release/"

        try:
            resp = requests.get(base_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            version_links = [
                a['href'] for a in soup.find_all('a', href=True)
                if a['href'].startswith("Blender")
            ]
            if not version_links:
                self.version_queue.put(('ERROR', _("No stable versions found.")))
                return

            versions = []
            links = {}
            dates = {}

            def fetch_version_page(version_link):
                vurl = base_url + version_link
                try:
                    vresp = requests.get(vurl, timeout=15)
                    vresp.raise_for_status()
                    vsoup = BeautifulSoup(vresp.text, "html.parser")
                    pre_tag = vsoup.find("pre")
                    if not pre_tag:
                        return [], {}, {}
                    lines = pre_tag.text.splitlines()
                    local_versions = []
                    local_links = {}
                    local_dates = {}
                    for line in lines:
                        parts = line.split()
                        if len(parts) < 3:
                            continue
                        file_name = parts[0]
                        date_str = " ".join(parts[1:3])
                        if file_name.endswith(".sha256") or file_name.endswith(".md5"):
                            continue
                        full_link = vurl + file_name
                        try:
                            version_name = "Blender " + file_name.split('-')[1]
                        except IndexError:
                            version_name = "Blender " + vurl.strip('/').split('/')[-1]

                        if plat == "windows":
                            is_64bit = "x64" in file_name or "windows64" in file_name
                            is_32bit = "x86" in file_name or "windows32" in file_name
                            is_generic = "windows" in file_name and not (is_64bit or is_32bit)
                            if architecture == "x64" and (is_64bit or is_generic):
                                if file_name.endswith(".zip"):
                                    local_versions.append(version_name)
                                    local_links[version_name] = full_link
                                    local_dates[version_name] = date_str
                            elif architecture == "x86" and (is_32bit or is_generic):
                                if file_name.endswith(".zip"):
                                    local_versions.append(version_name)
                                    local_links[version_name] = full_link
                                    local_dates[version_name] = date_str
                        elif plat == "darwin":
                            if ("darwin" in file_name or "macos" in file_name) and architecture in file_name and file_name.endswith(".dmg"):
                                local_versions.append(version_name)
                                local_links[version_name] = full_link
                                local_dates[version_name] = date_str
                        elif plat == "linux":
                            if "linux" in file_name and (file_name.endswith(".tar.xz") or file_name.endswith(".tar.gz")):
                                local_versions.append(version_name)
                                local_links[version_name] = full_link
                                local_dates[version_name] = date_str
                    return local_versions, local_links, local_dates
                except Exception:
                    return [], {}, {}

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(fetch_version_page, vl) for vl in version_links]
                for future in as_completed(futures):
                    v, l, d = future.result()
                    versions.extend(v)
                    links.update(l)
                    dates.update(d)

            if not versions:
                self.version_queue.put(('ERROR', _("No stable versions found for the selected platform.")))
                return

            self.version_queue.put(('UPDATE_TREEVIEW', versions, links, dates))
        except requests.RequestException as e:
            self.version_queue.put(('ERROR', _(f"Network error: {str(e)}")))
        except Exception as e:
            self.version_queue.put(('ERROR', _(f"An unexpected error occurred: {str(e)}")))

    def _get_unstable_versions(self):
        self.get_unstable_btn.config(text=_("Loading..."), state='disabled')
        run_in_background(self._fetch_unstable_versions_sync, name="fetch-unstable")

    def _fetch_unstable_versions_sync(self):
        os_map = {"Windows": "windows", "macOS": "darwin", "Linux": "linux"}
        selected_os = self.os_combobox.get()
        if selected_os not in os_map:
            from tkinter import messagebox
            self.frame.after(0, lambda: messagebox.showerror(_("Error"), _("Please select a valid OS.")))
            self.frame.after(0, lambda: self.get_unstable_btn.config(text=_("Get Unstable Versions"), state='normal'))
            return

        plat = os_map[selected_os]
        architecture = None

        if plat == "darwin":
            arch_selection = self.arch_combobox.get()
            if arch_selection == "Intel":
                architecture = "is-arch-x86_64"
            elif arch_selection == "Apple Silicon":
                architecture = "is-arch-arm64"
            else:
                from tkinter import messagebox
                self.frame.after(0, lambda: messagebox.showerror(_("Error"), _("Please select a valid architecture for macOS.")))
                self.frame.after(0, lambda: self.get_unstable_btn.config(text=_("Get Unstable Versions"), state='normal'))
                return
        elif plat == "windows":
            architecture = "is-arch-amd64"

        url = "https://builder.blender.org/download/daily/archive/"

        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            builds = soup.select(f'div.builds-list-container[data-platform="{plat}"] li.t-row.build')
            if not builds:
                self.frame.after(0, lambda: self.get_unstable_btn.config(text=_("Get Unstable Versions"), state='normal'))
                self.version_queue.put(('ERROR', _("No versions found. The site structure may have changed.")))
                return

            versions = []
            links = {}
            dates = {}

            for build in builds:
                classes = build.get("class", [])
                if architecture and architecture not in classes:
                    continue

                version_element = build.select_one(".t-cell.b-version")
                download_element = build.select_one(".t-cell.b-down a")
                if version_element and download_element:
                    version = version_element.text.strip()
                    download_link = download_element["href"]

                    if download_link.endswith(".sha256"):
                        download_link = download_link.replace(".sha256", "")

                    if plat == "windows" and not download_link.endswith(".zip"):
                        continue

                    if version not in versions:
                        versions.append(version)
                        links[version] = download_link
                        dates[version] = _("Unknown Date")

            if not versions:
                self.frame.after(0, lambda: self.get_unstable_btn.config(text=_("Get Unstable Versions"), state='normal'))
                self.version_queue.put(('ERROR', _("No versions found.")))
                return

            self.version_queue.put(('UPDATE_TREEVIEW', versions, links, dates))
            self.frame.after(0, lambda: self.get_unstable_btn.config(text=_("Get Unstable Versions"), state='normal'))
        except requests.RequestException as e:
            self.frame.after(0, lambda: self.get_unstable_btn.config(text=_("Get Unstable Versions"), state='normal'))
            self.version_queue.put(('ERROR', _(f"Network error: {str(e)}")))
        except Exception as e:
            self.frame.after(0, lambda: self.get_unstable_btn.config(text=_("Get Unstable Versions"), state='normal'))
            self.version_queue.put(('ERROR', _(f"An unexpected error occurred: {str(e)}")))

    def _on_treeview_select(self, event):
        selected_item = self.tree.focus()
        if selected_item:
            self.release_notes_btn.config(state='normal')
        else:
            self.release_notes_btn.config(state='disabled')

    def _sort_treeview_column(self, column_name):
        data = [(self.tree.set(item, column_name), item) for item in self.tree.get_children("")]

        if column_name == "Release Date":
            def parse_date(date_str):
                try:
                    parsed_date = datetime.strptime(date_str, "%d-%b-%Y %H:%M")
                    return (parsed_date.year, parsed_date.month, parsed_date.day, parsed_date.hour, parsed_date.minute)
                except ValueError:
                    return (0, 0, 0, 0, 0)
            data.sort(key=lambda x: parse_date(x[0]))
        else:
            data.sort(key=lambda x: x[0])

        is_currently_sorted_ascending = getattr(self, f"{column_name}_sorted_ascending", True)
        if not is_currently_sorted_ascending:
            data.reverse()

        for index, (_, item) in enumerate(data):
            self.tree.move(item, '', index)

        setattr(self, f"{column_name}_sorted_ascending", not is_currently_sorted_ascending)

    def _show_release_notes(self):
        selected_item = self.tree.focus()
        if not selected_item:
            from tkinter import messagebox
            messagebox.showerror(_("Error"), _("No version selected."))
            return

        version_text = self.tree.item(selected_item, "values")[0]
        version = version_text.replace("Blender", "").strip()
        version_parts = version.split('.')

        if len(version_parts) >= 2:
            major = version_parts[0]
            minor = version_parts[1]
            official_url = f"https://www.blender.org/download/releases/{major}.{minor}/"
            alternative_url = f"https://developer.blender.org/docs/release_notes/{major}.{minor}/"

            def check_url(url):
                try:
                    r = requests.head(url, timeout=5)
                    return r.status_code == 200
                except Exception:
                    return False

            try:
                target = None
                if check_url(official_url):
                    target = official_url
                elif check_url(alternative_url):
                    target = alternative_url

                if target:
                    try:
                        import webview
                        webview.create_window(_(f"Release Notes for Blender {major}.{minor}"), target)
                        webview.start()
                    except ImportError:
                        webbrowser.open(target)
                else:
                    from tkinter import messagebox
                    messagebox.showerror(_("Error"), _(f"Release notes for Blender {major}.{minor} not found."))
            except Exception as e:
                from tkinter import messagebox
                messagebox.showerror(_("Error"), _(f"An unexpected error occurred: {e}"))
        else:
            from tkinter import messagebox
            messagebox.showerror(_("Error"), _("Invalid version format."))

    def _install_version(self):
        if self.is_installing:
            from tkinter import messagebox
            messagebox.showwarning(_("Warning"), _("Another installation is in progress."))
            return

        selected_item = self.tree.selection()
        if not selected_item:
            from tkinter import messagebox
            messagebox.showwarning(_("Warning"), _("Please select a version to install."))
            return

        version = self.tree.item(selected_item, "values")[0]
        download_url = self.download_links.get(version)

        if not download_url:
            from tkinter import messagebox
            messagebox.showerror(_("Error"), _("Download URL not found."))
            return

        self.cancel_button.pack(pady=(0, 15), fill='x')
        self.is_installing = True
        self.install_progress_var.set(0)
        self.install_progress_frame.pack(fill='x', pady=(0, 10))
        self.install_btn.configure(text=_('Installing'), state='disabled')

        run_in_background(
            lambda: self._download_and_install(version, download_url),
            name="download-install"
        )

    def _download_and_install(self, version, download_url):
        chunk_mult = self.config.get("chunk_size_multiplier", 3)
        chunk_size = chunk_mult * 1024 * 1024
        file_name = os.path.basename(download_url)
        file_path = os.path.join(get_blender_manager_dir(), file_name)
        versions_dir = get_blender_versions_dir()

        session = requests.Session()

        try:
            response = session.get(download_url, stream=True, timeout=10)
            response.raise_for_status()

            total_length = int(response.headers.get('content-length', 0))
            downloaded = 0

            ensure_dir(os.path.dirname(file_path))

            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if self.cancel_event.is_set():
                        self.version_queue.put('INSTALLATION_CANCELED')
                        return
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        percent = (downloaded / total_length) * 100 if total_length > 0 else 0
                        self.install_progress_var.set(percent)
                        self.version_queue.put(percent)

            extracted_path = os.path.join(versions_dir, version)
            ensure_dir(extracted_path)

            if file_name.endswith('.zip'):
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    root_items = zip_ref.namelist()
                    top_level_dirs = set(item.split('/')[0] for item in root_items if item.strip())
                    if len(top_level_dirs) == 1:
                        root_folder = list(top_level_dirs)[0]
                        for member in zip_ref.infolist():
                            member_path = member.filename
                            if member_path.startswith(root_folder + '/'):
                                relative_path = member_path[len(root_folder) + 1:]
                                if relative_path:
                                    target_path = os.path.join(extracted_path, relative_path)
                                    if member.is_dir():
                                        os.makedirs(target_path, exist_ok=True)
                                    else:
                                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                                        with zip_ref.open(member) as source, open(target_path, 'wb') as target:
                                            shutil.copyfileobj(source, target)
                    else:
                        zip_ref.extractall(extracted_path)

            elif file_name.endswith('.dmg'):
                if sys.platform != "darwin":
                    self.version_queue.put(('ERROR', _("DMG files can only be extracted on macOS.")))
                    return
                mount_point = tempfile.mkdtemp()
                try:
                    subprocess.run(["hdiutil", "attach", file_path, "-mountpoint", mount_point], check=True)
                    blender_app_path = os.path.join(mount_point, "Blender.app")
                    if os.path.exists(blender_app_path):
                        shutil.copytree(blender_app_path, os.path.join(extracted_path, "Blender.app"))
                    else:
                        raise Exception(_("Blender.app not found in mounted .dmg."))
                finally:
                    subprocess.run(["hdiutil", "detach", mount_point], check=True)
                    shutil.rmtree(mount_point)

            elif file_name.endswith(('.tar.gz', '.tar.xz')):
                with tarfile.open(file_path, 'r:*') as tar_ref:
                    root_items = tar_ref.getnames()
                    top_level_dirs = set(item.split('/')[0] for item in root_items if item.strip())
                    if len(top_level_dirs) == 1:
                        root_folder = list(top_level_dirs)[0]
                        for member in tar_ref.getmembers():
                            if member.name.startswith(root_folder + '/'):
                                relative_path = member.name[len(root_folder) + 1:]
                                if relative_path:
                                    member.name = relative_path
                                    tar_ref.extract(member, extracted_path)
                    else:
                        tar_ref.extractall(extracted_path)
            else:
                self.version_queue.put(('ERROR', _("Unsupported file format.")))
                return

            self.version_queue.put(('INSTALLATION_SUCCESS', version, extracted_path))
            self._refresh_installed_versions_ui()

        except requests.RequestException as e:
            log.error(f"Download error: {e}")
            self.version_queue.put('INSTALLATION_FAILED')
        except Exception as e:
            log.error(f"Installation error: {e}")
            self.version_queue.put(('ERROR', _(f"Installation failed: {str(e)}")))
        finally:
            self.is_installing = False
            self.cancel_event.clear()
            session.close()
            self.version_queue.put('DOWNLOAD_COMPLETE')

    def _cancel_installation(self):
        if not self.is_installing:
            return
        from tkinter import messagebox
        confirm = messagebox.askyesno(_("Cancel Installation"), _("Are you sure you want to cancel the installation?"))
        if confirm:
            self.cancel_event.set()
            log.info("Installation cancelled by user.")

    # -----------------------------------------------------------
    # Installed View
    # -----------------------------------------------------------

    def _create_installed_view(self):
        self.installed_frame = ttkb.Frame(self.versions_parent_frame, padding=(0, 0, 0, 0))

        settings = self.config.get_all()
        bff = settings.get("button_font_family", "Segoe UI")
        tff = settings.get("treeview_font_family", "Segoe UI")
        tfs = settings.get("treeview_font_size", 12)

        buttons_frame = ttkb.Frame(self.installed_frame)
        buttons_frame.pack(side='left', padx=(0, 10), pady=(0, 0), fill='y')

        self.launch_installed_button = ttkb.Button(
            buttons_frame, text=_("Launch"), takefocus=False,
            padding=(30, 10), command=self._launch_blender, style='Custom.TButton'
        )
        self.launch_installed_button.pack(pady=(10, 10), padx=(10, 10), fill='x')

        self.launch_factory_var = tk.BooleanVar()
        self.launch_factory_check = ttkb.Checkbutton(
            buttons_frame, text=_("Factory Settings"), variable=self.launch_factory_var
        )
        self.launch_factory_check.pack(pady=(5, 5), padx=(10, 10), fill='x')

        self.refresh_button = ttkb.Button(
            buttons_frame, text=_("Refresh"), takefocus=False,
            padding=(30, 10), command=self._refresh_installed_versions, style='Custom.TButton'
        )
        self.refresh_button.pack(pady=(10, 10), padx=(10, 10), fill='x')

        self.transfer_to_menu_button = ttkb.Button(
            buttons_frame, text=_("Convert To Main"), takefocus=False,
            padding=(30, 10), command=self._transfer_version_to_menu, style='Custom.TButton'
        )
        self.transfer_to_menu_button.pack(pady=(10, 10), padx=(10, 10), fill='x')

        style = ttkb.Style()
        style.configure("InstalledVersions.Treeview", font=(tff, tfs), rowheight=30)
        style.configure("InstalledVersions.Treeview.Heading", font=('Segoe UI', 14, 'bold'))

        self.installed_versions_tree = ttkb.Treeview(
            self.installed_frame, columns=('Version',), show='headings',
            selectmode='browse', height=17, style='InstalledVersions.Treeview'
        )
        self.installed_versions_tree.heading('Version', text=_('Installed Versions'))
        self.installed_versions_tree.column('Version', width=300, anchor='center')
        self.installed_versions_tree.pack(side='right', fill='both', expand=True, padx=(0, 0))

        self.versions_context_menu = tk.Menu(self.installed_versions_tree, tearoff=0)
        self.versions_context_menu.add_command(label=_("Create Shortcut"), command=self._create_shortcut)
        self.versions_context_menu.add_command(label=_("Delete"), command=self._remove_installed_version)
        self.installed_versions_tree.bind("<Button-3>", self._show_installed_context_menu)

        self._refresh_installed_versions()

    def _refresh_installed_versions_ui(self):
        self.frame.after(0, self._refresh_installed_versions)

    def _refresh_installed_versions(self):
        self.installed_versions_tree.delete(*self.installed_versions_tree.get_children())
        versions_dir = get_blender_versions_dir()
        if not os.path.exists(versions_dir):
            os.makedirs(versions_dir, exist_ok=True)

        versions = sorted([
            d for d in os.listdir(versions_dir)
            if os.path.isdir(os.path.join(versions_dir, d)) and ('blender' in d.lower() or re.search(r'\d+\.\d+', d))
        ])

        for index, version in enumerate(versions):
            tag = 'evenrow' if index % 2 == 0 else 'oddrow'
            self.installed_versions_tree.insert('', 'end', values=(version,), tags=(tag,))

    def _launch_blender(self):
        selected_item = self.installed_versions_tree.focus()
        if not selected_item:
            from tkinter import messagebox
            messagebox.showwarning(_("Warning"), _("Please select a Blender version to launch."))
            return

        selected_version = self.installed_versions_tree.item(selected_item)['values'][0]
        versions_dir = get_blender_versions_dir()
        blender_dir = os.path.join(versions_dir, selected_version)

        if platform.system() == "Darwin":
            blender_exec = os.path.join(blender_dir, "Blender.app", "Contents", "MacOS", "Blender")
        else:
            blender_exec = os.path.join(blender_dir, "blender")
            if platform.system() == "Windows":
                blender_exec += ".exe"

        if not os.path.isfile(blender_exec):
            from tkinter import messagebox
            messagebox.showerror(_("Error"), _(f"Blender executable not found for version {selected_version}."))
            return

        self.launch_installed_button.configure(state='disabled')
        self.frame.after(5000, lambda: self.launch_installed_button.configure(state='normal'))

        try:
            args = [blender_exec]
            if self.launch_factory_var.get():
                args.append('--factory-startup')

            process = subprocess.Popen(args)

            def monitor_process():
                process.wait()
                log.info(f"Blender version {selected_version} has exited.")

            threading.Thread(target=monitor_process, daemon=True).start()
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror(_("Error"), _(f"Failed to launch Blender: {e}"))

    def _transfer_version_to_menu(self):
        selected_item = self.installed_versions_tree.focus()
        if not selected_item:
            from tkinter import messagebox
            messagebox.showwarning(_("Warning"), _("Please select a Blender version."))
            return
        selected_version = self.installed_versions_tree.item(selected_item)['values'][0]
        source_folder = os.path.join(get_blender_versions_dir(), selected_version)
        if not os.path.exists(source_folder):
            from tkinter import messagebox
            messagebox.showerror(_("Error"), _(f"Source folder not found: {source_folder}"))
            return
        cfg_path = os.path.join(get_blender_manager_dir(), "config.json")
        try:
            with open(cfg_path, "r") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        cfg["selected_main_version"] = selected_version
        try:
            with open(cfg_path, "w") as f:
                json.dump(cfg, f, indent=4)
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror(_("Error"), str(e))
            return
        from tkinter import messagebox
        messagebox.showinfo(_("Done"), _(f"{selected_version} set as main version."))
        self.frame.after(0, lambda: self.transfer_to_menu_button.configure(text=_('Convert To Main')))
        if hasattr(self.app, 'update_blender_version_label'):
            self.app.update_blender_version_label()

    def _disable_installed_buttons(self):
        self.transfer_to_menu_button.configure(state='disabled')
        self.launch_installed_button.configure(state='disabled')
        self.refresh_button.configure(state='disabled')

    def _enable_installed_buttons(self):
        self.transfer_to_menu_button.configure(state='normal')
        self.launch_installed_button.configure(state='normal')
        self.refresh_button.configure(state='normal')

    def _show_installed_context_menu(self, event):
        item_id = self.installed_versions_tree.identify_row(event.y)
        if item_id:
            self.installed_versions_tree.selection_set(item_id)
            self.installed_versions_tree.focus(item_id)
            self.versions_context_menu.post(event.x_root, event.y_root)

    def _create_shortcut(self):
        selected_item = self.installed_versions_tree.focus()
        if not selected_item:
            from tkinter import messagebox
            messagebox.showwarning(_("Warning"), _("Please select a Blender version to make a shortcut."))
            return

        selected_version = self.installed_versions_tree.item(selected_item)['values'][0]
        versions_dir = get_blender_versions_dir()
        blender_dir = os.path.join(versions_dir, selected_version)

        if platform.system() == "Darwin":
            blender_exec = os.path.join(blender_dir, "Blender.app", "Contents", "MacOS", "Blender")
        else:
            blender_exec = os.path.join(blender_dir, "blender")
            if platform.system() == "Windows":
                blender_exec += ".exe"

        if not os.path.isfile(blender_exec):
            from tkinter import messagebox
            messagebox.showerror(_("Error"), _(f"Blender executable not found in {blender_dir}"))
            return

        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        shortcut_name = f"{selected_version}.lnk" if platform.system() == "Windows" else selected_version
        shortcut_path = os.path.join(desktop_path, shortcut_name)

        try:
            if platform.system() == "Windows":
                self._create_windows_shortcut(shortcut_path, blender_exec, blender_dir)
            elif platform.system() == "Darwin":
                self._create_mac_shortcut(shortcut_path, blender_exec)
            elif platform.system() == "Linux":
                self._create_linux_shortcut(shortcut_path, blender_exec)
            else:
                raise OSError(_("Unsupported operating system"))

            from tkinter import messagebox
            messagebox.showinfo(_("Success"), _(f"Shortcut created: {shortcut_path}"))
        except Exception as error:
            from tkinter import messagebox
            messagebox.showerror(_("Error"), _(f"Failed to create shortcut.\n{error}"))

    def _create_windows_shortcut(self, shortcut_path, target_path, working_directory):
        try:
            import winshell
            with winshell.shortcut(shortcut_path) as shortcut:
                shortcut.path = target_path
                shortcut.working_directory = working_directory
                shortcut.description = _("Shortcut to Blender")
                shortcut.icon_location = target_path, 0
        except ImportError:
            import pythoncom
            from win32com.client import Dispatch
            pythoncom.CoInitialize()
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.TargetPath = target_path
            shortcut.WorkingDirectory = working_directory
            shortcut.Description = "Shortcut to Blender"
            shortcut.IconLocation = target_path
            shortcut.Save()

    def _create_mac_shortcut(self, shortcut_path, target_path):
        os.symlink(target_path, shortcut_path)

    def _create_linux_shortcut(self, shortcut_path, target_path):
        desktop_file = shortcut_path + ".desktop"
        with open(desktop_file, "w") as f:
            f.write(f"""[Desktop Entry]
Type=Application
Name={os.path.basename(shortcut_path)}
Exec={target_path}
Icon={target_path}
Terminal=false
""")
        os.chmod(desktop_file, 0o755)

    def _remove_installed_version(self):
        selected_item = self.installed_versions_tree.focus()
        if not selected_item:
            from tkinter import messagebox
            messagebox.showwarning(_("Warning"), _("Please select a Blender version to remove."))
            return

        selected_version = self.installed_versions_tree.item(selected_item)['values'][0]
        self._disable_installed_buttons()

        from tkinter import messagebox
        confirm = messagebox.askyesno(_("Confirm"), _("Are you sure you want to remove {0}?").format(selected_version))
        if confirm:
            path_to_remove = os.path.join(get_blender_versions_dir(), selected_version)
            try:
                shutil.rmtree(path_to_remove)
                self._refresh_installed_versions()
                messagebox.showinfo(_("Success"), _("{0} has been removed.").format(selected_version))
                self._enable_installed_buttons()
            except Exception as e:
                messagebox.showerror(_("Error"), _(f"Failed to remove {selected_version}: {e}"))
                self._enable_installed_buttons()
        else:
            self._enable_installed_buttons()
