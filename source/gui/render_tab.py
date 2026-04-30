import os
import tkinter as tk
from datetime import datetime

import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from PIL import Image, ImageTk

from core import Logger, DataManager, ConfigManager, run_in_background, open_file_with_default_app
from i18n import _

log = Logger()


class RenderManagementTab:
    def __init__(self, app, notebook):
        self.app = app
        self.notebook = notebook
        self.config = ConfigManager()
        self.data = DataManager()

        self.frame = ttkb.Frame(self.notebook, padding=(10, 10, 10, 10))
        self.render_file_paths = {}
        self.current_render_name = None
        self.notes_data = self.data.load_notes()
        self.current_folder = self.data.get_render_folder_path()
        self._build_ui()
        self.refresh_render_list()

    def _build_ui(self):
        self.frame.columnconfigure(0, weight=1, minsize=150)
        self.frame.columnconfigure(1, weight=4, minsize=500)
        self.frame.rowconfigure(0, weight=1, minsize=300)
        self.frame.rowconfigure(1, weight=0, minsize=120)

        self._build_render_list()
        self._build_preview_area()
        self._build_notes_section()

    def _build_render_list(self):
        settings = self.config.get_all()
        bff = settings.get("button_font_family", "Segoe UI")
        tff = settings.get("treeview_font_family", "Segoe UI")

        left = ttkb.Frame(self.frame)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        ttkb.Label(left, text=_("Render List"), font=(bff, 14, "bold")).grid(
            row=0, column=0, sticky="w", padx=5, pady=(0, 5)
        )

        self.render_tree = ttkb.Treeview(
            left,
            columns=("File Size", "Resolution", "File Date"),
            show="tree headings", selectmode="browse",
        )
        self.render_tree.heading("#0", text=_("Name"), anchor="w")
        self.render_tree.column("#0", anchor="w", stretch=True, minwidth=150)
        self.render_tree.heading("File Size", text=_("File Size"), anchor="center")
        self.render_tree.column("File Size", anchor="center", stretch=True, minwidth=100)
        self.render_tree.heading("Resolution", text=_("Resolution"), anchor="center")
        self.render_tree.column("Resolution", anchor="center", stretch=True, minwidth=100)
        self.render_tree.heading("File Date", text=_("File Date"), anchor="center")
        self.render_tree.column("File Date", anchor="center", stretch=True, minwidth=150)
        self.render_tree.grid(row=1, column=0, sticky="nsew")

        sy = ttkb.Scrollbar(left, orient="vertical", command=self.render_tree.yview)
        self.render_tree.configure(yscroll=sy.set)
        sy.grid(row=1, column=1, sticky="ns")

        sx = ttkb.Scrollbar(left, orient="horizontal", command=self.render_tree.xview)
        self.render_tree.configure(xscroll=sx.set)
        sx.grid(row=2, column=0, sticky="ew")

        self.render_tree.bind("<<TreeviewSelect>>", self._on_select)

    def _build_preview_area(self):
        right = ttkb.Frame(self.frame)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=3)
        right.rowconfigure(1, weight=0)

        settings = self.config.get_all()
        bff = settings.get("button_font_family", "Segoe UI")

        ttkb.Label(right, text=_("Render Preview"), font=(bff, 14, "bold")).grid(
            row=0, column=0, sticky="w", padx=5, pady=(0, 5)
        )

        pframe = ttkb.Frame(right, relief="solid", borderwidth=0)
        pframe.grid(row=0, column=0, sticky="nsew")
        pframe.columnconfigure(0, weight=1)
        pframe.rowconfigure(0, weight=1)

        self.preview_label = ttkb.Label(pframe, text=_("No Preview Available"), anchor="center")
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        bframe = ttkb.Frame(right)
        bframe.grid(row=1, column=0, sticky="ew", padx=3, pady=(5, 0))
        bframe.columnconfigure((0, 1, 2, 3), weight=1, uniform="button")

        ttkb.Button(bframe, text=_("Open"), takefocus=False,
                     command=self.open_render).grid(row=0, column=0, sticky="nsew", padx=3)
        ttkb.Button(bframe, text=_("Refresh"), takefocus=False,
                     command=self.refresh_render_list).grid(row=0, column=1, sticky="nsew", padx=3)
        ttkb.Button(bframe, text=_("Browse"), takefocus=False,
                     command=self.browse_render_directory).grid(row=0, column=2, sticky="nsew", padx=3)
        ttkb.Button(bframe, text=_("Delete"), takefocus=False,
                     command=self.delete_render).grid(row=0, column=3, sticky="nsew", padx=3)

    def _build_notes_section(self):
        settings = self.config.get_all()
        bff = settings.get("button_font_family", "Segoe UI")

        nframe = ttkb.Frame(self.frame)
        nframe.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=(10, 0))
        nframe.columnconfigure(0, weight=1)
        nframe.rowconfigure(1, weight=1)

        ttkb.Label(nframe, text=_("Render Notes"), font=(bff, 14, "bold")).grid(
            row=0, column=0, sticky="w", padx=5, pady=(0, 5)
        )

        self.notes_text = tk.Text(nframe, height=4, wrap="word", font=(bff, 10))
        self.notes_text.grid(row=1, column=0, sticky="nsew", padx=5)

        ns = ttkb.Scrollbar(nframe, orient="vertical", command=self.notes_text.yview)
        self.notes_text.configure(yscrollcommand=ns.set)
        ns.grid(row=1, column=1, sticky="ns")

        ttkb.Button(nframe, text=_("Save Note"), takefocus=False,
                     command=self.save_current_note).grid(
            row=2, column=0, sticky="ew", padx=5, pady=(5, 0)
        )

    def refresh_render_list(self):
        self.render_tree.delete(*self.render_tree.get_children())
        self.render_file_paths.clear()
        if not self.current_folder or not os.path.exists(self.current_folder):
            return

        def add_items(parent, path):
            for name in sorted(os.listdir(path)):
                fpath = os.path.join(path, name)
                if os.path.isdir(fpath):
                    fid = self.render_tree.insert(
                        parent, "end", text=name, values=("", "", ""), tags=("folder",)
                    )
                    add_items(fid, fpath)
                elif name.lower().endswith((".png", ".jpeg", ".jpg", ".mp4")):
                    try:
                        stats = os.stat(fpath)
                        fdate = datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M")
                        fsize = f"{stats.st_size / (1024 * 1024):.2f} MB"
                        ext = os.path.splitext(name)[1].lower()
                        res = "N/A"
                        if ext in (".png", ".jpeg", ".jpg"):
                            with Image.open(fpath) as img:
                                res = f"{img.width}x{img.height}"
                        fid = self.render_tree.insert(
                            parent, "end", text=name,
                            values=(fsize, res, fdate), tags=("file",)
                        )
                        self.render_file_paths[fid] = fpath
                    except Exception as e:
                        log.error(f"Error processing {name}: {e}")

        root = self.render_tree.insert("", "end", text=os.path.basename(self.current_folder),
                                        open=True, tags=("folder",))
        add_items(root, self.current_folder)

        children = self.render_tree.get_children()
        if children:
            self.render_tree.selection_set(children[0])
            self.render_tree.focus(children[0])
            self.render_tree.event_generate("<<TreeviewSelect>>")

    def browse_render_directory(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title=_("Select Render Folder"))
        if folder:
            self.current_folder = folder
            self.data.save_render_folder_path(folder)
            self.refresh_render_list()

    def open_render(self):
        sel = self.render_tree.focus()
        if not sel:
            return
        fpath = self.render_file_paths.get(sel)
        if fpath and os.path.exists(fpath):
            open_file_with_default_app(fpath)

    def delete_render(self):
        from tkinter import messagebox
        sel = self.render_tree.focus()
        if not sel:
            return
        fpath = self.render_file_paths.get(sel)
        if fpath and os.path.exists(fpath):
            name = os.path.basename(fpath)
            if messagebox.askyesno(_("Confirm Delete"), _("Delete '{}'?").format(name)):
                os.remove(fpath)
                self.render_tree.delete(sel)
                self.render_file_paths.pop(sel, None)

    def _on_select(self, event):
        sel = self.render_tree.focus()
        if not sel:
            return
        fpath = self.render_file_paths.get(sel)
        if not fpath or not os.path.exists(fpath):
            self.preview_label.config(image="", text=_("No Preview Available"))
            return
        ext = os.path.splitext(fpath)[1].lower()
        if ext in (".jpeg", ".jpg", ".png"):
            self._display_image(fpath)
        elif ext == ".mp4":
            open_file_with_default_app(fpath)
        self.current_render_name = os.path.basename(fpath)
        self._load_note(self.current_render_name)

    def _display_image(self, fpath):
        try:
            img = Image.open(fpath)
            pw = max(self.preview_label.winfo_width(), 200)
            ph = max(self.preview_label.winfo_height(), 200)
            img.thumbnail((pw, ph), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.preview_label.config(image=photo, text="")
            self.preview_label.image = photo
        except Exception as e:
            log.error(f"Image display error: {e}")
            self.preview_label.config(image="", text=_("No Preview Available"))

    def _load_note(self, name):
        note = self.notes_data.get(name, "")
        self.notes_text.delete("1.0", tk.END)
        self.notes_text.insert(tk.END, note)

    def save_current_note(self):
        if not self.current_render_name:
            return
        note = self.notes_text.get("1.0", tk.END).strip()
        self.notes_data[self.current_render_name] = note
        self.data.save_notes(self.notes_data)
        from tkinter import messagebox
        messagebox.showinfo(_("Saved"), _("Note saved."))
