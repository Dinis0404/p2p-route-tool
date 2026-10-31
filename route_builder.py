# -*- coding: utf-8 -*-
"""
點對點路線編排工具（桌面版，含任務）
地圖站點：S(起點) + 01~10，點擊建立路線，輸出如：S 07 08 09 10 02 S
每個站點可附帶任務（拿球／放球／轉圈／小人…），任務清單在 config.json 可調。

操作：
- 左鍵點地圖站點：加入路線尾端（若有空位則填入第一個空位），帶上目前任務筆刷
- 左鍵點路線欄位：筆刷=選取 → 選取該位置（再點一次取消）；筆刷=任務 → 貼上任務
- 右鍵點欄位：選單（指派任務／清除任務／刪除此點／選取）
- 選取後點地圖：替換該位置（帶上目前筆刷任務）
- 「插入空位」：在選取位置之後插入一個空欄位（沒選取就加在最後）
- 右鍵刪除 或 選取後按 Delete：刪除該站點；Esc：取消選取／回到選取筆刷
"""
import json
import os
import re
import sys
import threading
import tkinter as tk
from functools import partial

VERSION = "1.1.1"

try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# exe 版（PyInstaller）：程式和資料分離，config/存檔/地圖都放 exe 旁邊
if getattr(sys, "frozen", False):
    BASE = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
IMG_PATH = os.path.join(BASE, "image.png")
SAVE_PATH = os.path.join(BASE, "route_save.json")
CONFIG_PATH = os.path.join(BASE, "config.json")

NATIVE_W, NATIVE_H = 1439, 620
SCALE = 0.8
DW, DH = int(NATIVE_W * SCALE), int(NATIVE_H * SCALE)
HIT_R = 26                      # 地圖熱區半徑（顯示像素）

DEFAULT_PTS = {
    'S':  (708,  502),
    '01': (322,   78),
    '02': (550,   78),
    '03': (797,   72),
    '04': (1043,  80),
    '05': (1308, 240),
    '06': (1310, 404),
    '07': (1088, 540),
    '08': (388,  542),
    '09': (86,   402),
    '10': (100,  238),
}

DEFAULT_FUNC_BY_ID = {"T1": "ball", "T2": "rotate", "T3": "up", "T4": "open"}

DEFAULT_CONFIG = {
    "tasks": [
        {"id": "T1", "name": "拿球", "color": "#e11d48", "func": "ball"},
        {"id": "T2", "name": "小人", "color": "#16a34a", "func": "rotate"},
        {"id": "T3", "name": "擡小人", "color": "#d97706", "func": "up"},
        {"id": "T4", "name": "藥盒", "color": "#7c3aed", "func": "open"},
        {"id": "T5", "name": "任務5", "color": "#0284c7", "func": "task5"},
        {"id": "T6", "name": "任務6", "color": "#64748b", "func": "task6"},
        {"id": "T7", "name": "任務7", "color": "#c026d3", "func": "task7"}
    ],
    "stations": {
        "S": [708, 502], "01": [322, 78], "02": [550, 78], "03": [797, 72],
        "04": [1043, 80], "05": [1308, 240], "06": [1310, 404], "07": [1088, 540],
        "08": [388, 542], "09": [86, 402], "10": [100, 238]
    },
    "output": {"taskFormat": "{id}({task})"},
    "update": {"url": ""},
    "program": {
        "init": {"leftPort": 0, "rightPort": 3, "leftPower": -1,
                 "rightPower": 1, "portType": 1, "port0": 0},
        "scratchInit": {"leftch": 1, "rightch": 2, "port": 1},
        "startDelay": 1
    }
}

BLUE = "#2563eb"
BLUE_DARK = "#1e40af"
BLUE_BG = "#eef2ff"
BLUE_BORDER = "#c7d2fe"
ORANGE = "#d97706"
ORANGE_BG = "#fef3c7"
ORANGE_DARK = "#92400e"
GRAY = "#94a3b8"


def write_default_config():
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict) or not isinstance(cfg.get("tasks"), list):
            raise ValueError
    except Exception:
        write_default_config()
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    tasks = []
    for t in cfg["tasks"]:
        if isinstance(t, dict) and t.get("id") and t.get("name"):
            tid = str(t["id"])
            tasks.append({"id": tid, "name": str(t["name"]),
                          "color": str(t.get("color", "#64748b")),
                          "func": str(t.get("func") or DEFAULT_FUNC_BY_ID.get(tid, tid.lower()))})
    if not tasks:
        tasks = json.loads(json.dumps(DEFAULT_CONFIG["tasks"]))

    def parse_pts(st):
        pts = {}
        if isinstance(st, dict):
            for k, v in st.items():
                if k in DEFAULT_PTS and isinstance(v, (list, tuple)) and len(v) == 2:
                    pts[k] = (float(v[0]), float(v[1]))
        return pts if len(pts) == len(DEFAULT_PTS) else None

    photo = parse_pts(cfg.get("stations")) or dict(DEFAULT_PTS)
    schem = cfg.get("schematic") or {}
    schem_pts = parse_pts(schem.get("stations")) or photo
    schem_img = schem.get("image") if isinstance(schem.get("image"), str) else "map_bw.png"
    fmt = cfg.get("output", {}).get("taskFormat", "{id}({task})")
    if not isinstance(fmt, str) or "{id}" not in fmt:
        fmt = "{id}({task})"
    program = cfg.get("program") if isinstance(cfg.get("program"), dict) else {}
    return tasks, photo, {"pts": schem_pts, "img": schem_img}, fmt, program


class App:
    def __init__(self, root):
        self.root = root
        self.route = []        # [{'id': 站點 or None, 'task': 任務id or None}, ...]
        self.functions = {}    # 程式工作區：{函式名: [積木...]}
        self.selected = None   # 選取的欄位索引
        self.brush = "SELECT"  # "SELECT" | "CLEAR" | 任務id
        self._photo = None
        self._photos = {}      # 依路徑快取的底圖
        self._after_id = None
        self._prog_editor = None

        root.title("點對點路線編排工具 v%s" % VERSION)
        root.resizable(False, False)
        try:
            from tkinter import font as tkfont
            tkfont.nametofont("TkDefaultFont").configure(family="Microsoft JhengHei UI")
        except Exception:
            pass

        self.tasks, self.photo_pts, schem, self.task_fmt, self.program_cfg = load_config()
        self.tasks_by_id = {t["id"]: t for t in self.tasks}
        self.schem_pts = schem["pts"]
        self.schem_img = schem["img"]
        self.task_by_id = self.tasks_by_id
        self.view = "bw"
        self.PTS = self.photo_pts      # 先給預設座標供存檔驗證，稍後依檢視切換
        self._load_route()     # 會還原上次的地圖檢視
        if self.view == "bw" and not os.path.exists(os.path.join(BASE, self.schem_img)):
            self.view = "photo"
        self.PTS = self.schem_pts if self.view == "bw" else self.photo_pts
        self._build_ui()
        self.render()
        root.bind("<Escape>", self._on_escape)
        root.bind("<Delete>", lambda e: self._delete_selected())
        root.bind("<FocusIn>", lambda e: self.reload_config())
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.bind("<Escape>", self._on_escape)
        root.bind("<Delete>", lambda e: self._delete_selected())
        root.bind("<FocusIn>", lambda e: self.reload_config())
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- 設定 ----------------
    def reload_config(self):
        self.tasks, self.photo_pts, schem, self.task_fmt, self.program_cfg = load_config()
        self.schem_pts = schem["pts"]
        self.schem_img = schem["img"]
        self.tasks_by_id = {t["id"]: t for t in self.tasks}
        self.task_by_id = self.tasks_by_id
        if hasattr(self, "brush_bar") and self.brush not in (None, "SELECT", "CLEAR") \
                and self.brush not in self.task_by_id:
            self.brush = "SELECT"
        if hasattr(self, "brush_bar"):
            self._apply_view(self.view)
            self._render_brush_bar()
            self.render()

    # ---------------- UI ----------------
    def _build_ui(self):
        top = tk.Frame(self.root)
        top.pack(padx=10, pady=(10, 4))

        tbar = tk.Frame(top)
        tbar.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.btn_view_bw = tk.Button(tbar, text="黑白示意圖",
                                     command=lambda: self._set_view("bw"))
        self.btn_view_bw.pack(side="left")
        self.btn_view_photo = tk.Button(tbar, text="現場照片",
                                        command=lambda: self._set_view("photo"))
        self.btn_view_photo.pack(side="left", padx=(6, 0))
        self._style_view_buttons()
        tk.Label(tbar, text="示意圖只畫路線與站點，看得更清楚", fg=GRAY)\
            .pack(side="left", padx=10)

        self.canvas = tk.Canvas(top, width=DW, height=DH, bg="white", highlightthickness=0)
        self.canvas.grid(row=1, column=0)
        self._draw_base_image()

        self.canvas.bind("<Button-1>", self._on_map_click)

        # 任務筆刷
        tbox = tk.LabelFrame(self.root, text="任務筆刷")
        tbox.pack(fill="x", padx=10, pady=4)
        self.brush_bar = tk.Frame(tbox)
        self.brush_bar.pack(anchor="w", padx=8, pady=6)
        self._render_brush_bar()

        # 路線欄位
        box = tk.LabelFrame(self.root, text="路線順序（左鍵選取／右鍵＝任務與刪除選單）")
        box.pack(fill="x", padx=10, pady=4)
        self.chips = tk.Frame(box)
        self.chips.pack(anchor="w", padx=8, pady=6)

        # 控制列
        bar = tk.Frame(self.root)
        bar.pack(fill="x", padx=10, pady=2)
        self.btn_undo = tk.Button(bar, text="復原", width=8, command=self._undo)
        self.btn_undo.pack(side="left")
        self.btn_clear = tk.Button(bar, text="清除全部", width=8, command=self._clear)
        self.btn_clear.pack(side="left", padx=(6, 0))
        self.btn_insert = tk.Button(bar, text="插入空位", width=8, command=self._insert_slot)
        self.btn_insert.pack(side="left", padx=(6, 0))
        self.btn_del = tk.Button(bar, text="刪除選取", width=8, command=self._delete_selected)
        self.btn_del.pack(side="left", padx=(6, 0))
        self.btn_prog = tk.Button(bar, text="程序編輯器", width=10, bg=BLUE, fg="white",
                                  activebackground=BLUE, activeforeground="white",
                                  relief="flat", cursor="hand2",
                                  command=self.open_program_editor)
        self.btn_prog.pack(side="left", padx=(10, 0))
        self.btn_upd = tk.Button(bar, text="檢查更新", width=8, command=self.check_update)
        self.btn_upd.pack(side="left", padx=(6, 0))

        # 輸出（兩種格式各一列）
        out = tk.LabelFrame(self.root, text="輸出字串")
        out.pack(fill="x", padx=10, pady=(4, 2))
        self.out_plain = tk.StringVar()
        self.out_task = tk.StringVar()
        row = tk.Frame(out)
        row.pack(fill="x", padx=8, pady=(6, 2))
        tk.Label(row, text="純站點", width=7, anchor="e").pack(side="left")
        tk.Entry(row, textvariable=self.out_plain, state="readonly",
                 font=("Consolas", 12), readonlybackground="white")\
            .pack(side="left", fill="x", expand=True, padx=8)
        self.btn_copy1 = tk.Button(row, text="複製", width=6, command=lambda: self._copy(1))
        self.btn_copy1.pack(side="left")
        row2 = tk.Frame(out)
        row2.pack(fill="x", padx=8, pady=(2, 8))
        tk.Label(row2, text="含任務", width=7, anchor="e").pack(side="left")
        tk.Entry(row2, textvariable=self.out_task, state="readonly",
                 font=("Consolas", 12), readonlybackground="white")\
            .pack(side="left", fill="x", expand=True, padx=8)
        self.btn_copy2 = tk.Button(row2, text="複製", width=6, command=lambda: self._copy(2))
        self.btn_copy2.pack(side="left")

        # 狀態列
        status = tk.Frame(self.root)
        status.pack(fill="x", padx=12, pady=(2, 8))
        self.hint = tk.Label(status, text="", fg=GRAY, anchor="w")
        self.hint.pack(side="left")
        self.stat = tk.Label(status, text="", fg=GRAY, anchor="e")
        self.stat.pack(side="right")

    def _view_image_path(self):
        if self.view == "bw":
            p = os.path.join(BASE, self.schem_img)
            if os.path.exists(p):
                return p
        return os.path.join(BASE, "image.png")

    def _draw_base_image(self):
        path = self._view_image_path()
        if not os.path.exists(path):
            self.canvas.create_text(DW / 2, DH / 2, text="找不到地圖圖片 " + path,
                                    fill="red", font=("Microsoft JhengHei UI", 16))
            return
        if path not in self._photos:
            if HAS_PIL:
                img = Image.open(path).convert("RGB")
                img = img.resize((DW, DH), Image.LANCZOS)
                self._photos[path] = ImageTk.PhotoImage(img, master=self.root)
            else:
                ph = tk.PhotoImage(file=path)
                self._photos[path] = ph.subsample(2)
        self._photo = self._photos[path]
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)

    def _set_view(self, v):
        if v == self.view:
            return
        if v == "bw" and not os.path.exists(os.path.join(BASE, self.schem_img)):
            self._flash_hint("找不到 %s，無法切換示意圖" % self.schem_img)
            return
        self._apply_view(v)

    def _apply_view(self, v):
        self.view = v
        self.PTS = self.schem_pts if v == "bw" else self.photo_pts
        if hasattr(self, "canvas"):
            self.canvas.delete("all")
            self._draw_base_image()
            self._style_view_buttons()
            self.render()

    def _style_view_buttons(self):
        if not hasattr(self, "btn_view_bw"):
            return
        for btn, key in ((self.btn_view_bw, "bw"), (self.btn_view_photo, "photo")):
            on = (self.view == key)
            btn.config(bg=ORANGE if on else "white",
                       fg="white" if on else "#334155",
                       activebackground=ORANGE if on else "white",
                       activeforeground="white" if on else "#334155",
                       relief="flat", cursor="hand2", padx=12, pady=3,
                       highlightthickness=1,
                       highlightbackground=ORANGE if on else "#cbd5e1",
                       highlightcolor=ORANGE if on else "#cbd5e1")

    def _render_brush_bar(self):
        for w in self.brush_bar.winfo_children():
            w.destroy()
        specs = [("SELECT", "選取", "#334155", "#f1f5f9"),
                 ("CLEAR", "清除任務", "#dc2626", "#fee2e2")]
        for value, label, fg, bg in specs:
            self._brush_button(value, label, fg, bg)
        for t in self.tasks:
            self._brush_button(t["id"], t["name"], "white", t["color"])

    def _brush_button(self, value, label, fg, bg):
        active = (self.brush == value)
        b = tk.Button(self.brush_bar, text=label, cursor="hand2",
                      relief="flat", bd=0, padx=12, pady=4,
                      bg=(ORANGE if active else bg),
                      fg=("white" if active else fg),
                      activebackground=bg, activeforeground=fg,
                      highlightthickness=1,
                      highlightbackground=(ORANGE if active else "#cbd5e1"),
                      highlightcolor=(ORANGE if active else "#cbd5e1"))
        b.pack(side="left", padx=(0, 6))
        b.bind("<Button-1>", partial(lambda ev, v=value: self._set_brush(v)))

    def _set_brush(self, value):
        self.brush = value
        self._render_brush_bar()
        self.render()

    # ---------------- 事件 ----------------
    def _on_map_click(self, event):
        nx, ny = event.x / SCALE, event.y / SCALE
        best, best_d = None, HIT_R
        for pid in self.PTS:
            px, py = self.PTS[pid]
            d = ((nx - px) ** 2 + (ny - py) ** 2) ** 0.5 * SCALE
            if d <= best_d:
                best, best_d = pid, d
        if best:
            self._click_station(best)

    def _current_task(self):
        return None if self.brush in ("SELECT", "CLEAR") else self.brush

    def _click_station(self, pid):
        task = self._current_task() if self.brush != "SELECT" else None
        if self.selected is not None:
            self.route[self.selected] = {"id": pid, "task": task}
            self.selected = None
        else:
            entry = {"id": pid, "task": task}
            empties = [i for i, r in enumerate(self.route) if r["id"] is None]
            if empties:
                self.route[empties[0]] = entry
            else:
                self.route.append(entry)
        self.render()

    def _on_chip_click(self, idx):
        if self.brush not in ("SELECT", "CLEAR"):
            if self.route[idx]["id"] is None:
                self._flash_hint("空位要先填站點才能加任務（筆刷切回「選取」點地圖填）")
                return
            self.route[idx]["task"] = self.brush
            self.selected = None
        else:
            if self.brush == "CLEAR":
                self.route[idx]["task"] = None
                self.selected = None
            else:
                self.selected = None if self.selected == idx else idx
        self.render()

    def _chip_menu(self, idx):
        m = tk.Menu(self.root, tearoff=0)
        tasks = tk.Menu(m, tearoff=0)
        for t in self.tasks:
            tasks.add_command(label=t["name"],
                              command=partial(self._set_task, idx, t["id"]))
        m.add_cascade(label="指派任務", menu=tasks)
        m.add_command(label="清除任務", command=partial(self._set_task, idx, None))
        m.add_separator()
        m.add_command(label="選取此位置", command=partial(self._select_chip, idx))
        m.add_command(label="刪除此點", command=partial(self._do_delete, idx))
        try:
            m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            m.grab_release()

    def _select_chip(self, idx):
        self.selected = idx
        self.render()

    def _set_task(self, idx, task_id):
        if self.route[idx]["id"] is None:
            self._flash_hint("空位要先填站點才能加任務")
            return
        self.route[idx]["task"] = task_id
        self.render()

    def _do_delete(self, idx):
        del self.route[idx]
        if self.selected == idx:
            self.selected = None
        elif self.selected is not None and self.selected > idx:
            self.selected -= 1
        self.render()

    def _on_chip_right(self, idx):
        self._chip_menu(idx)

    def _deselect(self):
        if self.selected is not None:
            self.selected = None
            self.render()

    def _on_escape(self, e):
        if self.selected is not None:
            self._deselect()
        elif self.brush != "SELECT":
            self._set_brush("SELECT")

    def _delete_selected(self):
        if self.selected is not None:
            self._do_delete(self.selected)

    def _insert_slot(self):
        idx = (self.selected + 1) if self.selected is not None else len(self.route)
        self.route.insert(idx, {"id": None, "task": None})
        self.selected = idx
        self.render()

    def _undo(self):
        if self.route:
            self.route.pop()
            if self.selected is not None and self.selected >= len(self.route):
                self.selected = None
            self.render()

    def _clear(self):
        self.route = []
        self.selected = None
        self.render()

    def _copy(self, which):
        text = self.out_plain.get() if which == 1 else self.out_task.get()
        if not self.route:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        btn = self.btn_copy1 if which == 1 else self.btn_copy2
        btn.config(text="已複製 ✓", state="disabled")
        key = "_after_id%d" % which
        if getattr(self, key, None):
            self.root.after_cancel(getattr(self, key))
        setattr(self, key, self.root.after(
            1200, lambda: btn.config(text="複製")))

    def _flash_hint(self, msg):
        self.hint.config(text=msg, fg="#dc2626")
        self.root.after(2500, self.render)

    def _on_close(self):
        self._save_route()
        self.root.destroy()

    # ---------------- 狀態 ----------------
    def _fmt_entry(self, r, with_task=True):
        if r["id"] is None:
            return "__"
        if with_task and r["task"]:
            t = self.task_by_id.get(r["task"])
            name = t["name"] if t else "?"
            return self.task_fmt.format(id=r["id"], task=name)
        return r["id"]

    def _output_text(self, with_task):
        if not self.route:
            return "尚未選點"
        return " ".join(self._fmt_entry(r, with_task) for r in self.route)

    def _chip_text(self, r, idx):
        name = "起點" if r["id"] == "S" else (r["id"] if r["id"] is not None else "__")
        label = self._fmt_entry(r, with_task=False) if r["id"] == "S" else name
        if r["id"] == "S":
            label = "起點"
        if r["task"]:
            t = self.task_by_id.get(r["task"])
            label += "·" + (t["name"] if t else "?")
        return "%d. %s" % (idx + 1, label)

    def _load_route(self):
        try:
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            v = data.get("view")
            if v in ("bw", "photo"):
                self.view = v
            funcs = data.get("functions")
            if isinstance(funcs, dict):
                self.functions = {}
                for name, blocks in funcs.items():
                    if isinstance(name, str) and isinstance(blocks, list):
                        self.functions[name] = [
                            b for b in blocks
                            if isinstance(b, dict) and isinstance(b.get("p"), dict)]
            route = data.get("route")
            if not isinstance(route, list):
                return
            out = []
            for r in route:
                if isinstance(r, dict):
                    rid = r.get("id")
                    out.append({"id": rid if rid in self.PTS else None,
                                "task": r.get("task") if r.get("task") in self.task_by_id else None})
                elif isinstance(r, str) and r in self.PTS:   # 舊版純字串格式
                    out.append({"id": r, "task": None})
            self.route = out
        except Exception:
            pass

    def _save_route(self):
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump({"route": self.route, "view": self.view,
                           "functions": self.functions}, f, ensure_ascii=False)
        except Exception:
            pass

    def save_workspace(self):
        self._save_route()

    def apply_scratch_init(self, settings):
        """匯入 .srhs 時讀回巡線初始化設定（寫入 config.json 持久化）"""
        s = self.program_cfg.setdefault("scratchInit", {})
        s["leftch"] = int(float(settings.get("leftch", 1)))
        s["rightch"] = int(float(settings.get("rightch", 2)))
        s["port"] = int(float(settings.get("port", 1)))
        self.program_cfg.setdefault("init", {})
        self.program_cfg["init"]["leftPower"] = float(settings.get("leftspeed", -1))
        self.program_cfg["init"]["rightPower"] = float(settings.get("rightspeed", 1))
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg.setdefault("program", {})
            cfg["program"]["scratchInit"] = s
            cfg["program"]["init"] = self.program_cfg["init"]
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def sync_after_import(self):
        """程序編輯器匯入專案後同步主視窗"""
        self.render()

    def open_program_editor(self):
        import program_editor
        alive = False
        try:
            alive = self._prog_editor is not None and bool(self._prog_editor.winfo_exists())
        except Exception:
            alive = False
        if alive:
            self._prog_editor.deiconify()
            self._prog_editor.lift()
            self._prog_editor.focus_set()
        else:
            self._prog_editor = program_editor.ProgramEditor(self)

    # ---------------- 更新 ----------------
    @staticmethod
    def _ver_tuple(v):
        try:
            return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3])
        except Exception:
            return (0,)

    def check_update(self):
        import urllib.request
        import webbrowser

        def work():
            result = {"err": None, "data": None, "no_url": False}
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                url = (cfg.get("update") or {}).get("url", "")
                if not url:
                    result["no_url"] = True
                else:
                    with urllib.request.urlopen(url, timeout=8) as resp:
                        raw = json.loads(resp.read().decode("utf-8"))
                    if "api.github.com" in url and "releases/latest" in url:
                        # GitHub Releases API：tag=版本，body=更新說明
                        result["data"] = {
                            "version": str(raw.get("tag_name", "")).lstrip("vV"),
                            "url": raw.get("html_url", ""),
                            "notes": (raw.get("body") or "")[:300],
                        }
                    else:
                        result["data"] = raw
            except Exception as e:
                result["err"] = str(e)

            def show():
                self.btn_upd.config(state="normal")
                if result["no_url"]:
                    messagebox.showinfo(
                        "檢查更新",
                        "未設定更新來源。\n請在 config.json 加入：\n"
                        "\"update\": { \"url\": \"https://…/version.json\" }\n"
                        "version.json 內容：{\"version\": \"1.1.1\", \"url\": \"下載連結\"}")
                    return
                if result["err"]:
                    messagebox.showerror("檢查更新", "檢查失敗：%s" % result["err"])
                    return
                data = result["data"] or {}
                remote = str(data.get("version", ""))
                if self._ver_tuple(remote) > self._ver_tuple(VERSION):
                    notes = data.get("notes", "")
                    if messagebox.askyesno(
                            "檢查更新",
                            "發現新版本 %s（目前 v%s）\n%s\n\n開啟下載頁面？"
                            % (remote, VERSION, notes)):
                        webbrowser.open(data.get("url", ""))
                else:
                    messagebox.showinfo("檢查更新", "已是最新版本（v%s）" % VERSION)

            self.root.after(0, show)

        self.btn_upd.config(state="disabled")
        threading.Thread(target=work, daemon=True).start()

    # ---------------- 繪製 ----------------
    def render(self):
        self._render_map()
        self._render_chips()
        self.out_plain.set(self._output_text(with_task=False))
        self.out_task.set(self._output_text(with_task=True))
        has = bool(self.route)
        self.btn_undo.config(state="normal" if has else "disabled")
        self.btn_clear.config(state="normal" if has else "disabled")
        self.btn_copy1.config(state="normal" if has else "disabled")
        self.btn_copy2.config(state="normal" if has else "disabled")
        self.btn_del.config(state="normal" if self.selected is not None else "disabled")
        n_task = sum(1 for r in self.route if r["task"])
        self.stat.config(text="共 %d 站．帶任務 %d 項" % (len(self.route), n_task))
        if self.brush == "SELECT":
            if self.selected is not None:
                self.hint.config(text="已選取第 %d 個位置：點地圖替換／按 Delete 刪除／再點一次取消"
                                      % (self.selected + 1), fg=ORANGE_DARK)
            elif any(r["id"] is None for r in self.route):
                self.hint.config(text="有空位：點地圖會填入第一個空位", fg=BLUE_DARK)
            else:
                self.hint.config(text="先點地圖上的 S（起點），再依序點站點", fg=GRAY)
        else:
            label = "清除任務" if self.brush == "CLEAR" \
                else self.task_by_id.get(self.brush, {}).get("name", self.brush)
            self.hint.config(text="任務筆刷：%s — 點地圖加點帶任務／點欄位貼上任務／右鍵欄位也可指派"
                                  % label, fg="#dc2626" if self.brush == "CLEAR" else ORANGE_DARK)
        self._save_route()

    def _render_map(self):
        self.canvas.delete("hot")
        if len(self.route) >= 2:
            pts = [self.PTS[r["id"]] for r in self.route if r["id"] is not None]
            if len(pts) >= 2:
                flat = [c for p in ((x * SCALE, y * SCALE) for x, y in pts) for c in p]
                self.canvas.create_line(*flat, fill=BLUE, width=3,
                                        dash=(8, 5), tags="hot")
        for pid in self.PTS:
            x, y = self.PTS[pid][0] * SCALE, self.PTS[pid][1] * SCALE
            n = sum(1 for r in self.route if r["id"] == pid)
            if n:
                self.canvas.create_oval(x - 15, y - 15, x + 15, y + 15,
                                        fill=BLUE, outline=BLUE, tags="hot")
                self.canvas.create_text(x, y, text=pid, fill="white",
                                        font=("Microsoft JhengHei UI", 10, "bold"), tags="hot")
                bx, by = x + 14, y - 14
                self.canvas.create_oval(bx - 8, by - 8, bx + 8, by + 8,
                                        fill="#0f172a", outline="white", tags="hot")
                self.canvas.create_text(bx, by, text=str(n), fill="white",
                                        font=("Microsoft JhengHei UI", 8, "bold"), tags="hot")
            elif self.view != "bw":
                # 示意圖本身已畫站點圈，僅照片模式需要熱區圈
                self.canvas.create_oval(x - 15, y - 15, x + 15, y + 15,
                                        fill="white", outline=BLUE, width=2, tags="hot")
                self.canvas.create_text(x, y, text=pid, fill=BLUE,
                                        font=("Microsoft JhengHei UI", 10, "bold"), tags="hot")
        # 任務標籤（同一站多個任務時往上疊）
        stack = {}
        for r in self.route:
            if r["id"] is None or not r["task"]:
                continue
            t = self.task_by_id.get(r["task"])
            if not t:
                continue
            k = stack.get(r["id"], 0)
            stack[r["id"]] = k + 1
            x, y = self.PTS[r["id"]][0] * SCALE, self.PTS[r["id"]][1] * SCALE
            name = t["name"]
            tw = 12 * len(name) + 12
            ty = y + 22 + 21 * k if y < DH - 60 else y - 40 - 21 * k
            tx = min(max(x - tw / 2, 2), DW - tw - 2)
            self.canvas.create_rectangle(tx, ty, tx + tw, ty + 19,
                                         fill=t["color"], outline="", tags="hot")
            self.canvas.create_text(tx + tw / 2, ty + 9, text=name, fill="white",
                                    font=("Microsoft JhengHei UI", 9, "bold"), tags="hot")
        if self.selected is not None and self.selected < len(self.route):
            rid = self.route[self.selected]["id"]
            if rid is not None:
                x, y = self.PTS[rid][0] * SCALE, self.PTS[rid][1] * SCALE
                self.canvas.create_oval(x - 19, y - 19, x + 19, y + 19,
                                        outline=ORANGE, width=3, tags="hot")

    def _render_chips(self):
        for w in self.chips.winfo_children():
            w.destroy()
        n_slots = max(len(self.route) + 1, 6)
        for i in range(n_slots):
            if i > 0:
                tk.Label(self.chips, text="→", fg=GRAY).pack(side="left", padx=2)
            if i < len(self.route):
                r = self.route[i]
                sel = (self.selected == i)
                fg, bg, border = BLUE_DARK, BLUE_BG, BLUE_BORDER
                if sel:
                    fg, bg, border = ORANGE_DARK, ORANGE_BG, ORANGE
                b = tk.Button(self.chips, text=self._chip_text(r, i), cursor="hand2",
                              relief="flat", bd=0, padx=10, pady=4,
                              bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                              highlightthickness=2 if sel else 1,
                              highlightbackground=border, highlightcolor=border)
                b.pack(side="left")
                b.bind("<Button-1>", partial(lambda ev, k=i: self._on_chip_click(k)))
                b.bind("<Button-3>", partial(lambda ev, k=i: self._on_chip_right(k)))
            else:
                tk.Label(self.chips, text="__", fg=GRAY, width=3,
                         relief="groove", padx=6, pady=2).pack(side="left")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
