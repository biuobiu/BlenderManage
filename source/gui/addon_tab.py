import ast
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import webbrowser
import zipfile

import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES
from i18n import _

from core import (
    Logger, DataManager, ConfigManager,
    get_blender_config_path, get_blender_versions_dir,
    get_blender_manager_dir, get_blender_executable,
    get_paths_dir, open_file_with_default_app,
    run_in_background, ensure_dir, get_selected_main_version,
)

log = Logger()


class AddonManagementTab:
    def __init__(self, app, notebook):
        self.app = app
        self.notebook = notebook
        self.config = ConfigManager()
        self.data = DataManager()

        self.frame = ttkb.Frame(self.notebook, padding=(10, 10, 10, 10))
        self.directory_path = tk.StringVar(value=self._load_plugin_directory())
        self.plugin_search_var = tk.StringVar()
        self.plugin_placeholder_text = _("Search Addons")
        self.auto_activate_plugin_var = tk.BooleanVar(value=self.config.get("auto_activate_plugin", True))
        self.blender_versions = self._get_blender_versions()
        self.version_var = tk.StringVar()

        self._build_ui()
        self.refresh_plugins_list()

    def _build_ui(self):
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(2, weight=1)

        self._build_directory_bar()
        self._build_search_bar()
        self._build_addon_tree()
        self._build_context_menu()

    def _build_directory_bar(self):
        directory_frame = ttkb.Frame(self.frame)
        directory_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(0, 5))
        directory_frame.columnconfigure(0, weight=1)

        self.directory_entry = ttkb.Entry(directory_frame, textvariable=self.directory_path, width=50)
        self.directory_entry.pack(side="left", padx=(0, 5))
        self.directory_entry.bind("<Double-Button-1>", lambda e: self._go_to_file_path())

        ttkb.Button(
            directory_frame, text=_("Browse"),
            command=self.browse_directory, bootstyle=PRIMARY,
        ).pack(side="left", padx=(0, 5))

        ttkb.Button(
            directory_frame, text=_("Add Addon"),
            command=self.add_plugin, bootstyle=SUCCESS,
        ).pack(side="left", padx=(0, 5))

        ttkb.Button(
            directory_frame, text=_("Refresh"),
            command=self.refresh_plugins_list, bootstyle=INFO,
        ).pack(side="left", padx=(0, 5))

    def _build_search_bar(self):
        search_bar_frame = ttkb.Frame(self.frame)
        search_bar_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        search_bar_frame.columnconfigure(0, weight=1)

        self.plugin_search_entry = ttkb.Entry(
            search_bar_frame, textvariable=self.plugin_search_var, width=50
        )
        self.plugin_search_entry.pack(side="left", padx=(0, 5))
        self.plugin_search_entry.insert(0, self.plugin_placeholder_text)
        self.plugin_search_entry.configure(foreground="grey")
        self.plugin_search_entry.bind("<FocusIn>", self._on_plugin_entry_click)
        self.plugin_search_entry.bind("<FocusOut>", self._on_plugin_focus_out)
        self.plugin_search_var.trace("w", self._on_plugin_search_change)

        blender_installed = bool(self.blender_versions)
        version_values = self.blender_versions if blender_installed else []
        self.version_combobox = ttkb.Combobox(
            search_bar_frame, textvariable=self.version_var,
            values=version_values, state="readonly", width=22,
        )
        if version_values:
            default_ver = self.config.get("selected_main_version", "")
            selected = version_values[0]
            if default_ver:
                if default_ver in version_values:
                    selected = default_ver
                else:
                    for v in version_values:
                        if default_ver.endswith(v) or v in default_ver:
                            selected = v
                            break
            self.version_combobox.set(selected)
        else:
            self.version_combobox.set(_("Blender Not Installed"))
        self.version_combobox.pack(side="left", padx=(0, 5))
        self.version_combobox.bind("<<ComboboxSelected>>", self._on_blender_version_selected)

    def _build_addon_tree(self):
        self.plugins_tree = ttkb.Treeview(
            self.frame,
            columns=("Name", "Version", "Compatible", "Status"),
            show="headings",
            selectmode="browse",
        )
        self.plugins_tree.heading("Name", text=_("Plugin Name"))
        self.plugins_tree.heading("Version", text=_("Plugin Version"))
        self.plugins_tree.heading("Compatible", text=_("Compatible with"))
        self.plugins_tree.heading("Status", text=_("Status"))
        self.plugins_tree.column("Name", width=300, anchor="center")
        self.plugins_tree.column("Version", width=150, anchor="center")
        self.plugins_tree.column("Compatible", width=150, anchor="center")
        self.plugins_tree.column("Status", width=100, anchor="center")
        self.plugins_tree.tag_configure("enabled", foreground="#4a9eff")
        self.plugins_tree.tag_configure("disabled", foreground="#ff6b6b")
        self.plugins_tree.grid(row=2, column=0, sticky="nsew", padx=10)

        scrollbar = ttkb.Scrollbar(self.frame, orient="vertical", command=self.plugins_tree.yview)
        self.plugins_tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=2, column=1, sticky="ns")

        self.plugins_tree.drop_target_register(DND_FILES)
        self.plugins_tree.dnd_bind("<<Drop>>", self._handle_treeview_drop)

    def _build_context_menu(self):
        self.plugin_context_menu = tk.Menu(self.plugins_tree, tearoff=0)
        self.plugin_context_menu.add_command(label=_("Delete"), command=self.remove_plugin)
        self.plugin_context_menu.add_command(label=_("Go to File Path"), command=self._go_to_file_path)
        self.plugin_context_menu.add_command(label=_("Info"), command=self.view_plugin_content)
        self.plugin_context_menu.add_command(label=_("View Documentation"), command=self.view_plugin_document)

        self.duplicate_menu = tk.Menu(self.plugin_context_menu, tearoff=0)
        self.plugin_context_menu.add_cascade(label=_("Duplicate to..."), menu=self.duplicate_menu)
        self.plugin_context_menu.add_separator()
        self.plugin_context_menu.add_command(
            label=_("Activate Addon"), command=self.activate_selected_addon_in_versions
        )
        self.plugin_context_menu.add_command(
            label=_("Deactivate Addon"), command=self.deactivate_selected_addon_in_versions
        )

        self.app.bind_right_click(self.plugins_tree, self._show_plugin_context_menu)

    # ---------- Directory persistence ----------

    def _save_plugin_directory(self, directory):
        file_path = os.path.join(get_paths_dir(), "plugin_directory.json")
        try:
            ensure_dir(os.path.dirname(file_path))
            with open(file_path, "w") as f:
                json.dump({"plugin_directory": directory}, f)
        except Exception as e:
            log.error(f"Failed to save plugin directory: {e}")

    def _load_plugin_directory(self):
        return self._get_default_plugin_directory()

    def _get_default_plugin_directory(self):
        ver = get_selected_main_version()
        if ver:
            clean = ver.replace("Blender ", "", 1)
            major_minor = ".".join(clean.split(".")[:2])
            return os.path.join(get_blender_config_path(), major_minor, "scripts", "addons")
        return os.path.join(get_blender_manager_dir(), "addons")

    # ---------- Blender version helpers ----------

    def _get_blender_versions(self):
        versions = []
        try:
            vdir = get_blender_versions_dir()
            if not os.path.exists(vdir):
                return versions
            for folder in sorted(os.listdir(vdir), reverse=True):
                fpath = os.path.join(vdir, folder)
                if not os.path.isdir(fpath):
                    continue
                exe_name = "blender.exe" if os.name == "nt" else "blender"
                exe_path = os.path.join(fpath, exe_name)
                if not os.path.isfile(exe_path):
                    continue
                parts = folder.split()
                version_str = parts[-1]
                if re.match(r"^\d+\.\d+", version_str):
                    versions.append(version_str)
        except Exception as e:
            log.error(f"Failed to get Blender versions: {e}")
        return sorted(set(versions), reverse=True)

    def _get_matching_versions(self, base_version_prefix):
        matching = []
        blender_versions_dir = get_blender_versions_dir()
        if not os.path.exists(blender_versions_dir):
            return matching
        for folder in os.listdir(blender_versions_dir):
            fpath = os.path.join(blender_versions_dir, folder)
            if os.path.isdir(fpath) and folder.startswith("Blender"):
                folder_version = folder.split(" ")[-1]
                if folder_version.startswith(base_version_prefix):
                    exe_name = "blender.exe" if os.name == "nt" else "blender"
                    blender_exe = os.path.join(fpath, exe_name)
                    if os.path.exists(blender_exe):
                        matching.append(blender_exe)
        return matching

    def _check_version_match(self, blender_executable, selected_version):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            result = subprocess.run(
                [blender_executable, "--version"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, startupinfo=startupinfo,
            )
            if result.returncode == 0:
                version_output = result.stdout.splitlines()[0]
                blender_version = version_output.split()[-1]
                base_prefix = selected_version.split(".")[0] + "." + selected_version.split(".")[1]
                return blender_version.startswith(base_prefix)
        except Exception as e:
            log.error(f"Failed to check Blender version: {e}")
        return False

    def get_blender_version(self, blender_executable):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            result = subprocess.run(
                [blender_executable, "--version"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, startupinfo=startupinfo,
            )
            version_line = result.stdout.splitlines()[0]
            return version_line.split(" ")[1]
        except Exception as e:
            log.error(f"Failed to retrieve Blender version: {e}")
            return ""

    def get_matching_blender_executable(self, selected_version):
        blender_versions_dir = get_blender_versions_dir()
        try:
            blender_folders = [
                folder for folder in os.listdir(blender_versions_dir)
                if os.path.isdir(os.path.join(blender_versions_dir, folder))
                and folder.startswith(f"Blender {selected_version}")
            ]
            if not blender_folders:
                return None
            selected_folder = random.choice(blender_folders)
            exe_name = "blender.exe" if os.name == "nt" else "blender"
            blender_exe = os.path.join(blender_versions_dir, selected_folder, exe_name)
            if not os.path.exists(blender_exe):
                return None
            return blender_exe
        except Exception as e:
            log.error(f"Failed to find matching Blender executable: {e}")
            return None

    # ---------- UI event handlers ----------

    def _on_plugin_entry_click(self, event):
        if self.plugin_search_entry.get() == self.plugin_placeholder_text:
            self.plugin_search_entry.delete(0, "end")
            self.plugin_search_entry.configure(foreground="black")

    def _on_plugin_focus_out(self, event):
        if not self.plugin_search_entry.get():
            self.plugin_search_entry.insert(0, self.plugin_placeholder_text)
            self.plugin_search_entry.configure(foreground="grey")

    def _on_plugin_search_change(self, *args):
        if self.plugin_search_entry.get() != self.plugin_placeholder_text:
            self.filter_plugins_tree()

    def _on_blender_version_selected(self, event):
        selected_version = self.version_var.get()
        if not selected_version or selected_version == _("Select Blender Version"):
            return
        try:
            clean = selected_version.replace("Blender ", "", 1)
            major_minor = ".".join(clean.split(".")[:2])
            addons_path = os.path.join(get_blender_config_path(), major_minor, "scripts", "addons")
            os.makedirs(addons_path, exist_ok=True)
            self.directory_path.set(addons_path)
            self.refresh_plugins_list()
        except Exception as e:
            log.error(f"Error setting Blender version path: {e}")

    def _show_plugin_context_menu(self, event):
        item_id = self.plugins_tree.identify_row(event.y)
        if item_id:
            self.plugins_tree.selection_set(item_id)
            self.plugins_tree.focus(item_id)
            self._update_duplicate_menu()
            self.plugin_context_menu.tk_popup(event.x_root, event.y_root)
        else:
            self.plugin_context_menu.unpost()

    def _update_duplicate_menu(self):
        self.duplicate_menu.delete(0, "end")
        blender_versions = self._get_blender_versions()
        if not blender_versions:
            self.duplicate_menu.add_command(label=_("No versions found"), state="disabled")
            return
        for version in blender_versions:
            self.duplicate_menu.add_command(
                label=version,
                command=lambda v=version: self.duplicate_addon_to_version(v),
            )

    # ---------- Directory browsing ----------

    def browse_directory(self):
        current = self.directory_path.get()
        directory = filedialog.askdirectory(initialdir=current if os.path.exists(current) else None)
        if directory:
            self.directory_path.set(directory)
            self.refresh_plugins_list()

    def _go_to_file_path(self):
        directory = self.directory_path.get()
        if os.path.exists(directory):
            try:
                if os.name == "nt":
                    os.startfile(directory)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", directory])
                else:
                    subprocess.Popen(["xdg-open", directory])
            except Exception as e:
                messagebox.showerror(_("Error"), _(f"Failed to open directory: {e}"))
        else:
            messagebox.showwarning(_("Warning"), _("The selected directory does not exist."))

    # ---------- Plugin listing / searching ----------

    def refresh_plugins_list(self):
        self.plugins_tree.delete(*self.plugins_tree.get_children())
        addons_dir = self.directory_path.get()
        if not os.path.exists(addons_dir):
            return
        for item in sorted(os.listdir(addons_dir)):
            item_path = os.path.join(addons_dir, item)
            if item.startswith(".") or item == "__pycache__" or item.endswith(".pyc"):
                continue
            if os.path.isdir(item_path):
                if os.path.isfile(os.path.join(item_path, "__init__.py")):
                    version, compatible = self._get_plugin_info(item_path)
                    self.plugins_tree.insert("", "end", values=(item, version, compatible, " "))
                else:
                    for sub in sorted(os.listdir(item_path)):
                        sub_path = os.path.join(item_path, sub)
                        if sub.startswith(".") or sub == "__pycache__":
                            continue
                        if os.path.isdir(sub_path) and os.path.isfile(os.path.join(sub_path, "__init__.py")):
                            version, compatible = self._get_plugin_info(sub_path)
                            self.plugins_tree.insert("", "end", values=(f"{item}/{sub}", version, compatible, " "))
            elif item.endswith(".py"):
                version, compatible = self._get_plugin_info(item_path)
                plugin_name = os.path.splitext(item)[0]
                self.plugins_tree.insert("", "end", values=(plugin_name, version, compatible, " "))
        self._update_addon_status()

    def filter_plugins_tree(self):
        query = self.plugin_search_var.get().lower()
        self.plugins_tree.delete(*self.plugins_tree.get_children())
        addons_dir = self.directory_path.get()
        if not os.path.exists(addons_dir):
            return
        for item in os.listdir(addons_dir):
            item_path = os.path.join(addons_dir, item)
            if item.startswith(".") or item == "__pycache__" or item.endswith(".pyc"):
                continue
            if os.path.isdir(item_path):
                if os.path.isfile(os.path.join(item_path, "__init__.py")):
                    if query in item.lower():
                        version, compatible = self._get_plugin_info(item_path)
                        self.plugins_tree.insert("", "end", values=(item, version, compatible))
                else:
                    for sub in os.listdir(item_path):
                        sub_path = os.path.join(item_path, sub)
                        if sub.startswith(".") or sub == "__pycache__":
                            continue
                        if os.path.isdir(sub_path) and os.path.isfile(os.path.join(sub_path, "__init__.py")):
                            display = f"{item}/{sub}"
                            if query in display.lower():
                                version, compatible = self._get_plugin_info(sub_path)
                                self.plugins_tree.insert("", "end", values=(display, version, compatible))

    # ---------- Plugin info parsing ----------

    @staticmethod
    def _extract_bl_info(file_path):
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
                tree = ast.parse(content, filename=file_path)
                for node in tree.body:
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id == "bl_info":
                                return ast.literal_eval(node.value)
        except Exception as e:
            log.error(f"Failed to read bl_info from {file_path}: {e}")
        return None

    def _get_plugin_info(self, addon_path):
        version = "Unknown"
        compatible = "Unknown"

        if addon_path.endswith(".py"):
            info_file = addon_path
        else:
            info_file = os.path.join(addon_path, "__init__.py")

        if os.path.exists(info_file):
            bl_info = self._extract_bl_info(info_file)
            if bl_info:
                ver = ".".join(map(str, bl_info.get("version", [])))
                comp = ", ".join(map(str, bl_info.get("blender", ["Unknown"])))
                return ver or "Unknown", comp or "Unknown"

        for root, _dirs, files in os.walk(addon_path):
            for file in files:
                if file == "__init__.py":
                    bl_info = self._extract_bl_info(os.path.join(root, file))
                    if bl_info:
                        ver = ".".join(map(str, bl_info.get("version", [])))
                        comp = ", ".join(map(str, bl_info.get("blender", ["Unknown"])))
                        return ver or "Unknown", comp or "Unknown"

        return version, compatible

    # ---------- Adding plugins ----------

    def add_plugin(self):
        initial = self.directory_path.get()
        file_paths = filedialog.askopenfilenames(
            title=_("Select Plugin Files"),
            initialdir=initial if os.path.exists(initial) else None,
            filetypes=[(_("Python Files"), "*.py"), (_("Zip Files"), "*.zip")],
        )
        if not file_paths:
            return
        for file_path in file_paths:
            if os.path.isfile(file_path):
                if file_path.lower().endswith(".zip") or file_path.lower().endswith(".py"):
                    self._add_plugin_from_file(file_path)
                else:
                    messagebox.showerror(_("Invalid File"), _(f"Unsupported file format: {file_path}\nPlease select a .zip or .py file."))
            else:
                messagebox.showerror(_("Invalid File"), _(f"Not a file: {file_path}"))

    def _add_plugin_from_file(self, file_path):
        try:
            addons_dir = self.directory_path.get()
            if not os.path.exists(addons_dir):
                os.makedirs(addons_dir, exist_ok=True)

            basename = os.path.basename(file_path)
            destination = os.path.join(addons_dir, basename)

            if os.path.exists(destination):
                overwrite = messagebox.askyesno(
                    _("Overwrite"), _(f"{basename} already exists. Do you want to overwrite it?")
                )
                if not overwrite:
                    return

            addon_name = None
            if file_path.lower().endswith(".zip"):
                with zipfile.ZipFile(file_path, "r") as zip_ref:
                    namelist = zip_ref.namelist()
                    top_level_items = set(name.split("/")[0] for name in namelist if not name.endswith("/"))

                    if len(top_level_items) == 1:
                        addon_name = list(top_level_items)[0]
                        zip_ref.extractall(addons_dir)
                    else:
                        folder_name = os.path.splitext(basename)[0]
                        addon_name = folder_name
                        extract_path = os.path.join(addons_dir, folder_name)
                        os.makedirs(extract_path, exist_ok=True)
                        zip_ref.extractall(extract_path)
            elif file_path.lower().endswith(".py"):
                shutil.copy(file_path, destination)
                addon_name = os.path.splitext(basename)[0]

            self.refresh_plugins_list()
            messagebox.showinfo(_("Success"), _("Plugin '{0}' has been added successfully!").format(basename))

            if self.auto_activate_plugin_var.get() and addon_name:
                self._auto_activate_plugin(addon_name)
        except zipfile.BadZipFile:
            messagebox.showerror(
                _("Extraction Failed"),
                _(f"Failed to extract '{basename}'. The zip file is corrupted."),
            )
        except Exception as e:
            log.error(f"Error adding plugin from file: {e}")
            messagebox.showerror(_("Error"), _(f"Failed to add plugin: {e}"))

    def _auto_activate_plugin(self, addon_name):
        self.activate_addon_in_all_versions(addon_name)

    # ---------- Removing plugins ----------

    def remove_plugin(self):
        selected_item = self.plugins_tree.focus()
        if not selected_item:
            return
        plugin_name = self.plugins_tree.item(selected_item)["values"][0]
        addons_dir = self.directory_path.get()

        plugin_folder_path = os.path.join(addons_dir, plugin_name)
        plugin_file_path = os.path.join(addons_dir, plugin_name + ".py")

        if os.path.exists(plugin_folder_path):
            confirm = messagebox.askyesno(_("Confirm"), _("Are you sure you want to remove the plugin folder '{plugin_name}'?").format(plugin_name=plugin_name))
            if confirm:
                try:
                    shutil.rmtree(plugin_folder_path)
                    messagebox.showinfo(_("Success"), _("Plugin folder '{plugin_name}' removed.").format(plugin_name=plugin_name))
                    self.refresh_plugins_list()
                except Exception as e:
                    messagebox.showerror(_("Error"), _(f"Failed to remove plugin folder: {e}"))
        elif os.path.exists(plugin_file_path):
            confirm = messagebox.askyesno(_("Confirm"), _("Are you sure you want to remove the plugin file '{plugin_name}.py'?").format(plugin_name=plugin_name))
            if confirm:
                try:
                    os.remove(plugin_file_path)
                    messagebox.showinfo(_("Success"), _(f"Plugin file '{plugin_name}.py' removed."))
                    self.refresh_plugins_list()
                except Exception as e:
                    messagebox.showerror(_("Error"), _(f"Failed to remove plugin file: {e}"))
        else:
            messagebox.showwarning(_("Warning"), _("The selected plugin does not exist."))

    # ---------- View plugin content / documentation ----------

    def view_plugin_content(self):
        selected_item = self.plugins_tree.focus()
        if not selected_item:
            return
        plugin_name = self.plugins_tree.item(selected_item)["values"][0]
        plugin_file = os.path.join(self.directory_path.get(), plugin_name)

        if os.path.isfile(plugin_file + ".py"):
            file_path = plugin_file + ".py"
        else:
            file_path = os.path.join(plugin_file, "__init__.py")

        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                content_window = tk.Toplevel(self.app)
                content_window.title(_(f"{plugin_name} Info"))
                text_widget = tk.Text(content_window, wrap="word")
                text_widget.insert("1.0", content)
                text_widget.pack(expand=1, fill="both")
            except Exception as e:
                messagebox.showerror(_("Error"), _(f"Failed to read file: {e}"))
        else:
            messagebox.showwarning(_("Warning"), _("The plugin file does not exist."))

    def view_plugin_document(self):
        try:
            import webview
        except ImportError:
            webview = None

        selected_item = self.plugins_tree.focus()
        if not selected_item:
            messagebox.showerror(_("Error"), _("No addon selected."))
            return

        plugin_name = self.plugins_tree.item(selected_item)["values"][0]
        plugin_folder_path = os.path.join(self.directory_path.get(), plugin_name)

        if os.path.isfile(plugin_folder_path + ".py"):
            addon_file = plugin_folder_path + ".py"
        else:
            addon_file = os.path.join(plugin_folder_path, "__init__.py")

        if not os.path.exists(addon_file):
            messagebox.showerror(_("Error"), _("The selected plugin does not have an accessible file."))
            return

        bl_info = self._extract_bl_info(addon_file)
        if not bl_info:
            messagebox.showerror(_("Error"), _("Could not extract bl_info from the addon."))
            return

        doc_url = bl_info.get("doc_url")
        wiki_url = bl_info.get("wiki_url")
        ref_url = bl_info.get("#ref")
        url_to_open = doc_url or wiki_url or ref_url

        if url_to_open:
            if webview:
                try:
                    webview.create_window(_(f"{plugin_name} Documentation"), url_to_open)
                    webview.start()
                    return
                except Exception as e:
                    log.error(f"Failed to open with webview: {e}")
            try:
                webbrowser.open(url_to_open)
            except Exception as e:
                messagebox.showerror(_("Error"), _(f"Failed to open the documentation: {e}"))
        else:
            messagebox.showinfo(_("Info"), _("No documentation URL found for this plugin."))

    # ---------- Duplicate addon ----------

    def duplicate_addon_to_version(self, target_version):
        selected_item = self.plugins_tree.focus()
        if not selected_item:
            messagebox.showerror(_("Error"), _("No addon selected."))
            return

        addon_name = self.plugins_tree.item(selected_item, "values")[0]
        current_addon_path = os.path.join(self.directory_path.get(), addon_name)

        if not os.path.exists(current_addon_path):
            messagebox.showerror(_("Error"), _("The selected addon does not exist."))
            return

        try:
            blender_config_path = get_blender_config_path()
        except EnvironmentError as e:
            messagebox.showerror(_("Error"), _(f"Failed to determine Blender configuration path: {e}"))
            return

        target_addon_path = os.path.join(
            blender_config_path, target_version, "scripts", "addons", addon_name,
        )
        os.makedirs(os.path.dirname(target_addon_path), exist_ok=True)

        try:
            if os.path.isdir(current_addon_path):
                shutil.copytree(current_addon_path, target_addon_path)
            elif os.path.isfile(current_addon_path):
                shutil.copy2(current_addon_path, target_addon_path)
            messagebox.showinfo(
                _("Success"),
                _(f"Addon '{addon_name}' has been duplicated to Blender {target_version}."),
            )
        except Exception as e:
            messagebox.showerror(_("Error"), _(f"Failed to duplicate addon: {e}"))

    # ---------- Drag and drop ----------

    def _handle_treeview_drop(self, event):
        files = self.tk.splitlist(event.data)
        if not files:
            return
        for file_path in files:
            if os.path.isfile(file_path):
                if file_path.lower().endswith(".zip") or file_path.lower().endswith(".py"):
                    self._add_plugin_from_file(file_path)
                else:
                    messagebox.showerror(
                        _("Invalid File"),
                        _(f"Unsupported file format: {file_path}\nPlease drop a .zip or .py file."),
                    )
            else:
                messagebox.showerror(_("Invalid File"), _(f"Not a file: {file_path}"))

    # ---------- Activate / Deactivate ----------

    def activate_selected_addon_in_versions(self):
        selected_item = self.plugins_tree.focus()
        if not selected_item:
            messagebox.showerror(_("Error"), _("No addon selected."))
            return
        selected_addon = self.plugins_tree.item(selected_item, "values")[0]
        base_addon = selected_addon.split("/")[-1]
        threading.Thread(target=self.activate_addon_in_all_versions, args=(base_addon,), daemon=True).start()

    def deactivate_selected_addon_in_versions(self):
        selected_item = self.plugins_tree.focus()
        if not selected_item:
            messagebox.showerror(_("Error"), _("No addon selected."))
            return
        selected_addon = self.plugins_tree.item(selected_item, "values")[0]
        base_addon = selected_addon.split("/")[-1]
        threading.Thread(target=self.deactivate_addon_in_all_versions, args=(base_addon,), daemon=True).start()

    def activate_addon_in_all_versions(self, selected_addon):
        selected_version = self.version_var.get()
        self._show_addon_page_message(_("Activating..."))
        if not selected_version or selected_version == _("Select Blender Version"):
            messagebox.showerror(_("Error"), _("No Blender version selected."))
            return
        try:
            blender_executable = self.get_matching_blender_executable(selected_version)
            if blender_executable and self._check_version_match(blender_executable, selected_version):
                self._run_addon_script(blender_executable, selected_addon, enable=True)
            else:
                base_version_prefix = selected_version.split(".")[0] + "." + selected_version.split(".")[1]
                versions_to_process = self._get_matching_versions(base_version_prefix)
                for exe in versions_to_process:
                    self._run_addon_script(exe, selected_addon, enable=True)
        except Exception as e:
            log.error(f"Error activating addon: {e}")
        finally:
            self._hide_addon_page_message()
            self._update_addon_status()

    def deactivate_addon_in_all_versions(self, selected_addon):
        selected_version = self.version_var.get()
        self._show_addon_page_message(_("Deactivating..."))
        if not selected_version or selected_version == _("Select Blender Version"):
            messagebox.showerror(_("Error"), _("No Blender version selected."))
            return
        try:
            blender_executable = self.get_matching_blender_executable(selected_version)
            if blender_executable and self._check_version_match(blender_executable, selected_version):
                self._run_addon_script(blender_executable, selected_addon, enable=False)
            else:
                base_version_prefix = selected_version.split(".")[0] + "." + selected_version.split(".")[1]
                versions_to_process = self._get_matching_versions(base_version_prefix)
                for exe in versions_to_process:
                    self._run_addon_script(exe, selected_addon, enable=False)
        except Exception as e:
            log.error(f"Error deactivating addon: {e}")
        finally:
            self._hide_addon_page_message()
            self._update_addon_status()

    def _run_addon_script(self, blender_executable, addon_name, enable=True):
        action = "enable" if enable else "disable"
        params = "default_set=True, persistent=True" if enable else "default_set=True"
        script_content = f"""
import bpy, addon_utils, sys, os, importlib
for p in sys.path:
    if 'addons' in p.lower():
        print(f'ADDON_PATH: {{p}}', file=sys.stderr)
found = os.path.exists(os.path.join(bpy.utils.user_resource('SCRIPTS'), 'addons', '{addon_name}'))
print(f'ADDON_EXISTS: {{found}}', file=sys.stderr)
try:
    importlib.import_module('{addon_name}')
    print(f'IMPORT_OK', file=sys.stderr)
except Exception as e:
    print(f'IMPORT_FAIL: {{e}}', file=sys.stderr)
enabled = [a.module for a in bpy.context.preferences.addons]
if '{addon_name}' in enabled:
    print(f'ENABLED: yes', file=sys.stderr)
else:
    print(f'ENABLED: no', file=sys.stderr)
try:
    if {enable}:
        if '{addon_name}' in enabled:
            print("ALREADY_ACTIVE")
        else:
            ok = addon_utils.enable("{addon_name}", {params})
            if ok:
                bpy.ops.wm.save_userpref()
                print("SUCCESS")
            else:
                print(f"ERROR: addon '{addon_name}' enable failed")
    else:
        if '{addon_name}' not in enabled:
            print("ALREADY_INACTIVE")
        else:
            normalized = "{addon_name}".replace(" ", "_")
            ok = False
            for i, a in enumerate(bpy.context.preferences.addons):
                if a.module == normalized:
                    try:
                        addon_utils.unregister(module_name=normalized)
                    except Exception:
                        pass
                    bpy.context.preferences.addons.remove(bpy.context.preferences.addons[i])
                    ok = True
                    break
            if not ok:
                ok = addon_utils.disable("{addon_name}", {params})
            if ok:
                bpy.ops.wm.save_userpref()
                print("SUCCESS")
            else:
                print(f"ERROR: addon '{addon_name}' disable failed")
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
"""
        try:
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py", encoding="utf-8") as f:
                temp_script_path = f.name
                f.write(script_content)

            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

            result = subprocess.run(
                [blender_executable, "--background", "--python", temp_script_path],
                capture_output=True, text=False, startupinfo=startupinfo, check=False,
            )
            os.remove(temp_script_path)

            stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
            stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            output = stdout + stderr
            if "SUCCESS" in output:
                msg = _("Addon '{0}' enabled.").format(addon_name) if enable else _("Addon '{0}' disabled.").format(addon_name)
                self.frame.after(0, lambda: messagebox.showinfo(_("Success"), msg))
            elif "ALREADY_ACTIVE" in output:
                self.frame.after(0, lambda: messagebox.showinfo(_("Info"), _("Addon '{0}' is already enabled.").format(addon_name)))
            elif "ALREADY_INACTIVE" in output:
                self.frame.after(0, lambda: messagebox.showinfo(_("Info"), _("Addon '{0}' is already disabled.").format(addon_name)))
            else:
                err = output.strip() or _("Unknown error")
                log.error(f"Failed to {action} addon '{addon_name}': {err}")
                self.frame.after(0, lambda: messagebox.showerror(_("Error"), err))
        except Exception as e:
            log.error(f"Failed to {action} addon '{addon_name}' for {blender_executable}: {e}")

    # ---------- Addon status ----------

    def _update_addon_status(self, event=None):
        threading.Thread(target=self._update_addon_status_thread, daemon=True).start()

    def _update_addon_status_thread(self):
        selected_version = self.version_var.get()
        if not selected_version or selected_version == _("Select Blender Version"):
            return

        temp_script_path = None
        try:
            self._show_addon_page_message(_("Loading..."))
            blender_exe = self.get_matching_blender_executable(selected_version)
            if not blender_exe or not os.path.exists(blender_exe):
                return

            blender_manager_dir = get_blender_manager_dir().replace("\\", "/")

            script_content = f"""
import bpy
import json
import os

BLENDER_MANAGER_DIR = r"{blender_manager_dir}"
output_file = os.path.join(BLENDER_MANAGER_DIR, "addon_status.json")

addon_status = {{}}
try:
    for addon in bpy.context.preferences.addons.values():
        module_name = getattr(addon, "module", "Unknown")
        is_enabled = True
        addon_status[module_name] = is_enabled
except Exception as e:
    addon_status["error"] = f"Error fetching addons: {{str(e)}}"

try:
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(addon_status, f, indent=4)
    print(f"Addon status written to: {{output_file}}")
except Exception as e:
    print(f"Failed to write addon status JSON: {{str(e)}}")
"""
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py", encoding="utf-8") as f:
                temp_script_path = f.name
                f.write(script_content)

            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            subprocess.run(
                [blender_exe, "--background", "--python", temp_script_path],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, startupinfo=startupinfo,
            )

            addon_status_file = os.path.join(get_blender_manager_dir(), "addon_status.json")
            if not os.path.exists(addon_status_file):
                return

            with open(addon_status_file, "r", encoding="utf-8") as f:
                addon_status = json.load(f)

            def update_treeview():
                for item in self.plugins_tree.get_children():
                    addon_name = self.plugins_tree.item(item, "values")[0]
                    base_name = addon_name.split("/")[-1]
                    normalized = base_name.replace(" ", "_").replace("-", "_")
                    active = (addon_status.get(addon_name, False) or
                              addon_status.get(base_name, False) or
                              addon_status.get(normalized, False))
                    tag = "enabled" if active else "disabled"
                    status = _("Activated") if active else _("Deactivated")
                    self.plugins_tree.set(item, "Status", status)
                    self.plugins_tree.item(item, tags=(tag,))

            self.plugins_tree.after(0, update_treeview)

        except Exception as e:
            log.error(f"Failed to update addon status: {e}")
        finally:
            self._hide_addon_page_message()
            if temp_script_path and os.path.exists(temp_script_path):
                os.remove(temp_script_path)

    # ---------- Status bar messages on the addon page ----------

    def _show_addon_page_message(self, message):
        if hasattr(self, "_activating_label"):
            return
        self._activating_label = ttkb.Label(
            self.version_combobox.master, text=message, foreground="green"
        )
        self._activating_label.pack(side="left", padx=(10, 0))

    def _hide_addon_page_message(self):
        if hasattr(self, "_activating_label"):
            self._activating_label.destroy()
            del self._activating_label

    # ---------- Error helper ----------

    def _show_error(self, message):
        def show():
            messagebox.showerror(_("Error"), message)
        self.plugins_tree.after(0, show)
