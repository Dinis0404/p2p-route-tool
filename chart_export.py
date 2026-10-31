# -*- coding: utf-8 -*-
"""
路線工作區 → AbilixChart 3.0 (.chrts) 匯出模組
格式依據（反編譯 lua + 官方工程實測）：
- 主流程 = pagInfos[0]，type=1
- 每個函式 = 一個 pagInfos 條目，type=2，name=函式名
- 函式呼叫塊 = ids:2000，頂層 "name" = 函式頁名（必須完全一致）
- C 函數名由軟體自動編為 sub_program<頁序-1>，JSON 內不需存
- 每塊積木頂層欄位：ids/name/id/x/y/bColLineItem/parentItem(0=頁首)/parentItemPos/iteminfo

工作區函式本體格式：
  functions = { "func_S_to_07": [ {"b": "patrol", "p": {...}}, ... ], ... }
"""
import json
import zipfile

NOTE = {"value": "", "inputSelected": False}

# ---------------- 積木種類 schema ----------------
# params: (key, 標籤, 類型, 預設[, 選項表])
BLOCK_DEFS = {
    "patrol": {"label": "路口巡線", "params": [
        ("speed", "巡線速度(10-100)", "int", 50, None),
        ("cross", "路口類型", "choice", 2, {1: "左側路口", 2: "T字/十字", 3: "右側路口"}),
        ("crossTime", "通過路口時間(s)", "float", 0.05, None),
    ]},
    "advanced": {"label": "高級巡線", "params": [
        ("speed", "巡線速度", "int", 50, None),
        ("mode", "停止條件", "choice", 2, {1: "時間(秒)", 2: "編碼器(脈波)"}),
        ("value", "秒數或脈波數", "str", "1200", None),
        ("port", "編碼器電機 1=A..4=D", "int", 1, None),
    ]},
    "motor_enc": {"label": "雙馬達直行至編碼", "params": [
        ("left", "左輪速(負=後退)", "int", 50, None),
        ("right", "右輪速(負=後退)", "int", 50, None),
        ("enc", "編碼值", "str", "2000", None),
        ("encPort", "計哪顆編碼", "choice", 0, {0: "左電機", 1: "右電機"}),
    ]},
    "motor1": {"label": "單顆電機計時", "params": [
        ("channel", "電機端口", "choice", 4, {1: "A", 2: "B", 3: "C", 4: "D"}),
        ("speed", "速度", "int", 50, None),
        ("seconds", "持續(秒)", "float", 0.5, None),
    ]},
    "motor_gray": {"label": "雙馬達直到灰度停", "params": [
        ("left", "左輪速", "int", 60, None),
        ("right", "右輪速", "int", 60, None),
        ("port", "灰度端口", "int", 1, None),
        ("channel", "灰度通道", "int", 3, None),
        ("cmp", "條件", "choice", "GTE", {"GT": "超過 >", "GTE": "以上 ≥",
                                          "LT": "低於 <", "LTE": "以下 ≤"}),
        ("value", "灰度值", "int", 2500, None),
    ]},
    "turn": {"label": "轉彎", "params": [
        ("dir", "方向", "choice", 1, {-1: "左轉", 1: "右轉"}),
        ("speed", "輪速", "int", 40, None),
        ("stopPos", "結束位置", "choice", 2, {1: "偏左", 2: "中間", 3: "偏右"}),
    ]},
    "motor": {"label": "啟動電機(計時)", "params": [
        ("left", "左輪速(負=後退)", "int", 50, None),
        ("right", "右輪速(負=後退)", "int", 50, None),
        ("seconds", "時間(s)", "float", 0.5, None),
    ]},
    "enc_clear": {"label": "編碼器清零", "params": [
        ("port", "電機 1=A..4=D", "int", 1, None),
    ]},
    "delay": {"label": "延時", "params": [
        ("seconds", "秒", "float", 0.5, None),
    ]},
    "display": {"label": "顯示文字", "params": [
        ("text", "文字", "text", "OK", None),
    ]},
    "stop": {"label": "停車", "params": []},
    "wait_btn": {"label": "等待按鈕(碰撞)", "params": [
        ("channel", "碰撞/按鈕端口", "int", 12, None),
    ]},
    "call": {"label": "呼叫函式", "params": [
        ("target", "函式名", "func", "", None),
    ]},
}


def block_label(b):
    """一塊積木的人類可讀摘要"""
    kind, p = b["b"], b.get("p", {})
    d = BLOCK_DEFS[kind]
    if kind == "call":
        return "呼叫函式 → %s" % p.get("target", "?")
    parts = []
    for key, lab, typ, *rest in d["params"]:
        v = p.get(key, rest[0] if rest else "")
        opts = rest[1] if len(rest) > 1 else None
        if opts and v in opts:
            v = opts[v]
        parts.append("%s" % v)
    return "%s｜%s" % (d["label"], "｜".join(str(x) for x in parts))


# ---------------- 函式命名 ----------------
def p2p_name(a, b):
    return "func_%s_to_%s" % (a, b)


def task_func_name(task):
    return "func_task_%s" % task.get("func", str(task.get("id", ""))).lower()


def route_call_sequence(route, tasks_by_id):
    """路線 → [(類型, 函式名, 說明)]；route 元素為 {'id':..,'task':..} 或 None 槽"""
    seq = []
    holes = False
    for i in range(len(route) - 1):
        a, b = route[i], route[i + 1]
        if a["id"] is None or b["id"] is None:
            holes = True
            continue
        seq.append(("p2p", p2p_name(a["id"], b["id"]),
                    "%s → %s" % (a["id"], b["id"])))
        if b["task"]:
            t = tasks_by_id.get(b["task"])
            seq.append(("task", task_func_name(t) if t else "func_task_?",
                        "%s %s" % (b["id"], t["name"] if t else "?")))
    return seq, holes


def needed_funcs(route, tasks_by_id):
    """路線需要的所有函式名（依出現順序去重）"""
    seq, _ = route_call_sequence(route, tasks_by_id)
    out = []
    for _, name, _ in seq:
        if name not in out:
            out.append(name)
    return out


# ---------------- 積木 → chart item ----------------
def _val(v):
    return {"refSelected": False, "refType": None, "refIndex": None, "value": str(v)}


def _display_lines(text):
    info = {"displayindex": 1, "clear": True, "Note": dict(NOTE)}
    for i in range(1, 9):
        info["line%d" % i] = {"refType": 1, "refIndex": 1,
                              "value": text if i == 1 else "", "refSelected": False}
    return info


def block_to_iteminfo(b):
    """工作區積木 → (ids, iteminfo)；呼叫塊另回傳頂層 name"""
    kind, p = b["b"], b.get("p", {})
    if kind == "patrol":
        return 602, {"PatrolSpeed": int(p.get("speed", 50)),
                     "CrossIndex": int(p.get("cross", 2)),
                     "CrossTime": p.get("crossTime", 0.05),
                     "Note": dict(NOTE)}
    if kind == "advanced":
        mode = int(p.get("mode", 2))
        info = {"PatrolSpeed": int(p.get("speed", 50)), "OverFlag": mode,
                "CrossTime": "1", "CrossOver": _val(0),
                "MaPan": "0", "MaPanPort": int(p.get("port", 1)),
                "PortIndex": 0, "CompareIndex": 0, "Note": dict(NOTE)}
        if mode == 2:
            info["MaPan"] = str(p.get("value", "1200"))
        else:
            info["CrossTime"] = str(p.get("value", "1"))
        return 604, info
    if kind == "turn":
        s = int(p.get("speed", 40))
        d = int(p.get("dir", 1))
        return 605, {"StopPos": int(p.get("stopPos", 2)),
                     "LeftSpeed": s * d, "RightSpeed": -s * d,
                     "Note": dict(NOTE)}
    if kind == "motor":
        return 606, {"OverFlag": 1, "CrossTime": str(p.get("seconds", 0.5)),
                     "LeftSpeed": int(p.get("left", 50)),
                     "RightSpeed": int(p.get("right", 50)),
                     "CrossOver": _val(0), "MaPan": "0", "MaPanPort": 1,
                     "PortIndex": 0, "CompareIndex": 0, "Note": dict(NOTE)}
    if kind == "motor_enc":
        return 606, {"OverFlag": 2, "CrossTime": "1",
                     "CrossOver": _val(0), "MaPan": str(p.get("enc", "2000")),
                     "MaPanPort": int(p.get("encPort", 0)) + 1,
                     "PortIndex": 0, "CompareIndex": 0,
                     "LeftSpeed": int(p.get("left", 50)),
                     "RightSpeed": int(p.get("right", 50)),
                     "Note": dict(NOTE)}
    if kind == "motor1":
        ch = int(p.get("channel", 4))
        names = {1: "A", 2: "B", 3: "C", 4: "D"}
        info = {"selectedPortName": names[ch], "selectedPort": ch - 1,
                "Advance": False, "AdvAngle": False, "AdvSeconds": True,
                "AdvRefTimeValue": _val(p.get("seconds", 0.5)),
                "AdvRefAngleValue": {"refSelected": False, "refIndex": 1, "refType": 1, "value": 0},
                "Note": dict(NOTE)}
        for i in (1, 2, 3, 4):
            info[names[i]] = {"portSelected": i == ch,
                              "value": int(p.get("speed", 50)),
                              "refValue": {"refSelected": False, "refType": 1,
                                           "refIndex": 1, "value": 30}}
        return 100, info
    if kind == "motor_gray":
        cmp_map = {"GT": 4, "GTE": 3, "LT": 0, "LTE": 1}
        return 606, {"OverFlag": 3, "CrossTime": "1",
                     "CrossOver": _val(p.get("value", 2500)),
                     "MaPan": "0", "MaPanPort": 1,
                     "PortIndex": int(p.get("port", 1)),
                     "CompareIndex": cmp_map.get(p.get("cmp", "GTE"), 3),
                     "LeftSpeed": int(p.get("left", 60)),
                     "RightSpeed": int(p.get("right", 60)),
                     "Note": dict(NOTE)}
    if kind == "wait_btn":
        # 流程圖版：條件循環等按鈕（碰撞==0 時空轉），Equal 代碼為推斷值
        return 403, {"ConditionValue1": {"refType": 4, "refIndex": int(p.get("channel", 12))},
                     "CompareIndex1": 2, "ConditionCompareValue1": 0,
                     "Condition2": False, "color1": 0,
                     "Note": dict(NOTE, value="等按鈕按下(放開)後繼續")}
    if kind == "enc_clear":
        return 207, {"nCurrPort": int(p.get("port", 1)), "nMotorCodeType": 3,
                     "nRefValType": 14, "nRefValIndex": 1,
                     "isOnNotes": False, "strNoteContent": ""}
    if kind == "delay":
        return 405, {"Delay": _val(p.get("seconds", 0.5)), "Note": dict(NOTE)}
    if kind == "display":
        return 106, _display_lines(p.get("text", "OK"))
    if kind == "stop":
        names = {1: "A", 2: "B", 3: "C", 4: "D"}
        info = {"selectedPortName": "A", "selectedPort": 0,
                "Advance": False, "AdvAngle": False, "AdvSeconds": False,
                "AdvRefTimeValue": {"refSelected": False, "refIndex": 1, "refType": 1, "value": 3},
                "AdvRefAngleValue": {"refSelected": False, "refIndex": 1, "refType": 1, "value": 0},
                "Note": dict(NOTE)}
        for i in (1, 2, 3, 4):
            info[names[i]] = {"portSelected": i in (1, 4), "value": 0,
                              "refValue": {"refSelected": False, "refType": 1, "refIndex": 1, "value": 30}}
        return 100, info
    raise ValueError("unknown block kind: %s" % kind)


class ChartPage:
    """一個程序頁（主流程或函式）的積木鏈"""

    def __init__(self):
        self.items = []
        self.prev = 0

    def add(self, ids, iteminfo, name=""):
        iid = len(self.items) + 1
        self.items.append({
            "parentItem": self.prev, "iteminfo": iteminfo, "x": 10, "id": iid,
            "parentItemPos": "down", "y": -38, "bColLineItem": False,
            "ids": ids, "name": name,
        })
        self.prev = iid
        return iid


DEFAULT_INIT = {"leftPort": 0, "rightPort": 3, "leftPower": -1, "rightPower": 1,
                "portType": 1, "port0": 0}


def build_project(route, tasks_by_id, functions, prog_cfg):
    """工作區 → 完整工程 dict（.chrts 內的 abilixProject.chrt）
    回傳 (project, report)；report: {"calls": seq, "empty": [未定義函式], "holes": bool}
    """
    init = dict(DEFAULT_INIT)
    init.update(prog_cfg.get("init", {}))
    start_delay = prog_cfg.get("startDelay", 1)

    seq, holes = route_call_sequence(route, tasks_by_id)
    report = {"calls": seq, "empty": [], "holes": holes, "main_inlined": False}

    # 收集所有被引用的函式名（路線需求 + 函式內部呼叫），路線需求在前
    ordered = []
    for _, name, _ in seq:
        if name not in ordered:
            ordered.append(name)

    def collect_calls(func_name, seen):
        for b in functions.get(func_name, []):
            if b["b"] == "call":
                t = b.get("p", {}).get("target")
                if t and t not in ordered and t not in seen:
                    ordered.append(t)
                    seen.add(t)
                    collect_calls(t, seen)

    for name in list(ordered):
        if name in functions:
            collect_calls(name, set())
    for name in functions:
        if name not in ordered:
            ordered.append(name)

    # 主流程頁
    main = ChartPage()
    main.add(600, {"LeftPort": init["leftPort"], "RightPort": init["rightPort"],
                   "LeftPower": init["leftPower"], "RightPower": init["rightPower"],
                   "port1": 0, "port2": 1, "port3": 2, "port4": 3, "port5": 4,
                   "portType": init["portType"], "port0": init["port0"],
                   "Note": dict(NOTE)})
    main.add(405, {"Delay": _val(start_delay),
                   "Note": dict(NOTE, value="擺放到位後啟動")})
    for _, name, desc in seq:
        main.add(2000, {"Note": dict(NOTE, value=desc)}, name=name)
    # 路線為空且 func_main 有內容 → 直接作為主程序（與 .srhs 匯出一致）
    if not seq:
        fm = functions.get("func_main") or []
        for b in fm:
            if b["b"] == "call":
                main.add(2000, {"Note": dict(NOTE)},
                         name=b.get("p", {}).get("target", ""))
            else:
                ids_, info_ = block_to_iteminfo(b)
                main.add(ids_, info_)
        if fm:
            report["main_inlined"] = True
    main.add(106, _display_lines("任務完成!"))

    pag = {"robotType": 111, "downloadName": "ProgramA.c", "name": "點對點主程序",
           "pagInfos": [{
               "type": 1, "content_scale": 1, "name": "點對點主程序",
               "main_bColLineItem": False, "itemInfos": main.items, "id": 1,
           }],
           "version": "1.1.2.5", "variableDatas": {}}

    empty = []
    for idx, fname in enumerate(ordered):
        blocks = functions.get(fname, [])
        if not blocks:
            empty.append(fname)
        page = ChartPage()
        for b in blocks:
            if b["b"] == "call":
                page.add(2000, {"Note": dict(NOTE)},
                         name=b.get("p", {}).get("target", ""))
            else:
                ids, info = block_to_iteminfo(b)
                page.add(ids, info)
        pag["pagInfos"].append({
            "type": 2, "content_scale": 1, "name": fname,
            "main_bColLineItem": False, "itemInfos": page.items, "id": idx + 2,
        })

    report = {"calls": seq, "empty": empty, "holes": holes,
              "main_inlined": report.get("main_inlined", False)}
    return pag, report


def export_chrts(path, route, tasks_by_id, functions, prog_cfg):
    """匯出 .chrts；回傳 report"""
    project, report = build_project(route, tasks_by_id, functions, prog_cfg)
    raw = b"\xef\xbb\xbf" + json.dumps(project, ensure_ascii=False).encode("utf-8")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("abilixProject.chrt", raw)
        z.comment = b"111"
    return report


def load_chrts(path):
    """讀回 .chrts（驗證用）"""
    with zipfile.ZipFile(path, "r") as z:
        raw = z.read("abilixProject.chrt")
    return json.loads(raw.decode("utf-8-sig"))
