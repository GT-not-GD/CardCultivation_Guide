#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【卡牌修仙传】图鉴自动抓取工具（Windows · 1920×1080 全屏 / 无边框全屏）

两阶段流程：
  第 1 阶段（需要占用鼠标，速度快）：
      自动识别当前分类 → 左侧卡牌网格逐张点击 → 截取卡牌、右侧大图标、标题
      → 右侧说明文字超出时自动向下滚动并“像素级无缝拼接”成完整长图
      → 左侧网格自动向下滚动直到最后一张；每抓完一张立即存档（可断点续抓）。
  第 2 阶段（鼠标已释放，可离开游戏）：
      离线中文 OCR（RapidOCR · PP-OCRv5）识别 → 楷体形近字修正
      → 段落 / 【小标题】结构化 → 生成 docs/data/*.json + docs/index.html 攻略网页。

热键：
  F9          暂停 / 继续
  F10 或 F12  立即停止（已抓取的内容会保存，下次运行自动续抓）
  把鼠标甩到屏幕左上角 (0,0)  紧急停止
  运行中如果你手动移动了鼠标，脚本会自动暂停，按 F9 继续

常用命令：
  python capture_tujian.py                   # 抓取当前分类（默认 5 秒倒计时）
  python capture_tujian.py --fresh           # 丢弃旧进度，从头重新抓取当前分类
  python capture_tujian.py --update-locked   # 补全模式：只检查之前【未获得】的卡，获得了就补抓
  python capture_tujian.py --ocr-only        # 只对已抓取的截图重新 OCR 并生成网页
  python capture_tujian.py --high-accuracy   # 使用更大的 PP-OCRv5 server 模型（更准、更慢）
  python capture_tujian.py --test-image a.png  # 用一张游戏截图做离线自检（不动鼠标）
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
CAPTURE_DIR = BASE_DIR / "captures"
DOCS_DIR = BASE_DIR / "docs"
DATA_DIR = DOCS_DIR / "data"
ASSET_DIR = DOCS_DIR / "assets"

IS_WINDOWS = sys.platform == "win32"

# 控制台 UTF-8 输出（防止 Windows 旧控制台中文乱码 / 报错）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# =====================================================================
#  界面几何参数（以 1920×1080 为基准，其他 16:9 分辨率会自动等比缩放）
# =====================================================================
REF_W, REF_H = 1920, 1080

TOP_TABS: List[Tuple[str, int, int]] = [
    ("卡牌", 214, 425),
    ("人物", 438, 649),
    ("剧情", 662, 873),
    ("法宝&傀儡", 886, 1097),
    ("灵兽", 1110, 1321),
    ("妖兽", 1334, 1545),
    ("妖王", 1558, 1769),
]
TOP_TAB_Y = (38, 85)

SUB_TABS: List[Tuple[str, int, int]] = [
    ("材料", 185, 237),
    ("灵草&丹药", 242, 294),
    ("感悟&心法", 299, 351),
    ("技能&口诀", 356, 408),
    ("道具&传闻", 413, 464),
    ("指点卡", 470, 521),
    ("载具", 527, 578),
    ("天赋", 584, 635),
]
SUB_TAB_X = (225, 395)

TOP_SLUGS = {
    "卡牌": "kapai", "人物": "renwu", "剧情": "juqing", "法宝&傀儡": "fabao_kuilei",
    "灵兽": "lingshou", "妖兽": "yaoshou", "妖王": "yaowang",
}
SUB_SLUGS = {
    "材料": "cailiao", "灵草&丹药": "lingcao_danyao", "感悟&心法": "ganwu_xinfa",
    "技能&口诀": "jineng_koujue", "道具&传闻": "daoju_chuanwen", "指点卡": "zhidianka",
    "载具": "zaiju", "天赋": "tianfu",
}

# 左侧卡牌网格
GRID_COLS: List[Tuple[int, int]] = [
    (428, 551), (565, 689), (703, 826), (840, 964), (978, 1101), (1115, 1239),
]
GRID_BOX = (427, 132, 1241, 910)          # x1, y1, x2, y2（右/下为开区间）
GRID_SAFE_POINT = (833, 515)              # 第 3、4 列之间的羊皮纸空隙，滚轮/拖动都从这里开始
GRID_PITCH = 182                          # 行距
CARD_H_RANGE = (150, 178)                 # 完整卡牌高度
CARD_Y_MIN, CARD_Y_MAX = 135, 907         # 完整卡牌必须完全位于可视区域内
GRID_TARGET_STEP = 380                    # 每次滚动目标像素（远小于不漏行上限 611）
GRID_MAX_SAFE_STEP = 611

# 右侧详情面板
ICON_BOX = (1350, 126, 1667, 330)
TITLE_BOX = (1258, 332, 1774, 386)
BODY_BOX = (1258, 395, 1774, 895)         # 516×500 可滚动正文视口
BODY_POINT = (1515, 645)
BODY_TARGET_STEP = 260
BODY_OVERFLOW_Y = 380                     # 正文最后一行墨迹低于此值才需要滚动
DETAIL_CHANGE_BOX = (1258, 126, 1774, 386)  # 图标 + 标题：判断详情是否已切换

# 屏幕校验参考值
PARCH_P1 = ((150, 290, 1270, 1345), (229.8, 221.3, 202.7))
PARCH_P2 = ((670, 850, 225, 395), (229.0, 218.6, 197.5))

# 楷体常见 OCR 形近字修正（只收录不会误伤正常词语的组合）
KAITI_FIXES: List[Tuple[str, str]] = [
    ("获取途泾", "获取途径"),
    ("途泾", "途径"),
    ("义定", "必定"),
    ("义须", "必须"),
    ("义然", "必然"),
    ("义要", "必要"),
    ("务义", "务必"),
    ("何义", "何必"),
    ("义不可少", "必不可少"),
    ("末必", "未必"),
]

LOW_CONF = 0.96

# 未获得卡牌的浅褐色底板颜色
LOCKED_RGB = np.array([212.0, 198.0, 171.0], dtype=np.float32)
LOCKED_TOL = 15.0
GRID_FIRST_ROW_Y = 152                    # 列表滚到顶部时第一行卡牌的 y1


class StopRequested(Exception):
    """用户按下停止热键或触发了左上角紧急停止。"""


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# =====================================================================
#  Win32：DPI 感知 + SendInput 鼠标（64 位安全）+ 热键
# =====================================================================
def set_dpi_awareness() -> None:
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # Per-Monitor DPI aware
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def is_admin() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


if IS_WINDOWS:
    from ctypes import wintypes as wt

    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
            ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
            ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


class MouseInput:
    INPUT_MOUSE = 0
    MOVE, LEFTDOWN, LEFTUP, WHEEL = 0x0001, 0x0002, 0x0004, 0x0800
    VIRTUALDESK, ABSOLUTE = 0x4000, 0x8000

    def __init__(self) -> None:
        if not IS_WINDOWS:
            raise RuntimeError("鼠标控制仅支持 Windows。")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.SendInput.argtypes = (wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        self.user32.SendInput.restype = wt.UINT
        self.user32.GetCursorPos.argtypes = (ctypes.POINTER(wt.POINT),)
        self.user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
        self.user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
        self.user32.GetAsyncKeyState.restype = ctypes.c_short
        gsm = self.user32.GetSystemMetrics
        self.vx, self.vy = gsm(76), gsm(77)
        self.vw, self.vh = max(gsm(78), 1), max(gsm(79), 1)
        self.expected: Optional[Tuple[int, int]] = None
        self.blocked_warned = False

    def _send(self, flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> None:
        inp = INPUT(type=self.INPUT_MOUSE)
        inp.mi = MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)
        sent = self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if sent != 1 and not self.blocked_warned:
            self.blocked_warned = True
            log("⚠ SendInput 被系统拦截：游戏可能以【管理员身份】运行，请右键“开始抓取.bat”→以管理员身份运行。")

    def cursor_pos(self) -> Tuple[int, int]:
        pt = wt.POINT()
        self.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def move(self, x: int, y: int) -> None:
        nx = int(round((x - self.vx) * 65535 / max(self.vw - 1, 1)))
        ny = int(round((y - self.vy) * 65535 / max(self.vh - 1, 1)))
        self._send(self.MOVE | self.ABSOLUTE | self.VIRTUALDESK, nx, ny)
        cx, cy = self.cursor_pos()
        if abs(cx - x) > 2 or abs(cy - y) > 2:
            self.user32.SetCursorPos(int(x), int(y))
        self.expected = (int(x), int(y))

    def down(self) -> None:
        self._send(self.LEFTDOWN)

    def up(self) -> None:
        self._send(self.LEFTUP)

    def click(self, x: int, y: int) -> None:
        self.move(x, y)
        time.sleep(0.06)
        self.down()
        time.sleep(0.07)
        self.up()

    def wheel(self, x: int, y: int, notches: int) -> None:
        """notches > 0 向下滚动，< 0 向上滚动。"""
        self.move(x, y)
        time.sleep(0.05)
        step = -120 if notches > 0 else 120
        for _ in range(abs(int(notches))):
            self._send(self.WHEEL, data=step)
            time.sleep(0.025)

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.45) -> None:
        """平滑拖动；松手前静止 0.12s，消除 Unity ScrollRect 惯性。"""
        self.move(x1, y1)
        time.sleep(0.06)
        self.down()
        time.sleep(0.10)
        steps = max(12, int(duration / 0.015))
        for i in range(1, steps + 1):
            t = i / steps
            e = t * t * (3 - 2 * t)
            self.move(int(round(x1 + (x2 - x1) * e)), int(round(y1 + (y2 - y1) * e)))
            time.sleep(duration / steps)
        self.move(x2, y2)
        time.sleep(0.12)
        self.up()
        time.sleep(0.05)

    def key_down(self, vk: int) -> bool:
        return bool(self.user32.GetAsyncKeyState(vk) & 0x8000)


class Controller:
    """后台热键线程：F9 暂停/继续，F10/F12 停止，左上角紧急停止，手动动鼠标自动暂停。"""

    VK_F9, VK_F10, VK_F12 = 0x78, 0x79, 0x7B

    def __init__(self, mouse: MouseInput, origin: Tuple[int, int]) -> None:
        self.mouse = mouse
        self.origin = origin
        self.paused = False
        self.stop = False
        self._prev = {self.VK_F9: False}
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self.stop:
            try:
                f9 = self.mouse.key_down(self.VK_F9)
                if f9 and not self._prev[self.VK_F9]:
                    self.paused = not self.paused
                    if self.paused:
                        log("⏸ 已暂停（按 F9 继续，F10 停止并保存）")
                    else:
                        self.mouse.expected = None
                        log("▶ 继续运行")
                self._prev[self.VK_F9] = f9
                if self.mouse.key_down(self.VK_F10) or self.mouse.key_down(self.VK_F12):
                    log("⏹ 收到停止热键，正在保存进度……")
                    self.stop = True
                cx, cy = self.mouse.cursor_pos()
                if abs(cx - self.mouse.vx) <= 1 and abs(cy - self.mouse.vy) <= 1:
                    log("⏹ 检测到鼠标位于屏幕左上角，紧急停止。")
                    self.stop = True
            except Exception:
                pass
            time.sleep(0.04)

    def checkpoint(self) -> None:
        exp = self.mouse.expected
        if exp is not None and not self.paused and not self.stop:
            cx, cy = self.mouse.cursor_pos()
            if abs(cx - exp[0]) > 60 or abs(cy - exp[1]) > 60:
                self.paused = True
                log("⏸ 检测到你手动移动了鼠标，已自动暂停。切回游戏图鉴界面后按 F9 继续。")
        while self.paused and not self.stop:
            time.sleep(0.1)
        if self.stop:
            raise StopRequested()


# =====================================================================
#  截图：mss，多显示器，非 1080p 自动缩放到 1920×1080 参考坐标
# =====================================================================
class Screen:
    def __init__(self, monitor_index: int = 1) -> None:
        import mss  # 延迟导入，便于在非 Windows 环境做离线自检

        self.sct = mss.mss()
        mons = self.sct.monitors
        if monitor_index < 1 or monitor_index >= len(mons):
            log(f"⚠ 显示器编号 {monitor_index} 不存在，改用主显示器 1。")
            monitor_index = 1
        self.mon = mons[monitor_index]
        self.left, self.top = self.mon["left"], self.mon["top"]
        self.width, self.height = self.mon["width"], self.mon["height"]
        self.sx, self.sy = self.width / REF_W, self.height / REF_H
        self.scaled = (self.width, self.height) != (REF_W, REF_H)
        log(f"显示器 {monitor_index}: {self.width}×{self.height} @ ({self.left},{self.top})"
            + ("（将自动缩放到 1920×1080 坐标）" if self.scaled else ""))
        if abs(self.width / self.height - 16 / 9) > 0.02:
            log("⚠ 屏幕不是 16:9，游戏界面布局可能与 1920×1080 不同，识别可能失败。")

    def grab(self) -> np.ndarray:
        shot = self.sct.grab(self.mon)
        arr = np.asarray(shot)[:, :, :3][:, :, ::-1]
        if self.scaled:
            arr = np.asarray(Image.fromarray(arr).resize((REF_W, REF_H), Image.LANCZOS))
        return np.ascontiguousarray(arr)

    def to_screen(self, x: float, y: float) -> Tuple[int, int]:
        return self.left + int(round(x * self.sx)), self.top + int(round(y * self.sy))


# =====================================================================
#  纯图像分析（可离线单元测试）
# =====================================================================
def crop(arr: np.ndarray, box: Tuple[int, int, int, int]) -> np.ndarray:
    x1, y1, x2, y2 = box
    return arr[y1:y2, x1:x2]


def mean_abs_diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


def verify_tujian_screen(arr: np.ndarray) -> Tuple[bool, Dict[str, Any]]:
    """判断当前画面是否是图鉴界面（羊皮纸底色 + 深色边框）。"""
    f = arr.astype(np.float32)
    info: Dict[str, Any] = {}
    checks = 0
    for name, ((y1, y2, x1, x2), ref) in (("p1", PARCH_P1), ("p2", PARCH_P2)):
        patch = f[y1:y2, x1:x2].reshape(-1, 3)
        mean, std = patch.mean(0), patch.std(0)
        ok = bool(np.all(np.abs(mean - np.array(ref)) < 22) and np.all(std < 14))
        info[name] = {"mean": mean.round(1).tolist(), "std": std.round(1).tolist(), "ok": ok}
        checks += ok
    left = float(f[300:700, 186:193].mean())
    bottom = float(f[920:923, 500:1500].mean())
    info["border_left"], info["border_bottom"] = round(left, 1), round(bottom, 1)
    checks += left < 70
    checks += bottom < 95
    info["score"] = checks
    return checks >= 3, info


def detect_top_tab(arr: np.ndarray) -> Tuple[Optional[str], float]:
    y1, y2 = TOP_TAB_Y
    vals = []
    for name, x1, x2 in TOP_TABS:
        reg = arr[y1 + 6:y2 - 6, x1 + 12:x2 - 12].astype(np.float32)
        vals.append((float(reg[:, :, :2].mean()), name))
    vals.sort(reverse=True)
    best, name = vals[0]
    margin = best - vals[1][0]
    return (name if best > 175 and margin > 35 else None), round(best, 1)


def detect_sub_tab(arr: np.ndarray) -> Tuple[Optional[str], float]:
    x1, x2 = SUB_TAB_X
    vals = []
    for name, y1, y2 in SUB_TABS:
        reg = arr[y1 + 8:y2 - 8, x1:x2].astype(np.float32)
        vals.append((float((reg[:, :, 0] - reg[:, :, 1]).mean()), name))
    vals.sort(reverse=True)
    best, name = vals[0]
    margin = best - vals[1][0]
    return (name if margin > 6 else None), round(margin, 1)


def _runs(mask: np.ndarray, offset: int, close_gap: int = 3) -> List[Tuple[int, int]]:
    runs: List[List[int]] = []
    start = None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append([start, i - 1])
            start = None
    if start is not None:
        runs.append([start, len(mask) - 1])
    merged: List[List[int]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] - 1 <= close_gap:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [(a + offset, b + offset) for a, b in merged]


def detect_cards(arr: np.ndarray) -> List[Dict[str, Any]]:
    """检测每列中的卡牌（含被裁切的半张）。

    已获得的卡牌：左右两侧有深色内边框；
    未获得的卡牌：整张是一块颜色均匀的浅褐色底板 RGB≈(212,198,171)，比周围羊皮纸略深。
    两种都会被检测出来，并用 card["locked"] 标记是否未获得。
    """
    gx1, gy1, gx2, gy2 = GRID_BOX
    f = arr[gy1:gy2].astype(np.float32)
    bri = f.mean(2)
    cards: List[Dict[str, Any]] = []
    for col, (x1, x2) in enumerate(GRID_COLS):
        # 取内边框若干列的最小亮度：选中卡牌外圈白光会“渗”进边框，用最小值更稳
        left = bri[:, x1 + 1:x1 + 7].min(1)
        right = bri[:, x2 - 7:x2 - 1].min(1)
        dark = (left < 165) & (right < 165)
        dl = np.median(np.sqrt(((f[:, x1 + 3:x1 + 10] - LOCKED_RGB) ** 2).sum(2)), 1)
        dr = np.median(np.sqrt(((f[:, x2 - 9:x2 - 2] - LOCKED_RGB) ** 2).sum(2)), 1)
        pale = (dl < LOCKED_TOL) & (dr < LOCKED_TOL)
        for mask, kind in ((dark, False), (pale & ~dark, True)):
            for a, b in _runs(mask, gy1):
                h = b - a + 1
                if h < 12:
                    continue
                complete = (CARD_H_RANGE[0] <= h <= CARD_H_RANGE[1]
                            and a >= CARD_Y_MIN and b <= CARD_Y_MAX)
                card = {"col": col, "x1": x1, "x2": x2, "y1": a, "y2": b,
                        "h": h, "complete": complete, "locked": kind}
                if complete and not kind:
                    # 深色边框检测到的卡，再用卡头亮度复核一次是否真的已获得
                    hdr = bri[a - gy1 + 6:a - gy1 + 40, x1 + 8:x2 - 8]
                    card["locked"] = bool(hdr.size and hdr.mean() > 150)
                cards.append(card)
    # 按“行”分组排序（同一行卡牌 y1 相差不超过 25px）
    cards.sort(key=lambda c: c["y1"])
    row_id, last_y = -1, -999
    for c in cards:
        if c["y1"] - last_y > 25:
            row_id += 1
            last_y = c["y1"]
        c["_row"] = row_id
    cards.sort(key=lambda c: (c["_row"], c["col"]))
    for c in cards:
        c.pop("_row", None)
    return cards


def selection_score(arr: np.ndarray, card: Dict[str, Any]) -> float:
    """选中卡牌外圈有一道白色光边：统计边框外 2~4px 的纯白像素比例。"""
    x1, y1, x2, y2 = card["x1"], card["y1"], card["x2"], card["y2"]
    H, W = arr.shape[:2]
    strips = []
    if y1 - 4 >= 0:
        strips.append(arr[y1 - 4:y1 - 1, x1:x2])
    if y2 + 5 <= H:
        strips.append(arr[y2 + 2:y2 + 5, x1:x2])
    strips.append(arr[y1:y2, max(x1 - 4, 0):x1 - 1].transpose(1, 0, 2))
    strips.append(arr[y1:y2, x2 + 2:min(x2 + 5, W)].transpose(1, 0, 2))
    tot = cnt = 0
    for s in strips:
        s = s.reshape(-1, 3)
        if not len(s):
            continue
        white = (s[:, 0] > 245) & (s[:, 1] > 245) & (s[:, 2] > 242)
        cnt += int(white.sum())
        tot += len(s)
    return cnt / tot if tot else 0.0


def ink_map(region: np.ndarray, threshold: Optional[float] = None) -> np.ndarray:
    """逐行 85 百分位背景扣除，消除羊皮纸折痕。返回墨迹强度（或二值图）。"""
    f = region.astype(np.float32)
    bg = np.percentile(f, 85, axis=1, keepdims=True)
    d = np.sqrt(((f - bg) ** 2).sum(2))
    if threshold is None:
        return np.clip(d - 20, 0, 120)
    return d > threshold


def last_ink_row(body: np.ndarray) -> int:
    ink = ink_map(body, 48)
    rows = np.where(ink.sum(1) >= 3)[0]
    return int(rows[-1]) if len(rows) else -1


def estimate_body_shift(prev: np.ndarray, cur: np.ndarray, min_overlap: int = 60) -> Tuple[int, float]:
    """估计正文视口内容向上移动了多少像素（基于墨迹图的二维匹配）。"""
    A = ink_map(prev)[:, ::2]
    B = ink_map(cur)[:, ::2]
    H = A.shape[0]
    best_s, best = 0, 1e9
    for s in range(0, H - min_overlap):
        a = A[s:]
        b = B[:H - s]
        tot = a.sum() + b.sum()
        if tot < 3000:
            continue
        score = float(np.abs(a - b).sum() / tot)
        if score < best:
            best, best_s = score, s
    return best_s, best


def estimate_grid_shift(prev: np.ndarray, cur: np.ndarray, min_overlap: int = 100) -> Tuple[int, float]:
    """估计左侧网格内容向上移动的像素数（灰度二维匹配，卡面图案保证唯一性）。"""
    A = crop(prev, GRID_BOX).astype(np.float32).mean(2)[:, ::2]
    B = crop(cur, GRID_BOX).astype(np.float32).mean(2)[:, ::2]
    H = A.shape[0]
    best_s, best = 0, 1e9
    for s in range(0, H - min_overlap):
        score = float(np.abs(A[s:] - B[:H - s]).mean())
        if score < best:
            best, best_s = score, s
    return best_s, best


def stitch_body(canvas: np.ndarray, top: int, frame: np.ndarray, shift: int) -> Tuple[np.ndarray, int]:
    """把新一帧拼到长图上：在重叠区中找一行“没有墨迹”的空白行作为接缝，避免切断文字。"""
    new_top = top + shift
    H = frame.shape[0]
    overlap = H - shift
    ink_new = ink_map(frame, 48).sum(1).astype(np.float32)
    old_rows = canvas[new_top:new_top + overlap]
    ink_old = ink_map(old_rows, 48).sum(1).astype(np.float32) if len(old_rows) else np.zeros(0)
    lo = max(4, int(overlap * 0.25))
    hi = max(lo + 1, overlap - 8)
    cost = ink_new[lo:hi].copy()
    if len(ink_old) >= hi:
        cost += ink_old[lo:hi]
    # 同等空白时优先选靠下的接缝（让新帧覆盖被视口底部裁切的半行字）
    cost = cost - np.linspace(0, 0.5, len(cost))
    r = lo + int(np.argmin(cost))
    out = np.concatenate([canvas[:new_top + r], frame[r:]], axis=0)
    return out, new_top


# =====================================================================
#  OCR 引擎（RapidOCR · PP-OCRv5，自动回退）
# =====================================================================
class OcrEngine:
    def __init__(self, high_accuracy: bool = False) -> None:
        self.kind = ""
        err = None
        try:
            from rapidocr import ModelType, OCRVersion, RapidOCR

            mt = ModelType.SERVER if high_accuracy else ModelType.MOBILE
            try:
                self.engine = RapidOCR(params={
                    "Det.ocr_version": OCRVersion.PPOCRV5, "Det.model_type": mt,
                    "Rec.ocr_version": OCRVersion.PPOCRV5, "Rec.model_type": mt,
                })
                self.kind = "PP-OCRv5 " + ("server" if high_accuracy else "mobile")
            except Exception as e:
                if not high_accuracy:
                    raise
                log(f"⚠ server 模型不可用（{e}），改用 mobile 模型。")
                self.engine = RapidOCR(params={
                    "Det.ocr_version": OCRVersion.PPOCRV5, "Det.model_type": ModelType.MOBILE,
                    "Rec.ocr_version": OCRVersion.PPOCRV5, "Rec.model_type": ModelType.MOBILE,
                })
                self.kind = "PP-OCRv5 mobile"
        except Exception as e:
            err = e
            try:
                from rapidocr import RapidOCR

                self.engine = RapidOCR()
                self.kind = "rapidocr-default"
            except Exception:
                try:
                    from rapidocr_onnxruntime import RapidOCR as LegacyOCR

                    self.engine = LegacyOCR()
                    self.kind = "legacy"
                except Exception as e2:
                    raise RuntimeError(f"无法加载 OCR 引擎：{err} / {e2}。请先运行“一键安装依赖.bat”。")
        if err is not None:
            log(f"⚠ PP-OCRv5 初始化失败（{err}），已回退到 {self.kind}，识别率可能下降。")

    @staticmethod
    def _bgr(img: Image.Image) -> np.ndarray:
        return np.ascontiguousarray(np.asarray(img.convert("RGB"))[:, :, ::-1])

    def detect(self, img: Image.Image) -> List[Tuple[np.ndarray, str, float]]:
        if self.kind == "legacy":
            res, _ = self.engine(self._bgr(img), use_det=True, use_cls=False, use_rec=True)
            return [(np.array(b, dtype=np.float32), str(t), float(s)) for b, t, s in (res or [])]
        # 注意：rapidocr 会记住上一次调用的 use_det 等开关，所以每次都显式传入
        out = self.engine(img, use_det=True, use_cls=False, use_rec=True)
        if getattr(out, "boxes", None) is None or getattr(out, "txts", None) is None:
            return []
        return [(np.array(b, dtype=np.float32), str(t), float(s))
                for b, t, s in zip(out.boxes, out.txts, out.scores)]

    def rec(self, img: Image.Image) -> Tuple[str, float]:
        try:
            if self.kind == "legacy":
                res, _ = self.engine(self._bgr(img), use_det=False, use_cls=False, use_rec=True)
                if res:
                    return str(res[0][0]), float(res[0][1])
                return "", 0.0
            out = self.engine(img, use_det=False, use_cls=False, use_rec=True)
            txts = getattr(out, "txts", None) or ()
            scores = getattr(out, "scores", None) or ()
            if txts:
                return str(txts[0]), float(scores[0])
        except Exception:
            pass
        return "", 0.0


# =====================================================================
#  文本后处理与段落结构化
# =====================================================================
CJK = r"\u4e00-\u9fff\u3000-\u303f\uff00-\uffef"


def clean_text(s: str) -> Tuple[str, bool]:
    orig = s
    s = s.strip().replace(" ", "").replace("\u3000", "")
    for a, b in KAITI_FIXES:
        s = s.replace(a, b)
    # 中文语境下的半角标点 → 全角
    s = re.sub(rf"(?<=[{CJK}]),|,(?=[{CJK}])", "，", s)
    s = re.sub(rf"(?<=[{CJK}]);|;(?=[{CJK}])", "；", s)
    s = re.sub(rf"(?<=[{CJK}]):|:(?=[{CJK}])", "：", s)
    s = re.sub(rf"(?<=[{CJK}])!|!(?=[{CJK}])", "！", s)
    s = re.sub(rf"(?<=[{CJK}])\?|\?(?=[{CJK}])", "？", s)
    s = re.sub(rf"\((?=[{CJK}])", "（", s)
    s = re.sub(rf"(?<=[{CJK}])\)", "）", s)
    s = re.sub(r"^[\[［【](.{1,14}?)[\]］】]", r"【\1】", s)
    changed_semantic = any(a in orig for a, _ in KAITI_FIXES)
    return s, changed_semantic


def group_lines(dets: List[Tuple[np.ndarray, str, float]]) -> List[Dict[str, Any]]:
    items = []
    for box, txt, sc in dets:
        if not txt.strip():
            continue
        xs, ys = box[:, 0], box[:, 1]
        items.append({"x0": float(xs.min()), "x1": float(xs.max()),
                      "y0": float(ys.min()), "y1": float(ys.max()),
                      "txt": txt, "score": sc})
    items.sort(key=lambda d: (d["y0"] + d["y1"]) / 2)
    lines: List[Dict[str, Any]] = []
    for it in items:
        placed = False
        for ln in lines:
            ov = min(ln["y1"], it["y1"]) - max(ln["y0"], it["y0"])
            if ov > 0.5 * min(ln["y1"] - ln["y0"], it["y1"] - it["y0"]):
                ln["parts"].append(it)
                ln["y0"], ln["y1"] = min(ln["y0"], it["y0"]), max(ln["y1"], it["y1"])
                placed = True
                break
        if not placed:
            lines.append({"y0": it["y0"], "y1": it["y1"], "parts": [it]})
    out = []
    for ln in sorted(lines, key=lambda l: l["y0"]):
        parts = sorted(ln["parts"], key=lambda p: p["x0"])
        text = "".join(p["txt"] for p in parts)
        n = sum(len(p["txt"]) for p in parts) or 1
        score = sum(p["score"] * len(p["txt"]) for p in parts) / n
        out.append({"y0": ln["y0"], "y1": ln["y1"], "x0": parts[0]["x0"],
                    "text": text, "score": score, "min_score": min(p["score"] for p in parts)})
    return out


def split_chunks(img: np.ndarray, max_h: int = 480) -> List[Tuple[int, int]]:
    """在空白行处把长图切成不超过 max_h 的块，保证 OCR 精度且不切断文字。"""
    H = img.shape[0]
    if H <= max_h:
        return [(0, H)]
    prof = ink_map(img, 48).sum(1)
    chunks, start = [], 0
    while start < H:
        end = min(start + max_h, H)
        if end < H:
            lo = start + max_h // 2
            seg = prof[lo:end]
            blank = np.where(seg <= 1)[0]
            end = lo + (int(blank[-1]) if len(blank) else int(np.argmin(seg)))
        chunks.append((start, end))
        start = end
    return chunks


def ocr_body(engine: OcrEngine, body: np.ndarray) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    ink = ink_map(body, 48)
    for a, b in split_chunks(body):
        seg = body[a:b]
        pad = 10
        bg = np.median(seg.reshape(-1, 3), axis=0).astype(np.uint8)
        padded = np.empty((seg.shape[0] + 2 * pad, seg.shape[1], 3), np.uint8)
        padded[:] = bg
        padded[pad:pad + seg.shape[0]] = seg
        for ln in group_lines(engine.detect(Image.fromarray(padded))):
            ln["y0"] += a - pad
            ln["y1"] += a - pad
            lines.append(ln)
    for ln in lines:
        y0 = int(max(0, ln["y0"] + (ln["y1"] - ln["y0"]) * 0.2))
        y1 = int(min(body.shape[0], ln["y1"] - (ln["y1"] - ln["y0"]) * 0.2))
        cols = np.where(ink[y0:max(y1, y0 + 1)].sum(0) >= 1)[0]
        ln["dx"] = int(cols[0]) if len(cols) else int(ln["x0"])
    lines.sort(key=lambda l: l["y0"])
    return lines


def structure_paragraphs(lines: List[Dict[str, Any]]) -> Tuple[List[str], List[Dict[str, Any]], bool]:
    intro: List[str] = []
    sections: List[Dict[str, Any]] = []
    fixed_any = False
    cur: Optional[List[str]] = None

    def target() -> List[str]:
        return sections[-1]["paragraphs"] if sections else intro

    for ln in lines:
        text, fixed = clean_text(ln["text"])
        fixed_any |= fixed
        if not text:
            continue
        m = re.match(r"^【(.{1,14}?)】(.*)$", text)
        is_header = bool(m) or (22 <= ln["dx"] <= 45 and len(text) <= 10)
        if is_header:
            title = m.group(1) if m else text.strip("【】[]")
            sections.append({"title": title, "paragraphs": []})
            cur = None
            rest = m.group(2).strip() if m else ""
            if rest:
                cur = [rest]
                target().append("")
            continue
        if ln["dx"] > 45 or cur is None:
            target().append("")
            cur = [text]
        else:
            prev = cur[-1]
            sep = " " if (prev[-1:].isascii() and prev[-1:].isalnum() and text[:1].isascii() and text[:1].isalnum()) else ""
            cur.append(sep + text)
        target()[-1] = "".join(cur)
    intro = [fix_quotes(p) for p in intro if p.strip()]
    for s in sections:
        s["paragraphs"] = [fix_quotes(p) for p in s["paragraphs"] if p.strip()]
    return intro, sections, fixed_any


def fix_quotes(p: str) -> str:
    """把中文段落里成对的半角双引号 "xx" 替换为中文引号 “xx”。"""
    if p.count('"') % 2 == 0 and re.search(rf"[{CJK}]", p):
        out, open_q = [], True
        for ch in p:
            if ch == '"':
                out.append("“" if open_q else "”")
                open_q = not open_q
            else:
                out.append(ch)
        return "".join(out)
    return p


def compose_full_text(intro: List[str], sections: List[Dict[str, Any]]) -> str:
    out = list(intro)
    for s in sections:
        if out:
            out.append("")
        out.append(f"【{s['title']}】")
        out.extend(s["paragraphs"])
    return "\n".join(out)


def ocr_title(engine: OcrEngine, title_img: np.ndarray) -> Tuple[str, float]:
    dets = engine.detect(Image.fromarray(title_img))
    lines = group_lines(dets)
    if not lines:
        return "", 0.0
    best = max(lines, key=lambda l: (l["y1"] - l["y0"]) * len(l["text"]))
    return clean_text(best["text"])[0], float(best["score"])


def ocr_card_header(engine: OcrEngine, card_img: np.ndarray) -> Tuple[str, float]:
    if card_img.shape[0] < 45:
        return "", 0.0
    hdr = card_img[6:40, 5:card_img.shape[1] - 5]
    txt, sc = engine.rec(Image.fromarray(hdr))
    return clean_text(txt)[0], sc


# =====================================================================
#  第 1 阶段：自动点击 + 滚动 + 截图
# =====================================================================
def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def save_png(arr: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(path, optimize=True)


def category_info(top: Optional[str], sub: Optional[str], override: Optional[str]) -> Dict[str, str]:
    if override:
        parts = [p.strip() for p in re.split(r"[/／>]", override) if p.strip()]
        top = parts[0] if parts else override
        sub = parts[1] if len(parts) > 1 else None
    top = top or "未知分类"
    top_slug = TOP_SLUGS.get(top, re.sub(r"\W+", "_", top.encode("unicode_escape").decode()).strip("_")[:24])
    if sub:
        sub_slug = SUB_SLUGS.get(sub, re.sub(r"\W+", "_", sub.encode("unicode_escape").decode()).strip("_")[:24])
        return {"top": top, "sub": sub, "category": sub,
                "full_category": f"{top} / {sub}", "slug": f"{top_slug}_{sub_slug}"}
    return {"top": top, "sub": "", "category": top, "full_category": top, "slug": top_slug}


class TujianCapturer:
    def __init__(self, screen: Screen, mouse: MouseInput, ctl: Controller, cat: Dict[str, str],
                 fresh: bool = False, mode: str = "resume") -> None:
        self.screen, self.mouse, self.ctl, self.cat = screen, mouse, ctl, cat
        self.mode = mode                         # "resume" 续抓 / "update" 补全未获得
        self.run_started_at = datetime.now().isoformat(timespec="seconds")
        self.newly_unlocked: List[int] = []
        self.still_locked = 0
        self.dir = CAPTURE_DIR / cat["slug"]
        self.raw = self.dir / "raw"
        self.progress_path = self.dir / "progress.json"
        if fresh and self.dir.exists():
            shutil.rmtree(self.dir)
            log("已清除旧进度（--fresh）。")
        self.raw.mkdir(parents=True, exist_ok=True)
        (self.dir / "grid").mkdir(exist_ok=True)
        self.progress: Dict[str, Any] = {"category": cat, "items": {}, "complete": False}
        if self.progress_path.exists():
            try:
                old = json.loads(self.progress_path.read_text(encoding="utf-8"))
                self.progress["items"] = old.get("items", {})
                if self.progress["items"] and mode == "resume":
                    log(f"发现旧进度：已抓取 {len(self.progress['items'])} 张，将自动跳过（断点续抓）。")
            except Exception:
                pass
        self.grid_method: Optional[str] = None   # "wheel" / "drag"
        self.grid_notches = 2
        self.body_method: Optional[str] = None
        self.body_notches = 2
        self.body_was_scrolled = False

    # ---------- 基础动作 ----------
    def grab(self) -> np.ndarray:
        return self.screen.grab()

    def pt(self, x: float, y: float) -> Tuple[int, int]:
        return self.screen.to_screen(x, y)

    def click(self, x: float, y: float) -> None:
        self.ctl.checkpoint()
        self.mouse.click(*self.pt(x, y))

    def wheel(self, point: Tuple[int, int], notches: int) -> None:
        self.ctl.checkpoint()
        self.mouse.wheel(*self.pt(*point), notches)

    def drag(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.ctl.checkpoint()
        a, b = self.pt(x1, y1)
        c, d = self.pt(x2, y2)
        self.mouse.drag(a, b, c, d)

    def wait_settle(self, box: Tuple[int, int, int, int], timeout: float = 2.5,
                    thresh: float = 0.6, need: int = 2, interval: float = 0.07) -> np.ndarray:
        cur = self.grab()
        prev = crop(cur, box)
        stable, t0 = 0, time.time()
        while time.time() - t0 < timeout:
            time.sleep(interval)
            self.ctl.checkpoint()
            cur = self.grab()
            c = crop(cur, box)
            if mean_abs_diff(c, prev) < thresh:
                stable += 1
                if stable >= need:
                    return cur
            else:
                stable = 0
            prev = c
        return cur

    def save_progress(self) -> None:
        atomic_write_json(self.progress_path, self.progress)

    # ---------- 屏幕校验 ----------
    def ensure_tujian(self, max_wait: float = 60) -> np.ndarray:
        t0 = time.time()
        warned = False
        while True:
            self.ctl.checkpoint()
            arr = self.grab()
            ok, info = verify_tujian_screen(arr)
            if ok:
                return arr
            if not warned:
                log(f"⚠ 当前画面不像图鉴界面（校验 {info['score']}/4），请切回游戏【图鉴】界面……")
                warned = True
            if time.time() - t0 > max_wait:
                raise RuntimeError("等待图鉴界面超时，请确认游戏为 1920×1080 全屏并停留在【图鉴】界面。")
            time.sleep(1.0)

    # ---------- 左侧网格滚动 ----------
    def grid_scroll_to_top(self) -> None:
        log("左侧卡牌列表滚动到顶部……")
        for _ in range(25):
            before = self.grab()
            self.wheel(GRID_SAFE_POINT, -15)
            after = self.wait_settle(GRID_BOX, timeout=2.0)
            if mean_abs_diff(crop(before, GRID_BOX), crop(after, GRID_BOX)) < 1.0:
                # 滚轮无效时用拖动再确认一次
                self.drag(GRID_SAFE_POINT[0], 260, GRID_SAFE_POINT[0], 860)
                after2 = self.wait_settle(GRID_BOX, timeout=2.0)
                if mean_abs_diff(crop(after, GRID_BOX), crop(after2, GRID_BOX)) < 1.0:
                    break
        time.sleep(0.2)

    def grid_scroll_down(self) -> int:
        before = self.wait_settle(GRID_BOX, timeout=1.0)
        if self.grid_method is None:
            # 第一次：标定 1 格滚轮对应的像素
            self.wheel(GRID_SAFE_POINT, 1)
            after = self.wait_settle(GRID_BOX, timeout=3.0)
            s, _ = estimate_grid_shift(before, after)
            if s >= 4:
                self.grid_method = "wheel"
                self.grid_notches = int(np.clip(round(GRID_TARGET_STEP / s), 1, 40))
                log(f"列表滚轮标定：1 格 ≈ {s}px，之后每次滚动 {self.grid_notches} 格。")
                return s
            self.drag(GRID_SAFE_POINT[0], 800, GRID_SAFE_POINT[0], 800 - GRID_TARGET_STEP)
            after = self.wait_settle(GRID_BOX, timeout=3.0)
            s, _ = estimate_grid_shift(before, after)
            if s >= 4:
                self.grid_method = "drag"
                log(f"滚轮无效，改用拖动滚动列表（每次 ≈ {s}px）。")
            return s
        if self.grid_method == "wheel":
            self.wheel(GRID_SAFE_POINT, self.grid_notches)
        else:
            self.drag(GRID_SAFE_POINT[0], 800, GRID_SAFE_POINT[0], 800 - GRID_TARGET_STEP)
        after = self.wait_settle(GRID_BOX, timeout=3.0)
        s, _ = estimate_grid_shift(before, after)
        if s > GRID_MAX_SAFE_STEP:
            log(f"⚠ 单次滚动 {s}px 过大，可能漏行，自动减小步长。")
            self.grid_notches = max(1, self.grid_notches // 2)
        return s

    # ---------- 右侧正文滚动 ----------
    def body_scroll_to_top(self) -> None:
        for _ in range(6):
            before = crop(self.grab(), BODY_BOX)
            if self.body_method == "drag":
                self.drag(BODY_POINT[0], 450, BODY_POINT[0], 880)
            else:
                self.wheel(BODY_POINT, -25)
            after = crop(self.wait_settle(BODY_BOX, timeout=1.5), BODY_BOX)
            if mean_abs_diff(before, after) < 0.8:
                break

    def body_scroll_down(self, before_arr: np.ndarray) -> Tuple[int, np.ndarray]:
        before = crop(before_arr, BODY_BOX)
        if self.body_method is None:
            self.wheel(BODY_POINT, 1)
            after_arr = self.wait_settle(BODY_BOX, timeout=2.0)
            s, _ = estimate_body_shift(before, crop(after_arr, BODY_BOX))
            if s >= 3:
                self.body_method = "wheel"
                self.body_notches = int(np.clip(round(BODY_TARGET_STEP / s), 1, 30))
                log(f"详情滚轮标定：1 格 ≈ {s}px，之后每次滚动 {self.body_notches} 格。")
                return s, after_arr
            self.drag(BODY_POINT[0], 820, BODY_POINT[0], 820 - BODY_TARGET_STEP)
            after_arr = self.wait_settle(BODY_BOX, timeout=2.0)
            s, _ = estimate_body_shift(before, crop(after_arr, BODY_BOX))
            if s >= 3:
                self.body_method = "drag"
                log("详情滚轮无效，改用拖动滚动正文。")
            return s, after_arr
        if self.body_method == "wheel":
            self.wheel(BODY_POINT, self.body_notches)
        else:
            self.drag(BODY_POINT[0], 820, BODY_POINT[0], 820 - BODY_TARGET_STEP)
        after_arr = self.wait_settle(BODY_BOX, timeout=2.0)
        s, _ = estimate_body_shift(before, crop(after_arr, BODY_BOX))
        if s > 440:
            self.body_notches = max(1, self.body_notches // 2)
        return s, after_arr

    def capture_full_body(self, arr: np.ndarray) -> Tuple[np.ndarray, int]:
        frame = crop(arr, BODY_BOX).copy()
        if last_ink_row(frame) < BODY_OVERFLOW_Y:
            return frame, 1
        canvas, top, frames = frame, 0, 1
        cur_arr = arr
        for _ in range(40):
            s, nxt = self.body_scroll_down(cur_arr)
            if s < 3:
                break
            canvas, top = stitch_body(canvas, top, crop(nxt, BODY_BOX).copy(), s)
            cur_arr = nxt
            frames += 1
            self.body_was_scrolled = True
        return canvas, frames

    # ---------- 处理单张卡牌 ----------
    def process_card(self, arr: np.ndarray, card: Dict[str, Any], key: str, index: int) -> np.ndarray:
        card_img = arr[card["y1"]:card["y2"] + 1, card["x1"]:card["x2"] + 1].copy()
        is_locked = bool(card.get("locked"))
        already = selection_score(arr, card) > 0.5
        before_detail = crop(arr, DETAIL_CHANGE_BOX)
        cx = (card["x1"] + card["x2"]) / 2
        cy = card["y1"] + min(110, card["h"] * 0.65)

        selected = changed = False
        cur = arr
        for attempt in range(2):
            self.click(cx, cy)
            t0 = time.time()
            while time.time() - t0 < 2.0:
                time.sleep(0.08)
                self.ctl.checkpoint()
                cur = self.grab()
                selected = selection_score(cur, card) > 0.5
                changed = mean_abs_diff(crop(cur, DETAIL_CHANGE_BOX), before_detail) > 2.0
                if selected and (changed or already):
                    break
            if selected and (changed or already):
                break
        detail_ok = bool(selected and (changed or already))

        cur = self.wait_settle((1258, 126, 1774, 895), timeout=2.5)
        if self.body_was_scrolled:
            self.body_was_scrolled = False
            self.body_scroll_to_top()
            cur = self.wait_settle((1258, 126, 1774, 895), timeout=1.5)

        prev = self.progress["items"].get(key) or {}
        now = datetime.now().isoformat(timespec="seconds")
        prefix = f"{index:03d}"
        files = {"card": f"raw/{prefix}_card.png"}
        save_png(card_img, self.dir / files["card"])
        item: Dict[str, Any] = {
            "key": key, "index": index, "row": index // 6, "col": index % 6,
            "locked": is_locked, "detail_ok": detail_ok, "captured_at": now,
            "first_seen": prev.get("first_seen") or prev.get("captured_at") or now,
        }
        if prev.get("unlocked_at"):
            item["unlocked_at"] = prev["unlocked_at"]
        if prev and prev.get("locked") and not is_locked:
            item["unlocked_at"] = self.run_started_at
            self.newly_unlocked.append(index)
        tag = "【未获得】" if is_locked else ""
        if detail_ok:
            body, frames = self.capture_full_body(cur)
            files["icon"] = f"raw/{prefix}_icon.png"
            files["title"] = f"raw/{prefix}_title.png"
            files["body"] = f"raw/{prefix}_body.png"
            save_png(crop(cur, ICON_BOX), self.dir / files["icon"])
            save_png(crop(cur, TITLE_BOX), self.dir / files["title"])
            save_png(body, self.dir / files["body"])
            item["body_frames"] = frames
            item["body_height"] = int(body.shape[0])
            log(f"  #{index + 1:03d}{tag} 已抓取（正文 {body.shape[0]}px，{frames} 屏）"
                + ("  ★ 新获得！" if item.get("unlocked_at") == self.run_started_at else ""))
        else:
            log(f"  #{index + 1:03d}{tag} 点击后详情没有变化，只保存卡牌缩略图")
        item["files"] = files
        self.progress["items"][key] = item
        self.save_progress()
        return self.grab()

    def need_capture(self, key: str, card: Dict[str, Any]) -> bool:
        prev = self.progress["items"].get(key)
        if prev is None:
            return True                                  # 从没抓过（包括旧版本漏掉的未获得卡）
        prev_detail = prev.get("detail_ok", "body" in prev.get("files", {}))
        if self.mode == "update":
            if prev.get("locked"):
                if card.get("locked"):
                    self.still_locked += 1               # 依然未获得：不点击，直接跳过
                    return False
                return True                              # 之前未获得、现在已获得 → 补抓
            return not prev_detail                       # 之前没拿到详情的也再试一次
        return False

    # ---------- 主流程 ----------
    def run(self) -> bool:
        self.run_started_at = datetime.now().isoformat(timespec="seconds")
        self.progress["run_started_at"] = self.run_started_at
        self.newly_unlocked: List[int] = []
        self.still_locked = 0
        if self.mode == "update":
            n_locked = sum(1 for v in self.progress["items"].values() if v.get("locked"))
            log(f"补全模式：上次记录了 {n_locked} 张【未获得】卡牌，只检查这些卡（以及从未抓到过的卡）。")

        arr = self.ensure_tujian()
        self.grid_scroll_to_top()
        arr = self.wait_settle(GRID_BOX, timeout=1.5)
        cards = [c for c in detect_cards(arr) if c["complete"]]
        if not cards:
            raise RuntimeError("左侧未检测到任何卡牌，请确认停留在图鉴卡牌列表界面。")
        top0 = min(c["y1"] for c in cards)
        if abs(top0 - GRID_FIRST_ROW_Y) <= 30:
            top0 = GRID_FIRST_ROW_Y
        else:
            log(f"⚠ 第一行卡牌位置 y={top0} 与预期 {GRID_FIRST_ROW_Y} 不同，列表可能没有滚到顶部。")
        offset, step_no = 0, 0
        seen_keys: set = set()
        locked_seen = 0

        while True:
            self.ctl.checkpoint()
            arr = self.grab()
            Image.fromarray(crop(arr, GRID_BOX)).save(self.dir / "grid" / f"grid_{step_no:02d}.jpg", quality=85)
            all_cards = detect_cards(arr)
            cards = [c for c in all_cards if c["complete"]]
            for c in cards:
                row = int(round((c["y1"] + offset - top0) / GRID_PITCH))
                key = f"r{row:03d}_c{c['col']}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                locked_seen += bool(c.get("locked"))
                if not self.need_capture(key, c):
                    continue
                arr = self.process_card(arr, c, key, row * 6 + c["col"])
            bottom_partial = any((not c["complete"]) and c["y2"] >= CARD_Y_MAX - 3 for c in all_cards)
            last_bottom = max((c["y2"] for c in all_cards), default=0)
            shift = self.grid_scroll_down()
            step_no += 1
            if shift < 4:
                if bottom_partial:
                    log("⚠ 下方仍有被裁切的卡牌但列表无法继续滚动，请检查。")
                break
            offset += shift
            log(f"列表向下滚动 {shift}px（累计 {offset}px，上一屏最低卡牌 y={last_bottom}）")

        self.progress["complete"] = True
        self.progress["finished_at"] = datetime.now().isoformat(timespec="seconds")
        self.save_progress()
        rows = sorted({int(k[1:4]) for k in seen_keys})
        missing = [r for r in range(rows[0], rows[-1] + 1) if r not in rows] if rows else []
        if missing:
            log(f"⚠ 以下行可能被跳过：{missing}，建议重新运行脚本补抓（会自动续抓）。")
        items = self.progress["items"].values()
        n_locked = sum(1 for v in items if v.get("locked"))
        log(f"✅ 第 1 阶段完成：本分类共 {len(self.progress['items'])} 张（已获得 "
            f"{len(self.progress['items']) - n_locked} / 未获得 {n_locked}）。")
        if self.mode == "update":
            log(f"   本次新获得 {len(self.newly_unlocked)} 张，仍未获得 {self.still_locked} 张。")
        return True


# =====================================================================
#  第 2 阶段：OCR + 生成攻略数据
# =====================================================================
def ocr_one_item(engine: OcrEngine, cdir: Path, adir: Path, slug: str, it: Dict[str, Any]) -> Dict[str, Any]:
    idx = it["index"]
    files = it.get("files", {})
    prefix = f"{idx:03d}"
    card = np.asarray(Image.open(cdir / files["card"]).convert("RGB"))
    Image.fromarray(card).save(adir / "cards" / f"{prefix}.png", optimize=True)
    hdr_name, hdr_score = ocr_card_header(engine, card)
    rec: Dict[str, Any] = {
        "index": idx, "row": it.get("row"), "col": it.get("col"),
        "name": hdr_name, "locked": bool(it.get("locked")),
        "card_image": f"assets/{slug}/cards/{prefix}.png",
        "icon_image": "", "detail_image": "",
        "intro_paragraphs": [], "sections": [], "full_text": "",
        "avg_confidence": round(hdr_score, 4), "needs_review": False,
    }
    if "body" in files:
        title = np.asarray(Image.open(cdir / files["title"]).convert("RGB"))
        body = np.asarray(Image.open(cdir / files["body"]).convert("RGB"))
        icon = Image.open(cdir / files["icon"]).convert("RGB")
        icon.save(adir / "icons" / f"{prefix}.png", optimize=True)
        # 校对用详情长图：标题 + 分隔线 + 完整正文
        sep = np.full((4, title.shape[1], 3), (150, 125, 90), np.uint8)
        Image.fromarray(np.concatenate([title, sep, body], 0)).save(
            adir / "details" / f"{prefix}.jpg", quality=90)
        rec["icon_image"] = f"assets/{slug}/icons/{prefix}.png"
        rec["detail_image"] = f"assets/{slug}/details/{prefix}.jpg"

        t_name, t_score = ocr_title(engine, title)
        lines = ocr_body(engine, body)
        intro, sections, fixed = structure_paragraphs(lines)
        name = t_name or hdr_name
        if t_name and hdr_name and t_name != hdr_name:
            name = t_name if t_score >= hdr_score else hdr_name
            rec["needs_review"] = True
        rec["name"] = name
        rec["intro_paragraphs"], rec["sections"] = intro, sections
        rec["full_text"] = compose_full_text(intro, sections)
        scores = [l["score"] for l in lines] + ([t_score] if t_name else [])
        rec["avg_confidence"] = round(float(np.mean(scores)) if scores else 0.0, 4)
        low = [l for l in lines if l["min_score"] < LOW_CONF]
        rec["needs_review"] = bool(rec["needs_review"] or fixed or low
                                   or (t_name and t_score < LOW_CONF) or not lines)
        rec["ocr_lines"] = [{"text": l["text"], "score": round(l["score"], 4), "dx": l["dx"]} for l in lines]
    if not rec["name"]:
        rec["name"] = f"未识别 #{idx + 1}"
        rec["needs_review"] = True
    return rec


def run_ocr_phase(slug: str, engine: OcrEngine, force: bool = False) -> Path:
    """增量 OCR：截图没有变化的条目直接沿用 docs/data 里已有的记录（保留你手动校对过的文字），
    只对新抓取 / 新获得的卡牌重新识别。force=True 时全部重新识别。"""
    cdir = CAPTURE_DIR / slug
    progress = json.loads((cdir / "progress.json").read_text(encoding="utf-8"))
    cat = progress.get("category") or category_info(None, None, slug)
    run_started = progress.get("run_started_at", "")
    items_raw = sorted(progress["items"].values(), key=lambda d: d["index"])
    adir = ASSET_DIR / slug
    for sub in ("cards", "icons", "details"):
        (adir / sub).mkdir(parents=True, exist_ok=True)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / f"{slug}.json"
    existing: Dict[int, Dict[str, Any]] = {}
    if out.exists() and not force:
        try:
            for r in json.loads(out.read_text(encoding="utf-8")).get("items", []):
                existing[int(r["index"])] = r
        except Exception as e:
            log(f"⚠ 读取旧数据失败（{e}），将全部重新识别。")

    out_items: List[Dict[str, Any]] = []
    total = len(items_raw)
    reused = 0
    log(f"第 2 阶段：整理 {total} 条数据（OCR 引擎 {engine.kind}{'，全部重新识别' if force else '，只识别新内容'}）……")
    for n, it in enumerate(items_raw, 1):
        idx = it["index"]
        old = existing.get(idx)
        same_shot = bool(old) and (
            old.get("captured_at") == it.get("captured_at")
            or (not old.get("captured_at") and (not run_started or it.get("captured_at", "") < run_started))
        )
        if same_shot:
            rec = dict(old)
            rec["locked"] = bool(it.get("locked"))
            reused += 1
        else:
            rec = ocr_one_item(engine, cdir, ASSET_DIR / slug, slug, it)
            if old and old.get("name") and old["name"] != rec["name"] and not old.get("locked"):
                rec["needs_review"] = True        # 同一位置名称变了，提醒核对
        rec["status"] = "未获得" if rec["locked"] else "已获得"
        for k in ("captured_at", "first_seen", "unlocked_at"):
            if it.get(k):
                rec[k] = it[k]
            else:
                rec.pop(k, None)
        out_items.append(rec)
        if not same_shot:
            flag = "（建议核对）" if rec["needs_review"] else ""
            new_tag = " ★新获得" if rec.get("unlocked_at") and rec["unlocked_at"] == run_started else ""
            log(f"  [{n}/{total}] {rec['name']}{'【未获得】' if rec['locked'] else ''}{new_tag}{flag}")

    payload = {
        "slug": slug,
        "category": cat.get("category", slug),
        "full_category": cat.get("full_category", slug),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_run_at": run_started,
        "ocr_engine": engine.kind,
        "items": out_items,
    }
    if out.exists():
        bdir = DATA_DIR.parent / "data_backup"
        bdir.mkdir(exist_ok=True)
        shutil.copy2(out, bdir / f"{slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    atomic_write_json(out, payload)
    n_locked = sum(1 for r in out_items if r["locked"])
    review = sum(1 for r in out_items if r["needs_review"])
    log(f"✅ 已写入 {out.relative_to(BASE_DIR)}：共 {len(out_items)} 条（已获得 {len(out_items) - n_locked} / "
        f"未获得 {n_locked}），沿用旧记录 {reused} 条，建议核对 {review} 条")
    return out


def build_and_open(open_browser: bool = True) -> None:
    sys.path.insert(0, str(BASE_DIR))
    import build_html

    index = build_html.build_site(publish_mode=False)
    log(f"✅ 攻略网页已生成：{index}")
    if open_browser:
        try:
            webbrowser.open(index.as_uri())
        except Exception:
            pass


# =====================================================================
#  离线自检（不动鼠标）：用一张游戏截图检验所有识别环节
# =====================================================================
def run_self_test(image_path: Path, engine: Optional[OcrEngine]) -> int:
    img = Image.open(image_path).convert("RGB")
    if img.size != (REF_W, REF_H):
        log(f"截图尺寸 {img.size}，自动缩放到 1920×1080。")
        img = img.resize((REF_W, REF_H), Image.LANCZOS)
    arr = np.asarray(img)
    outdir = BASE_DIR / "selftest_output"
    outdir.mkdir(exist_ok=True)
    ok, info = verify_tujian_screen(arr)
    log(f"图鉴界面校验：{'通过' if ok else '未通过'}  {info}")
    top, tv = detect_top_tab(arr)
    sub, sv = detect_sub_tab(arr)
    cat = category_info(top, sub, None)
    log(f"当前分类：{cat['full_category']}（slug={cat['slug']}，顶栏亮度 {tv}，子分类差值 {sv}）")
    cards = detect_cards(arr)
    complete = [c for c in cards if c["complete"]]
    log(f"检测到卡牌 {len(cards)} 张，其中完整 {len(complete)} 张（未获得 {sum(1 for c in complete if c.get('locked'))} 张）。")
    for c in complete:
        c["sel"] = round(selection_score(arr, c), 3)
        card_img = arr[c["y1"]:c["y2"] + 1, c["x1"]:c["x2"] + 1]
        c["name"], c["score"] = ocr_card_header(engine, card_img) if engine else ("", 0.0)
    rows: Dict[int, List[str]] = {}
    for c in complete:
        rows.setdefault(c["y1"] // 40, []).append(
            f"{c['name'] or '?'}({c['score']:.2f}){'🔒未获得' if c.get('locked') else ''}{'★选中' if c['sel'] > 0.5 else ''}")
    for k in sorted(rows):
        log("  " + " | ".join(rows[k]))
    body = crop(arr, BODY_BOX)
    log(f"正文最后一行墨迹 y={last_ink_row(body)}（≥{BODY_OVERFLOW_Y} 则需要向下滚动）")
    save_png(crop(arr, ICON_BOX), outdir / "icon.png")
    save_png(crop(arr, TITLE_BOX), outdir / "title.png")
    save_png(body, outdir / "body.png")
    if engine:
        t, ts = ocr_title(engine, crop(arr, TITLE_BOX))
        log(f"标题：{t}（{ts:.3f}）")
        lines = ocr_body(engine, body)
        for l in lines:
            log(f"  dx={l['dx']:>3}  {l['score']:.3f}  {l['text']}")
        intro, sections, fixed = structure_paragraphs(lines)
        text = compose_full_text(intro, sections)
        (outdir / "body.txt").write_text(f"{t}\n\n{text}\n", encoding="utf-8")
        log("结构化正文：\n" + text)
    log(f"自检输出目录：{outdir}")
    return 0 if ok else 1


# =====================================================================
#  入口
# =====================================================================
def pick_slug_for_ocr(arg_slug: Optional[str]) -> List[str]:
    if arg_slug:
        return [arg_slug]
    if not CAPTURE_DIR.exists():
        return []
    dirs = [d for d in CAPTURE_DIR.iterdir() if (d / "progress.json").exists()]
    dirs.sort(key=lambda d: (d / "progress.json").stat().st_mtime, reverse=True)
    return [d.name for d in dirs]


def main() -> int:
    ap = argparse.ArgumentParser(description="卡牌修仙传 图鉴自动抓取 + 离线 OCR + 生成 HTML 攻略")
    ap.add_argument("--delay", type=float, default=5, help="开始前倒计时秒数（用于切回游戏），默认 5")
    ap.add_argument("--monitor", type=int, default=1, help="游戏所在显示器编号（1=主显示器）")
    ap.add_argument("--fresh", action="store_true", help="忽略旧进度，从头抓取当前分类")
    ap.add_argument("--update-locked", action="store_true",
                    help="补全模式：只检查上次标记为【未获得】的卡牌，已获得的自动补抓")
    ap.add_argument("--force-ocr", action="store_true", help="重新 OCR 全部条目（默认只识别新抓取的条目）")
    ap.add_argument("--ocr-only", action="store_true", help="不操作游戏，只对已抓取截图重新 OCR 并生成网页")
    ap.add_argument("--capture-only", action="store_true", help="只抓取截图，不做 OCR")
    ap.add_argument("--high-accuracy", action="store_true", help="使用 PP-OCRv5 server 大模型（更准更慢）")
    ap.add_argument("--slug", help="指定分类目录名（如 kapai_ganwu_xinfa），配合 --ocr-only 使用")
    ap.add_argument("--category", help="手动指定分类名，如 \"卡牌/感悟&心法\"（自动识别失败时使用）")
    ap.add_argument("--test-image", help="离线自检：分析一张 1920×1080 游戏截图，不移动鼠标")
    ap.add_argument("--no-open", action="store_true", help="完成后不自动打开浏览器")
    args = ap.parse_args()

    set_dpi_awareness()

    if args.test_image:
        engine = OcrEngine(args.high_accuracy)
        return run_self_test(Path(args.test_image), engine)

    if args.ocr_only:
        slugs = pick_slug_for_ocr(args.slug)
        if not slugs:
            log("没有找到已抓取的数据（captures/*/progress.json）。")
            return 1
        engine = OcrEngine(args.high_accuracy)
        targets = slugs if not args.slug else slugs[:1]
        for s in targets:
            run_ocr_phase(s, engine, force=args.force_ocr)
        build_and_open(not args.no_open)
        return 0

    if not IS_WINDOWS:
        log("自动抓取需要在 Windows 上运行（可用 --test-image 在其他系统做离线自检）。")
        return 1

    engine = None
    if not args.capture_only:
        log("正在加载离线 OCR 模型（首次运行会自动下载约 20MB，请稍候）……")
        engine = OcrEngine(args.high_accuracy)
        log(f"OCR 引擎就绪：{engine.kind}")

    screen = Screen(args.monitor)
    mouse = MouseInput()
    if not is_admin():
        log("提示：若脚本点击游戏无反应，请右键“开始抓取.bat”→【以管理员身份运行】。")

    log(f"请在 {args.delay:.0f} 秒内切换到游戏【图鉴】界面（F9 暂停/继续，F10 停止，鼠标甩到左上角紧急停止）")
    for i in range(int(args.delay), 0, -1):
        print(f"  {i}…", flush=True)
        time.sleep(1)

    ctl = Controller(mouse, (screen.left, screen.top))
    arr = screen.grab()
    ok, info = verify_tujian_screen(arr)
    top, _ = detect_top_tab(arr)
    sub, _ = detect_sub_tab(arr)
    cat = category_info(top, sub if top in (None, "卡牌") else None, args.category)
    log(f"识别到当前分类：{cat['full_category']}  →  captures/{cat['slug']}/")

    mode = "update" if (args.update_locked and not args.fresh) else "resume"
    cap = TujianCapturer(screen, mouse, ctl, cat, fresh=args.fresh, mode=mode)
    finished = False
    try:
        finished = cap.run()
    except StopRequested:
        log(f"已停止，进度已保存（{len(cap.progress['items'])} 张）。再次运行会自动续抓。")
    except Exception as e:
        log(f"❌ 抓取出错：{e}")
        traceback.print_exc()
        cap.save_progress()
    finally:
        ctl.stop = True
    log("🖱 鼠标已释放，你可以自由操作电脑了。")

    if engine is not None and cap.progress["items"]:
        if not finished:
            log("（抓取未全部完成，先对已抓取部分生成网页）")
        run_ocr_phase(cat["slug"], engine, force=args.force_ocr)
        build_and_open(not args.no_open)
    return 0 if finished else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("已手动中断。")
        sys.exit(130)
