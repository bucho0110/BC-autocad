# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""HWLM 하천 횡단 홍수위 표시 일괄 — 엑셀 [측점, H.W.L, S.W.L(선택), 여유고(선택)]를 횡단면마다 표기.

단면은 견본 한 단면으로 찾고(skills/common/xsec.py), 측점은 누가거리 소수 4자리로 맞춘다(구조물 인접 0.0005km 단면 보존).
표기: 수위 기호(역삼각형 + 아래 짧은 선 셋), 수면선(지반선과 만나는 바깥 두 점 사이), 'H.W.L EL.12.345' 문자.
build_lisp()는 창 없이도 쓴다(MCP run_skill).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as XL
from skills.common import settings as S
from skills.common import ui
from skills.common import xsec as X
from validators import lisp_str as ls

CMD = "HWLM"
FIELDS = [
    ("H축척", "횡단 수평 축척 (단면 아래 거리 눈금이 없을 때만, 글자 크기 기준)", "real", 1000.0, None),
    ("V축척", "횡단 수직 축척 (단면 왼쪽 EL 눈금이 없을 때만)", "real", 1000.0, None),
    ("측점구분", "측점 구분", "choice", "Station", ["Station", "Number"]),
    ("측점간격", "Number 측점 간격 (m)", "real", 20.0, None),
    ("HWL표기", "H.W.L 표기", "bool", True, None),
    ("SWL표기", "S.W.L 표기(엑셀 3열)", "bool", True, None),
    ("여유고선", "여유고 선(엑셀 4열 = 여유고 m)", "bool", False, None),
    ("수면선", "수면선(지반선 사이) 그리기", "bool", True, None),
    ("기호위치", "횡단 중심~기호 거리 (m, + 오른쪽)", "real", 0.0, None),
    ("높이", "문자 높이 (축척 1000 기준)", "real", 2.0, None),
    ("소수", "수위 소수 자리", "int", 3, None),
    ("HWL머리", "H.W.L 머리말", "str", "H.W.L EL.", None),
    ("SWL머리", "S.W.L 머리말", "str", "S.W.L EL.", None),
    ("레이어", "레이어 (비우면 현재)", "str", "", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def rows_to_data(rows, cfg):
    """엑셀 행 → {누가거리(소수 4자리): (HWL, SWL, 여유고)}. 머리글은 건너뛴다."""
    out = {}
    for r in rows:
        r = list(r) + [None] * 4
        d = C.station_to_dist(r[0], cfg["측점구분"], float(cfg["측점간격"]))
        hwl = XL.to_float(r[1])
        if d is None or hwl is None:
            continue
        out[round(d, 4)] = (hwl, XL.to_float(r[2]), XL.to_float(r[3]))
    return out


def _water_span(sec, y):
    """수면 y에서 지반선과 만나는 가장 바깥 두 X(중심 양쪽). 못 찾으면 중심 ± 짧게."""
    pts = sec["ground_pts"]
    xs = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if (y0 - y) * (y1 - y) <= 0 and abs(y1 - y0) > 1e-12:
            xs.append(x0 + (x1 - x0) * (y - y0) / (y1 - y0))
    cx = sec["center"][0]
    left = [x for x in xs if x <= cx]
    right = [x for x in xs if x >= cx]
    if left and right:
        return max(left), min(right)
    return None


def mark_lisp(sec, el, head, cfg) -> str:
    V, uh = float(cfg["V축척"]), 1000.0 / float(cfg["H축척"])
    h = float(cfg["높이"]) * uh
    lay = ls(cfg["레이어"])
    y = X.y_of(sec, el, V)
    x = sec["center"][0] + float(cfg["기호위치"]) * X.uh(sec, float(cfg["H축척"]))
    s = []
    if cfg["수면선"]:
        sp = _water_span(sec, y)
        if sp:
            s.append('(bc:line (list %.10f %.10f 0.0) (list %.10f %.10f 0.0) "%s")' % (sp[0], y, sp[1], y, lay))
    # 역삼각형(꼭짓점이 수면)
    s.append('(bc:pline (list (list %.10f %.10f) (list %.10f %.10f) (list %.10f %.10f)) T "%s")'
             % (x, y, x - h * 0.5, y + h * 0.8, x + h * 0.5, y + h * 0.8, lay))
    for i, w in enumerate((1.0, 0.7, 0.4)):
        yy = y - h * 0.3 * (i + 1)
        s.append('(bc:line (list %.10f %.10f 0.0) (list %.10f %.10f 0.0) "%s")' % (x - h * w, yy, x + h * w, yy, lay))
    txt = ls("%s%s" % (head, C.fmt(el, cfg["소수"])))
    s.append('(bc:text (list %.10f %.10f 0.0) "%s" %.6f "%s" "BL" 0.0)' % (x + h * 0.9, y + h * 0.15, txt, h, lay))
    return "".join(s)


def build_lisp(sections, data, cfg):
    """반환 (LISP, 표기한 단면 수, 엑셀에 없는 단면 측점 목록)."""
    s, n, miss = [], 0, []
    for sec in sections:
        if not X.usable(sec) or sec["dist"] is None:
            continue
        v = data.get(round(sec["dist"], 4))
        if not v:
            miss.append(sec["station"])
            continue
        hwl, swl, fb = v
        if cfg["HWL표기"]:
            s.append(mark_lisp(sec, hwl, cfg["HWL머리"], cfg))
        if cfg["SWL표기"] and swl is not None:
            s.append(mark_lisp(sec, swl, cfg["SWL머리"], cfg))
        if cfg["여유고선"] and fb is not None:
            y = X.y_of(sec, hwl + fb, float(cfg["V축척"]))
            sp = _water_span(sec, y)
            if sp:
                s.append('(bc:line (list %.10f %.10f 0.0) (list %.10f %.10f 0.0) "%s")' % (sp[0], y, sp[1], y, ls(cfg["레이어"])))
        n += 1
    return "".join(s), n, miss


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "하천 횡단 홍수위 표시 일괄", size="560x660")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Label(body, text="엑셀 범위: [측점(누가거리), H.W.L, S.W.L, 여유고] — 뒤 두 열은 선택", bg=ui.PANEL, fg=ui.FG,
                 font=ui.FONT).pack(fill="x", padx=8, pady=4)
        bar = tk.Frame(self, bg=ui.BG)
        bar.pack(fill="x", padx=10, pady=4)
        tk.Button(bar, text="견본 단면 등록", command=self.sample, bg="#383A3E", fg="#FFFFFF", relief="flat",
                  height=2, width=16).pack(side="left", padx=3)
        tk.Button(bar, text="엑셀 범위 선택 후 → 일괄 표기", command=self.run, bg="#3E5879", fg="#FFFFFF", relief="flat",
                  height=2).pack(side="left", padx=3, expand=True, fill="x")
        sp = X.load_spec()
        self.status("견본: %s" % ("등록됨 (측점 %s)" % sp.get("sample_station") if sp else "없음 — 먼저 등록하세요"))

    def sample(self):
        rows = self.in_cad(self.acad.lisp, X.SAMPLE_BODY, A.PICK_TIMEOUT)
        sp = X.spec_from_rows(rows or [])
        if not sp:
            self.status("견본 등록을 취소했습니다.")
            return
        X.save_spec(sp)
        self.status("견본 등록: 측점 '%s', 지반고 '%s'" % (sp["sample_station"], sp["sample_el"]))

    def run(self):
        try:
            cfg = self.form.values()
            S.save(CMD, cfg)
            data = rows_to_data(XL.selection_values(), cfg)
        except (ValueError, XL.ExcelNotReady) as e:
            self.error(str(e))
            return
        sp = X.load_spec()
        if not sp:
            self.error("견본 단면을 먼저 등록하세요.")
            return
        rows = self.in_cad(self.acad.lisp, X.dump_body(sp), 120)
        if rows is None:
            return
        secs = X.find(sp, C.parse_dump(rows), cfg["측점구분"], float(cfg["측점간격"]))
        body, n, miss = build_lisp(secs, data, cfg)
        if not n:
            self.error("엑셀 측점과 맞는 단면이 없습니다(측점 구분·간격 확인). 찾은 단면 %d개" % len(secs))
            return
        if self.in_cad(self.acad.lisp_undo, body, 120) is not None:
            self.status("단면 %d개에 표기했습니다. 엑셀에 없는 단면 %d개: %s" % (n, len(miss), ", ".join(miss[:8])))


def main():
    Window().mainloop()
