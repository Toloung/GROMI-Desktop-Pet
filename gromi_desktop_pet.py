# -*- coding: utf-8 -*-
"""GROMI: a Windows taskbar companion using the Codex v2 pet atlas."""

import ctypes
import json
import os
import queue
import random
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import Menu, messagebox, simpledialog

from PIL import Image, ImageTk
import pystray


PET_NAME = "GROMI"
ASSET_NAME = "gromi_spritesheet.webp"
DEFAULT_SCALE = 0.46
TRANSPARENT_COLOR = "#ff00ff"
ANIMATION_MS = 100
MOVE_MS = 30
MOVE_SPEED = 2
CONFIG_PATH = Path(os.environ.get("APPDATA", Path.home())) / "GROMI Desktop Pet" / "settings.json"
MUTEX_NAME = "Local\\GROMI_Desktop_Pet_Single_Instance"
ACTIVITY_LEVELS = {
    "calm": ("安静", (28, 44)),
    "normal": ("普通", (16, 30)),
    "active": ("活泼", (8, 16)),
}
TASKBAR_START_MARGIN = 96
TASKBAR_TRAY_MARGIN = 220

WEATHER_CODES = {
    0: "晴朗", 1: "大致晴朗", 2: "局部多云", 3: "阴天", 45: "有雾", 48: "雾凇",
    51: "毛毛雨", 53: "小雨", 55: "较强毛毛雨", 56: "冻毛毛雨", 57: "强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "冰粒", 80: "阵雨", 81: "较强阵雨",
    82: "强阵雨", 85: "阵雪", 86: "强阵雪", 95: "雷暴", 96: "冰雹雷暴", 99: "强冰雹雷暴",
}
STATE_NAMES = {
    "idle": "休息", "walking": "巡逻", "wave": "挥手", "jump": "跳跃",
    "waiting": "等待", "working": "专注工作", "review": "检查", "failed": "沮丧",
}
class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def resource_path(name):
    return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), name)


def acquire_single_instance():
    """Return a mutex handle, or None when another GROMI is already running."""
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.kernel32.CloseHandle(mutex)
        return None
    return mutex


def notify_existing_instance():
    """Show a visible hint when the windowed app exits because GROMI is already running."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    messagebox.showinfo("GROMI 已在运行", "GROMI 已经在运行啦。\n如果没有看到它，请检查系统托盘。", parent=root)
    root.destroy()


class GromiPet:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(PET_NAME)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", TRANSPARENT_COLOR)
        self.root.configure(bg=TRANSPARENT_COLOR)

        self.config = self.load_config()
        self.mode = self.config.get("mode", "taskbar")
        self.desktop_scale = float(self.config.get("desktop_scale", self.config.get("scale", DEFAULT_SCALE)))
        self.scale = self.desktop_scale
        self.city = self.config.get("city", "")
        self.weather_enabled = bool(self.config.get("weather_enabled", True))
        self.guard_mode = bool(self.config.get("guard_mode", False))
        self.always_on_top = bool(self.config.get("always_on_top", True))
        self.peek_mode = bool(self.config.get("peek_mode", False))
        self.activity_level = self.config.get("activity_level", "normal")
        if self.activity_level not in ACTIVITY_LEVELS:
            self.activity_level = "normal"
        self.weather_refresh_minutes = int(self.config.get("weather_refresh_minutes", 10))
        self.weather_refresh_minutes = max(5, min(60, self.weather_refresh_minutes))
        self.taskbar_hosted = False
        self.taskbar_hwnd = 0
        self.taskbar_width = 0
        self.taskbar_height = 0
        self.taskbar_left = 0
        self.taskbar_top = 0
        self.next_taskbar_check = 0.0
        self.state = "idle"
        self.direction = "right"
        self.frame_index = 0
        self.action_until = 0.0
        self.next_activity_at = float("inf") if self.guard_mode else time.monotonic() + self.next_activity_delay()
        self.dragging = False
        self.did_drag = False
        self.drag_offset = (0, 0)
        self.press_position = None
        self.hover_job = None
        self.hide_hover_job = None
        self.hover_card = None
        self.info_card = None
        self.weather_loading = False
        self.weather_request_id = 0
        self.weather_queue = queue.Queue()
        self.ui_queue = queue.Queue()
        self.tray_icon = None
        self.settings_window = None
        self.visible = True
        self.weather = {"title": "天气未设置", "detail": "右键 GROMI → 设置城市", "tip": "提示：设置城市后会显示天气。", "updated": ""}

        self.load_sprites()
        self.set_render_scale(self.scale)
        self.update_screen_metrics()
        self.x = self.screen_w // 2 - self.pet_w // 2
        self.y = self.screen_h - self.pet_h - 84
        self.last_geometry = None
        self.vx = MOVE_SPEED
        self.walk_ticks = 0
        self.walk_limit = random.randint(440, 820)

        self.label = tk.Label(self.root, bg=TRANSPARENT_COLOR, bd=0, cursor="hand2")
        self.label.pack()
        self.label.bind("<Button-1>", self.on_press)
        self.label.bind("<B1-Motion>", self.on_drag)
        self.label.bind("<ButtonRelease-1>", self.on_release)
        self.label.bind("<Button-3>", self.on_menu)
        self.label.bind("<Enter>", self.on_enter)
        self.label.bind("<Leave>", self.on_leave)
        self.label.bind("<MouseWheel>", self.on_wheel)

        self.menu = Menu(self.root, tearoff=0)
        self.set_mode(self.mode, persist=False)
        self.start_tray_icon()
        self.refresh_weather()
        self.refresh()
        self.animate()
        self.move_loop()
        self.root.after(150, self.process_weather_queue)
        self.root.after(100, self.process_ui_queue)

    def load_config(self):
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {"mode": "taskbar", "desktop_scale": DEFAULT_SCALE, "city": "", "weather_enabled": True,
                    "guard_mode": False, "always_on_top": True, "peek_mode": False,
                    "activity_level": "normal", "weather_refresh_minutes": 10}

    def save_config(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps({
            "mode": self.mode, "desktop_scale": self.desktop_scale, "city": self.city,
            "weather_enabled": self.weather_enabled, "guard_mode": self.guard_mode,
            "always_on_top": self.always_on_top, "peek_mode": self.peek_mode,
            "activity_level": self.activity_level,
            "weather_refresh_minutes": self.weather_refresh_minutes,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def next_activity_delay(self):
        _, delay_range = ACTIVITY_LEVELS.get(self.activity_level, ACTIVITY_LEVELS["normal"])
        return random.uniform(*delay_range)

    def activity_label(self):
        return ACTIVITY_LEVELS.get(self.activity_level, ACTIVITY_LEVELS["normal"])[0]

    def weather_refresh_seconds(self):
        return max(5, min(60, self.weather_refresh_minutes)) * 60

    def update_screen_metrics(self):
        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()

    def set_render_scale(self, scale):
        self.scale = scale
        self.pet_w = max(28, int(self.cell_w * self.scale))
        self.pet_h = max(30, int(self.cell_h * self.scale))

    def get_taskbar(self):
        try:
            hwnd = int(ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None))
            rect = RECT()
            if hwnd and ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return hwnd, rect
        except (AttributeError, OSError):
            pass
        return 0, None

    def taskbar_is_horizontal(self, rect):
        return rect and (rect.right - rect.left) >= (rect.bottom - rect.top)

    def taskbar_patrol_bounds(self):
        left = self.taskbar_left + TASKBAR_START_MARGIN
        right = self.taskbar_left + self.taskbar_width - TASKBAR_TRAY_MARGIN
        if right - left < self.pet_w + 40:
            left = self.taskbar_left
            right = self.taskbar_left + self.taskbar_width
        return left, right

    def is_peeking(self):
        return self.taskbar_hosted and self.guard_mode and self.peek_mode

    def visible_pet_h(self):
        if self.is_peeking():
            return max(28, int(self.pet_h * 0.52))
        return self.pet_h

    def fit_taskbar_size(self):
        taskbar_scale = max(0.14, min(0.30, (self.taskbar_height - 6) / self.cell_h))
        self.set_render_scale(taskbar_scale)
        visible_h = self.visible_pet_h()
        # Explorer can clip external child windows behind the Windows 11 taskbar.
        # Dock as a transparent top-level companion instead, using the same lane.
        if self.taskbar_top > self.screen_h // 2:
            self.y = max(0, self.taskbar_top - visible_h + 5)
        else:
            self.y = min(self.screen_h - visible_h, self.taskbar_top + self.taskbar_height - 5)
        left, right = self.taskbar_patrol_bounds()
        self.x = max(left, min(self.x, right - self.pet_w))

    def host_in_taskbar(self):
        hwnd, rect = self.get_taskbar()
        if not hwnd or not self.taskbar_is_horizontal(rect):
            return False
        self.taskbar_hwnd = hwnd
        self.taskbar_left = rect.left
        self.taskbar_top = rect.top
        self.taskbar_width = rect.right - rect.left
        self.taskbar_height = rect.bottom - rect.top
        # 任务栏模式是一个贴着任务栏上缘的独立透明窗口。始终置前，避免被
        # Explorer 的任务栏遮住；“置顶”开关只影响普通桌面模式。
        self.root.attributes("-topmost", True)
        self.taskbar_hosted = True
        self.fit_taskbar_size()
        return True

    def sync_taskbar(self, now):
        """Poll Explorer at a low rate; the position normally changes rarely."""
        if not self.taskbar_hosted or now < self.next_taskbar_check:
            return
        self.next_taskbar_check = now + 1.0
        _, rect = self.get_taskbar()
        if not rect or not self.taskbar_is_horizontal(rect):
            return
        current = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
        previous = (self.taskbar_left, self.taskbar_top, self.taskbar_width, self.taskbar_height)
        if current != previous:
            self.taskbar_left, self.taskbar_top, self.taskbar_width, self.taskbar_height = current
            self.fit_taskbar_size()

    def leave_taskbar(self):
        if not self.taskbar_hosted:
            return
        self.root.attributes("-topmost", self.always_on_top)
        self.taskbar_hosted = False
        self.set_render_scale(self.desktop_scale)

    def tray_image(self):
        """Make a compact, crisp tray icon from GROMI's idle frame."""
        frame = self.frames["idle"][0].copy()
        frame.thumbnail((64, 64), Image.Resampling.LANCZOS)
        icon = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        icon.alpha_composite(frame, ((64 - frame.width) // 2, (64 - frame.height) // 2))
        return icon

    def enqueue_ui(self, action):
        # pystray runs on its own thread. Tkinter must only be touched on Tk's thread.
        self.ui_queue.put(action)

    def start_tray_icon(self):
        try:
            menu = pystray.Menu(
                pystray.MenuItem("显示 / 隐藏 GROMI", lambda _i, _m: self.enqueue_ui("toggle_visibility"), default=True),
                pystray.MenuItem("任务栏巡逻", lambda _i, _m: self.enqueue_ui("taskbar"),
                                 checked=lambda _m: self.taskbar_hosted),
                pystray.MenuItem("守护模式", lambda _i, _m: self.enqueue_ui("guard"),
                                 checked=lambda _m: self.guard_mode),
                pystray.MenuItem("设置…", lambda _i, _m: self.enqueue_ui("settings")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", lambda _i, _m: self.enqueue_ui("quit")),
            )
            self.tray_icon = pystray.Icon("GROMI", self.tray_image(), "GROMI 桌面宠物", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception:
            # The pet itself remains usable when a restrictive Windows environment
            # prevents the notification-area icon from being created.
            self.tray_icon = None

    def process_ui_queue(self):
        try:
            while True:
                action = self.ui_queue.get_nowait()
                if action == "toggle_visibility":
                    self.toggle_visibility()
                elif action == "taskbar":
                    self.set_mode("desktop" if self.taskbar_hosted else "taskbar")
                elif action == "guard":
                    self.toggle_guard()
                elif action == "settings":
                    self.show_settings()
                elif action == "quit":
                    self.close()
                    return
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(100, self.process_ui_queue)

    def toggle_visibility(self):
        if self.visible:
            self.hide_hover_card()
            if self.info_card:
                self.info_card.destroy()
                self.info_card = None
            self.root.withdraw()
            self.visible = False
        else:
            self.root.deiconify()
            self.root.attributes("-topmost", True if self.taskbar_hosted else self.always_on_top)
            self.visible = True
            self.last_geometry = None
            self.refresh()

    def startup_script_path(self):
        startup_dir = Path(os.environ.get("APPDATA", Path.home())) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        return startup_dir / "GROMI Desktop Pet.vbs"

    def startup_command(self):
        if getattr(sys, "frozen", False):
            return f'"{Path(sys.executable)}"'
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        interpreter = pythonw if pythonw.exists() else Path(sys.executable)
        return f'"{interpreter}" "{Path(__file__).resolve()}"'

    def startup_enabled(self):
        return self.startup_script_path().exists()

    def set_startup_enabled(self, enabled):
        path = self.startup_script_path()
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            command = self.startup_command().replace('"', '""')
            path.write_text(
                'Set WshShell = CreateObject("WScript.Shell")\n'
                f'WshShell.Run "{command}", 0, False\n',
                encoding="utf-8",
            )
        elif path.exists():
            path.unlink()

    def show_settings(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            return

        window = tk.Toplevel(self.root)
        self.settings_window = window
        window.title("GROMI 设置")
        window.configure(bg="#FFF8EE")
        window.resizable(False, False)
        window.attributes("-topmost", True)
        window.geometry("410x620")
        window.minsize(410, 620)

        body = tk.Frame(window, bg="#FFF8EE", padx=16, pady=14)
        body.pack(fill="both", expand=True)
        title = tk.Label(body, text="GROMI 设置", bg="#FFF8EE", fg="#55436F",
                         font=("Microsoft YaHei UI", 12, "bold"))
        title.pack(anchor="w")
        tk.Label(body, text="轻轻调一调，GROMI 就按你的节奏活动。", bg="#FFF8EE", fg="#786A7B",
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(2, 10))

        def add_section(text):
            tk.Label(body, text=text, bg="#FFF8EE", fg="#55436F",
                     font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w", pady=(8, 3))

        def add_hint(text):
            tk.Label(body, text=text, bg="#FFF8EE", fg="#A08D9B",
                     font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(2, 0))

        add_section("模式")
        mode_var = tk.StringVar(value="taskbar" if self.taskbar_hosted else "desktop")
        mode_row = tk.Frame(body, bg="#FFF8EE")
        mode_row.pack(fill="x")
        tk.Radiobutton(mode_row, text="任务栏巡逻", value="taskbar", variable=mode_var,
                       bg="#FFF8EE", activebackground="#FFF8EE", selectcolor="#FFF8EE").pack(side="left")
        tk.Radiobutton(mode_row, text="普通桌面", value="desktop", variable=mode_var,
                       bg="#FFF8EE", activebackground="#FFF8EE", selectcolor="#FFF8EE").pack(side="left", padx=(14, 0))
        add_hint("任务栏模式会自动缩小，并避开开始菜单和系统托盘区域。")

        guard_var = tk.BooleanVar(value=self.guard_mode)
        peek_var = tk.BooleanVar(value=self.peek_mode)
        weather_var = tk.BooleanVar(value=self.weather_enabled)
        top_var = tk.BooleanVar(value=self.always_on_top)
        startup_var = tk.BooleanVar(value=self.startup_enabled())
        activity_var = tk.StringVar(value=self.activity_level)
        refresh_var = tk.StringVar(value=str(self.weather_refresh_minutes))

        add_section("行为")
        tk.Checkbutton(body, text="守护模式（固定不动）", variable=guard_var,
                       bg="#FFF8EE", activebackground="#FFF8EE", selectcolor="#FFF8EE").pack(anchor="w")
        tk.Checkbutton(body, text="任务栏守护时只露头", variable=peek_var,
                       bg="#FFF8EE", activebackground="#FFF8EE", selectcolor="#FFF8EE").pack(anchor="w")
        tk.Checkbutton(body, text="开机自动启动", variable=startup_var,
                       bg="#FFF8EE", activebackground="#FFF8EE", selectcolor="#FFF8EE").pack(anchor="w")
        tk.Checkbutton(body, text="悬停 3 秒显示天气", variable=weather_var,
                       bg="#FFF8EE", activebackground="#FFF8EE", selectcolor="#FFF8EE").pack(anchor="w")

        activity_row = tk.Frame(body, bg="#FFF8EE")
        activity_row.pack(fill="x", pady=(4, 0))
        tk.Label(activity_row, text="动作频率：", bg="#FFF8EE", fg="#786A7B").pack(side="left")
        for value, (label, _delay) in ACTIVITY_LEVELS.items():
            tk.Radiobutton(activity_row, text=label, value=value, variable=activity_var,
                           bg="#FFF8EE", activebackground="#FFF8EE", selectcolor="#FFF8EE").pack(side="left")

        add_section("显示")
        tk.Checkbutton(body, text="普通桌面时置顶", variable=top_var,
                       bg="#FFF8EE", activebackground="#FFF8EE", selectcolor="#FFF8EE").pack(anchor="w")

        size_row = tk.Frame(body, bg="#FFF8EE")
        size_row.pack(fill="x", pady=(4, 0))
        size_var = tk.StringVar(value=f"普通桌面大小：{int(self.desktop_scale * 100)}%")

        def adjust_desktop_size(step):
            self.zoom(step)
            size_var.set(f"普通桌面大小：{int(self.desktop_scale * 100)}%")

        tk.Label(size_row, textvariable=size_var, bg="#FFF8EE", fg="#786A7B").pack(side="left")
        tk.Button(size_row, text="－", command=lambda: adjust_desktop_size(-0.05), bg="#E8DEF8", relief="flat", width=3).pack(side="right")
        tk.Button(size_row, text="＋", command=lambda: adjust_desktop_size(0.05), bg="#E8DEF8", relief="flat", width=3).pack(side="right", padx=(0, 4))

        add_section("天气")
        city_var = tk.StringVar(value=f"天气城市：{self.city if self.city else '未设置城市'}")
        city_row = tk.Frame(body, bg="#FFF8EE")
        city_row.pack(fill="x")
        tk.Label(city_row, textvariable=city_var, bg="#FFF8EE", fg="#786A7B").pack(side="left")

        def change_city():
            self.set_city()
            city_var.set(f"天气城市：{self.city if self.city else '未设置城市'}")

        tk.Button(city_row, text="修改", command=change_city, bg="#F4E7D5", relief="flat", padx=8).pack(side="right")

        refresh_row = tk.Frame(body, bg="#FFF8EE")
        refresh_row.pack(fill="x", pady=(5, 0))
        tk.Label(refresh_row, text="刷新间隔：", bg="#FFF8EE", fg="#786A7B").pack(side="left")
        tk.OptionMenu(refresh_row, refresh_var, "5", "10", "30", "60").pack(side="left")
        tk.Label(refresh_row, text="分钟", bg="#FFF8EE", fg="#786A7B").pack(side="left", padx=(4, 0))

        saved_label = tk.Label(body, text="", bg="#FFF8EE", fg="#62835F", font=("Microsoft YaHei UI", 9, "bold"))
        saved_label.pack(anchor="w", pady=(10, 2))

        def save_settings():
            desired_guard = bool(guard_var.get())
            desired_weather = bool(weather_var.get())
            desired_topmost = bool(top_var.get())
            desired_startup = bool(startup_var.get())
            desired_mode = mode_var.get()
            desired_peek = bool(peek_var.get())
            desired_activity = activity_var.get() if activity_var.get() in ACTIVITY_LEVELS else "normal"
            desired_refresh_minutes = max(5, min(60, int(refresh_var.get())))
            try:
                if desired_guard != self.guard_mode:
                    self.toggle_guard()
                if desired_peek != self.peek_mode:
                    self.peek_mode = desired_peek
                    self.last_geometry = None
                    if self.taskbar_hosted:
                        self.fit_taskbar_size()
                    self.refresh()
                if desired_weather != self.weather_enabled:
                    self.toggle_weather()
                if desired_topmost != self.always_on_top:
                    self.always_on_top = desired_topmost
                    self.root.attributes("-topmost", True if self.taskbar_hosted else self.always_on_top)
                if desired_activity != self.activity_level:
                    self.activity_level = desired_activity
                    if not self.guard_mode:
                        self.next_activity_at = time.monotonic() + self.next_activity_delay()
                if desired_refresh_minutes != self.weather_refresh_minutes:
                    self.weather_refresh_minutes = desired_refresh_minutes
                if desired_startup != self.startup_enabled():
                    self.set_startup_enabled(desired_startup)
                if desired_mode != ("taskbar" if self.taskbar_hosted else "desktop"):
                    self.set_mode(desired_mode)
                self.save_config()
                if self.tray_icon:
                    self.tray_icon.update_menu()
                saved_label.configure(text="已保存 ✓")
            except OSError as error:
                saved_label.configure(text=f"保存失败：{error}")

        def close_settings():
            self.settings_window = None
            window.destroy()

        tk.Button(body, text="保存设置", command=save_settings, bg="#D6C2F3", fg="#4D3A67",
                  relief="flat", padx=10, pady=4).pack(anchor="e", pady=(0, 1))
        window.protocol("WM_DELETE_WINDOW", close_settings)

    def set_mode(self, mode, persist=True):
        self.update_screen_metrics()
        if mode == "taskbar":
            if self.host_in_taskbar():
                self.mode = "taskbar"
            else:
                self.mode = "desktop"
                self.root.attributes("-topmost", self.always_on_top)
        else:
            self.leave_taskbar()
            self.mode = "desktop"
            self.root.attributes("-topmost", self.always_on_top)
            self.set_render_scale(self.desktop_scale)
            self.x = max(0, min(self.x, self.screen_w - self.pet_w))
            self.y = max(0, min(self.y, self.screen_h - self.pet_h))
        if persist:
            self.save_config()
        self.refresh()

    def load_sprites(self):
        sheet = Image.open(resource_path(ASSET_NAME)).convert("RGBA")
        if sheet.size != (1536, 2288):
            raise ValueError(f"Expected a 1536x2288 v2 spritesheet, got {sheet.size}")
        self.cell_w, self.cell_h = 192, 208

        def row(index, count):
            return [sheet.crop((col * self.cell_w, index * self.cell_h,
                                (col + 1) * self.cell_w, (index + 1) * self.cell_h))
                    for col in range(count)]

        self.frames = {
            "idle": row(0, 6), "right": row(1, 8), "left": row(2, 8),
            "wave": row(3, 4), "jump": row(4, 5), "failed": row(5, 8),
            "waiting": row(6, 6), "working": row(7, 6), "review": row(8, 6),
        }

    def active_frames(self):
        return self.frames[self.direction] if self.state == "walking" else self.frames.get(self.state, self.frames["idle"])

    def current_frame(self):
        frame = self.active_frames()[self.frame_index % len(self.active_frames())]
        frame = frame.resize((self.pet_w, self.pet_h), Image.Resampling.LANCZOS).convert("RGBA")
        if self.is_peeking():
            frame = frame.crop((0, 0, self.pet_w, self.visible_pet_h()))
        mask = frame.getchannel("A").point(lambda value: 255 if value >= 160 else 0)
        keyed = Image.new("RGBA", frame.size, (255, 0, 255, 255))
        keyed.paste(frame, mask=mask)
        return ImageTk.PhotoImage(keyed.convert("RGB"))

    def update_geometry(self):
        geometry = f"{self.pet_w}x{self.visible_pet_h()}+{int(self.x)}+{int(self.y)}"
        if geometry != self.last_geometry:
            self.root.geometry(geometry)
            self.last_geometry = geometry

    def refresh(self):
        self.update_geometry()
        self.photo = self.current_frame()
        self.label.configure(image=self.photo)

    def animate(self):
        self.frame_index += 1
        self.refresh()
        self.root.after(ANIMATION_MS, self.animate)

    def play_action(self, state, duration):
        if self.dragging or self.guard_mode:
            return
        self.state = state
        self.frame_index = 0
        self.action_until = time.monotonic() + duration
        self.next_activity_at = self.action_until + self.next_activity_delay()

    def start_walking(self):
        if self.guard_mode:
            return
        self.state = "walking"
        self.frame_index = 0
        self.walk_ticks = 0
        if self.activity_level == "calm":
            self.walk_limit = random.randint(260, 420)
        elif self.activity_level == "active":
            self.walk_limit = random.randint(620, 980)
        else:
            self.walk_limit = random.randint(440, 820)
        self.direction = random.choice(["left", "right"])
        self.vx = MOVE_SPEED if self.direction == "right" else -MOVE_SPEED

    def choose_activity(self):
        if self.guard_mode:
            return
        if self.taskbar_hosted:
            activities = [
                ("walking", 0), ("walking", 0), ("walking", 0), ("waiting", 3.5),
                ("working", 5.5), ("review", 4.3),
            ]
        else:
            activities = [
                ("walking", 0), ("walking", 0), ("walking", 0), ("waiting", 3.5),
                ("working", 5.5), ("review", 4.3), ("wave", 2.0), ("jump", 1.6), ("failed", 3.0),
            ]
        choice, duration = random.choice(activities)
        if choice == "walking":
            self.start_walking()
        else:
            self.play_action(choice, duration)

    def move_loop(self):
        now = time.monotonic()
        if self.guard_mode:
            self.state = "idle"
            self.frame_index = 0
        elif not self.dragging:
            self.update_screen_metrics()
            if self.taskbar_hosted:
                self.sync_taskbar(now)
                left_boundary, boundary = self.taskbar_patrol_bounds()
            else:
                left_boundary, boundary = 0, self.screen_w
            if self.state == "walking":
                self.x += self.vx
                self.walk_ticks += 1
                if self.x <= left_boundary or self.x + self.pet_w >= boundary:
                    self.x = max(left_boundary, min(self.x, boundary - self.pet_w))
                    self.vx = -self.vx
                    self.direction = "right" if self.vx > 0 else "left"
                elif self.walk_ticks >= self.walk_limit:
                    self.state = "idle"
                    self.frame_index = 0
                    self.next_activity_at = now + self.next_activity_delay()
            elif self.state != "idle" and now >= self.action_until:
                self.state = "idle"
                self.frame_index = 0
            elif self.state == "idle" and now >= self.next_activity_at:
                self.choose_activity()
        self.update_geometry()
        self.root.after(MOVE_MS, self.move_loop)

    def on_press(self, event):
        self.press_position = (event.x_root, event.y_root)
        self.drag_offset = (event.x, event.y)
        self.did_drag = False

    def on_drag(self, event):
        if self.guard_mode:
            return
        if not self.press_position:
            return
        moved = abs(event.x_root - self.press_position[0]) + abs(event.y_root - self.press_position[1])
        if moved > 6:
            self.dragging = self.did_drag = True
            if self.taskbar_hosted:
                self.x = self.root.winfo_pointerx() - self.drag_offset[0]
                self.fit_taskbar_size()
            else:
                self.mode = "desktop"
                self.x = self.root.winfo_pointerx() - self.drag_offset[0]
                self.y = self.root.winfo_pointery() - self.drag_offset[1]
            self.refresh()

    def on_release(self, _event):
        if not self.did_drag and not self.guard_mode and not self.taskbar_hosted:
            self.play_action("wave", 2.0)
        self.dragging = False
        self.press_position = None
        self.save_config()

    def menu_status(self):
        location = "任务栏贴边巡逻（已开启）" if self.taskbar_hosted else "普通桌面模式"
        weather = f"天气：{'开启' if self.weather_enabled else '关闭'} · {self.city if self.city else '未设置城市'}"
        guard = "守护模式：开启（固定不动）" if self.guard_mode else "守护模式：关闭"
        peek = "只露头：开启" if self.peek_mode else "只露头：关闭"
        startup = f"开机启动：{'开启' if self.startup_enabled() else '关闭'}"
        activity = f"动作频率：{self.activity_label()}"
        topmost = f"置顶：{'开启' if self.always_on_top else '关闭'}"
        size = "任务栏高度自动适配" if self.taskbar_hosted else f"桌面大小：{int(self.desktop_scale * 100)}%"
        return (
            f"当前：{location} · {STATE_NAMES.get(self.state, '休息')}",
            weather,
            f"{guard} · {peek}",
            f"{activity} · {startup}",
            f"{topmost} · {size}",
        )

    def rebuild_menu(self):
        self.menu.delete(0, "end")
        for status in self.menu_status():
            self.menu.add_command(label=status, state="disabled")
        self.menu.add_separator()
        self.menu.add_command(label="切换到普通桌面" if self.taskbar_hosted else "切换到任务栏巡逻",
                              command=lambda: self.set_mode("desktop" if self.taskbar_hosted else "taskbar"))
        self.menu.add_command(label="隐藏到系统托盘" if self.visible else "从系统托盘显示", command=self.toggle_visibility)
        self.menu.add_command(label=("✓ " if self.guard_mode else "") + "守护模式（固定不动）", command=self.toggle_guard)
        self.menu.add_command(label="设置…", command=self.show_settings)
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=self.close)

    def on_menu(self, event):
        self.hide_hover_card()
        self.rebuild_menu()
        self.menu.tk_popup(event.x_root, event.y_root)

    def on_enter(self, _event):
        if not self.weather_enabled or not self.city:
            return
        if self.hide_hover_job:
            self.root.after_cancel(self.hide_hover_job)
        self.hover_job = self.root.after(3000, self.show_hover_card)

    def on_leave(self, _event):
        if self.hover_job:
            self.root.after_cancel(self.hover_job)
            self.hover_job = None
        self.hide_hover_job = self.root.after(280, self.hide_hover_card)

    def card_enter(self, _event):
        if self.hide_hover_job:
            self.root.after_cancel(self.hide_hover_job)

    def card_leave(self, _event):
        self.hide_hover_job = self.root.after(280, self.hide_hover_card)

    def on_wheel(self, event):
        if not self.taskbar_hosted:
            self.zoom(0.05 if event.delta > 0 else -0.05)

    def toggle_weather(self):
        self.weather_enabled = not self.weather_enabled
        if not self.weather_enabled:
            self.hide_hover_card()
        self.save_config()

    def toggle_guard(self):
        self.guard_mode = not self.guard_mode
        if self.guard_mode:
            self.state = "idle"
            self.frame_index = 0
            self.action_until = 0.0
            self.next_activity_at = float("inf")
        else:
            self.next_activity_at = time.monotonic() + self.next_activity_delay()
        self.last_geometry = None
        if self.taskbar_hosted:
            self.fit_taskbar_size()
        self.refresh()
        self.save_config()

    def toggle_always_on_top(self):
        self.always_on_top = not self.always_on_top
        # Taskbar mode remains above Explorer even when desktop-mode topmost is off.
        self.root.attributes("-topmost", True if self.taskbar_hosted else self.always_on_top)
        self.save_config()

    def weather_tip(self, title, apparent_temperature=None):
        if "雨" in title:
            return "提示：出门记得带伞。"
        if "雪" in title:
            return "提示：路滑，慢慢走。"
        if "雷" in title:
            return "提示：先躲进安全的地方。"
        try:
            temp = float(apparent_temperature)
        except (TypeError, ValueError):
            temp = None
        if temp is not None and temp >= 32:
            return "提示：今天适合补水和少晒太阳。"
        if temp is not None and temp <= 8:
            return "提示：多穿一点，别被风偷袭。"
        if "晴" in title:
            return "提示：今天适合散步，也适合摸鱼。"
        return "提示：保持好心情。"

    def draw_bubble(self, canvas, x1, y1, x2, y2, radius, fill, outline, tail="bottom-left"):
        if tail == "bottom-right":
            points = (x2 - 52, y2 - 2, x2 - 32, y2 - 2, x2 - 37, y2 + 12)
        else:
            points = (x1 + 32, y2 - 2, x1 + 52, y2 - 2, x1 + 37, y2 + 12)
        canvas.create_polygon(points, fill=fill, outline=outline, width=2)
        canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, fill=fill, outline="")
        canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius, fill=fill, outline="")
        for left, top, right, bottom, start in (
            (x1, y1, x1 + radius * 2, y1 + radius * 2, 90),
            (x2 - radius * 2, y1, x2, y1 + radius * 2, 0),
            (x2 - radius * 2, y2 - radius * 2, x2, y2, 270),
            (x1, y2 - radius * 2, x1 + radius * 2, y2, 180),
        ):
            canvas.create_arc(left, top, right, bottom, start=start, extent=90,
                              style="pieslice", fill=fill, outline="")
            canvas.create_arc(left, top, right, bottom, start=start, extent=90,
                              style="arc", outline=outline, width=2)
        canvas.create_line(x1 + radius, y1, x2 - radius, y1, fill=outline, width=2)
        canvas.create_line(x2, y1 + radius, x2, y2 - radius, fill=outline, width=2)
        canvas.create_line(x1 + radius, y2, x2 - radius, y2, fill=outline, width=2)
        canvas.create_line(x1, y1 + radius, x1, y2 - radius, fill=outline, width=2)

    def make_card(self, width, tail="bottom-left"):
        detailed = width > 220
        height = 132 if detailed else 126
        card = tk.Toplevel(self.root)
        card.overrideredirect(True)
        card.attributes("-topmost", True)
        card.attributes("-transparentcolor", TRANSPARENT_COLOR)
        card.configure(bg=TRANSPARENT_COLOR)
        canvas = tk.Canvas(card, width=width, height=height, bg=TRANSPARENT_COLOR, highlightthickness=0, bd=0)
        canvas.pack()
        bubble_fill, outline = "#FFF8EE", "#3F354A"
        self.draw_bubble(canvas, 8, 8, width - 8, height - 20, 16, bubble_fill, outline, tail)
        canvas.create_rectangle(25, 20, width - 25, 41, fill="#D6C2F3", outline="")
        canvas.create_text(35, 30, text="GROMI 天气", anchor="w", fill="#55436F",
                           font=("Microsoft YaHei UI", 9, "bold"))
        canvas.create_oval(width - 45, 23, width - 31, 37, fill="#FF9DB1", outline="")
        title_text = self.weather["title"]
        if self.weather.get("updated"):
            title_text = f"{title_text} · {self.weather['updated']}"
        canvas.create_text(27, 55, text=title_text, anchor="w", fill="#40364B",
                           font=("Microsoft YaHei UI", 10, "bold"), width=width - 58)
        canvas.create_text(27, 78, text=self.weather["detail"], anchor="w", fill="#6D6072",
                           font=("Microsoft YaHei UI", 9), width=width - 54)
        canvas.create_text(27, 101, text=self.weather.get("tip", "提示：保持好心情。"),
                           anchor="w", fill="#7C6A82", font=("Microsoft YaHei UI", 8), width=width - 62)
        for widget in (card, canvas):
            widget.bind("<Enter>", self.card_enter)
            widget.bind("<Leave>", self.card_leave)
        card.update_idletasks()
        return card

    def show_hover_card(self):
        self.hover_job = None
        if not self.weather_enabled or self.info_card:
            return
        self.refresh_weather()
        self.hide_hover_card()
        width = 260 if self.taskbar_hosted else 240
        prefer_left = self.root.winfo_rootx() + self.pet_w + width > self.screen_w - 8
        tail = "bottom-right" if prefer_left else "bottom-left"
        self.hover_card = self.make_card(width, tail)
        if prefer_left:
            x = max(8, self.root.winfo_rootx() - self.hover_card.winfo_width() + self.pet_w // 2)
        else:
            x = self.root.winfo_rootx() + max(10, self.pet_w // 2)
        y = self.root.winfo_rooty() - self.hover_card.winfo_height() - 6
        if y < 8:
            y = min(self.screen_h - self.hover_card.winfo_height() - 8,
                    self.root.winfo_rooty() + self.visible_pet_h() + 8)
        self.hover_card.geometry(f"+{x}+{y}")

    def hide_hover_card(self):
        self.hide_hover_job = None
        if self.hover_card:
            self.hover_card.destroy()
            self.hover_card = None

    def show_info_card(self):
        self.hide_hover_card()
        if not self.city:
            self.set_city()
            if not self.city:
                return
        if self.info_card:
            self.info_card.destroy()
            self.info_card = None
            return
        self.refresh_weather(force=True)
        self.info_card = self.make_card(300)
        self.info_card.bind("<Button-1>", lambda _event: self.show_info_card())
        x = max(6, min(self.screen_w - self.info_card.winfo_width() - 6, self.root.winfo_rootx() - 80))
        y = max(6, self.root.winfo_rooty() - self.info_card.winfo_height() - 8)
        self.info_card.geometry(f"+{x}+{y}")

    def set_city(self):
        city = simpledialog.askstring("GROMI 天气", "输入城市名称（例如：北京、上海、深圳）：", initialvalue=self.city, parent=self.root)
        if city and city.strip():
            self.city = city.strip()
            self.weather = {"title": f"{self.city}：正在更新天气", "detail": "GROMI 正在查看天空…",
                            "tip": "提示：天气消息正在路上。", "updated": ""}
            self.save_config()
            self.refresh_weather(force=True)

    def refresh_weather(self, force=False):
        if not self.city:
            return
        if self.weather_loading and not force:
            return
        if not force and self.weather.get("updated_at", 0) and time.time() - self.weather["updated_at"] < self.weather_refresh_seconds():
            return
        self.weather_loading = True
        self.weather_request_id += 1
        request_id = self.weather_request_id
        request_city = self.city

        def worker():
            try:
                city = urllib.parse.quote(request_city)
                geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=zh&format=json"
                with urllib.request.urlopen(geo_url, timeout=8) as response:
                    place = json.load(response)["results"][0]
                weather_url = ("https://api.open-meteo.com/v1/forecast?latitude="
                               f"{place['latitude']}&longitude={place['longitude']}"
                               "&current=temperature_2m,apparent_temperature,weather_code&timezone=auto")
                with urllib.request.urlopen(weather_url, timeout=8) as response:
                    current = json.load(response)["current"]
                title = f"{place['name']} · {WEATHER_CODES.get(current.get('weather_code', -1), '天气')}"
                apparent = current.get("apparent_temperature", "--")
                weather = {
                    "title": title,
                    "detail": f"{current.get('temperature_2m', '--')}°C  ·  体感 {apparent}°C",
                    "tip": self.weather_tip(title, apparent),
                    "updated": datetime.now().strftime("%H:%M"), "updated_at": time.time(),
                }
            except (OSError, KeyError, IndexError, ValueError, json.JSONDecodeError):
                weather = {"title": f"{request_city}：天气暂不可用", "detail": "请检查网络，稍后重试",
                           "tip": "提示：暂时看不清天空。", "updated": ""}
            self.weather_queue.put((request_id, weather))

        threading.Thread(target=worker, daemon=True).start()

    def process_weather_queue(self):
        try:
            while True:
                request_id, weather = self.weather_queue.get_nowait()
                if request_id == self.weather_request_id:
                    self.weather = weather
                    self.weather_loading = False
        except queue.Empty:
            pass
        self.root.after(150, self.process_weather_queue)

    def set_desktop_scale(self, scale):
        self.desktop_scale = max(0.28, min(1.20, scale))
        if not self.taskbar_hosted:
            self.set_render_scale(self.desktop_scale)
            self.last_geometry = None
            self.refresh()
        self.save_config()

    def zoom(self, step):
        self.set_desktop_scale(round(self.desktop_scale + step, 2))

    def close(self):
        self.hide_hover_card()
        if self.info_card:
            self.info_card.destroy()
            self.info_card = None
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.destroy()
        if self.tray_icon:
            self.tray_icon.stop()
        self.save_config()
        self.root.destroy()


if __name__ == "__main__":
    mutex_handle = acquire_single_instance()
    if mutex_handle:
        try:
            GromiPet().root.mainloop()
        finally:
            ctypes.windll.kernel32.CloseHandle(mutex_handle)
    else:
        notify_existing_instance()
