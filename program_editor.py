# -*- coding: utf-8 -*-
"""
程序編輯器（積木）— tkinter Toplevel
- 左：函式清單（主流程自動生成 + 路線需要的函式 + 自訂函式）
- 中：選中函式的積木鏈（上移/下移/修改/刪除）
- 右：積木工具箱（點一下加到鏈尾並開參數視窗）
- 頂：匯出 .chrts / 匯入專案
"""
import json
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from functools import partial

import chart_export as ce
import srhs_export as se

BLUE = "#2563eb"
BLUE_DARK = "#1e40af"
BLUE_BG = "#eef2ff"
ORANGE = "#d97706"
ORANGE_BG = "#fef3c7"
ORANGE_DARK = "#92400e"
GREEN = "#16a34a"
RED = "#dc2626"
GRAY = "#94a3b8"


class ProgramEditor(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("程序編輯器（積木）")
        self.geometry("1000x580")
        self.cur = None          # None=主流程預覽；其他=函式名
        self._build()
        self.refresh_functions()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # app 便捷介面 ------------------------------------------------
    @property
    def functions(self):
        return self.app.functions

    @property
    def tasks_by_id(self):
        return self.app.tasks_by_id

    @property
    def route(self):
        return self.app.route

    def touch(self):
        self.app.save_workspace()

    # ---------------- UI ----------------
    def _build(self):
        top = tk.Frame(self)
        top.pack(fill="x", padx=10, pady=(10, 4))
        tk.Button(top, text="匯出 .srhs（AbilixScratch）", bg=BLUE, fg="white",
                  activebackground=BLUE, activeforeground="white", relief="flat",
                  padx=12, pady=4, cursor="hand2", command=self.export_srhs)\
            .pack(side="left")
        tk.Button(top, text="匯出 .chrts（流程圖）", relief="flat", padx=12, pady=4,
                  cursor="hand2", highlightthickness=1,
                  highlightbackground="#cbd5e1", command=self.export_chrts)\
            .pack(side="left", padx=(8, 0))
        tk.Button(top, text="匯入專案", relief="flat", padx=12, pady=4,
                  cursor="hand2", highlightthickness=1,
                  highlightbackground="#cbd5e1", command=self.import_project)\
            .pack(side="left", padx=(8, 0))
        self.status = tk.Label(top, text="", fg=GRAY)
        self.status.pack(side="right")

        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=4)

        # 左：函式清單
        left = tk.LabelFrame(body, text="函式清單")
        left.pack(side="left", fill="y", padx=(0, 8))
        self.flist = tk.Listbox(left, width=34, height=22, activestyle="none",
                                font=("Microsoft JhengHei UI", 11))
        self.flist.pack(fill="both", expand=True, padx=6, pady=(6, 2))
        self.flist.bind("<<ListboxSelect>>", self._on_func_select)
        lf = tk.Frame(left)
        lf.pack(fill="x", padx=6, pady=(2, 6))
        tk.Button(lf, text="新增自訂函式", relief="flat", cursor="hand2",
                  highlightthickness=1, highlightbackground="#cbd5e1",
                  command=self.add_custom_func).pack(side="left")
        tk.Button(lf, text="重新命名", relief="flat", cursor="hand2",
                  highlightthickness=1, highlightbackground="#cbd5e1",
                  command=self.rename_func).pack(side="left", padx=(4, 0))
        tk.Button(lf, text="刪除", relief="flat", cursor="hand2",
                  highlightthickness=1, highlightbackground="#cbd5e1",
                  command=self.delete_func).pack(side="left", padx=(4, 0))

        # 中：積木鏈
        mid = tk.LabelFrame(body, text="積木鏈")
        mid.pack(side="left", fill="both", expand=True)
        self.cur_label = tk.Label(mid, text="", anchor="w",
                                  font=("Microsoft JhengHei UI", 11, "bold"))
        self.cur_label.pack(fill="x", padx=8, pady=(6, 0))
        self.blist = tk.Listbox(mid, height=18, activestyle="none",
                                font=("Consolas", 11))
        self.blist.pack(fill="both", expand=True, padx=8, pady=4)
        self.blist.bind("<Double-Button-1>", lambda e: self.edit_block())
        self.blist.bind("<Delete>", lambda e: self.del_block())
        bf = tk.Frame(mid)
        bf.pack(fill="x", padx=8, pady=(0, 4))
        for label, cmd in (("↑ 上移", lambda: self.move_block(-1)),
                           ("↓ 下移", lambda: self.move_block(1)),
                           ("修改", self.edit_block),
                           ("刪除", self.del_block)):
            tk.Button(bf, text=label, relief="flat", cursor="hand2", width=7,
                      highlightthickness=1, highlightbackground="#cbd5e1",
                      command=cmd).pack(side="left", padx=(0, 4))
        self.main_info = tk.Label(mid, text="", anchor="w", fg=GRAY, justify="left")
        self.main_info.pack(fill="x", padx=8, pady=(0, 6))

        # 右：積木工具箱
        right = tk.LabelFrame(body, text="積木工具箱（點擊加到鏈尾）")
        right.pack(side="left", fill="y", padx=(8, 0))
        grid = tk.Frame(right)
        grid.pack(padx=8, pady=6)
        order = ["patrol", "advanced", "turn", "motor",
                 "motor_enc", "motor1", "motor_gray",
                 "enc_clear", "delay", "display", "stop", "wait_btn", "call"]
        for i, key in enumerate(order):
            d = ce.BLOCK_DEFS[key]
            tk.Button(grid, text=d["label"], width=12, relief="flat", cursor="hand2",
                      bg=BLUE_BG, fg=BLUE_DARK, activebackground=BLUE_BG,
                      activeforeground=BLUE_DARK,
                      highlightthickness=1, highlightbackground="#c7d2fe",
                      command=partial(self.add_block, key))\
                .grid(row=i // 2, column=i % 2, padx=3, pady=3, sticky="nsew")
        tip = ("提示：\n"
               "・主流程由路線自動生成，不可編輯\n"
               "・路線需要的函式帶 ✗，點進去加第一塊積木即建立\n"
               "・雙擊積木＝修改參數；Delete＝刪除\n"
               "・函式可互相呼叫（呼叫函式積木）")
        tk.Label(right, text=tip, fg=GRAY, justify="left").pack(anchor="w", padx=8, pady=6)

    # ---------------- 函式清單 ----------------
    def func_entries(self):
        """[(顯示文字, 函式名 or None)]，None=主流程"""
        entries = [("★ 主流程（自動生成）", None)]
        needed = ce.needed_funcs(self.route, self.tasks_by_id)
        for n in needed:
            mark = "✓" if self.functions.get(n) else "✗"
            entries.append(("%s %s" % (mark, n), n))
        for n in self.functions:
            if n not in needed:
                entries.append(("· %s" % n, n))
        return entries

    def refresh_functions(self, keep=None):
        sel = keep if keep is not None else self.cur
        self.flist.delete(0, "end")
        self._entries = self.func_entries()
        for text, _ in self._entries:
            self.flist.insert("end", text)
        idx = 0
        for i, (_, name) in enumerate(self._entries):
            if name == sel:
                idx = i
                break
        self.flist.selection_clear(0, "end")
        self.flist.selection_set(idx)
        self.flist.see(idx)
        self.cur = self._entries[idx][1]
        self._style_list()
        self.refresh_blocks()
        self.touch()

    def _style_list(self):
        needed = ce.needed_funcs(self.route, self.tasks_by_id)
        for i, (text, name) in enumerate(self._entries):
            color = "#0f172a"
            if name is None:
                color = ORANGE_DARK
            elif name not in self.functions:
                color = RED
            self.flist.itemconfig(i, fg=color)

    def _on_func_select(self, _e=None):
        sel = self.flist.curselection()
        if not sel:
            return
        self.cur = self._entries[sel[0]][1]
        self.refresh_blocks()

    # ---------------- 積木鏈 ----------------
    def refresh_blocks(self):
        self.blist.delete(0, "end")
        if self.cur is None:
            self.cur_label.config(text="主流程（由路線自動生成，不可編輯）",
                                  fg=ORANGE_DARK)
            seq, holes = ce.route_call_sequence(self.route, self.tasks_by_id)
            n = 1
            self.blist.insert("end", "%2d. [初始化] 馬達/灰度設定" % n); n += 1
            self.blist.insert("end", "%2d. [延時] 擺放後啟動" % n); n += 1
            for _, name, desc in seq:
                self.blist.insert("end", "%2d. 呼叫 %s　← %s" % (n, name, desc)); n += 1
            self.blist.insert("end", "%2d. [顯示] 任務完成!" % n)
            if holes:
                self.main_info.config(text="⚠ 路線有空位，對應呼叫已跳過；先回主視窗補齊路線",
                                      fg=RED)
            else:
                self.main_info.config(
                    text="共 %d 個呼叫；未定義函式匯出時會生成空頁，可回 AbilixChart 補" % len(seq),
                    fg=GRAY)
            return
        blocks = self.functions.get(self.cur, [])
        self.cur_label.config(text="%s 的積木（%d 塊）" % (self.cur, len(blocks)),
                              fg="#0f172a")
        for i, b in enumerate(blocks):
            self.blist.insert("end", "%2d. %s" % (i + 1, ce.block_label(b)))
        self.main_info.config(text="", fg=GRAY)

    def _sel_block(self):
        sel = self.blist.curselection()
        if not sel or self.cur is None:
            return None
        blocks = self.functions.setdefault(self.cur, [])
        if sel[0] >= len(blocks):
            return None
        return sel[0]

    # ---------------- 積木操作 ----------------
    def add_block(self, kind, open_dialog=True):
        if self.cur is None:
            self._status("主流程不可編輯，請先在左邊選一個函式")
            return
        d = ce.BLOCK_DEFS[kind]
        p = {}
        for prm in d["params"]:
            key, _lab, typ, default = prm[0], prm[1], prm[2], prm[3]
            p[key] = "" if typ == "func" else default
        blocks = self.functions.setdefault(self.cur, [])
        blocks.append({"b": kind, "p": p})
        self.refresh_functions(keep=self.cur)
        self.blist.selection_clear(0, "end")
        self.blist.selection_set(len(blocks) - 1)
        if open_dialog:
            self.edit_block()

    def edit_block(self):
        idx = self._sel_block()
        if idx is None:
            return
        b = self.functions[self.cur][idx]
        self._param_dialog(b, on_ok=self._after_change)

    def del_block(self):
        idx = self._sel_block()
        if idx is None:
            return
        del self.functions[self.cur][idx]
        self._after_change()

    def move_block(self, delta):
        idx = self._sel_block()
        if idx is None:
            return
        blocks = self.functions[self.cur]
        j = idx + delta
        if 0 <= j < len(blocks):
            blocks[idx], blocks[j] = blocks[j], blocks[idx]
            self._after_change(keep_sel=j)

    def _after_change(self, keep_sel=None):
        if keep_sel is not None:
            self.refresh_functions(keep=self.cur)
            self.blist.selection_clear(0, "end")
            self.blist.selection_set(keep_sel)
        else:
            self.refresh_functions(keep=self.cur)

    # ---------------- 函式操作 ----------------
    def add_custom_func(self):
        name = self._ask_name("新增自訂函式", "func_custom")
        if name:
            self.functions.setdefault(name, [])
            self.refresh_functions(keep=name)

    def rename_func(self):
        if self.cur is None:
            self._status("主流程不能重新命名")
            return
        old = self.cur
        name = self._ask_name("重新命名函式", old)
        if not name or name == old:
            return
        self.functions[name] = self.functions.pop(old)
        for blocks in self.functions.values():
            for b in blocks:
                if b["b"] == "call" and b.get("p", {}).get("target") == old:
                    b["p"]["target"] = name
        self.refresh_functions(keep=name)

    def delete_func(self):
        if self.cur is None:
            self._status("主流程不能刪除")
            return
        if not messagebox.askyesno("刪除函式", "確定刪除 %s？" % self.cur, parent=self):
            return
        needed = ce.needed_funcs(self.route, self.tasks_by_id)
        warn = []
        if self.cur in needed:
            warn.append("主流程仍會呼叫它（匯出時生成空頁）")
        for fname, blocks in self.functions.items():
            if fname == self.cur:
                continue
            for b in blocks:
                if b["b"] == "call" and b.get("p", {}).get("target") == self.cur:
                    warn.append("%s 內有呼叫它的積木" % fname)
        if warn:
            if not messagebox.askyesno("刪除函式", "注意：\n" + "\n".join(warn) + "\n仍要刪除？",
                                       parent=self):
                return
        self.functions.pop(self.cur, None)
        self.refresh_functions(keep=None)

    def _ask_name(self, title, initial):
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)
        tk.Label(dlg, text="函式名：").grid(row=0, column=0, padx=10, pady=12)
        e = tk.Entry(dlg, width=32, font=("Consolas", 11))
        e.grid(row=0, column=1, padx=(0, 10), pady=12)
        e.insert(0, initial)
        e.selection_range(0, "end")
        result = []

        def ok():
            v = e.get().strip()
            if not v:
                return
            result.append(v)
            dlg.destroy()
        tk.Button(dlg, text="確定", command=ok, bg=BLUE, fg="white", relief="flat",
                  padx=10, cursor="hand2").grid(row=1, column=0, columnspan=2, pady=(0, 12))
        e.bind("<Return>", lambda e: ok())
        dlg.wait_window()
        return result[0] if result else None

    # ---------------- 參數視窗 ----------------
    def _param_dialog(self, block, on_ok):
        kind = block["b"]
        d = ce.BLOCK_DEFS[kind]
        p = block.setdefault("p", {})
        dlg = tk.Toplevel(self)
        dlg.title("修改積木：" + d["label"])
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)
        widgets = {}

        for row, prm in enumerate(d["params"]):
            key, lab, typ, default = prm[0], prm[1], prm[2], prm[3]
            tk.Label(dlg, text=lab).grid(row=row, column=0, sticky="e",
                                         padx=(14, 6), pady=5)
            cur = p.get(key, default)
            if typ == "choice":
                opts = prm[4]
                w = ttk.Combobox(dlg, state="readonly", width=18,
                                 values=[opts[k] for k in sorted(opts)])
                cur_val = cur if cur in opts else sorted(opts)[0]
                w.set(opts[cur_val])
                widgets[key] = ("choice", w, {opts[k]: k for k in opts})
            elif typ == "func":
                names = sorted(set(list(self.functions.keys())
                                   + ce.needed_funcs(self.route, self.tasks_by_id)))
                w = ttk.Combobox(width=28)
                w["values"] = names
                if cur:
                    w.set(cur)
                widgets[key] = ("func", w, None)
            else:
                w = tk.Entry(dlg, width=22, font=("Consolas", 11))
                w.insert(0, str(cur))
                widgets[key] = (typ, w, None)
            w.grid(row=row, column=1, sticky="w", padx=(0, 14), pady=5)

        def ok():
            try:
                for key, (typ, w, mapping) in widgets.items():
                    if typ == "choice":
                        p[key] = mapping[w.get()]
                    elif typ == "int":
                        p[key] = int(float(w.get()))
                    elif typ == "float":
                        p[key] = float(w.get())
                    else:
                        p[key] = w.get()
            except ValueError:
                messagebox.showerror("參數錯誤", "數字欄位格式不正確", parent=dlg)
                return
            dlg.destroy()
            on_ok()

        btns = tk.Frame(dlg)
        btns.grid(row=len(d["params"]), column=0, columnspan=2, pady=(2, 12))
        tk.Button(btns, text="確定", command=ok, bg=BLUE, fg="white", relief="flat",
                  padx=14, cursor="hand2").pack(side="left", padx=6)
        tk.Button(btns, text="取消", command=dlg.destroy, relief="flat",
                  padx=14, cursor="hand2",
                  highlightthickness=1, highlightbackground="#cbd5e1").pack(side="left")

    # ---------------- 匯出/匯入 ----------------
    def _check_route_ready(self):
        if any(r["id"] is None for r in self.route):
            messagebox.showwarning("無法匯出", "路線還有空位，先回主視窗補齊", parent=self)
            return False
        return True

    def export_srhs(self):
        if not self._check_route_ready():
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="匯出 .srhs", defaultextension=".srhs",
            initialfile="點對點程序.srhs",
            filetypes=[("Abilix Scratch 工程", "*.srhs")])
        if not path:
            return
        try:
            report = se.export_srhs(path, self.route, self.tasks_by_id,
                                    self.functions, self.app.program_cfg)
        except Exception as e:
            messagebox.showerror("匯出失敗", str(e), parent=self)
            return
        msg = "已匯出：%s\n主流程呼叫 %d 個函式，共 %d 個函式定義" % (
            os.path.basename(path), len(report["calls"]),
            len(set(n for _, n, _ in report["calls"]) | set(self.functions)))
        if report["empty"]:
            msg += "\n\n以下函式尚未定義內容（已生成空函式，可在 AbilixScratch 補）：\n" \
                   + "\n".join(report["empty"])
        if report["skipped"]:
            msg += "\n\n⚠ 跳過的積木：\n" + "\n".join(set(report["skipped"]))
        messagebox.showinfo("匯出成功", msg, parent=self)
        self._status("已匯出 " + os.path.basename(path))

    def export_chrts(self):
        if not self._check_route_ready():
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="匯出 .chrts", defaultextension=".chrts",
            initialfile="點對點程序.chrts",
            filetypes=[("Abilix Chart 工程", "*.chrts")])
        if not path:
            return
        try:
            report = ce.export_chrts(path, self.route, self.tasks_by_id,
                                     self.functions, self.app.program_cfg)
        except Exception as e:
            messagebox.showerror("匯出失敗", str(e), parent=self)
            return
        msg = "已匯出：%s\n主流程呼叫 %d 個函式，共 %d 個函式頁" % (
            os.path.basename(path), len(report["calls"]),
            len(set(n for _, n, _ in report["calls"]) | set(self.functions)))
        if report["empty"]:
            msg += "\n\n以下函式尚未定義內容（已生成空頁，可在 AbilixChart 補）：\n" \
                   + "\n".join(report["empty"])
        messagebox.showinfo("匯出成功", msg, parent=self)
        self._status("已匯出 " + os.path.basename(path))

    def import_project(self):
        path = filedialog.askopenfilename(
            parent=self, title="匯入專案 / .srhs",
            filetypes=[("Abilix Scratch 工程 / 專案 JSON", "*.srhs *.json"),
                       ("Abilix Scratch 工程", "*.srhs"),
                       ("專案 JSON", "*.json")])
        if not path:
            return
        if path.lower().endswith(".srhs"):
            self._import_srhs(path)
        else:
            self._import_json(path)

    def _import_srhs(self, path):
        tasks_by_func = {t["func"].lower(): t["id"] for t in self.tasks_by_id.values()}
        try:
            parsed = se.parse_srhs(path, tasks_by_func=tasks_by_func,
                                   valid_stations=set(self.app.PTS))
        except Exception as e:
            messagebox.showerror("匯入失敗", "解析 .srhs 失敗：%s" % e, parent=self)
            return
        funcs = parsed["functions"]
        route = parsed["route"]
        rep = parsed["report"]
        total_blocks = sum(len(v) for v in funcs.values())
        n_empty = sum(1 for v in funcs.values() if not v)
        lost = sum(sum(rep["fn_stats"][n].values()) for n in funcs)

        if rep.get("main_imported"):
            msg = ("此工程沒有自訂函式，主程序共 %d 塊積木\n"
                   "會整串匯入為一個函式「func_main」，之後可自行拆段\n" % total_blocks)
        else:
            msg = "函式 %d 個（空 %d 個），可匯入積木 %d 塊" % (
                len(funcs), n_empty, total_blocks)
            if route:
                ids = [r["id"] for r in route]
                msg += "\n由主程序推得路線：%s" % " → ".join(ids)
            else:
                msg += "\n主程序裡沒有可辨識的點對點呼叫，路線保持不變"
        if rep.get("scratch_init"):
            si = rep["scratch_init"]
            msg += "\n初始化設定已讀入：左CH%s@%s 右CH%s@%s 灰度P%s" % (
                si["leftch"], si["leftspeed"], si["rightch"],
                si["rightspeed"], si["port"])
        if rep["unmatched_calls"]:
            msg += "\n⚠ " + rep["route_note"] + "：" + "、".join(
                rep["unmatched_calls"][:5]) + ("…" if len(rep["unmatched_calls"]) > 5 else "")
        if lost:
            details = []
            for n in funcs:
                for reason, cnt in rep["fn_stats"][n].items():
                    details.append("%s（%d）" % (reason, cnt))
            msg += "\n⚠ 略過 %d 塊：%s" % (lost, "、".join(sorted(set(details))[:6]))
        msg += "\n\n要匯入什麼？"

        dlg = tk.Toplevel(self)
        dlg.title("匯入 .srhs")
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)
        tk.Message(dlg, text=msg, width=460, justify="left",
                   font=("Microsoft JhengHei UI", 10)).pack(padx=14, pady=(12, 6))
        btns = tk.Frame(dlg)
        btns.pack(pady=(2, 12))

        def apply(with_route):
            self._apply_srhs_import(funcs, route if with_route else None,
                                    scratch_init=rep.get("scratch_init"))
            self._status("已匯入 " + os.path.basename(path))
            dlg.destroy()

        if rep.get("main_imported"):
            tk.Button(btns, text="匯入主程序為函式", bg=BLUE, fg="white",
                      relief="flat", padx=12, cursor="hand2",
                      command=lambda: apply(False)).pack(side="left", padx=5)
        else:
            tk.Button(btns, text="匯入函式＋路線", bg=BLUE, fg="white", relief="flat",
                      padx=12, cursor="hand2",
                      command=lambda: apply(True)).pack(side="left", padx=5)
            tk.Button(btns, text="只匯入函式", relief="flat", padx=12, cursor="hand2",
                      highlightthickness=1, highlightbackground="#cbd5e1",
                      command=lambda: apply(False)).pack(side="left", padx=5)
        tk.Button(btns, text="取消", relief="flat", padx=12, cursor="hand2",
                  highlightthickness=1, highlightbackground="#cbd5e1",
                  command=dlg.destroy).pack(side="left", padx=5)

    def _apply_srhs_import(self, funcs, route, scratch_init=None):
        self.app.functions = dict(funcs)
        if route:
            self.app.route = [dict(r) for r in route]
        if scratch_init:
            self.app.apply_scratch_init(scratch_init)
        self.app.sync_after_import()
        self.refresh_functions(keep=None)

    def _import_json(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("匯入失敗", str(e), parent=self)
            return
        funcs = data.get("functions")
        if not isinstance(funcs, dict):
            messagebox.showerror("匯入失敗", "檔案裡沒有 functions 資料", parent=self)
            return
        msg = "將匯入 %d 個函式。" % len(funcs)
        if isinstance(data.get("route"), list) and data["route"]:
            msg += "\n同時匯入檔案中的路線（%d 站）。" % len(data["route"])
        msg += "\n目前的函式%s會被覆蓋，確定？" % (
            "和路線" if isinstance(data.get("route"), list) else "")
        if not messagebox.askyesno("匯入專案", msg, parent=self):
            return
        # 清理非法積木
        clean = {}
        for name, blocks in funcs.items():
            if not isinstance(name, str):
                continue
            bs = []
            for b in blocks if isinstance(blocks, list) else []:
                if isinstance(b, dict) and b.get("b") in ce.BLOCK_DEFS \
                        and isinstance(b.get("p"), dict):
                    bs.append({"b": b["b"], "p": dict(b["p"])})
            clean[name] = bs
        self.app.functions = clean
        if isinstance(data.get("route"), list) and data["route"]:
            rr = []
            for r in data["route"]:
                if isinstance(r, dict) and (r.get("id") is None or r.get("id") in self.app.PTS):
                    rr.append({"id": r.get("id"), "task": r.get("task")})
            self.app.route = rr
        self.app.sync_after_import()
        self.refresh_functions(keep=None)
        self._status("已匯入 " + os.path.basename(path))

    def _status(self, msg):
        self.status.config(text=msg, fg=GREEN)
        self.after(3000, lambda: self.status.config(text="", fg=GRAY))
