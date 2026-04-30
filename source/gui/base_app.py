import ctypes
import os
import platform
import sys
import time as time_module
import tkinter as tk

import ttkbootstrap as ttkb
from tkinterdnd2 import TkinterDnD


class _Redirector:
	def __init__(self, text_widget):
		self.text_widget = text_widget

	def write(self, text):
		self.text_widget.configure(state="normal")
		self.text_widget.insert("end", text)
		self.text_widget.see("end")
		self.text_widget.configure(state="disabled")

	def flush(self):
		pass

from core import (
	ConfigManager, Logger, DataManager,
	SafeTaskQueue, run_in_background, resource_path,
	ensure_dir, get_blender_manager_dir,
	get_blender_install_dir, get_blender_executable,
	get_blender_versions_dir, get_blender_config_path,
)
from core.exceptions import BlenderManagerError, PlatformError
from services import VersionService, UpdateService, NetworkService

from i18n import _

log = Logger()


class ACCENT_POLICY(ctypes.Structure):
	_fields_ = [
		("AccentState", ctypes.c_int),
		("Flags", ctypes.c_int),
		("GradientColor", ctypes.c_uint),
		("AnimationId", ctypes.c_int),
	]


class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
	_fields_ = [
		("Attribute", ctypes.c_int),
		("Data", ctypes.c_void_p),
		("SizeOfData", ctypes.c_size_t),
	]


def enable_dark_mode(hwnd):
	DWMWA_USE_IMMERSIVE_DARK_MODE = 20
	dark_mode = ctypes.c_int(1)
	ctypes.windll.dwmapi.DwmSetWindowAttribute(
		hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
		ctypes.byref(dark_mode), ctypes.sizeof(dark_mode)
	)


class BlenderManagerApp(TkinterDnD.Tk):
	def __init__(self):
		super().__init__()
		self._start_time = time_module.time()
		self.tray_name = _("Blender Manager")
		self._window_check_running = False

		self.config = ConfigManager()
		self.data = DataManager()
		self.version_service = VersionService()
		self.update_service = UpdateService()
		self.network = NetworkService()
		self.task_queue = SafeTaskQueue(self)

		self._setup_window()
		self._setup_platform_features()
		self.style = ttkb.Style()
		self._init_variables()
		self._init_services()
		self._schedule_startup()

		log.info(f"App initialized in {time_module.time() - self._start_time:.2f}s")

	def _setup_window(self):
		self.title(_("Blender Manager"))
		self.geometry("800x550")
		self.minsize(800, 550)
		self.maxsize(1920, 1080)
		self.protocol("WM_DELETE_WINDOW", self._on_closing)
		self.attributes("-fullscreen", False)
		icon_path = resource_path(os.path.join("Assets", "Images", "bmng.ico"))
		if os.path.exists(icon_path):
			self.iconbitmap(icon_path)

	def _setup_platform_features(self):
		if platform.system() == "Windows":
			self._setup_restore_hook()
			hwnd = ctypes.windll.user32.FindWindowW(None, "Blender Manager")
			if hwnd:
				enable_dark_mode(hwnd)

	def _setup_restore_hook(self):
		try:
			hwnd = self.winfo_id()
			self._restore_needed = False

			WndProc = ctypes.WINFUNCTYPE(
				ctypes.c_int, ctypes.c_void_p, ctypes.c_uint,
				ctypes.c_void_p, ctypes.c_void_p
			)
			GWLP_WNDPROC = -4
			original_proc = ctypes.windll.user32.GetWindowLongW(hwnd, GWLP_WNDPROC)
			original_proc = ctypes.c_void_p(original_proc)

			def new_proc(hwnd, msg, wparam, lparam):
				if msg == 0x0006 and wparam != 0:
					self._restore_needed = True
				return ctypes.windll.user32.CallWindowProcW(
					original_proc, hwnd, msg, wparam, lparam
				)

			self._window_proc_callback = WndProc(new_proc)
			ctypes.windll.user32.SetWindowLongW(
				hwnd, GWLP_WNDPROC, self._window_proc_callback
			)

			def _restore_all():
				if not self._restore_needed:
					return
				self._restore_needed = False
				try:
					SW_RESTORE = 9
					ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
					ctypes.windll.user32.SetForegroundWindow(hwnd)
					for w in self.winfo_children():
						if isinstance(w, tk.Toplevel):
							try:
								chwnd = w.winfo_id()
								ctypes.windll.user32.ShowWindow(chwnd, SW_RESTORE)
							except Exception:
								pass
				except Exception:
					pass

			def poll():
				_restore_all()
				self.after(300, poll)
			self.after(300, poll)
		except Exception as e:
			log.error(f"Failed to setup window hook: {e}")

	def _init_variables(self):
		self._cancel_events = {}
		self.base_install_dir = get_blender_manager_dir()
		self.blender_install_dir = get_blender_install_dir()
		self.current_folder = self.data.get_render_folder_path()
		self.current_render_name = None
		self.notes_data = self.data.load_notes()
		self.base_meshes = self.data.load_base_meshes()
		self.project_times = self.data.load_project_times()
		self.is_installing = False
		self._tray_icon = None
		settings = self.config.get_all()

		self.theme_choice = tk.StringVar(value=self.style.theme_use())
		self.available_themes = self._build_available_themes()
		self._apply_theme(settings.get("selected_theme", "darkly"))
		self._apply_custom_styles()

	def _build_available_themes(self):
		registered = set(self.style.theme_names())
		name_map = {
			"cosmo": _("Cosmo"), "flatly": _("Flatly"), "litera": _("Litera"),
			"minty": _("Minty"), "lumen": _("Lumen"), "sandstone": _("Sandstone"),
			"yeti": _("Yeti"), "pulse": _("Pulse"), "united": _("United"),
			"morph": _("Morph"), "journal": _("Journal"),
			"darkly": _("Darkly"), "superhero": _("Superhero"),
			"solar": _("Solar"), "cyborg": _("Cyborg"),
			"vapor": _("Vapor"), "simplex": _("Simplex"), "cerculean": _("Cerculean"),
		}
		return {name_map.get(t, t.capitalize()): t for t in registered}

	def _apply_theme(self, theme_name):
		if theme_name in self.style.theme_names():
			self.style.theme_use(theme_name)
		else:
			self.style.theme_use("darkly")
			self.config.save_setting("selected_theme", "darkly")
		self._apply_custom_styles()

	def _apply_custom_styles(self):
		settings = self.config.get_all()
		bff = settings.get("button_font_family", "Segoe UI")
		bfs = settings.get("button_font_size", 11)
		tff = settings.get("treeview_font_family", "Segoe UI")
		tfs = settings.get("treeview_font_size", 12)
		thfs = settings.get("treeview_heading_font_size", 10)

		self.style.configure("Custom.Large.TButton", font=(bff, bfs), padding=(10, 5))
		self.style.configure("Custom.Large.TLabel", font=(bff, 14), padding=(5, 2))
		self.style.configure("Custom.Small.TButton", font=(bff, 10), padding=(5, 2), borderwidth=0)
		self.style.configure("TNotebook.Tab", font=(bff, 10), padding=(10, 4))
		self.style.configure("Treeview", font=(tff, tfs), rowheight=28)
		self.style.configure("Treeview.Heading", font=(tff, thfs, "bold"))
		for s in ["TButton", "success.TButton", "primary.TButton",
				   "info.TButton", "danger.TButton", "secondary.TButton",
				   "warning.TButton", "light.TButton", "dark.TButton"]:
			self.style.configure(s, font=(bff, bfs))

	def _init_services(self):
		self._ensure_directories()
		self._ensure_default_files()

	def _ensure_directories(self):
		base = get_blender_manager_dir()
		dirs = ["BlenderVersions", "mngaddon", "paths", "renders", "addons", "Projects", "logs"]
		for d in dirs:
			ensure_dir(os.path.join(base, d))

	def _ensure_default_files(self):
		paths_dir = os.path.join(get_blender_manager_dir(), "paths")
		for fname in ["base_mesh_path.json", "project_directory.json",
					   "render_notes.json", "renderfolderpath.json"]:
			fpath = os.path.join(paths_dir, fname)
			if not os.path.exists(fpath):
				self.data.write_absolute_json(fpath, {})

	def _schedule_startup(self):
		self.after(100, self._init_ui)
		self.after(1000, self._start_window_visibility_check)
		self.after(3000, self._create_tray_icon)

	def _start_window_visibility_check(self):
		if not self._window_check_running:
			self._window_check_running = True
			self._check_window_visibility()

	def _check_window_visibility(self):
		try:
			if self.winfo_exists():
				current_state = self.state()
				if current_state == 'withdrawn':
					self._rebuild_main_window()
		except:
			pass
		self.after(500, self._check_window_visibility)

	def _init_ui(self):
		main_frame = ttkb.Frame(self, padding=0)
		main_frame.pack(expand=1, fill="both")
		self.notebook = ttkb.Notebook(main_frame)
		self.notebook.pack(expand=1, fill="both")

		self._create_main_menu_tab()
		self._create_management_tabs()
		self._create_logs_tab()

		self._post_init_checks()

	def _create_main_menu_tab(self):
		from gui.main_menu_tab import MainMenuTab
		frame = ttkb.Frame(self.notebook)
		self.notebook.add(frame, text=_("Main Menu"))
		self.notebook.select(frame)
		self.main_menu_tab = MainMenuTab(self, frame)

	def _create_management_tabs(self):
		vis = self.config.get_tab_visibility()
		if vis.get("Addon Management", True):
			from gui.addon_tab import AddonManagementTab
			self.addon_management_tab = AddonManagementTab(self, self.notebook)
			self.notebook.add(self.addon_management_tab.frame, text=_("Addon Management"))
		if vis.get("Project Management", True):
			from gui.project_tab import ProjectManagementTab
			self.project_management_tab = ProjectManagementTab(self, self.notebook)
			self.notebook.add(self.project_management_tab.frame, text=_("Project Management"))
		if vis.get("Render Management", True):
			from gui.render_tab import RenderManagementTab
			self.render_management_tab = RenderManagementTab(self, self.notebook)
			self.notebook.add(self.render_management_tab.frame, text=_("Render Management"))
		if vis.get("Version Management", True):
			from gui.version_tab import VersionManagementTab
			self.version_management_tab = VersionManagementTab(self, self.notebook)
			self.notebook.add(self.version_management_tab.frame, text=_("Version Management"))

	def _create_logs_tab(self):
		self.logs_tab = ttkb.Frame(self.notebook)
		self.notebook.add(self.logs_tab, text=_("Logs"))
		log_text = tk.Text(self.logs_tab, state="disabled", wrap="word",
						   font=("Consolas", 10))
		log_text.pack(fill="both", expand=True, padx=5, pady=5)
		sys.stdout = _Redirector(log_text)
		sys.stderr = _Redirector(log_text)

	def _post_init_checks(self):
		run_in_background(self._check_updates_background)
		if self.config.get("auto_update_checkbox", True):
			run_in_background(self._auto_update_blender)

	def _auto_update_blender(self):
		blender_exe = get_blender_executable()
		if not os.path.exists(blender_exe):
			return
		installed = self._get_installed_blender_version(blender_exe)
		if not installed:
			return
		from services.version_service import VersionService
		vs = VersionService()
		latest = vs.get_latest_blender_version()
		if not latest:
			return
		if vs.is_newer(installed, latest):
			log.info(f"Blender update available: {installed} -> {latest}")

	@staticmethod
	def _get_installed_blender_version(blender_exe):
		import subprocess, re
		try:
			startupinfo = None
			if os.name == "nt":
				startupinfo = subprocess.STARTUPINFO()
				startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
				startupinfo.wShowWindow = 0
			result = subprocess.run(
				[blender_exe, "--version"], stdout=subprocess.PIPE,
				text=True, startupinfo=startupinfo, timeout=15
			)
			version_line = result.stdout.splitlines()[0] if result.stdout else ""
			match = re.search(r"(\d+\.\d+(?:\.\d+)?)", version_line)
			return match.group(1) if match else None
		except Exception:
			return None

	def _check_updates_background(self):
		if self.config.get("bm_auto_update_checkbox", False):
			latest = self.update_service.check_bm_latest_version()
			current = self.config.get("version", "0.0.0")
			if latest and self.version_service.is_newer(current, latest):
				self.task_queue.put(lambda: self._notify_update(latest))

	def _notify_update(self, version):
		from tkinter import messagebox
		response = messagebox.askyesno(
			_("Update Available"),
			_(f"Blender Manager v{version} is available. Update now?")
		)
		if response:
			self._perform_update(version)

	def _perform_update(self, version):
		from services.update_service import UpdateService
		svc = UpdateService()
		current_os = platform.system().lower()
		os_map = {"windows": "windows", "darwin": "macos", "linux": "linux"}
		os_suffix = os_map.get(current_os)
		if not os_suffix:
			return
		url = f"https://github.com/verlorengest/BlenderManager/releases/download/v{version}/blender_manager_v{version}_{os_suffix}.zip"
		app_dir = os.getcwd()
		zip_path = os.path.join(app_dir, f"blender_manager_v{version}.zip")
		try:
			svc.download_file(url, zip_path)
			svc.run_updater(zip_path)
			os._exit(0)
		except Exception as e:
			log.error(f"Update failed: {e}")

	def _create_tray_icon(self):
		import pystray
		from PIL import Image
		icon_path = resource_path(os.path.join("Assets", "Images", "bmng.ico"))
		if not os.path.exists(icon_path):
			return
		image = Image.open(icon_path)
		self._tray_icon = pystray.Icon(
			"BlenderManager", image, _("Blender Manager"),
			self._create_tray_menu()
		)
		self._tray_icon.on_click = self._show_window
		self._tray_icon.run_detached()

	def _create_tray_menu(self):
		import pystray
		return pystray.Menu(
			pystray.MenuItem(_("Show Blender Manager"), lambda i, i2: self._show_window(), default=True),
			pystray.MenuItem(_("Exit"), self._exit_app),
		)

	def _show_window(self):
		try:
			if not self.winfo_exists():
				return
			self.deiconify()
			self.state('normal')
			self.lift()
			self.focus_force()
			self.update_idletasks()
			hwnd = self.winfo_id()
			ctypes.windll.user32.ShowWindow(hwnd, 9)
			ctypes.windll.user32.SetForegroundWindow(hwnd)
		except Exception as e:
			log.error(f"Show window failed: {e}")

	def _on_closing(self):
		if self.config.get("run_in_background", True):
			self.withdraw()
			log.info("Minimized to tray")
		else:
			self._exit_app(None, None)

	def _exit_app(self, icon, item):
		try:
			if self._tray_icon:
				self._tray_icon.stop()
		except Exception:
			pass
		os._exit(0)

	def bind_right_click(self, widget, callback):
		widget.bind("<Button-3>", callback)
		if platform.system() == "Darwin":
			widget.bind("<Button-2>", callback)
			widget.bind("<Control-Button-1>", callback)

	def center_window(self, window, width, height):
		x = self.winfo_x() + (self.winfo_width() // 2) - (width // 2)
		y = self.winfo_y() + (self.winfo_height() // 2) - (height // 2)
		window.geometry(f"+{x}+{y}")

	def _open_settings_window(self):
		from gui.windows import SettingsWindow
		SettingsWindow(self)

	def _open_help_window(self):
		from gui.windows import HelpWindow
		HelpWindow(self)

	def _open_create_project_window(self):
		from gui.windows import ProjectWindow
		ProjectWindow(self)

	def update_recent_projects(self):
		if hasattr(self, "main_menu_tab"):
			self.main_menu_tab.refresh_projects()

	def refresh_recent_projects(self):
		self.update_recent_projects()

	def update_blender_version_label(self):
		if hasattr(self, "main_menu_tab"):
			self.main_menu_tab._update_blender_version_label()

	def run_automatic_addon_setup(self):
		log.info("Automatic addon setup triggered after Blender installation.")
