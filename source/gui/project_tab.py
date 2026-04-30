import datetime as dt
import json
import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import zipfile
from io import BytesIO

import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from PIL import Image, ImageTk
from tkinterdnd2 import DND_FILES

from i18n import _

from core import (
    Logger, DataManager, ConfigManager, run_in_background, resource_path,
    get_blender_executable, get_blender_versions_dir,
    get_blender_config_path, get_blender_manager_dir,
    get_paths_dir, open_file_with_default_app
)

log = Logger()


class ProjectManagementTab:
    def __init__(self, app, notebook):
        self.app = app
        self.notebook = notebook
        self.config = ConfigManager()
        self.data = DataManager()

        self.frame = ttkb.Frame(self.notebook, padding=(10, 10, 10, 10))
        self.project_directory_path = tk.StringVar(value=self._load_project_directory())
        self.project_search_var = tk.StringVar()
        self.project_search_var.trace("w", self.on_search_change)
        self.placeholder_text = _("Search Projects")
        self.folder_list = []
        self.current_index = 0
        self._build_ui()
        self.load_folder_into_tree(self.project_directory_path.get(), "")
        self.refresh_projects_list()

    def _build_ui(self):
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(2, weight=1)

        self._build_directory_browser()
        self._build_search_bar()
        self._build_treeview()
        self._build_context_menu()

    def _build_directory_browser(self):
        browser_frame = ttkb.Frame(self.frame)
        browser_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=(0, 5))
        browser_frame.columnconfigure(0, weight=1)

        self.project_directory_entry = ttkb.Entry(
            browser_frame, textvariable=self.project_directory_path, width=50
        )
        self.project_directory_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        ttkb.Button(
            browser_frame, text=_("Browse"), takefocus=False,
            command=self.browse_project_directory
        ).grid(row=0, column=1, padx=(0, 5))

        ttkb.Button(
            browser_frame, text=_("Add Project"), takefocus=False,
            command=self.add_project
        ).grid(row=0, column=2, padx=(0, 5))

        ttkb.Button(
            browser_frame, text=_("Refresh"), takefocus=False,
            command=self.refresh_projects_list
        ).grid(row=0, column=3)

    def _build_search_bar(self):
        self.project_search_entry = ttkb.Entry(
            self.frame, textvariable=self.project_search_var, width=50
        )
        self.project_search_entry.grid(row=1, column=0, sticky="w", padx=5, pady=(0, 10))
        self.project_search_entry.insert(0, self.placeholder_text)
        self.project_search_entry.configure(foreground="grey")

        self.project_search_entry.bind("<FocusIn>", self._on_entry_click)
        self.project_search_entry.bind("<FocusOut>", self._on_focus_out)

    def _on_entry_click(self, event):
        if self.project_search_entry.get() == self.placeholder_text:
            self.project_search_entry.delete(0, "end")
            self.project_search_entry.configure(foreground="black")

    def _on_focus_out(self, event):
        query = self.project_search_var.get().strip()
        if not query:
            self.project_search_entry.configure(foreground="grey")
            self.project_search_entry.delete(0, "end")
            self.project_search_entry.insert(0, self.placeholder_text)
            self.refresh_projects_list()

    def _build_treeview(self):
        tree_frame = ttkb.Frame(self.frame)
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=5)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        style = ttkb.Style()
        style.configure("ProjectManagement.Treeview", font=("Segoe UI", 12), rowheight=30)
        style.configure("ProjectManagement.Treeview.Heading", font=("Segoe UI", 14, "bold"))

        self.projects_tree = ttkb.Treeview(
            tree_frame,
            columns=("Last Modified", "Size", "Last Blender Version"),
            show="tree headings",
            selectmode="browse",
            style="ProjectManagement.Treeview"
        )

        self.projects_tree.heading("#0", text=_("Project Name"),
                                    command=lambda: self.sort_tree_column("#0", False))
        self.projects_tree.column("#0", width=300, anchor="w", minwidth=150, stretch=True)

        self.projects_tree.heading("Last Modified", text=_("Last Modified"),
                                    command=lambda: self.sort_tree_column("Last Modified", False))
        self.projects_tree.column("Last Modified", width=200, anchor="center", minwidth=100)

        self.projects_tree.heading("Size", text=_("Size"),
                                    command=lambda: self.sort_tree_column("Size", False))
        self.projects_tree.column("Size", width=100, anchor="center", minwidth=80)

        self.projects_tree.heading("Last Blender Version", text=_("Blender Ver."),
                                    command=lambda: self.sort_tree_column("Last Blender Version", False))
        self.projects_tree.column("Last Blender Version", width=150, anchor="center", minwidth=100)

        self.projects_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttkb.Scrollbar(tree_frame, orient="vertical", command=self.projects_tree.yview)
        self.projects_tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.projects_tree.bind("<<TreeviewOpen>>", self.on_treeview_open)
        self.projects_tree.drop_target_register(DND_FILES)
        self.projects_tree.dnd_bind("<<Drop>>", self.handle_project_treeview_drop)

    def _build_context_menu(self):
        self.context_menu = tk.Menu(self.projects_tree, tearoff=0)
        self.open_menu = tk.Menu(self.context_menu, tearoff=0)
        self.context_menu.add_cascade(label=_("Open With..."), menu=self.open_menu)
        self.context_menu.add_command(label=_("Rename"), command=self.rename_project)
        self.context_menu.add_command(label=_("Go to File Path"), command=self.go_to_project_file_path)
        self.context_menu.add_command(label=_("Delete"), command=self.remove_project)
        self.context_menu.add_command(label=_("Export"), command=self.export_project)
        self.context_menu.add_command(label=_("Info"), command=self.view_project_content)
        self.move_menu = tk.Menu(self.context_menu, tearoff=0)
        self.context_menu.add_cascade(label=_("Move to Folder"), menu=self.move_menu)

        self.app.bind_right_click(self.projects_tree, self.show_context_menu_projects)

    def show_context_menu_projects(self, event):
        selected_item = self.projects_tree.identify_row(event.y)
        if selected_item:
            self.projects_tree.selection_set(selected_item)
            self.projects_tree.focus(selected_item)
            self._populate_move_menu()
            self._open_project_menu()
            self.context_menu.post(event.x_root, event.y_root)

    def _open_project_menu(self):
        versions_dir = get_blender_versions_dir()
        self.open_menu.delete(0, "end")

        main_blender_path = get_blender_executable()
        if os.path.exists(main_blender_path):
            self.open_menu.add_command(
                label=_("Blender Main"),
                command=lambda: self.open_project_with_blender(main_blender_path)
            )
        else:
            self.open_menu.add_command(label=_("Blender Main (Not Found)"), state="disabled")

        blender_versions = []
        if os.path.exists(versions_dir):
            blender_versions = [
                folder for folder in os.listdir(versions_dir)
                if os.path.isdir(os.path.join(versions_dir, folder))
            ]

        if not blender_versions:
            self.open_menu.add_command(label=_("No Blender versions found"), state="disabled")
            return

        exe_name = "blender.exe" if os.name == "nt" else "blender"
        for version in sorted(blender_versions):
            version_path = os.path.join(versions_dir, version, exe_name)
            if not os.path.exists(version_path) and sys.platform == "darwin":
                version_path = os.path.join(versions_dir, version, "Blender.app", "Contents", "MacOS", "Blender")
            if os.path.exists(version_path):
                self.open_menu.add_command(
                    label=version,
                    command=lambda path=version_path: self.open_project_with_blender(path)
                )

    def _populate_move_menu(self):
        self.move_menu.delete(0, "end")
        project_root = self.project_directory_path.get()
        self.folder_list = []
        self.current_index = 0
        thread = threading.Thread(target=self._collect_folders_in_background, args=(project_root,))
        thread.start()
        self.frame.after(100, lambda: self._load_folders_to_menu(self.move_menu))

    def _collect_folders_in_background(self, folder_path):
        try:
            items = sorted(os.listdir(folder_path))
            for item in items:
                item_path = os.path.join(folder_path, item)
                if os.path.isdir(item_path):
                    self.folder_list.append(item_path)
                    self._collect_folders_in_background(item_path)
        except Exception as e:
            log.error(f"Error collecting folders: {e}")

    def _load_folders_to_menu(self, menu, batch_size=10):
        if self.current_index >= len(self.folder_list):
            return
        end_index = min(self.current_index + batch_size, len(self.folder_list))
        for folder_path in self.folder_list[self.current_index:end_index]:
            folder_name = os.path.basename(folder_path)
            submenu = tk.Menu(menu, tearoff=0)
            submenu.add_command(
                label=_("Select This Folder"),
                command=lambda path=folder_path: self._move_blend_file(
                    self.get_item_full_path(self.projects_tree.focus()), path
                )
            )
            self._load_submenu(submenu, folder_path)
            menu.add_cascade(label=folder_name, menu=submenu)
        self.current_index = end_index
        if self.current_index < len(self.folder_list):
            self.frame.after(100, lambda: self._load_folders_to_menu(menu, batch_size))

    def _load_submenu(self, submenu, folder_path):
        try:
            submenu.delete(0, "end")
            submenu.add_command(
                label=_("Select This Folder"),
                command=lambda path=folder_path: self._move_blend_file(
                    self.get_item_full_path(self.projects_tree.focus()), path
                )
            )
            items = sorted(os.listdir(folder_path))
            for item in items:
                item_path = os.path.join(folder_path, item)
                if os.path.isdir(item_path):
                    nested_submenu = tk.Menu(submenu, tearoff=0)
                    nested_submenu.add_command(
                        label=_("Select This Folder"),
                        command=lambda path=item_path: self._move_blend_file(
                            self.get_item_full_path(self.projects_tree.focus()), path
                        )
                    )
                    self._load_submenu(nested_submenu, item_path)
                    submenu.add_cascade(label=os.path.basename(item_path), menu=nested_submenu)
        except Exception as e:
            log.error(f"Error loading submenu: {e}")

    def _move_blend_file(self, source_path, target_folder):
        try:
            target_path = os.path.join(target_folder, os.path.basename(source_path))
            if os.path.exists(target_path):
                confirm = messagebox.askyesno(_("Confirm"), _("File already exists in the target folder. Overwrite?"))
                if not confirm:
                    return
            shutil.move(source_path, target_path)
            messagebox.showinfo(_("Success"),
                                _("Moved {0} to {1}. Refresh list to see changes.").format(os.path.basename(source_path), target_folder))
        except Exception as e:
            messagebox.showerror(_("Error"), _("Failed to move file: {0}").format(e))

    def sort_tree_column(self, column, reverse):
        def is_folder(item):
            full_path = self.get_item_full_path(item)
            return os.path.isdir(full_path)

        def parse_version(version_str):
            try:
                if "+" in version_str:
                    cleaned = version_str.replace("+", "").strip()
                    return (*tuple(map(int, cleaned.split("."))), 1)
                return (*tuple(map(int, version_str.split("."))), 0)
            except ValueError:
                return (0, 0, 0)

        def sort_items(parent_item):
            if column == "#0":
                items = [(self.projects_tree.item(item, "text"), item)
                         for item in self.projects_tree.get_children(parent_item)]
            else:
                items = [(self.projects_tree.set(item, column), item)
                         for item in self.projects_tree.get_children(parent_item)]

            folders = [(text, item) for text, item in items if is_folder(item)]
            files = [(text, item) for text, item in items if not is_folder(item)]

            if column == "Size":
                files.sort(key=lambda x: float(x[0].replace(" MB", ""))
                           if x[0] and " MB" in x[0] else 0.0, reverse=reverse)
            elif column == "Last Modified":
                files.sort(key=lambda x: x[0] if x[0] else "", reverse=reverse)
            elif column == "Last Blender Version":
                files.sort(key=lambda x: parse_version(x[0]), reverse=reverse)
            else:
                folders.sort(key=lambda x: x[0].lower(), reverse=reverse)
                files.sort(key=lambda x: x[0].lower(), reverse=reverse)

            sorted_items = folders + files
            for index, (text, item) in enumerate(sorted_items):
                self.projects_tree.move(item, parent_item, index)
                sort_items(item)

        sort_items("")
        self.projects_tree.heading(column, command=lambda: self.sort_tree_column(column, not reverse))

    def refresh_projects_list(self, query=None):
        self.projects_tree.delete(*self.projects_tree.get_children())
        project_dir = self.project_directory_path.get()
        if not os.path.exists(project_dir):
            return
        self._insert_directory("", project_dir, query, depth=0)

    def _insert_directory(self, parent, path, query=None, depth=0):
        if depth >= 5:
            return
        try:
            items = sorted(os.listdir(path))
            for item in items:
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    if self._contains_blend_files(item_path):
                        folder_id = self.projects_tree.insert(
                            parent, "end", text=item, values=("", "", ""), open=False
                        )
                        self._insert_directory(folder_id, item_path, query, depth + 1)
            for item in items:
                item_path = os.path.join(path, item)
                if item.lower().endswith((".blend", ".blend1", ".blend2", ".blend3")):
                    if query is None or query.lower() in item.lower():
                        last_modified = time.strftime(
                            "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(item_path))
                        )
                        size = os.path.getsize(item_path) / (1024 * 1024)
                        blender_version = self._get_blend_version(item_path)
                        self.projects_tree.insert(
                            parent, "end", text=item,
                            values=(last_modified, f"{size:.2f} MB", blender_version)
                        )
        except Exception as e:
            log.error(f"Error inserting directory: {e}")

    def _contains_blend_files(self, directory):
        try:
            for root, _, files in os.walk(directory):
                for file in files:
                    if file.lower().endswith((".blend", ".blend1", ".blend2", ".blend3")):
                        return True
            return False
        except Exception as e:
            log.error(f"Error checking for blend files: {e}")
            return False

    def load_folder_into_tree(self, folder_path, parent_item):
        try:
            items = sorted(os.listdir(folder_path))
            for item in items:
                item_path = os.path.join(folder_path, item)
                if os.path.isdir(item_path):
                    folder_id = self.projects_tree.insert(
                        parent_item, "end", text=item, values=("", "", ""), open=False
                    )
                    self.projects_tree.insert(folder_id, "end", text="dummy")
                elif item.lower().endswith((".blend", ".blend1", ".blend2", ".blend3")):
                    last_modified = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(item_path))
                    )
                    size = os.path.getsize(item_path) / (1024 * 1024)
                    blender_version = self._get_blend_version(item_path)
                    self.projects_tree.insert(
                        parent_item, "end", text=item,
                        values=(last_modified, f"{size:.2f} MB", blender_version)
                    )
        except Exception as e:
            log.error(f"Error loading folder into tree: {e}")

    def on_treeview_open(self, event):
        item_id = self.projects_tree.focus()
        children = self.projects_tree.get_children(item_id)
        if len(children) == 1 and self.projects_tree.item(children[0], "text") == "dummy":
            self.projects_tree.delete(children[0])
            folder_path = self.get_item_full_path(item_id)
            self.load_folder_into_tree(folder_path, item_id)

    def on_search_change(self, *args):
        if not hasattr(self, "projects_tree"):
            return
        query = self.project_search_var.get().strip().lower()
        if not query or query == self.placeholder_text:
            self.refresh_projects_list()
        else:
            self.projects_tree.delete(*self.projects_tree.get_children())
            self._expand_and_search(self.project_directory_path.get(), query)

    def _expand_and_search(self, folder_path, query, parent_item=""):
        try:
            items = sorted(os.listdir(folder_path))
            for item in items:
                item_path = os.path.join(folder_path, item)
                if os.path.isdir(item_path):
                    folder_id = self.projects_tree.insert(
                        parent_item, "end", text=item, values=("", "", ""), open=True
                    )
                    self._expand_and_search(item_path, query, folder_id)
                elif item.lower().endswith((".blend", ".blend1", ".blend2", ".blend3")):
                    if query in item.lower():
                        last_modified = time.strftime(
                            "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(item_path))
                        )
                        size = os.path.getsize(item_path) / (1024 * 1024)
                        blender_version = self._get_blend_version(item_path)
                        file_item = self.projects_tree.insert(
                            parent_item, "end", text=item,
                            values=(last_modified, f"{size:.2f} MB", blender_version)
                        )
                        self._scroll_to_item(file_item)
        except Exception as e:
            log.error(f"Error during search: {e}")

    def _scroll_to_item(self, item):
        try:
            self.projects_tree.see(item)
            self.projects_tree.focus(item)
            self.projects_tree.selection_set(item)
        except Exception as e:
            log.error(f"Error scrolling to item: {e}")

    def browse_project_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            total_files = sum([len(files) for _, _, files in os.walk(directory)])
            if total_files > 1000:
                proceed = messagebox.askyesno(
                    _("Large Directory Warning"),
                    _("The selected directory contains {0} files. "
                      "Loading this directory may take a long time and could freeze the application.\n\n"
                      "Do you want to continue?").format(total_files)
                )
                if not proceed:
                    return
            self.project_directory_path.set(directory)
            self._save_project_directory(directory)
            self.refresh_projects_list()

    def add_project(self, project_dir=None, copy_individually=False, extract_individually=False):
        if project_dir is None:
            project_dir = filedialog.askdirectory()
            if not project_dir:
                return
        try:
            destination = self.project_directory_path.get()
            if os.path.isfile(project_dir) and project_dir.lower().endswith(
                (".blend", ".blend1", ".blend2", ".blend11", ".blend3")
            ):
                shutil.copy(project_dir, destination)
                log.info(f"Copied .blend file to {destination}")
            elif os.path.isdir(project_dir):
                if copy_individually:
                    self._copy_blend_files_from_directory(project_dir, destination)
                else:
                    folder_name = os.path.basename(project_dir).replace(".", "_")
                    target_folder = os.path.join(destination, folder_name)
                    os.makedirs(target_folder, exist_ok=True)
                    shutil.copytree(project_dir, target_folder, dirs_exist_ok=True)
                    log.info(f"Copied entire folder to {target_folder}")
            elif project_dir.lower().endswith(".zip"):
                if extract_individually:
                    self._extract_blend_files_from_zip(project_dir, destination)
                else:
                    folder_name = os.path.basename(project_dir).replace(".", "_")
                    target_folder = os.path.join(destination, folder_name)
                    os.makedirs(target_folder, exist_ok=True)
                    self._extract_blend_files_from_zip(project_dir, target_folder)
                    log.info(f"Extracted zip contents to {target_folder}")
            else:
                messagebox.showerror(_("Error"), _("Unsupported file type."))
                return
            messagebox.showinfo(_("Success"), _("Project added successfully!"))
            self.refresh_projects_list()
        except Exception as e:
            messagebox.showerror(_("Error"), _("Failed to add project: {0}").format(e))

    def _copy_blend_files_from_directory(self, directory_path, destination):
        os.makedirs(destination, exist_ok=True)
        for root, _, files in os.walk(directory_path):
            for file in files:
                if file.lower().endswith((".blend", ".blend1", ".blend11")):
                    src_file = os.path.join(root, file)
                    shutil.copy(src_file, destination)
                    log.info(f"Copied {src_file} to {destination}")

    def _extract_blend_files_from_zip(self, zip_path, destination):
        os.makedirs(destination, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for file_info in zip_ref.infolist():
                file_name = file_info.filename
                if file_name.lower().endswith((".blend", ".blend1", ".blend11")):
                    extracted_path = os.path.join(destination, os.path.basename(file_name))
                    try:
                        with zip_ref.open(file_info) as source, open(extracted_path, "wb") as target:
                            shutil.copyfileobj(source, target)
                        log.info(f"Extracted {file_name} to {extracted_path}")
                    except Exception as e:
                        log.error(f"Failed to extract {file_name}: {e}")

    def remove_project(self):
        selected_item = self.projects_tree.focus()
        if selected_item:
            project_path = self.get_item_full_path(selected_item)
            if os.path.exists(project_path):
                confirm = messagebox.askyesno(_("Confirm"),
                                              _("Are you sure you want to remove '{0}'?").format(project_path))
                if confirm:
                    try:
                        if os.path.isdir(project_path):
                            shutil.rmtree(project_path)
                        else:
                            os.remove(project_path)
                        messagebox.showinfo(_("Success"), _("'{0}' removed.").format(project_path))
                        self.refresh_projects_list()
                    except Exception as e:
                        messagebox.showerror(_("Error"), _("Failed to remove project: {0}").format(e))
            else:
                messagebox.showwarning(_("Warning"), _("The selected item does not exist."))
        else:
            messagebox.showwarning(_("Warning"), _("No item selected."))

    def rename_project(self):
        selected_item = self.projects_tree.focus()
        if not selected_item:
            messagebox.showwarning(_("Warning"), _("No item selected."))
            return
        project_path = self.get_item_full_path(selected_item)
        if not os.path.exists(project_path):
            messagebox.showerror(_("Error"), _("Selected item does not exist."))
            return
        current_name = os.path.basename(project_path)
        is_file = os.path.isfile(project_path)
        file_extension = os.path.splitext(current_name)[1] if is_file else ""
        initial_name = os.path.splitext(current_name)[0] if is_file else current_name
        new_name = simpledialog.askstring(_("Rename"), _("Enter new name:"), initialvalue=initial_name)
        if new_name and new_name != initial_name:
            new_name_with_ext = new_name + file_extension if is_file else new_name
            new_path = os.path.join(os.path.dirname(project_path), new_name_with_ext)
            if os.path.exists(new_path):
                messagebox.showerror(_("Error"), _("A file or folder with that name already exists."))
                return
            try:
                os.rename(project_path, new_path)
                messagebox.showinfo(_("Success"), _("Renamed to '{0}'.").format(new_name_with_ext))
                self.refresh_projects_list()
            except Exception as e:
                messagebox.showerror(_("Error"), _("Failed to rename: {0}").format(e))

    def go_to_project_file_path(self):
        selected_item = self.projects_tree.selection()
        if not selected_item:
            messagebox.showwarning(_("Warning"), _("No project selected."))
            return
        project_path = self._get_item_project_folder_path(selected_item[0])
        if os.path.exists(project_path):
            try:
                if os.name == "nt":
                    os.startfile(project_path)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", project_path])
                else:
                    subprocess.Popen(["xdg-open", project_path])
            except Exception as e:
                messagebox.showerror(_("Error"), _("Failed to open directory: {0}").format(e))
        else:
            messagebox.showwarning(_("Warning"), _("The selected directory does not exist."))

    def open_project_with_blender(self, blender_executable_path):
        selected_item = self.projects_tree.focus()
        if selected_item:
            project_path = self.get_item_full_path(selected_item)
            if os.path.isfile(project_path) and project_path.lower().endswith(
                (".blend", ".blend1", ".blend11", ".blend111")
            ):
                try:
                    startupinfo = None
                    if os.name == "nt":
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    subprocess.Popen([blender_executable_path, project_path],
                                     startupinfo=startupinfo, shell=False)
                except Exception as e:
                    messagebox.showerror(_("Error"), _("Failed to open project with Blender: {0}").format(e))
            else:
                messagebox.showwarning(_("Warning"), _("The selected item is not a .blend file."))
        else:
            messagebox.showwarning(_("Warning"), _("No project selected."))

    def handle_project_treeview_drop(self, event):
        file_path = event.data.strip().strip("{}")
        log.info(f"Dragged file path: {file_path}")
        if os.path.isfile(file_path) and file_path.lower().endswith(
            (".blend", ".blend1", ".blend2", ".blend3")
        ):
            self.add_project(file_path)
        elif os.path.isdir(file_path):
            if any(
                file.lower().endswith((".blend", ".blend1", ".blend2", ".blend3"))
                for root, _, files in os.walk(file_path) for file in files
            ):
                user_choice = messagebox.askyesno(
                    _("Copy Options"),
                    _("Do you want to copy the .blend files individually, "
                      "or keep the folder structure?\n\nYes: Individually\nNo: Keep folder structure")
                )
                self.add_project(file_path, copy_individually=user_choice)
            else:
                messagebox.showerror(_("Error"), _("The folder does not contain any .blend files."))
        elif file_path.lower().endswith(".zip"):
            with zipfile.ZipFile(file_path, "r") as zip_ref:
                if any(
                    file.lower().endswith((".blend", ".blend1", ".blend2", ".blend3"))
                    for file in zip_ref.namelist()
                ):
                    user_choice = messagebox.askyesno(
                        _("Extraction Options"),
                        _("Do you want to extract .blend files individually, "
                          "or keep them inside a folder?\n\nYes: Individually\nNo: Keep in folder")
                    )
                    self.add_project(file_path, extract_individually=user_choice)
                else:
                    messagebox.showerror(_("Error"), _("The zip file does not contain any .blend files."))
        else:
            messagebox.showerror(
                _("Error"),
                _("Only .blend files, folders, or zip files containing .blend files can be added.")
            )

    def export_project(self):
        selected_item = self.projects_tree.focus()
        if not selected_item:
            messagebox.showwarning(_("Warning"), _("No item selected."))
            return
        blend_path = self.get_item_full_path(selected_item)
        if not os.path.isfile(blend_path) or not blend_path.lower().endswith(
            (".blend", ".blend1", ".blend2", ".blend3")
        ):
            messagebox.showerror(_("Error"), _("Selected item is not a .blend file."))
            return
        export_format = simpledialog.askstring(
            _("Export Format"), _("Enter export format (fbx, gltf, abc):"), initialvalue="fbx"
        )
        if not export_format:
            return
        export_format = export_format.lower()
        if export_format not in ["fbx", "obj", "gltf", "ply", "stl", "abc"]:
            messagebox.showerror(_("Error"), _("Invalid export format."))
            return
        output_dir = filedialog.askdirectory(title=_("Select Export Directory"))
        if not output_dir:
            return
        output_file = os.path.splitext(os.path.basename(blend_path))[0] + f".{export_format}"
        output_path = os.path.join(output_dir, output_file)
        blender_path = get_blender_executable()
        if not os.path.exists(blender_path):
            messagebox.showerror(_("Error"), _("Blender executable not found at: {0}").format(blender_path))
            return
        self._show_exporting_message()
        threading.Thread(
            target=self._run_export_process,
            args=(blend_path, output_path, export_format, blender_path),
            daemon=True
        ).start()

    def _run_export_process(self, blend_path, output_path, export_format, blender_path):
        blend_path = os.path.normpath(blend_path).encode("utf-8", errors="surrogateescape").decode("utf-8")
        output_path = os.path.normpath(output_path).encode("utf-8", errors="surrogateescape").decode("utf-8")
        temp_script_path = os.path.join(os.path.dirname(output_path), "temp_export_script.py")
        try:
            export_script = f"""
import bpy
bpy.ops.wm.open_mainfile(filepath=r'{blend_path}')
if '{export_format}' == 'fbx':
    for obj in bpy.data.objects:
        if obj.type == 'LIGHT':
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.export_scene.fbx(
        filepath=r'{output_path}',
        use_selection=False,
        embed_textures=True,
        path_mode='COPY',
        bake_space_transform=True,
        apply_scale_options='FBX_SCALE_ALL',
        mesh_smooth_type='FACE',
        use_tspace=True,
        use_mesh_modifiers=True,
        use_triangles=True
    )
elif '{export_format}' == 'gltf':
    bpy.ops.export_scene.gltf(
        filepath=r'{output_path}',
        export_format='GLTF_SEPARATE',
        export_materials='EXPORT',
        export_apply=True,
        export_tangents=True,
        use_selection=False
    )
elif '{export_format}' == 'abc':
    bpy.ops.wm.alembic_export(
        filepath=r'{output_path}',
        apply_scale=True,
        visible_objects_only=True,
        flatten=False,
        uv_write=True
    )
"""
            with open(temp_script_path, "w", encoding="utf-8") as f:
                f.write(export_script)
            if not os.path.exists(temp_script_path):
                self._show_error_exporting(_("Temporary script file could not be created."))
                return
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
            subprocess.run(
                [blender_path, "--background", "--factory-startup", "--python", temp_script_path],
                check=True, startupinfo=startupinfo
            )
            self._show_info_exporting(_("Exported to {0}").format(output_path))
        except Exception as e:
            self._show_error_exporting(_("Failed to export: {0}").format(e))
        finally:
            if os.path.exists(temp_script_path):
                os.remove(temp_script_path)
            self._hide_exporting_message()

    def _show_error_exporting(self, message):
        self.frame.after(0, lambda: messagebox.showerror(_("Error"), message))

    def _show_info_exporting(self, message):
        self.frame.after(0, lambda: messagebox.showinfo(_("Success"), message))

    def _show_exporting_message(self):
        if hasattr(self, "exporting_label"):
            return
        self.exporting_label = ttkb.Label(
            self.frame, text=_("Exporting..."), foreground="red"
        )
        self.exporting_label.grid(row=3, column=0, sticky="w", padx=10, pady=(5, 0))

    def _hide_exporting_message(self):
        if hasattr(self, "exporting_label"):
            self.exporting_label.destroy()
            del self.exporting_label

    def view_project_content(self):
        selected_item = self.projects_tree.focus()
        if not selected_item:
            messagebox.showwarning(_("Warning"), _("No project selected."))
            return
        project_path = self.get_item_full_path(selected_item)
        if not os.path.exists(project_path):
            messagebox.showerror(_("Error"), _("Selected project does not exist."))
            return
        try:
            stats = os.stat(project_path)
            size = stats.st_size
            size_mb = size / (1024 * 1024)
            size_mb_str = f"{size_mb:.2f} MB"
            created_time = dt.datetime.fromtimestamp(stats.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
            modified_time = dt.datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            accessed_time = dt.datetime.fromtimestamp(stats.st_atime).strftime("%Y-%m-%d %H:%M:%S")
            is_dir = os.path.isdir(project_path)
            permissions = stat.filemode(stats.st_mode)

            time_spent = _("Unknown")
            json_path = os.path.join(os.path.expanduser("~"), ".BlenderManager", "mngaddon", "project_time.json")
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as json_file:
                        time_data = json.load(json_file)
                    project_basename = os.path.basename(project_path)
                    for file_path, time_in_seconds in time_data.items():
                        if os.path.basename(file_path) == project_basename:
                            hours, remainder = divmod(time_in_seconds, 3600)
                            minutes, seconds = divmod(remainder, 60)
                            time_spent = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
                            break
                except Exception as e:
                    time_spent = _("Error reading time data: {0}").format(e)

            thumbnail, meshes, total_vertex_count, materials, textures = \
                self._get_embedded_thumbnail_meshes_and_vertex_count(project_path)

            content_window = tk.Toplevel(self.frame)
            content_window.title(_("Properties of {0}").format(os.path.basename(project_path)))
            content_window.geometry("800x600")
            content_window.transient(self.frame)
            content_window.resizable(False, False)
            icon_path = resource_path(os.path.join("Assets", "Images", "bmng.ico"))
            if os.path.exists(icon_path):
                content_window.iconbitmap(icon_path)
            content_window.update_idletasks()
            x = self.frame.winfo_rootx() + (self.frame.winfo_width() // 2) - (content_window.winfo_width() // 2)
            y = self.frame.winfo_rooty() + (self.frame.winfo_height() // 2) - (content_window.winfo_height() // 2)
            content_window.geometry(f"+{x}+{y}")

            main_frame = ttkb.Frame(content_window, padding=(10, 10, 10, 10))
            main_frame.pack(fill="both", expand=True)

            properties_frame = ttkb.Frame(main_frame)
            properties_frame.pack(side="left", fill="y", padx=10, pady=10)

            preview_frame = ttkb.Frame(main_frame)
            preview_frame.pack(side="right", fill="both", expand=True, padx=10, pady=10)

            type_str = _("Folder") if is_dir else _("File")
            properties = (
                _("Name: {0}\n").format(os.path.basename(project_path)) +
                _("Path: {0}\n").format(project_path) +
                _("Type: {0}\n").format(type_str) +
                _("Size: {0}\n").format(size_mb_str) +
                _("Created Time: {0}\n").format(created_time) +
                _("Modified Time: {0}\n").format(modified_time) +
                _("Accessed Time: {0}\n").format(accessed_time) +
                _("Permissions: {0}\n").format(permissions) +
                _("Time Spent: {0}\n").format(time_spent) +
                _("Total Vertex Count: {0}\n").format(total_vertex_count)
            )

            properties_label = tk.Text(properties_frame, wrap="word", width=40, height=20)
            properties_label.insert("1.0", properties)
            properties_label.configure(state="disabled")
            properties_label.pack(expand=1, fill="both")

            canvas = tk.Canvas(preview_frame, width=200, height=200)
            canvas.pack(anchor="n", padx=5, pady=5)
            if thumbnail:
                thumbnail_resized = thumbnail.resize((200, 200), Image.LANCZOS)
                tk_thumbnail = ImageTk.PhotoImage(thumbnail_resized)
                canvas.create_image(100, 100, image=tk_thumbnail)
                canvas.image = tk_thumbnail
            else:
                placeholder = Image.new("RGB", (200, 200), color=(200, 200, 200))
                tk_placeholder = ImageTk.PhotoImage(placeholder)
                canvas.create_image(100, 100, image=tk_placeholder)
                canvas.image = tk_placeholder

            content_notebook = ttkb.Notebook(preview_frame)
            content_notebook.pack(expand=1, fill="both", padx=5, pady=5)

            meshes_frame = ttkb.Frame(content_notebook)
            content_notebook.add(meshes_frame, text=_("Meshes"))

            meshes_listbox = tk.Listbox(meshes_frame)
            meshes_listbox.pack(expand=1, fill="both", padx=5, pady=5)

            if meshes:
                for mesh_name in meshes:
                    meshes_listbox.insert(tk.END, mesh_name)
            else:
                meshes_listbox.insert(tk.END, _("No meshes found."))
                meshes_listbox.configure(state="disabled")

            export_mesh_btn = ttkb.Button(
                meshes_frame, text=_("Export Selected Mesh"),
                command=lambda: self._export_selected_mesh(meshes_listbox, project_path)
            )
            export_mesh_btn.pack(pady=5)

            materials_frame = ttkb.Frame(content_notebook)
            content_notebook.add(materials_frame, text=_("Materials"))

            materials_listbox = tk.Listbox(materials_frame)
            materials_listbox.pack(expand=1, fill="both", padx=5, pady=5)

            if materials:
                for mat_name in materials:
                    materials_listbox.insert(tk.END, mat_name)
            else:
                materials_listbox.insert(tk.END, _("No materials found."))
                materials_listbox.configure(state="disabled")

            export_mat_btn = ttkb.Button(
                materials_frame, text=_("Export Selected Material"),
                command=lambda: self._export_selected_material(materials_listbox, project_path)
            )
            export_mat_btn.pack(pady=5)

            textures_frame = ttkb.Frame(content_notebook)
            content_notebook.add(textures_frame, text=_("Textures"))

            textures_listbox = tk.Listbox(textures_frame)
            textures_listbox.pack(expand=1, fill="both", padx=5, pady=5)

            if textures:
                for tex_path in textures:
                    textures_listbox.insert(tk.END, tex_path)
            else:
                textures_listbox.insert(tk.END, _("No textures found."))
                textures_listbox.configure(state="disabled")

            export_tex_btn = ttkb.Button(
                textures_frame, text=_("Export Selected Texture"),
                command=lambda: self._export_selected_texture(textures_listbox)
            )
            export_tex_btn.pack(pady=5)

        except Exception as e:
            messagebox.showerror(_("Error"), _("Failed to retrieve properties: {0}").format(e))

    def _get_embedded_thumbnail_meshes_and_vertex_count(self, blend_file_path):
        def _blend_extract_thumb(path):
            REND = b"REND"
            TEST = b"TEST"
            with open(path, "rb") as blendfile:
                head = blendfile.read(12)
                if not head.startswith(b"BLENDER"):
                    return None, 0, 0
                is_64_bit = head[7] == 45
                is_big_endian = head[8] == 86
                sizeof_bhead = 24 if is_64_bit else 20
                int_endian = ">i" if is_big_endian else "<i"
                int_endian_pair = int_endian + "i"
                while True:
                    bhead = blendfile.read(sizeof_bhead)
                    if len(bhead) < sizeof_bhead:
                        return None, 0, 0
                    code = bhead[:4]
                    length = struct.unpack(int_endian, bhead[4:8])[0]
                    if code == REND:
                        blendfile.seek(length, os.SEEK_CUR)
                    else:
                        break
                if code != TEST:
                    return None, 0, 0
                try:
                    x, y = struct.unpack(int_endian_pair, blendfile.read(8))
                except struct.error:
                    return None, 0, 0
                length -= 8
                if length != x * y * 4:
                    return None, 0, 0
                image_buffer = blendfile.read(length)
                if len(image_buffer) != length:
                    return None, 0, 0
                return image_buffer, x, y

        import zlib

        thumbnail_image = None
        try:
            buf, width, height = _blend_extract_thumb(blend_file_path)
            if buf:
                def _write_png(buf, width, height):
                    width_byte_4 = width * 4
                    raw_data = b"".join(
                        b"\x00" + buf[span:span + width_byte_4]
                        for span in range((height - 1) * width * 4, -1, -width_byte_4)
                    )

                    def _png_pack(png_tag, data):
                        chunk_head = png_tag + data
                        return (struct.pack("!I", len(data)) + chunk_head +
                                struct.pack("!I", 0xFFFFFFFF & zlib.crc32(chunk_head)))

                    return b"".join([
                        b"\x89PNG\r\n\x1a\n",
                        _png_pack(b"IHDR", struct.pack("!2I5B", width, height, 8, 6, 0, 0, 0)),
                        _png_pack(b"IDAT", zlib.compress(raw_data, 9)),
                        _png_pack(b"IEND", b""),
                    ])

                png_data = _write_png(buf, width, height)
                thumbnail_image = Image.open(BytesIO(png_data))
        except Exception as e:
            log.error(f"Error extracting thumbnail: {e}")

        blender_exe_path = get_blender_executable()
        if not blender_exe_path or not os.path.exists(blender_exe_path):
            log.error("Blender executable path not found.")
            return thumbnail_image, None, None, None, None

        with tempfile.TemporaryDirectory() as temp_dir:
            data_path = os.path.join(temp_dir, "data.json")
            script_path = os.path.join(temp_dir, "extract_data.py")

            script_content = """
import bpy
import os
import json
import sys

blend_file_path = sys.argv[-2]
data_path = sys.argv[-1]

bpy.ops.wm.open_mainfile(filepath=blend_file_path)

meshes = [obj.name for obj in bpy.data.objects if obj.type == 'MESH']
total_vertex_count = sum(len(obj.data.vertices) for obj in bpy.data.objects if obj.type == 'MESH')

materials = [mat.name for mat in bpy.data.materials if not mat.library]

textures = []
for image in bpy.data.images:
    if image.filepath:
        tex_path = bpy.path.abspath(image.filepath)
        if os.path.exists(tex_path):
            textures.append(tex_path)

data = {
    "meshes": meshes,
    "total_vertex_count": total_vertex_count,
    "materials": materials,
    "textures": textures
}
with open(data_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False)
"""
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(script_content)

            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0

            try:
                subprocess.run(
                    [blender_exe_path, "--background", "--factory-startup",
                     "--python", script_path, "--", blend_file_path, data_path],
                    check=True, startupinfo=startupinfo
                )
                with open(data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                log.error(f"Failed to extract blend data: {e}")
                return thumbnail_image, None, None, None, None

        meshes = data.get("meshes", [])
        total_vertex_count = data.get("total_vertex_count", 0)
        materials = data.get("materials", [])
        textures = data.get("textures", [])

        return thumbnail_image, meshes, total_vertex_count, materials, textures

    def _export_selected_mesh(self, meshes_listbox, project_path):
        selected_indices = meshes_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning(_("Warning"), _("No mesh selected."))
            return
        selected_mesh = meshes_listbox.get(selected_indices[0])

        export_path = filedialog.asksaveasfilename(
            defaultextension=".fbx",
            filetypes=[(_("Autodesk FBX"), "*.fbx"), (_("All Files"), "*.*")],
            title=_("Save Mesh As")
        )
        if not export_path:
            return

        try:
            blender_exe_path = get_blender_executable()
            if not blender_exe_path or not os.path.exists(blender_exe_path):
                messagebox.showerror(_("Error"), _("Blender executable path not found."))
                return

            with tempfile.TemporaryDirectory() as temp_dir:
                script_path = os.path.join(temp_dir, "export_mesh.py")

                script_content = f"""
import bpy

blend_file_path = r"{project_path}"
mesh_name = r"{selected_mesh}"
export_path = r"{export_path}"

bpy.ops.wm.open_mainfile(filepath=blend_file_path)

for obj in bpy.data.objects:
    obj.select_set(False)

obj = bpy.data.objects.get(mesh_name)
if obj:
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    bpy.ops.export_scene.fbx(
        filepath=export_path,
        use_selection=True,
        apply_unit_scale=True,
        apply_scale_options='FBX_SCALE_ALL'
    )
else:
    print(f"Mesh {mesh_name} not found.")
"""
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(script_content)

                startupinfo = None
                if os.name == "nt":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0

                subprocess.run(
                    [blender_exe_path, "--background", "--factory-startup", "--python", script_path],
                    check=True, startupinfo=startupinfo
                )

            messagebox.showinfo(
                _("Success"), _("Mesh '{0}' exported successfully to '{1}'.").format(selected_mesh, export_path)
            )
        except subprocess.CalledProcessError as e:
            messagebox.showerror(_("Error"), _("Failed to export mesh: {0}").format(e))
        except Exception as e:
            messagebox.showerror(_("Error"), _("An error occurred: {0}").format(e))

    def _export_selected_material(self, materials_listbox, project_path):
        selected_indices = materials_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning(_("Warning"), _("No material selected."))
            return
        selected_material = materials_listbox.get(selected_indices[0])

        filetypes = [
            (_("Blender File"), "*.blend"),
            (_("FBX File"), "*.fbx"),
            (_("OBJ File"), "*.obj"),
            (_("Substance Archive"), "*.sbsar"),
            (_("All Files"), "*.*"),
        ]
        export_path = filedialog.asksaveasfilename(
            defaultextension=".blend",
            filetypes=filetypes,
            title=_("Save Material As")
        )
        if not export_path:
            return

        try:
            blender_exe_path = get_blender_executable()
            if not blender_exe_path or not os.path.exists(blender_exe_path):
                messagebox.showerror(_("Error"), _("Blender executable path not found."))
                return

            with tempfile.TemporaryDirectory() as temp_dir:
                script_path = os.path.join(temp_dir, "export_material.py")
                _, ext = os.path.splitext(export_path)
                ext = ext.lower()

                if ext == ".blend":
                    script_content = f"""
import bpy

blend_file_path = r"{project_path}"
material_name = r"{selected_material}"
export_path = r"{export_path}"

bpy.ops.wm.read_factory_settings(use_empty=True)

with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
    if material_name in data_from.materials:
        data_to.materials = [material_name]
    else:
        print(f"Material {material_name} not found in the blend file.")
        exit()

bpy.ops.wm.save_as_mainfile(filepath=export_path)
"""
                elif ext in (".fbx", ".obj"):
                    script_content = f"""
import bpy

blend_file_path = r"{project_path}"
material_name = r"{selected_material}"
export_path = r"{export_path}"

bpy.ops.wm.read_factory_settings(use_empty=True)

bpy.ops.mesh.primitive_cube_add()
obj = bpy.context.active_object

with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
    if material_name in data_from.materials:
        data_to.materials = [material_name]
    else:
        print(f"Material {material_name} not found in the blend file.")
        exit()

mat = bpy.data.materials.get(material_name)
if mat:
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

if export_path.lower().endswith(".fbx"):
    bpy.ops.export_scene.fbx(
        filepath=export_path,
        use_selection=True,
        embed_textures=True
    )
elif export_path.lower().endswith(".obj"):
    bpy.ops.export_scene.obj(
        filepath=export_path,
        use_selection=True,
        use_materials=True
    )
"""
                elif ext == ".sbsar":
                    messagebox.showerror(_("Error"), _("Exporting to .sbsar format is not supported."))
                    return
                else:
                    messagebox.showerror(_("Error"), _("Unsupported file extension: {0}").format(ext))
                    return

                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(script_content)

                startupinfo = None
                if os.name == "nt":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0

                subprocess.run(
                    [blender_exe_path, "--background", "--factory-startup", "--python", script_path],
                    check=True, startupinfo=startupinfo
                )

            messagebox.showinfo(
                _("Success"),
                _("Material '{0}' exported successfully to '{1}'.").format(selected_material, export_path)
            )
        except subprocess.CalledProcessError as e:
            messagebox.showerror(_("Error"), _("Failed to export material: {0}").format(e))
        except Exception as e:
            messagebox.showerror(_("Error"), _("An error occurred: {0}").format(e))

    def _export_selected_texture(self, textures_listbox):
        selected_indices = textures_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning(_("Warning"), _("No texture selected."))
            return
        selected_texture_path = textures_listbox.get(selected_indices[0])
        if not os.path.exists(selected_texture_path):
            messagebox.showerror(_("Error"), _("Texture file not found: {0}").format(selected_texture_path))
            return
        save_dir = filedialog.askdirectory(title=_("Select Folder to Save Texture"))
        if not save_dir:
            return
        try:
            destination = os.path.join(save_dir, os.path.basename(selected_texture_path))
            shutil.copy(selected_texture_path, destination)
            messagebox.showinfo(_("Success"), _("Texture copied to '{0}'.").format(destination))
        except Exception as e:
            messagebox.showerror(_("Error"), _("Failed to copy texture: {0}").format(e))

    def get_item_full_path(self, item_id):
        parts = []
        while item_id:
            item_text = self.projects_tree.item(item_id, "text")
            parts.insert(0, item_text)
            item_id = self.projects_tree.parent(item_id)
        return os.path.join(self.project_directory_path.get(), *parts)

    def _get_item_project_folder_path(self, item_id):
        parts = []
        while item_id:
            item_text = self.projects_tree.item(item_id, "text")
            parts.insert(0, item_text)
            item_id = self.projects_tree.parent(item_id)
        full_path = os.path.join(self.project_directory_path.get(), *parts)
        if os.path.isfile(full_path):
            return os.path.dirname(full_path)
        return full_path

    def _get_blend_version(self, file_path):
        try:
            with open(file_path, "rb") as f:
                header = f.read(12)
            if not header.startswith(b"BLENDER"):
                return _("4.2+")
            version_bytes = header[9:12]
            version_str = version_bytes.decode("ascii")
            if not version_str.isdigit():
                return _("Unknown")
            version_num = int(version_str)
            major = version_num // 100
            minor = version_num % 100
            return f"{major}.{minor}"
        except Exception as e:
            log.error(f"Error reading Blender version from {file_path}: {e}")
            return _("Compressed Format")

    def _save_project_directory(self, directory):
        config_file_path = os.path.join(get_paths_dir(), "project_directory.json")
        try:
            os.makedirs(os.path.dirname(config_file_path), exist_ok=True)
            with open(config_file_path, "w") as f:
                json.dump({"project_directory": directory}, f)
        except PermissionError:
            messagebox.showerror(
                _("Error"),
                _("Permission denied: Unable to save project directory. Please check your permissions.")
            )
        except Exception as e:
            messagebox.showerror(_("Error"), _("Failed to save project directory: {0}").format(e))

    def _load_project_directory(self):
        config_file_path = os.path.join(get_paths_dir(), "project_directory.json")
        default_project_dir = os.path.join(get_blender_manager_dir(), "Projects")
        try:
            with open(config_file_path, "r") as f:
                data = json.load(f)
            return data.get("project_directory", default_project_dir)
        except FileNotFoundError:
            os.makedirs(default_project_dir, exist_ok=True)
            return default_project_dir
        except Exception as e:
            messagebox.showerror(_("Error"), _("Failed to load project directory: {0}").format(e))
            return default_project_dir
