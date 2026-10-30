# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""TTP Z값 점·문자 생성 — 문자 ↔ Z값 점, 점·블록·선 정점의 Z값 문자, 문자 주변 점·블록의 Z 올리기.

build()는 창 없이도 쓴다(MCP skill_run).
"""

import math
import re
import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "TTP"
MODES = ["문자→Z점", "점·블록→Z문자", "선 정점→Z점·문자", "문자 주변 점·블록 Z 올리기"]
FIELDS = [
    ("기능", "기능", "choice", MODES[0], MODES),
    ("문자기준", "문자 위치 기준", "choice", "삽입점", ["삽입점", "정렬점"]),
    ("이격X", "생성 위치 X 이격 (도면 단위)", "real", 0.0, None),
    ("이격Y", "생성 위치 Y 이격 (도면 단위)", "real", 0.0, None),
    ("점레이어", "점 레이어 (비우면 현재 레이어)", "str", "", None),
    ("문자레이어", "문자 레이어 (비우면 현재 레이어)", "str", "", None),
    ("높이", "문자 높이 (도면 단위)", "real", 1.0, None),
    ("정렬", "문자 정렬", "choice", "왼쪽", ["왼쪽", "중심", "오른쪽"]),
    ("소수", "Z 문자 소수 자리", "int", 2, None),
    ("Z0제외", "Z=0 제외", "bool", True, None),
    ("문자Z", "문자 자체 Z 값도 설정", "bool", False, None),
    ("반경", "문자 주변 찾을 거리 (도면 단위)", "real", 1.0, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
JUST = {"왼쪽": "L", "중심": "C", "오른쪽": "R"}  # 기준선 정렬
_NUM = re.compile(r"(\(-\)|-)?(\d+(?:\.\d+)?)")


def types_for(cfg) -> str:
    """기능별로 고를 객체 종류."""
    return {MODES[0]: "TEXT,MTEXT", MODES[1]: "POINT,INSERT", MODES[2]: "LINE,LWPOLYLINE,POLYLINE",
            MODES[3]: "TEXT,MTEXT,POINT,INSERT"}[cfg["기능"]]


def num_in_text(s):
    """맨 뒤 숫자(LISP bc:num-in-text와 같은 규칙): 'EL=10.12'→10.12, '123AB456'→456, 'EL.(-)1.50'→-1.5."""
    m = list(_NUM.finditer(str(s).replace(",", "")))
    if not m:
        return None
    return float(m[-1].group(2)) * (-1.0 if m[-1].group(1) else 1.0)


def _pt(x, y, z):
    return "(list %.6f %.6f %.6f)" % (x, y, z)


def _setz(handle, z, text=False):
    """객체의 Z를 바꾼다(삽입점 10, 문자는 정렬점 11도)."""
    s = '(setq _e (entget (handent "%s")) _e (subst (list 10 (cadr (assoc 10 _e)) (caddr (assoc 10 _e)) %.6f) (assoc 10 _e) _e))' % (
        handle, z)
    if text:
        s += ' (if (assoc 11 _e) (setq _e (subst (list 11 (cadr (assoc 11 _e)) (caddr (assoc 11 _e)) %.6f) (assoc 11 _e) _e)))' % z
    return s + " (entmod _e)"


def build(ents, cfg):
    """덤프(문자 기준점은 호출부가 정렬점 여부를 정해 뽑는다) → (LISP, 결과 요약)."""
    dx, dy = float(cfg["이격X"]), float(cfg["이격Y"])
    play, tlay = ls(cfg["점레이어"]), ls(cfg["문자레이어"])
    h, dec, just = float(cfg["높이"]), int(cfg["소수"]), JUST[cfg["정렬"]]
    skip0 = cfg["Z0제외"]
    out, made, skipped = [], {"points": 0, "texts": 0, "raised": 0}, 0

    def point(x, y, z):
        out.append('(bc:point %s "%s")' % (_pt(x + dx, y + dy, z), play))
        made["points"] += 1

    def text(x, y, z):
        out.append('(bc:text %s "%s" %.6f "%s" "%s" 0.0)' % (_pt(x + dx, y + dy, z if cfg["문자Z"] else 0.0),
                                                            ls(C.fmt(z, dec)), h, tlay, just))
        made["texts"] += 1

    mode = cfg["기능"]
    if mode == MODES[0]:
        for e in ents:
            z = num_in_text(e["text"])
            if z is None or not e["points"] or (skip0 and z == 0):
                skipped += 1
                continue
            x, y = e["points"][0][:2]
            point(x, y, z)
            if cfg["문자Z"]:
                out.append(_setz(e["handle"], z, True))
    elif mode in (MODES[1], MODES[2]):
        for e in ents:
            for x, y, z in e["points"]:
                if skip0 and abs(z) < 1e-12:
                    skipped += 1
                    continue
                if mode == MODES[2]:
                    out.append('(bc:point %s "%s")' % (_pt(x, y, z), play))
                    made["points"] += 1
                text(x, y, z)
    else:
        texts = [(e["points"][0], num_in_text(e["text"])) for e in ents
                 if e["type"] in ("TEXT", "MTEXT") and e["points"]]
        texts = [(p, z) for p, z in texts if z is not None and not (skip0 and z == 0)]
        r = float(cfg["반경"])
        for e in ents:
            if e["type"] not in ("POINT", "INSERT") or not e["points"]:
                continue
            x, y = e["points"][0][:2]
            best = min(texts, key=lambda t: math.hypot(t[0][0] - x, t[0][1] - y), default=None)
            if best is None or math.hypot(best[0][0] - x, best[0][1] - y) > r:
                skipped += 1
                continue
            out.append(_setz(e["handle"], best[1]))
            made["raised"] += 1
    made["skipped"] = skipped
    return "".join(out), made


def report(made) -> str:
    parts = []
    if made["points"]:
        parts.append("점 %d개" % made["points"])
    if made["texts"]:
        parts.append("문자 %d개" % made["texts"])
    if made["raised"]:
        parts.append("Z 올린 객체 %d개" % made["raised"])
    s = ", ".join(parts) or "만든 것 없음"
    return s + (" (건너뜀 %d)" % made["skipped"] if made["skipped"] else "")


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "Z값 점·문자 생성", size="520x520")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="도면에서 객체 선택 → 실행", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        body = ('(princ "\\n대상 객체 선택: ") (setq _ss (ssget (list (cons 0 "%s")))) (bc:dump-ss _ss %s _fp)'
                % (types_for(cfg), "T" if cfg["문자기준"] == "정렬점" else "nil"))
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
        if rows is None:
            return
        ents = C.parse_dump(rows)
        if not ents:
            self.status("고른 객체가 없습니다.")
            return
        code, made = build(ents, cfg)
        if code and self.in_cad(self.acad.lisp_undo, code, 120) is None:
            return
        self.status(report(made))


def main():
    Window().mainloop()
