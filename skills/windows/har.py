# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""HAR 종류별 해치 면적 조회 — 고른 해치를 색·레이어·무늬별로 묶어 면적 표를 그린다.

구분을 모두 끄면 전체 면적 하나. 개별 번호를 켜면 해치마다 번호를 쓰고 표에 해치마다 한 줄(묶음마다 소계).
면적 = 도면 면적 ÷ (1000 ÷ 축척)² ㎡, 단위 ㎡·평(py)·a·ha·㎢. group()·table_rows()는 창 없이도 쓴다(MCP skill_run).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import cadtable as TB
from skills.common import geo as G
from skills.common import profile as P
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "HAR"
FIELDS = [
    ("색별", "색으로 나누기", "bool", False, None),
    ("레이어별", "레이어로 나누기", "bool", True, None),
    ("무늬별", "무늬(패턴)로 나누기", "bool", True, None),
    ("축척", "산출 축척 (1000 = m 도면, 1 = mm 도면)", "real", 1000.0, None),
    ("단위", "면적 단위", "choice", G.AREA_UNITS[0], G.AREA_UNITS),
    ("소수", "소수 자리", "int", 2, None),
    ("소수적용", "소수 처리", "choice", "반올림", ["반올림", "올림", "내림"]),
    ("천단위", "천 단위 구분 기호", "bool", True, None),
    ("개별번호", "해치마다 번호 쓰고 개별 면적 (묶음마다 소계)", "bool", False, None),
    ("번호머리", "번호 머리말", "str", "A-", None),
    ("문자높이", "표·번호 문자 높이", "real", 2.5, None),
    ("문자레이어", "표·번호 문자 레이어", "str", "면적표_문자", None),
    ("선레이어", "표 선 레이어", "str", "면적표_선", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def key_of(e, cfg):
    k = []
    if cfg["무늬별"]:
        k.append(e["pattern"])
    if cfg["레이어별"]:
        k.append(e["layer"])
    if cfg["색별"]:
        k.append("ByLayer" if e["color"] == 256 else str(e["color"]))
    return tuple(k)


def head_of(cfg):
    return ["무늬"] * bool(cfg["무늬별"]) + ["레이어"] * bool(cfg["레이어별"]) + ["색"] * bool(cfg["색별"])


def group(ents, cfg):
    """→ [(묶음 키, [(번호, 해치, 면적)])] — 키 순, 번호는 묶음 순으로 이어서."""
    k2 = G.upm(cfg["축척"]) ** 2
    groups = {}
    for e in ents:
        groups.setdefault(key_of(e, cfg), []).append(e)
    out, n = [], 0
    for k in sorted(groups):
        items = []
        for e in groups[k]:
            n += 1
            items.append(("%s%d" % (cfg["번호머리"], n), e, G.area_in(e["area"] / k2, cfg["단위"])))
        out.append((k, items))
    return out


def fmt_area(v, cfg):
    return G.num_str(G.round_mode(v, int(cfg["소수"]), cfg["소수적용"]), int(cfg["소수"]), cfg["천단위"])


def table_rows(groups, cfg):
    """표 행(머리 포함)과 병합. 소계·합계는 보이는 값(반올림)으로 더한다."""
    head = (["번호"] if cfg["개별번호"] else []) + head_of(cfg) + ["개수", "면적(%s)" % cfg["단위"]]
    rows, merges = [head], []
    total = 0.0
    nk = len(head_of(cfg))
    for k, items in groups:
        vals = [G.round_mode(a, int(cfg["소수"]), cfg["소수적용"]) for _n, _e, a in items]
        sub = sum(vals)
        total += sub
        if cfg["개별번호"]:
            for (no, _e, _a), v in zip(items, vals):
                rows.append([no] + list(k) + ["1", G.num_str(v, int(cfg["소수"]), cfg["천단위"])])
            if nk or len(groups) > 1:
                rows.append(["소계"] + [""] * nk + [str(len(items)), G.num_str(sub, int(cfg["소수"]), cfg["천단위"])])
                merges.append((len(rows) - 1, 0, len(rows) - 1, nk))
        else:
            rows.append(list(k) + [str(len(items)), G.num_str(sub, int(cfg["소수"]), cfg["천단위"])])
    span = len(head) - 3
    rows.append(["합계"] + [""] * span + [str(sum(len(i) for _k, i in groups)), G.num_str(total, int(cfg["소수"]), cfg["천단위"])])
    if span > 0:
        merges.append((len(rows) - 1, 0, len(rows) - 1, span))
    return rows, merges, total


def number_lisp(groups, cfg):
    lay, h = ls(cfg["문자레이어"]), float(cfg["문자높이"])
    out = []
    for _k, items in groups:
        for no, e, _a in items:
            pts = G.polygon(e["pieces"]) if e["pieces"] else []
            if len(pts) < 3:
                continue
            x, y = P.label_point(pts)
            out.append('(bc:text (list %.6f %.6f 0.0) "%s" %.6f "%s" "MC" 0.0)' % (x, y, ls(no), h, lay))
    return "".join(out)


def table_lisp(rows, merges, origin, cfg):
    h = float(cfg["문자높이"])
    widths = [max(8 * h, max(len(str(r[j])) if j < len(r) else 0 for r in rows) * h * 0.9 + 2 * h) for j in range(len(rows[0]))]
    code, _w, _h = TB.table_lisp(rows, origin, widths, 3 * h, h, cfg["문자레이어"], cfg["선레이어"], merges)
    return code


def dump_lisp():
    """해치 G 줄(면적·무늬)과 첫 외곽 고리 구간. 고리가 폴리선 객체가 아니면(선·호 경계) 외곽 상자 가운데."""
    return ('(foreach _en (bc:ss-list _ss) (setq _ed (entget _en) _o (vlax-ename->vla-object _en) _b (bc:cr-box _en))'
            ' (write-line (strcat "G" _d (cdr (assoc 5 _ed)) _d "HATCH" _d (cdr (assoc 8 _ed)) _d'
            '  (itoa (if (assoc 62 _ed) (cdr (assoc 62 _ed)) 256)) _d "1" _d "0" _d'
            '  (bc:rtos (vla-get-Area _o) 2 10) _d (bc:rtos (car (car _b)) 2 10) _d (bc:rtos (cadr (car _b)) 2 10) _d'
            '  (bc:rtos (car (cadr _b)) 2 10) _d (bc:rtos (cadr (cadr _b)) 2 10) _d "0" _d (cdr (assoc 2 _ed))) _fp)'
            ' (setq _v nil _on nil)'
            ' (foreach _g _ed (cond ((= (car _g) 92) (setq _on (if (not _v) T nil)))'
            '                       ((and _on (= (car _g) 10) (= (length _g) 3)) (setq _v (cons (cdr _g) _v)))'
            '                       ((and _v (= (car _g) 97)) (setq _on nil))))'
            ' (setq _v (reverse _v))'
            ' (if (> (length _v) 2) (progn (setq _v (append _v (list (car _v))))'
            '  (while (cdr _v) (write-line (strcat "K" _d (bc:rtos (caar _v) 2 10) _d (bc:rtos (cadar _v) 2 10) _d'
            '   (bc:rtos (caadr _v) 2 10) _d (bc:rtos (cadadr _v) 2 10) _d "0") _fp) (setq _v (cdr _v))))))')


def fill_missing(ents):
    """외곽 구간이 없는 해치(선·호 경계)는 외곽 상자로 번호 자리를 잡는다(start·end에 상자)."""
    for e in ents:
        if not e["pieces"]:
            (x0, y0), (x1, y1) = e["start"], e["end"]
            e["pieces"] = [((x0, y0), (x1, y0), 0.0), ((x1, y0), (x1, y1), 0.0), ((x1, y1), (x0, y1), 0.0),
                           ((x0, y1), (x0, y0), 0.0)]
    return ents


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "종류별 해치 면적 조회", size="520x700")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="해치 선택 → 표 넣을 점 지정", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        body = ('(princ "\\n해치 선택: ") (setq _ss (ssget (list (cons 0 "HATCH")))) (if _ss (progn %s'
                ' (setq _p (getpoint "\\n표 넣을 점(왼쪽 위) 지정: ")) (if _p (progn (setq _p (trans _p 1 0))'
                ' (write-line (strcat "O" _d (bc:rtos (car _p) 2 10) _d (bc:rtos (cadr _p) 2 10)) _fp)))))' % dump_lisp())
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
        org = [r.split("\t") for r in rows or [] if r.startswith("O\t")]
        if not org:
            return
        ents = fill_missing(G.parse(rows))
        gs = group(ents, cfg)
        trows, merges, total = table_rows(gs, cfg)
        code = table_lisp(trows, merges, (float(org[0][1]), float(org[0][2])), cfg)
        if cfg["개별번호"]:
            code += number_lisp(gs, cfg)
        if self.in_cad(self.acad.lisp_undo, code, 120) is not None:
            self.status("해치 %d개, 합계 %s %s" % (len(ents), fmt_area(total, cfg), cfg["단위"]))


def main():
    Window().mainloop()
