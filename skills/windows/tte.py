# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""TTE 문자를 엑셀로 — 고른 문자·치수 값·블록 속성 값을 정렬 순서대로 엑셀 선택 셀부터 넣는다.

여러 번 고르면 고른 묶음(그룹)마다 다음 열(또는 다음 행)에 이어 넣는다.
grid()·after_lisp()는 창 없이도 쓴다(MCP skill_run).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "TTE"
SORTS = ["선택한 대로"] + C.SORTS[1:]
AFTER = ["변경 없음", "레이어 변경", "색상 변경", "내보낸 후 삭제"]
FIELDS = [
    ("정렬", "문자 정렬", "choice", "위→아래 우선, 좌→우", SORTS),
    ("문자기준", "정렬 기준 위치", "choice", "삽입점", ["삽입점", "정렬점"]),
    ("방향", "엑셀 입력 방향 (그룹은 그 옆으로)", "choice", "아래로", ["아래로", "오른쪽으로"]),
    ("대상치수", "치수 값도 포함", "bool", True, None),
    ("속성태그", "블록 속성 태그 (비우면 블록 제외)", "str", "", None),
    ("처리", "내보낸 문자 처리", "choice", AFTER[0], AFTER),
    ("처리레이어", "처리: 바꿀 레이어", "str", "TTE_내보냄", None),
    ("처리색", "처리: 바꿀 색 (ACI)", "int", 1, None),
    ("열너비맞춤", "엑셀 열 너비 자동 맞춤", "bool", True, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def types_for(cfg) -> str:
    t = "TEXT,MTEXT"
    if cfg["대상치수"]:
        t += ",DIMENSION"
    if cfg["속성태그"]:
        t += ",INSERT"
    return t


def dump_lisp(cfg) -> str:
    """선택 집합 _ss → 'T<탭>핸들<탭>x<탭>y<탭>내용' 줄. 치수는 덮어쓴 문자(<>는 측정값), 블록은 그 태그의 속성."""
    al = "T" if cfg["문자기준"] == "정렬점" else "nil"
    return (
        '(defun _tte-dim (o / m s)'
        ' (setq m (rtos (vla-get-Measurement o) 2 (vla-get-PrimaryUnitsPrecision o)) s (vla-get-TextOverride o))'
        ' (cond ((= s "") m) ((vl-string-search "<>" s) (vl-string-subst m "<>" s)) (T s)))'
        '(defun _tte-att (en / o r)'
        ' (setq o (vlax-ename->vla-object en))'
        ' (if (= (vla-get-HasAttributes o) :vlax-true)'
        '  (foreach a (vlax-invoke o (quote GetAttributes))'
        '   (if (= (strcase (vla-get-TagString a)) (strcase "%s")) (setq r (vla-get-TextString a))))) r)'
        '(if _ss (progn (setq _i 0) (while (< _i (sslength _ss))'
        ' (setq _en (ssname _ss _i) _ed (entget _en) _ty (cdr (assoc 0 _ed)) _i (1+ _i)'
        '  _tx (cond ((= _ty "DIMENSION") (_tte-dim (vlax-ename->vla-object _en)))'
        '            ((= _ty "INSERT") (_tte-att _en)) (T (bc:text-of _en)))'
        '  _p (cond ((= _ty "DIMENSION") (trans (cdr (assoc 11 _ed)) _en 0)) (T (car (bc:ent-points _en %s)))))'
        ' (if (and _tx _p) (write-line (strcat "T" _d (cdr (assoc 5 _ed)) _d (bc:rtos (car _p) 2 8) _d (bc:rtos (cadr _p) 2 8)'
        '  _d (vl-string-translate "\\t\\n\\r" "   " _tx)) _fp)))))'
        % (ls(cfg["속성태그"]), al))


def parse(rows):
    """dump_lisp 결과 → [{handle, x, y, text}]"""
    out = []
    for r in rows:
        c = r.split("\t", 4)
        if c[0] == "T" and len(c) == 5:
            out.append({"handle": c[1], "x": float(c[2]), "y": float(c[3]), "text": c[4]})
    return out


def sort_items(items, how):
    if how == "내용 오름차순":
        return sorted(items, key=lambda it: it["text"])
    if how == "내용 내림차순":
        return sorted(items, key=lambda it: it["text"], reverse=True)
    if how == "선택한 대로":
        return list(items)
    return C.sort_points(items, how, key=lambda it: (it["x"], it["y"], 0.0))


def grid(groups, cfg):
    """그룹 목록(각각 정렬된 항목) → 엑셀에 넣을 2차원 표. 아래로: 그룹마다 한 열, 오른쪽으로: 그룹마다 한 행."""
    cols = [[it["text"] for it in g] for g in groups if g]
    if cfg["방향"] == "오른쪽으로":
        return cols
    n = max((len(c) for c in cols), default=0)
    return [[c[i] if i < len(c) else "" for c in cols] for i in range(n)]


def after_lisp(handles, cfg) -> str:
    """내보낸 문자 처리(레이어·색 바꾸기, 지우기)."""
    how = cfg["처리"]
    if how == AFTER[0] or not handles:
        return ""
    hs = " ".join('"%s"' % ls(h) for h in handles)
    if how == AFTER[1]:
        lay = ls(cfg["처리레이어"])
        act = '(bc:ensure-layer "%s" 7) (setq _e (subst (cons 8 "%s") (assoc 8 _e) _e)) (entmod _e)' % (lay, lay)
    elif how == AFTER[2]:
        act = ('(setq _e (if (assoc 62 _e) (subst (cons 62 %d) (assoc 62 _e) _e) (append _e (list (cons 62 %d)))))'
               ' (entmod _e)' % (int(cfg["처리색"]), int(cfg["처리색"])))
    else:
        act = "(entdel (handent _h))"
    return "(foreach _h (list %s) (if (handent _h) (progn (setq _e (entget (handent _h))) %s)))" % (hs, act)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "문자를 엑셀로", size="520x440")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Label(self, text="엑셀에서 넣을 첫 셀을 먼저 고른 뒤 실행하세요. 문자 묶음을 여러 번 고를 수 있고 엔터로 끝냅니다.",
                 bg=ui.BG, fg=ui.STATUS, font=ui.FONT, wraplength=490, justify="left").pack(fill="x", padx=10)
        tk.Button(self, text="도면에서 문자 선택 → 엑셀로", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def _pick(self, cfg):
        groups, n = [], 1
        while True:
            body = ('(princ "\\n그룹 %d 문자 선택 (끝내려면 엔터): ") (setq _ss (ssget (list (cons 0 "%s")))) %s'
                    % (n, types_for(cfg), dump_lisp(cfg)))
            items = parse(self.acad.lisp(body, A.PICK_TIMEOUT))
            if not items:
                return groups
            groups.append(sort_items(items, cfg["정렬"]))
            n += 1

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        groups = self.in_cad(self._pick, cfg)
        if not groups:
            self.status("고른 문자가 없습니다.")
            return
        data = grid(groups, cfg)
        try:
            ws, r, c = X.active_cell()
            X.write_rows(ws, r, c, data, cfg["열너비맞춤"])
        except X.ExcelNotReady as e:
            self.error(str(e))
            return
        code = after_lisp([it["handle"] for g in groups for it in g], cfg)
        if code:
            self.in_cad(self.acad.lisp_undo, code)
        self.status("그룹 %d개, 문자 %d개를 엑셀 %s!%s행 %s열부터 넣었습니다."
                    % (len(groups), sum(len(g) for g in groups), ws.Name, r, c))


def main():
    Window().mainloop()
