# -*- coding: utf-8 -*-
"""
黑白示意圖產生器：只畫路線（黑線）與站點（圓圈），輸出 map_bw.png
- 座標以 1439x620 為基準，輸出 2 倍大小（2878x1240）方便放大檢視
- 跑一次會順手把站點座標同步進 config.json 的 "schematic" 欄位
- 想調整版面：改下面 SCHEMATIC / LINES / JUNCTIONS 再重跑本腳本
"""
import json
import os
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "map_bw.png")
CONFIG_PATH = os.path.join(BASE, "config.json")

BASE_W, BASE_H = 1439, 620
FINAL_SCALE = 2          # 輸出 2 倍圖
SS = 2                   # 超採樣倍數（抗鋸齒）
K = FINAL_SCALE * SS

# 站點圓圈中心（1439x620 座標系）
SCHEMATIC = {
    '01': (320, 85),  '02': (560, 85),  '03': (800, 85),  '04': (1045, 85),
    '10': (75, 250),  '05': (1370, 250),
    '09': (75, 420),  '06': (1370, 420),
    '08': (390, 555), '07': (1045, 555),
    'S':  (710, 520),
}

# 路線線段（站點圓邊到圓邊 / 交叉點）
LINES = [
    ((320, 117), (320, 340)),      # 01 垂線（過十字路口後到死端）
    ((560, 117), (560, 250)),      # 02 垂線
    ((800, 117), (800, 340)),      # 03 垂線
    ((1045, 117), (1045, 523)),    # 04—07 長垂線
    ((107, 250), (800, 250)),      # 10—03 橫線（上排）
    ((710, 340), (950, 340)),      # 起點角—中橫線東端（死端）
    ((107, 420), (390, 420)),      # 09 橫線
    ((390, 420), (390, 523)),      # 09 線轉角下行到 08
    ((1045, 250), (1338, 250)),    # 04線—05 橫線
    ((1045, 420), (1338, 420)),    # 04線—06 橫線
    ((710, 340), (710, 488)),      # 起點上行線
]

# 交叉點（三叉以上）實心點
JUNCTIONS = [
    (320, 250),   # 01 十字路口（上=01 下=短枝 左右=10線）
    (560, 250),   # 02 T字路口
    (800, 250),   # 03線×10線 T字路口
    (800, 340),   # 03線×中橫線 T字路口
    (1045, 250),  # 05 T字路口
    (1045, 420),  # 06 T字路口
]

LINE_W = 12
CIRC_R = 32
CIRC_BORDER = 8
DOT_R = 9
FONT_SZ = 34
CAP_SZ = 24


def get_font(size):
    for p in (r"C:\Windows\Fonts\msjhbd.ttc", r"C:\Windows\Fonts\msjh.ttc",
              r"C:\Windows\Fonts\arialbd.ttf"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def draw_map():
    W, H = BASE_W * K, BASE_H * K
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    def px(p):
        return (p[0] * K, p[1] * K)

    # 路線
    for a, b in LINES:
        d.line([px(a), px(b)], fill="black", width=LINE_W * K)

    # 交叉點
    for j in JUNCTIONS:
        x, y = px(j)
        r = DOT_R * K
        d.ellipse([x - r, y - r, x + r, y + r], fill="black")

    # 站點圓圈
    f_num = get_font(FONT_SZ * K)
    for sid, (sx, sy) in SCHEMATIC.items():
        x, y = px((sx, sy))
        r = CIRC_R * K
        bw = CIRC_BORDER * K
        if sid == "S":   # 起點雙圈強調
            r2 = (CIRC_R + 11) * K
            d.ellipse([x - r2, y - r2, x + r2, y + r2], fill="white", outline="black", width=bw)
        d.ellipse([x - r, y - r, x + r, y + r], fill="white", outline="black", width=bw)
        bbox = d.textbbox((0, 0), sid, font=f_num)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text((x - tw / 2 - bbox[0], y - th / 2 - bbox[1]), sid,
               fill="black", font=f_num)

    # 起點說明文字
    f_cap = get_font(CAP_SZ * K)
    cap = "起點 / 終點"
    cx, cy = px((SCHEMATIC["S"][0], SCHEMATIC["S"][1] + CIRC_R + 34))
    bbox = d.textbbox((0, 0), cap, font=f_cap)
    tw = bbox[2] - bbox[0]
    d.text((cx - tw / 2, cy), cap, fill="black", font=f_cap)

    out = img.resize((BASE_W * FINAL_SCALE, BASE_H * FINAL_SCALE), Image.LANCZOS)
    out.save(OUT)
    print("saved", OUT, out.size)
    return out


def sync_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["schematic"] = {
            "image": "map_bw.png",
            "stations": {k: [v[0], v[1]] for k, v in SCHEMATIC.items()},
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print("config.json schematic synced")
    except Exception as e:
        print("config sync skipped:", e)


if __name__ == "__main__":
    draw_map()
    sync_config()
