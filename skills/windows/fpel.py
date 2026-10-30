# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""FPEL 종단도 다중 EL 표기 — 엑셀 [측점(누가거리), 찾을 EL, 표기1, 표기2]로 종단도 위 점을 찾아 표기.

종단 시작점(도면 점)과 그 점의 EL을 기준으로
  x = 시작점 x + (누가거리 − 시작 거리) × 1000 / H축척
  y = 시작점 y + (EL − 시작점 EL) × 1000 / V축척
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui

CMD = "FPEL"
FIELDS = [
    ("측점구분", "측점 구분", "choice", "Station", ["Station", "Number"]),
    ("시작거리", "시작 거리 (숫자 또는 0+000)", "str", "0", None),
    ("측점간격", "Number 측점 간격 (m)", "real", 20.0, None),
    ("H축척", "H 축척 (1000 = 1m가 도면 1)", "real", 1000.0, None),
    ("V축척", "V 축척", "real", 200.0, None),
    ("소수", "EL 소수 자리", "int", 2, None),
    ("머리말", "EL 머리말 (예: EL=)", "str", "", None),
    ("레이어", "레이어 (비우면 현재)", "str", "", None),
    ("높이", "문자 높이", "real", 2.5, None),
    ("선길이", "선 길이 (문자 높이 배수)", "real", 10.0, None),
    ("표기종류", "표기 종류", "choice", "지시선", ["지시선", "수직선"]),
    ("표기위치", "표기 위치", "choice", "아래", ["아래", "위"]),
    ("표기값", "표기 값", "choice", "EL", ["EL", "EL+엑셀값"]),
    ("측점표기", "측점도 표기", "bool", True, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def _q(s):
    """LISP 문자열 리터럴 안에 넣을 값(역슬래시·따옴표 이스케이프,)."""
    from validators import lisp_str
    return lisp_str(s)


def items_from_rows(rows, cfg):
    out = []
    for r in rows:
        r = list(r) + [None] * 4
        d = C.station_to_dist(r[0], cfg["측점구분"], float(cfg["측점간격"]))
        el = X.to_float(r[1])
        if d is None or el is None:
            continue
        lab = r[0] if isinstance(r[0], str) else C.fmt(float(r[0]), 3)
        out.append((d, el, _q(lab), _q(r[2] or ""), _q(r[3] or "")))
    return out


def build_lisp(items, cfg, sp, el0) -> str:
    d0 = C.station_to_dist(cfg["시작거리"], cfg["측점구분"], float(cfg["측점간격"])) or 0.0
    kx, ky = 1000.0 / float(cfg["H축척"]), 1000.0 / float(cfg["V축척"])
    h = float(cfg["높이"])
    L = h * float(cfg["선길이"])
    lay = _q(cfg["레이어"])
    sgn = -1.0 if cfg["표기위치"] == "아래" else 1.0
    s = []
    for d, el, lab, t1, t2 in items:
        x = sp[0] + (d - d0) * kx
        y = sp[1] + (el - el0) * ky
        e = (x, y + sgn * L)
        val = _q("%s%s" % (cfg["머리말"], C.fmt(el, cfg["소수"])))
        if cfg["표기종류"] == "수직선":
            s.append('(bc:line (list %.10f %.10f 0.0) (list %.10f %.10f 0.0) "%s")' % (x, y, e[0], e[1], lay))
            s.append('(bc:text (list %.10f %.10f 0.0) "%s" %.6f "%s" "%s" %.10f)'
                     % (e[0] - h * 0.3, e[1], val, h, lay, "MR" if sgn < 0 else "ML", math.pi / 2))
        else:
            w = h * 0.85 * max(6, len(val), len(t1), len(t2))
            s.append('(bc:pline (list (list %.10f %.10f) (list %.10f %.10f) (list %.10f %.10f)) nil "%s")'
                     % (x, y, e[0], e[1], e[0] + w, e[1], lay))
            top = val if cfg["표기값"] == "EL" else (t1 or val)
            s.append('(bc:text (list %.10f %.10f 0.0) "%s" %.6f "%s" "BL" 0.0)' % (e[0] + h * 0.3, e[1] + h * 0.3, top, h, lay))
            low = t2 if cfg["표기값"] != "EL" else ""
            if cfg["표기값"] != "EL" and t1:
                low = (val + " " + t2).strip()
            if low:
                s.append('(bc:text (list %.10f %.10f 0.0) "%s" %.6f "%s" "TL" 0.0)' % (e[0] + h * 0.3, e[1] - h * 0.3, low, h, lay))
        if cfg["측점표기"]:
            s.append('(bc:text (list %.10f %.10f 0.0) "%s" %.6f "%s" "BC" %.10f)'
                     % (x - h * 0.3, (y + e[1]) / 2.0, lab, h * 0.8, lay, math.pi / 2))
    return "".join(s)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "종단도 다중 EL 표기", size="560x660")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Label(body, text="엑셀 범위: [측점(누가거리), 찾을 EL] 또는 [측점, EL, 표기1, 표기2]", bg=ui.PANEL, fg=ui.FG,
                 font=ui.FONT).pack(fill="x", padx=8, pady=4)
        tk.Button(self, text="실행 (엑셀 범위 먼저 선택 → 종단 시작점·EL 지정)", command=self.run, bg="#3E5879",
                  fg="#FFFFFF", relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
            S.save(CMD, cfg)
            items = items_from_rows(X.selection_values(), cfg)
        except (ValueError, X.ExcelNotReady) as e:
            self.error(str(e))
            return
        if not items:
            self.error("엑셀 선택 범위에서 측점·EL을 읽지 못했습니다.")
            return
        body = ('(setq _p (getpoint "\\n종단 시작점 지정: "))'
                ' (if _p (progn (setq _p (trans _p 1 0))'
                ' (setq _e (bc:get-number-or-pick "종단 시작점의 EL 문자 선택 또는 [EL 값 입력(E)]" "E" nil))'
                ' (if (= _e "E") (setq _e (getreal "\\nEL 값: ")))'
                ' (if (numberp _e) (write-line (strcat "S\\t" (bc:rtos (car _p) 2 10) "\\t" (bc:rtos (cadr _p) 2 10) "\\t" (bc:rtos _e 2 10)) _fp))))')
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
        st = [r for r in (rows or []) if r.startswith("S\t")]
        if not st:
            self.status("취소했습니다.")
            return
        _t, x, y, el0 = st[0].split("\t")
        if self.in_cad(self.acad.lisp_undo, build_lisp(items, cfg, (float(x), float(y)), float(el0)), 120) is not None:
            self.status("EL %d개를 표기했습니다." % len(items))


def main():
    Window().mainloop()
