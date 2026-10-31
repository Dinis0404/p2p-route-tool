# -*- coding: utf-8 -*-
"""
路線工作區 → AbilixScratch 3.0 (.srhs) 匯出模組
.srhs = ZIP → abilixProject.srh：
  段1 <Abilix.ScratchProject.Info>  專案資訊 XML
  段2 <Abilix.ScratchProject.ProjectString>  Blockly workspace XML
格式依據 2025 世錦賽程序實測 + WER2025程序分析.md

工作區函式格式同 chart_export（{"b": 種類, "p": 參數}），映射：
  patrol(路口巡線)      → walkline_linewayc   (field type; speed/time)
  advanced/編碼器       → walkline_lineway_e  (speed/encoder_value)
  advanced/時間         → 【不支援】Scratch 沒有按時巡線積木，匯出時跳過並警告
  turn(轉彎)            → walkline_around     (stopoption=stopPos-1; 左右速)
  motor(計時雙馬達)     → walkline_start_motor_last (左/右速/duration)
  enc_clear(編碼清零)   → resetencoder        (port)
  delay(延時)           → wait                (time)
  display(顯示)         → printf_text         (text)
  stop(停車)            → motor ch1=0 + motor ch2=0
  call(呼叫函式)        → procedures_callnoreturn (mutation name)
"""
import json
import zipfile
from xml.sax.saxutils import escape

import chart_export as ce
from chart_export import BLOCK_DEFS

SCRATCH_INIT_DEFAULT = {"leftch": 1, "rightch": 2, "port": 1}

START_DELAY_DEFAULT = 1


class _Ids:
    def __init__(self):
        self.n = 0

    def next(self):
        self.n += 1
        return "zb%05d" % self.n


def _num_el(ids, name, value):
    return ('<value name="%s"><shadow type="math_number" id="%s">'
            '<field name="NUM">%s</field></shadow></value>'
            % (name, ids.next(), value))


def _chain(blocks_xml):
    """用 <next> 串起積木列表；<next> 必須是 block 的子元素（</block> 之前）"""
    if not blocks_xml:
        return ""
    out = blocks_xml[-1]
    for b in reversed(blocks_xml[:-1]):
        i = b.rindex("</block>")
        out = b[:i] + "<next>" + out + "</next>" + b[i:]
    return out


def _block(kind, p, ids, report):
    """工作區積木 → Blockly XML 清單（stop 會展開成兩塊）；不支援回空清單"""
    if kind == "patrol":
        return ['<block type="walkline_linewayc" id="%s">'
                '<field name="type">%s</field>%s%s</block>'
                % (ids.next(), p.get("cross", 2),
                   _num_el(ids, "speed", p.get("speed", 50)),
                   _num_el(ids, "time", p.get("crossTime", 0.05)))]
    if kind == "advanced":
        if int(p.get("mode", 2)) == 2:
            return ['<block type="walkline_lineway_e" id="%s">'
                    '<field name="motor_port">0</field>%s%s</block>'
                    % (ids.next(),
                       _num_el(ids, "speed", p.get("speed", 50)),
                       _num_el(ids, "encoder_value", p.get("value", "1200")))]
        return ['<block type="walkline_linewayt" id="%s">%s%s</block>'
                % (ids.next(),
                   _num_el(ids, "speed", p.get("speed", 50)),
                   _num_el(ids, "time", p.get("value", "1")))]
    if kind == "motor_enc":
        return ['<block type="wer_set_motor_e" id="%s">'
                '<field name="motor_port">%s</field>%s%s%s</block>'
                % (ids.next(), p.get("encPort", 0),
                   _num_el(ids, "left_speed", p.get("left", 50)),
                   _num_el(ids, "right_speed", p.get("right", 50)),
                   _num_el(ids, "encoder_value", p.get("enc", "2000")))]
    if kind == "motor1":
        return ['<block type="motor_time" id="%s">'
                '<field name="channel">%s</field>%s%s</block>'
                % (ids.next(), p.get("channel", 4),
                   _num_el(ids, "speed", p.get("speed", 50)),
                   _num_el(ids, "time", p.get("seconds", 0.5)))]
    if kind == "motor_gray":
        op = p.get("cmp", "GTE")
        sensor = ('<block type="get_integrated_grayscale" id="%s">'
                  '<field name="port">%s</field>'
                  '<field name="channel">%s</field></block>'
                  % (ids.next(), p.get("port", 1), p.get("channel", 3)))
        cond = ('<block type="logic_compare" id="%s">'
                '<field name="OP">%s</field>'
                '<value name="A"><shadow type="math_number" id="%s">'
                '<field name="NUM">10</field></shadow>%s</value>'
                '<value name="B"><shadow type="math_number" id="%s">'
                '<field name="NUM">%s</field></shadow></value></block>'
                % (ids.next(), op, ids.next(), sensor, ids.next(),
                   p.get("value", 2500)))
        return ['<block type="walkline_motor_stop_until" id="%s">%s%s'
                '<value name="stopbool">'
                '<shadow type="logic_boolean"><field name="BOOL">TRUE</field></shadow>'
                '%s</value></block>'
                % (ids.next(),
                   _num_el(ids, "leftspeed", p.get("left", 60)),
                   _num_el(ids, "rightspeed", p.get("right", 60)), cond)]
    if kind == "turn":
        s = int(p.get("speed", 40))
        d = int(p.get("dir", 1))
        return ['<block type="walkline_around" id="%s">'
                '<field name="stopoption">%d</field>%s%s</block>'
                % (ids.next(), int(p.get("stopPos", 2)) - 1,
                   _num_el(ids, "leftspeed", s * d),
                   _num_el(ids, "rightspeed", -s * d))]
    if kind == "motor":
        return ['<block type="walkline_start_motor_last" id="%s">%s%s%s</block>'
                % (ids.next(),
                   _num_el(ids, "left_speed", p.get("left", 50)),
                   _num_el(ids, "right_speed", p.get("right", 50)),
                   _num_el(ids, "duration", p.get("seconds", 0.5)))]
    if kind == "enc_clear":
        return ['<block type="resetencoder" id="%s">'
                '<field name="port">%s</field></block>'
                % (ids.next(), p.get("port", 1))]
    if kind == "delay":
        return ['<block type="wait" id="%s">%s</block>'
                % (ids.next(), _num_el(ids, "time", p.get("seconds", 0.5)))]
    if kind == "display":
        return ['<block type="printf_text" id="%s">'
                '<field name="text">%s</field></block>'
                % (ids.next(), escape(str(p.get("text", "OK"))))]
    if kind == "stop":
        return ['<block type="motor" id="%s"><field name="channel">1</field>%s</block>'
                % (ids.next(), _num_el(ids, "speed", 0)),
                '<block type="motor" id="%s"><field name="channel">2</field>%s</block>'
                % (ids.next(), _num_el(ids, "speed", 0))]
    if kind == "wait_btn":
        return ['<block type="wait_until" id="%s">'
                '<value name="bool">'
                '<shadow type="logic_boolean"><field name="BOOL">TRUE</field></shadow>'
                '<block type="getai_touch" id="%s">'
                '<field name="channel">%s</field></block></value></block>'
                % (ids.next(), ids.next(), p.get("channel", 12))]
    if kind == "call":
        target = escape(str(p.get("target", "")))
        return ['<block type="procedures_callnoreturn" id="%s">'
                '<mutation name="%s"></mutation></block>' % (ids.next(), target)]
    report["skipped"].append("未知積木 %s" % kind)
    return []


def _func_blocks(blocks, ids, report):
    out = []
    for b in blocks:
        out.extend(_block(b["b"], b.get("p", {}), ids, report))
    return out


def build_project_xml(route, tasks_by_id, functions, prog_cfg):
    """→ (xml_string, report)"""
    ids = _Ids()
    report = {"skipped": [], "empty": [], "calls": [], "holes": False,
              "main_inlined": False}

    seq, holes = ce.route_call_sequence(route, tasks_by_id)
    report["calls"] = seq
    report["holes"] = holes

    # 引用收集（同 chart_export 邏輯）
    ordered = []
    for _, name, _ in seq:
        if name not in ordered:
            ordered.append(name)

    def collect(fname):
        for b in functions.get(fname, []):
            if b["b"] == "call":
                t = b.get("p", {}).get("target")
                if t and t not in ordered:
                    ordered.append(t)
                    collect(t)
    for name in list(ordered):
        if name in functions:
            collect(name)
    for name in functions:
        if name not in ordered:
            ordered.append(name)

    init = dict(ce.DEFAULT_INIT)
    init.update(prog_cfg.get("init", {}))
    sinit = dict(SCRATCH_INIT_DEFAULT)
    sinit.update(prog_cfg.get("scratchInit", {}))
    start_delay = prog_cfg.get("startDelay", START_DELAY_DEFAULT)

    # 主流程
    main = []
    main.append('<block type="walkline_init_integrated_grayscale" id="%s">'
                '<field name="leftch">%s</field><field name="leftspeed">%s</field>'
                '<field name="rightch">%s</field><field name="rightspeed">%s</field>'
                '<field name="port">%s</field></block>'
                % (ids.next(), sinit["leftch"], init["leftPower"],
                   sinit["rightch"], init["rightPower"], sinit["port"]))
    main.append('<block type="wait" id="%s">%s</block>'
                % (ids.next(), _num_el(ids, "time", start_delay)))
    for _, name, _desc in seq:
        main.extend(_block("call", {"target": name}, ids, report))
    # 路線為空（主程序沒有任何呼叫）且 func_main 有內容 → 直接作為主程序
    if not seq:
        fm = functions.get("func_main") or []
        if fm:
            main.extend(_func_blocks(fm, ids, report))
            report["main_inlined"] = True
    main.append('<block type="printf_text" id="%s">'
                '<field name="text">任務完成!</field></block>' % ids.next())

    start_x, start_y = -500, -1600
    parts = []
    parts.append('<block type="start" id="%s" deletable="false" x="%d" y="%d">'
                 '<statement name="code">%s</statement></block>'
                 % (ids.next(), start_x, start_y, _chain(main)))

    # 函式定義鋪在畫布上
    for idx, fname in enumerate(ordered):
        blocks = functions.get(fname, [])
        if not blocks:
            report["empty"].append(fname)
        if fname == "func_main" and report.get("main_inlined"):
            # 內容已放進主程序，函式定義保持空殼避免重複執行
            parts.append('<block type="procedures_defnoreturn" id="%s" x="%d" y="%d">'
                         '<field name="NAME">%s</field></block>'
                         % (ids.next(),
                            start_x + 700 + (idx % 3) * 420,
                            start_y + (idx // 3) * 520, escape(fname)))
            continue
        bx = start_x + 700 + (idx % 3) * 420
        by = start_y + (idx // 3) * 520
        inner = _chain(_func_blocks(blocks, ids, report))
        if inner:
            parts.append('<block type="procedures_defnoreturn" id="%s" x="%d" y="%d">'
                         '<field name="NAME">%s</field>'
                         '<statement name="STACK">%s</statement></block>'
                         % (ids.next(), bx, by, escape(fname), inner))
        else:
            parts.append('<block type="procedures_defnoreturn" id="%s" x="%d" y="%d">'
                         '<field name="NAME">%s</field></block>'
                         % (ids.next(), bx, by, escape(fname)))

    xml = ('<xml xmlns="http://www.w3.org/1999/xhtml">'
           '<variables></variables>%s</xml>' % "".join(parts))
    return xml, report


def build_srh(route, tasks_by_id, functions, prog_cfg, download_name="ProgramA"):
    xml, report = build_project_xml(route, tasks_by_id, functions, prog_cfg)
    doc = (
        "<Abilix.ScratchProject.Info>\n"
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ScratchProjectInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n'
        "  <Version>1.0.3.4</Version>\n"
        "  <RobotType>SKCON9</RobotType>\n"
        "  <DownloadProgramName>%s</DownloadProgramName>\n"
        "</ScratchProjectInfo>\n"
        "</Abilix.ScratchProject.Info>\n"
        "\n"
        "<Abilix.ScratchProject.ProjectString>\n"
        "%s\n"
        "</Abilix.ScratchProject.ProjectString>\n"
        % (escape(download_name), xml)
    )
    return doc, report


def export_srhs(path, route, tasks_by_id, functions, prog_cfg, download_name="ProgramA"):
    doc, report = build_srh(route, tasks_by_id, functions, prog_cfg, download_name)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("abilixProject.srh", doc.encode("utf-8"))
        z.comment = b"111"
    return report


def load_srhs_xml(path):
    """讀回第一段 ProjectString 的 XML 字串（驗證用）"""
    with zipfile.ZipFile(path, "r") as z:
        doc = z.read("abilixProject.srh").decode("utf-8")
    start = doc.index("<Abilix.ScratchProject.ProjectString>") + \
        len("<Abilix.ScratchProject.ProjectString>")
    end = doc.index("</Abilix.ScratchProject.ProjectString>")
    return doc[start:end].strip()


# ============================================================
# 匯入：.srhs → 工作區（函式 + 由主程序呼叫序列反推路線）
# ============================================================
import re
import xml.etree.ElementTree as ET

_NS = "{http://www.w3.org/1999/xhtml}"
_P2P_RE = re.compile(r"^func_(.+)_to_(.+)$")


def _q(tag):
    return _NS + tag


def _iter_chain(first):
    """沿 <next> 走積木鏈"""
    b = first
    while b is not None:
        yield b
        nxt = b.find(_q("next"))
        b = nxt.find(_q("block")) if nxt is not None else None


def _num_literal(block, name):
    """value 輸入的數字字面值；運算式回 None"""
    v = block.find(_q("value") + "[@name='%s']" % name)
    if v is None:
        return None
    for kind in ("block", "shadow"):
        el = v.find(_q(kind))
        if el is not None and el.get("type") == "math_number":
            f = el.find(_q("field"))
            if f is not None and f.text is not None:
                return f.text
    return None


def _field(block, name):
    f = block.find(_q("field") + "[@name='%s']" % name)
    return f.text if f is not None and f.text is not None else None


def _conv_block(block, stats, report):
    """Scratch 積木 → 工作區積木；無法表示回 None 並記錄原因"""
    t = block.get("type")
    disabled = block.get("disabled") == "true"
    if disabled:
        stats["停用積木"] += 1
        return None
    if t == "walkline_init_integrated_grayscale":
        # 讀入初始化設定（不計入略過）
        report["scratch_init"] = {
            "leftch": _field(block, "leftch") or "1",
            "leftspeed": _field(block, "leftspeed") or "-1",
            "rightch": _field(block, "rightch") or "2",
            "rightspeed": _field(block, "rightspeed") or "1",
            "port": _field(block, "port") or "1",
        }
        return None
    if t == "wait_until":
        v = block.find(_q("value") + "[@name='bool']")
        el = v.find(_q("block")) if v is not None else None
        if el is not None and el.get("type") == "getai_touch":
            ch = _field(el, "channel") or "12"
            try:
                channel = int(ch)
            except ValueError:
                channel = 12
            return {"b": "wait_btn", "p": {"channel": channel}}
        stats["等待直到（非按鈕條件）"] += 1
        return None
    if t == "walkline_linewayc":
        speed = _num_literal(block, "speed")
        time_v = _num_literal(block, "time")
        ctype = _field(block, "type")
        if speed is None:
            stats["速度不是數字"] += 1
            return None
        try:
            ct = float(time_v) if time_v is not None else 0.05
        except ValueError:
            ct = 0.05
        try:
            cross = int(ctype) if ctype is not None else 2
        except ValueError:
            cross = 2
        return {"b": "patrol", "p": {"speed": int(float(speed)),
                                     "cross": cross, "crossTime": ct}}
    if t == "walkline_linewayt":
        speed = _num_literal(block, "speed")
        tv = _num_literal(block, "time")
        if speed is None or tv is None:
            stats["高級巡線(計時)參數不是數字"] += 1
            return None
        return {"b": "advanced", "p": {"speed": int(float(speed)), "mode": 1,
                                       "value": tv, "port": 1}}
    if t == "wer_set_motor_e":
        l = _num_literal(block, "left_speed")
        r = _num_literal(block, "right_speed")
        enc = _num_literal(block, "encoder_value")
        mp = _field(block, "motor_port")
        if None in (l, r, enc):
            stats["雙馬達編碼參數不是數字"] += 1
            return None
        try:
            enc_port = int(mp) if mp is not None else 0
        except ValueError:
            enc_port = 0
        return {"b": "motor_enc", "p": {"left": int(float(l)),
                                        "right": int(float(r)),
                                        "enc": enc, "encPort": enc_port}}
    if t == "motor_time":
        ch = _field(block, "channel")
        sp = _num_literal(block, "speed")
        tv = _num_literal(block, "time")
        if sp is None or tv is None:
            stats["單顆電機參數不是數字"] += 1
            return None
        try:
            channel = int(ch) if ch is not None else 4
        except ValueError:
            channel = 4
        return {"b": "motor1", "p": {"channel": channel,
                                     "speed": int(float(sp)),
                                     "seconds": float(tv)}}
    if t == "walkline_motor_stop_until":
        l = _num_literal(block, "leftspeed")
        r = _num_literal(block, "rightspeed")
        cond = block.find(_q("value") + "[@name='stopbool']")
        cmp_el = cond.find(_q("block")) if cond is not None else None
        if cmp_el is None or cmp_el.get("type") != "logic_compare":
            stats["灰度停車條件不是單一比較式"] += 1
            return None
        op = _field(cmp_el, "OP") or "GTE"
        sensor = num = None
        for side in ("A", "B"):
            v = cmp_el.find(_q("value") + "[@name='%s']" % side)
            if v is None:
                continue
            el = v.find(_q("block"))
            if el is not None and el.get("type") == "get_integrated_grayscale":
                sensor = (_field(el, "port") or "1", _field(el, "channel") or "3")
            elif num is None:
                sh = v.find(_q("shadow"))
                if el is not None and el.get("type") == "math_number":
                    f = el.find(_q("field"))
                    num = f.text if f is not None else None
                elif sh is not None and sh.get("type") == "math_number":
                    f = sh.find(_q("field"))
                    num = f.text if f is not None else None
        if l is None or r is None or sensor is None or num is None:
            stats["灰度停車條件無法解析"] += 1
            return None
        if op not in ("GT", "GTE", "LT", "LTE"):
            stats["灰度停車條件無法解析"] += 1
            return None
        try:
            value = int(float(num))
            port = int(sensor[0])
            channel = int(sensor[1])
        except ValueError:
            stats["灰度停車條件無法解析"] += 1
            return None
        return {"b": "motor_gray", "p": {"left": int(float(l)),
                                         "right": int(float(r)),
                                         "port": port, "channel": channel,
                                         "cmp": op, "value": value}}
    if t == "walkline_lineway_e":
        speed = _num_literal(block, "speed")
        enc = _num_literal(block, "encoder_value")
        if speed is None or enc is None:
            stats["巡線編碼值不是數字"] += 1
            return None
        return {"b": "advanced", "p": {"speed": int(float(speed)), "mode": 2,
                                       "value": enc, "port": 1}}
    if t == "walkline_around":
        l = _num_literal(block, "leftspeed")
        r = _num_literal(block, "rightspeed")
        stop = _field(block, "stopoption")
        if l is None or r is None:
            stats["轉彎速度不是數字"] += 1
            return None
        lf, rf = float(l), float(r)
        if abs(lf) != abs(rf):
            stats["轉彎左右速不對稱"] += 1
            return None
        try:
            stop_pos = int(stop) + 1 if stop is not None else 2
        except ValueError:
            stop_pos = 2
        d = 1 if lf >= 0 else -1
        return {"b": "turn", "p": {"dir": d, "speed": int(abs(lf)),
                                   "stopPos": stop_pos}}
    if t == "walkline_start_motor_last":
        l = _num_literal(block, "left_speed")
        r = _num_literal(block, "right_speed")
        dur = _num_literal(block, "duration")
        if None in (l, r, dur):
            stats["盲走參數不是數字"] += 1
            return None
        return {"b": "motor", "p": {"left": int(float(l)),
                                    "right": int(float(r)),
                                    "seconds": float(dur)}}
    if t == "resetencoder":
        port = _field(block, "port") or "1"
        return {"b": "enc_clear", "p": {"port": int(port)}}
    if t == "wait":
        tv = _num_literal(block, "time")
        if tv is None:
            stats["延時不是數字"] += 1
            return None
        return {"b": "delay", "p": {"seconds": float(tv)}}
    if t == "printf_text":
        return {"b": "display", "p": {"text": _field(block, "text") or "OK"}}
    if t == "motor":
        # 單顆電機：只有「轉速0」的配對會在外層合成停車；其餘不支援
        stats["單顆電機積木（僅支援雙0停車配對）"] += 1
        return None
    if t == "procedures_callnoreturn":
        m = block.find(_q("mutation"))
        target = m.get("name") if m is not None else None
        if not target:
            stats["無名呼叫"] += 1
            return None
        return {"b": "call", "p": {"target": target}}
    stats["不支援的積木 " + t] += 1
    return None


def _collapse_stops(ws_blocks, stats):
    """把相鄰的 電機1=0 + 電機2=0 合成 stop；沒配對成功就計入不支援
    做法：解析前先在 scratch 鏈上做，這裡退而求其次——由呼叫方處理"""
    return ws_blocks


def parse_srhs(path, tasks_by_func=None, valid_stations=None):
    """.srhs → {"functions": {...}, "route": [...]|None, "report": {...}}"""
    from collections import Counter
    xml_str = load_srhs_xml(path)
    root = ET.fromstring(xml_str)
    functions = {}
    report = {"fn_stats": {}, "main_calls": [], "unmatched_calls": [],
              "route_note": "", "main_imported": False}

    def convert_chain(first):
        stats = Counter()
        ws = []
        pending_zero = None   # 等待配對的 停車一半（通道 '1' 或 '2'）
        ORPHAN = "單顆電機積木（僅支援雙0停車配對）"
        for blk in _iter_chain(first):
            t = blk.get("type")
            if t == "motor":
                ch = _field(blk, "channel")
                sp = _num_literal(blk, "speed")
                is_zero = (ch in ("1", "2") and sp is not None
                           and float(sp) == 0)
                if is_zero and pending_zero is None:
                    pending_zero = ch
                elif is_zero and pending_zero != ch:
                    ws.append({"b": "stop", "p": {}})   # 1+2 配對成功
                    pending_zero = None
                else:
                    if pending_zero is not None:
                        pending_zero = None
                    stats[ORPHAN] += 1
                continue
            if pending_zero is not None:
                stats[ORPHAN] += 1
                pending_zero = None
            conv = _conv_block(blk, stats, report)
            if conv:
                ws.append(conv)
        return ws, stats

    # 函式定義
    for proc in root.iter(_q("block")):
        if proc.get("type") != "procedures_defnoreturn":
            continue
        name = _field(proc, "NAME")
        if not name:
            continue
        st = proc.find(_q("statement") + "[@name='STACK']")
        first = st.find(_q("block")) if st is not None else None
        ws, stats = convert_chain(first)
        functions[name] = ws
        report["fn_stats"][name] = dict(stats)

    # 沒有任何函式定義 → 把主程序整串匯入為一個函式
    if not functions:
        start = None
        for b in root.iter(_q("block")):
            if b.get("type") == "start":
                start = b
                break
        if start is not None:
            st = start.find(_q("statement") + "[@name='code']")
            first = st.find(_q("block")) if st is not None else None
            ws, stats = convert_chain(first)
            if ws:
                functions["func_main"] = ws
                report["fn_stats"]["func_main"] = dict(stats)
                report["main_imported"] = True

    # 主程序呼叫序列 → 反推路線（會走進 while/if 的 statement 內部）
    start = None
    for b in root.iter(_q("block")):
        if b.get("type") == "start":
            start = b
            break
    route = None
    if start is not None:
        calls = []

        def collect_calls(block):
            for blk in _iter_chain(block):
                if blk.get("type") == "procedures_callnoreturn":
                    m = blk.find(_q("mutation"))
                    if m is not None and m.get("name"):
                        calls.append(m.get("name"))
                for st_el in blk.findall(_q("statement")):
                    inner = st_el.find(_q("block"))
                    if inner is not None:
                        collect_calls(inner)

        st = start.find(_q("statement") + "[@name='code']")
        first = st.find(_q("block")) if st is not None else None
        if first is not None:
            collect_calls(first)
        report["main_calls"] = calls
        stations = []
        cur_task_idx = []
        route_entries = []

        def last_entry():
            return route_entries[-1] if route_entries else None

        for name in calls:
            m = _P2P_RE.match(name)
            if m:
                a, b2 = m.group(1), m.group(2)
                if valid_stations is not None:
                    if a not in valid_stations or b2 not in valid_stations:
                        report["unmatched_calls"].append(name + "（站點不在地圖上）")
                        continue
                if not route_entries:
                    route_entries.append({"id": a, "task": None})
                    route_entries.append({"id": b2, "task": None})
                elif last_entry()["id"] == a:
                    route_entries.append({"id": b2, "task": None})
                elif last_entry()["id"] == b2:
                    pass
                else:
                    route_entries.append({"id": a, "task": None})
                    route_entries.append({"id": b2, "task": None})
                continue
            if name.startswith("func_task_"):
                fid = name[len("func_task_"):]
                tid = (tasks_by_func or {}).get(fid)
                le = last_entry()
                if tid and le is not None and le["id"] not in (None,):
                    if le.get("task"):
                        report["unmatched_calls"].append(
                            name + "（%s 已有任務，忽略）" % le["id"])
                    else:
                        le["task"] = tid
                elif not tid:
                    report["unmatched_calls"].append(name + "（config 沒這個任務）")
                continue
            report["unmatched_calls"].append(name + "（自訂函式，不影響路線）")
        if route_entries:
            route = route_entries
        if report["unmatched_calls"]:
            report["route_note"] = "有 %d 個呼叫無法對應到路線" % len(report["unmatched_calls"])
    return {"functions": functions, "route": route, "report": report}
