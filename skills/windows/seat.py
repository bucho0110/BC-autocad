# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""SEAT 선택 객체 면적 표 그리기 — 고른 닫힌 객체(폴리선·원·타원·스플라인·해치)마다 번호를 쓰고 면적 표를 그린다.

구분: 레이어·색·없음(번호만). 순서: 구분 순·좌표 순(위 → 아래, 왼 → 오른)·선택 순·면적 순.
둘레 길이 열도 넣을 수 있다. 면적 = 도면 면적 ÷ (1000 ÷ 축척)² ㎡. build()는 창 없이도 쓴다(MCP skill_run).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import cadtable as TB
from skills.common import coords as C
from skills.common import geo as G
from skills.common import profile as P
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "SEAT"
KINDS = ["레이어", "색", "구분 없음"]
ORDERS = ["구분 순", "좌표 순(위→아래, 왼→오른)", "선택 순", "면적 작은 순"]
FIELDS = [
    ("구분", "면적 구분", "choice", KINDS[0], KINDS),
    ("순서", "표 순서", "choice", ORDERS[1], ORDERS),
    ("축척", "산출 축척 (1000 = m 도면, 1 = mm 도면)", "real", 1000.0, None),
    ("단위", "면적 단위", "choice", G.AREA_UNITS[0], G.AREA_UNITS),
    ("소수", "소수 자리", "int", 2, None),
    ("소수적용", "소수 처리", "choice", "반올림", ["반올림", "올림", "내림"]),
    ("천단위", "천 단위 구분 기호", "bool", True, None),
    ("둘레", "둘레 길이 열 넣기", "bool", False, None),
    ("소계", "구분마다 소계 (구분 순일 때)", "bool", True, None),
    ("번호", "객체에 번호 쓰기", "bool", True, None),
    ("번호머리", "번호 머리말", "str", "", None),
    ("시작번호", "시작 번호", "int", 1, None),
    ("원", "번호에 원 두르기", "bool", True, None),
    ("문자높이", "표·번호 문자 높이", "real", 2.5, None),
    ("문자레이어", "표·번호 문자 레이어", "str", "면적표_문자", None),
    ("선레이어", "표 선 레이어", "str", "면적표_선", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
TYPES = "LWPOLYLINE,POLYLINE,CIRCLE,ELLIPSE,SPLINE,HATCH"


def _gkey(e, cfg):
    return {"레이어": e["layer"], "색": "ByLayer" if e["color"] == 256 else str(e["color"])}.get(cfg["구분"], "")


def build(ents, cfg):
    """→ (표 행, 병합, 번호 자리 [(x, y, 번호)], 합계)."""
    ents = [e for e in ents if e["area"] > 0 and (e["pieces"] or e["type"] == "HATCH")]
    for e in ents:
        pts = G.polygon(e["pieces"]) if e["pieces"] else []
        e["_lab"] = P.label_point(pts) if len(pts) >= 3 else ((e["start"][0] + e["end"][0]) / 2, (e["start"][1] + e["end"][1]) / 2)
    k2 = G.upm(cfg["축척"]) ** 2
    dec = int(cfg["소수"])
    if cfg["순서"] == ORDERS[0]:
        ents.sort(key=lambda e: (_gkey(e, cfg), -e["_lab"][1], e["_lab"][0]))
    elif cfg["순서"] == ORDERS[1]:
        ents = C.sort_points(ents, "위→아래 우선, 좌→우", key=lambda e: (e["_lab"][0], e["_lab"][1], 0.0))
    elif cfg["순서"] == ORDERS[3]:
        ents.sort(key=lambda e: e["area"])
    show_k = cfg["구분"] != KINDS[2]
    head = ["번호"] + ([cfg["구분"]] if show_k else []) + ["면적(%s)" % cfg["단위"]] + (["둘레(m)"] if cfg["둘레"] else [])
    rows, merges, marks = [head], [], []
    total, sub, cur = 0.0, 0.0, None
    subtotal = cfg["소계"] and show_k and cfg["순서"] == ORDERS[0]

    def sub_row(k):
        rows.append(["소계"] + ([k] if show_k else []) + [G.num_str(sub, dec, cfg["천단위"])] + ([""] if cfg["둘레"] else []))

    for i, e in enumerate(ents):
        k = _gkey(e, cfg)
        if subtotal and cur is not None and k != cur:
            sub_row(cur)
            sub = 0.0
        cur = k
        no = "%s%d" % (cfg["번호머리"], int(cfg["시작번호"]) + i)
        a = G.round_mode(G.area_in(e["area"] / k2, cfg["단위"]), dec, cfg["소수적용"])
        total += a
        sub += a
        rows.append([no] + ([k] if show_k else []) + [G.num_str(a, dec, cfg["천단위"])] +
                    ([G.num_str(e["length"] / G.upm(cfg["축척"]), dec, cfg["천단위"])] if cfg["둘레"] else []))
        marks.append((e["_lab"][0], e["_lab"][1], no))
    if subtotal and cur is not None:
        sub_row(cur)
    rows.append(["합계"] + ([""] if show_k else []) + [G.num_str(total, dec, cfg["천단위"])] + ([""] if cfg["둘레"] else []))
    if show_k:
        merges.append((len(rows) - 1, 0, len(rows) - 1, 1))
    return rows, merges, marks, total


def draw_lisp(rows, merges, marks, origin, cfg):
    h = float(cfg["문자높이"])
    widths = [max(8 * h, max(len(str(r[j])) for r in rows) * h * 0.9 + 2 * h) for j in range(len(rows[0]))]
    code, _w, _hh = TB.table_lisp(rows, origin, widths, 3 * h, h, cfg["문자레이어"], cfg["선레이어"], merges)
    lay = ls(cfg["문자레이어"])
    if cfg["번호"]:
        for x, y, no in marks:
            code += '(bc:text (list %.6f %.6f 0.0) "%s" %.6f "%s" "MC" 0.0)' % (x, y, ls(no), h, lay)
            if cfg["원"]:
                code += '(bc:circle (list %.6f %.6f 0.0) %.6f "%s")' % (x, y, max(1.2 * h, 0.45 * h * len(no) + 0.6 * h), lay)
    return code


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "선택 객체 면적 표 그리기", size="520x760")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="닫힌 객체 선택 → 표 넣을 점 지정", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        from skills.windows.har import dump_lisp as hatch_dump
        body = ('(princ "\\n면적 낼 객체 선택: ") (setq _all (ssget (list (cons 0 "%s"))))'
                ' (if _all (progn (setq _ss (ssadd) _hs (ssadd)) (foreach _e (bc:ss-list _all)'
                ' (if (= (cdr (assoc 0 (entget _e))) "HATCH") (ssadd _e _hs) (ssadd _e _ss))) %s (setq _ss _hs) %s'
                ' (setq _p (getpoint "\\n표 넣을 점(왼쪽 위) 지정: ")) (if _p (progn (setq _p (trans _p 1 0))'
                ' (write-line (strcat "O" _d (bc:rtos (car _p) 2 10) _d (bc:rtos (cadr _p) 2 10)) _fp)))))'
                % (TYPES, G.GEO_LISP, hatch_dump()))
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
        org = [r.split("\t") for r in rows or [] if r.startswith("O\t")]
        if not org:
            return
        from skills.windows.har import fill_missing
        trows, merges, marks, total = build(fill_missing(G.parse(rows)), cfg)
        code = draw_lisp(trows, merges, marks, (float(org[0][1]), float(org[0][2])), cfg)
        if self.in_cad(self.acad.lisp_undo, code, 120) is not None:
            self.status("객체 %d개, 합계 %s %s" % (len(marks), G.num_str(total, int(cfg["소수"]), cfg["천단위"]), cfg["단위"]))


def main():
    Window().mainloop()
