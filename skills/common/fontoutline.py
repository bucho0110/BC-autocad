# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""트루타입 글꼴의 글자 윤곽선(fontTools). CTS 문자 외곽선 그림자가 쓴다.

글꼴 파일은 Windows 글꼴 등록(레지스트리)에서 글꼴 이름으로 찾고, 없으면 글꼴 폴더의 이름표를 훑는다.
곡선은 정밀도(곡선 한 마디를 나눌 수)만큼 직선으로 나눈다. 자간(커닝)은 쓰지 않는다.
"""

import logging
import os
import winreg

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTCollection, TTFont

logging.getLogger("fontTools").setLevel(logging.ERROR)  # 이름표 오프셋 경고 등 읽는 데 지장 없는 알림은 숨긴다
_CACHE = {}
SPECIAL = {"%%c": "Ø", "%%C": "Ø", "%%d": "°", "%%D": "°", "%%p": "±", "%%P": "±", "%%%": "%",
           "%%u": "", "%%U": "", "%%o": "", "%%O": ""}


def plain(s):
    for k, v in SPECIAL.items():
        s = s.replace(k, v)
    return s


def _norm(s):
    return "".join(str(s).lower().split())


def _font_dirs():
    yield os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    yield os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")


def _registry():
    """[(등록 이름, 파일 경로)]"""
    out = []
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            k = winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
        except OSError:
            continue
        i = 0
        while True:
            try:
                name, val, _t = winreg.EnumValue(k, i)
            except OSError:
                break
            i += 1
            path = val if os.path.isabs(val) else os.path.join(next(_font_dirs()), val)
            out.append((name, path))
    return out


def _families(path):
    """글꼴 파일 안 글꼴들의 (번호, 이름 집합)."""
    out = []
    try:
        fonts = TTCollection(path, lazy=True).fonts if path.lower().endswith(".ttc") else [TTFont(path, lazy=True)]
    except Exception:  # noqa: BLE001 — 읽지 못하는 글꼴 파일은 건너뛴다
        return out
    for i, f in enumerate(fonts):
        names = set()
        try:
            for rec in f["name"].names:
                if rec.nameID in (1, 4, 16):
                    names.add(_norm(rec.toUnicode()))
        except Exception:  # noqa: BLE001
            pass
        out.append((i, names))
    return out


def find_font(typeface):
    """글꼴 이름(예: '맑은 고딕', 'Malgun Gothic') → (파일 경로, 글꼴 번호). 없으면 None."""
    key = _norm(typeface)
    if key in _CACHE:
        return _CACHE[key]
    found = None
    reg = _registry()
    # 1) 등록 이름에 그 글꼴 이름이 들어 있는 파일만 이름표로 확인(빠름)
    for name, path in reg:
        parts = [_norm(p.replace("(TrueType)", "").replace("(OpenType)", "")) for p in name.split("&")]
        if key in parts and os.path.exists(path):
            for i, names in _families(path):
                if key in names:
                    found = (path, i)
                    break
            found = found or (path, 0)
            break
    # 2) 그래도 없으면 등록된 모든 파일의 이름표(다른 언어 이름 포함)를 훑는다
    if not found:
        for _n, path in reg:
            if os.path.exists(path) and path.lower().endswith((".ttf", ".ttc", ".otf")):
                for i, names in _families(path):
                    if key in names:
                        found = (path, i)
                        break
            if found:
                break
    _CACHE[key] = found
    return found


class _FlatPen(BasePen):
    """윤곽선을 직선 점 목록으로(곡선은 steps 마디로 나눔)."""

    def __init__(self, glyphset, steps, dx):
        super().__init__(glyphset)
        self.steps, self.dx, self.contours, self.cur = max(1, int(steps)), dx, [], []

    def _moveTo(self, p):
        self.cur = [(p[0] + self.dx, p[1])]

    def _lineTo(self, p):
        self.cur.append((p[0] + self.dx, p[1]))

    def _curveToOne(self, p1, p2, p3):
        x0, y0 = self.cur[-1][0] - self.dx, self.cur[-1][1]
        n = self.steps
        for k in range(1, n + 1):
            t = k / n
            a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
            self.cur.append((a * x0 + b * p1[0] + c * p2[0] + d * p3[0] + self.dx, a * y0 + b * p1[1] + c * p2[1] + d * p3[1]))

    def _qCurveToOne(self, p1, p2):
        x0, y0 = self.cur[-1][0] - self.dx, self.cur[-1][1]
        n = self.steps
        for k in range(1, n + 1):
            t = k / n
            a, b, c = (1 - t) ** 2, 2 * t * (1 - t), t * t
            self.cur.append((a * x0 + b * p1[0] + c * p2[0] + self.dx, a * y0 + b * p1[1] + c * p2[1]))

    def _closePath(self):
        if len(self.cur) > 2:
            if self.cur[0] == self.cur[-1]:
                self.cur.pop()
            self.contours.append(self.cur)
        self.cur = []

    _endPath = _closePath


def outlines(text, font, steps=4):
    """문자열 → (윤곽선 목록 [[(x, y)…]] 글꼴 단위, 기준선 0), 윤곽 상자 (x0, y0, x1, y1). 글자가 없으면 상자 None."""
    path, idx = font
    f = TTCollection(path, lazy=True).fonts[idx] if path.lower().endswith(".ttc") else TTFont(path, lazy=True)
    cmap, gs, hmtx = f.getBestCmap(), f.getGlyphSet(), f["hmtx"]
    x, out = 0.0, []
    for ch in plain(text):
        g = cmap.get(ord(ch), ".notdef")
        pen = _FlatPen(gs, steps, x)
        gs[g].draw(pen)
        out += pen.contours
        x += hmtx[g][0]
    pts = [p for c in out for p in c]
    if not pts:
        return out, None
    return out, (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
