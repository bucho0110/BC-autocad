# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""DDE 동일 중복 객체 정리 — 고른 객체 중 똑같은 것(종류별 기준이 소수 자리까지 같음)을 하나만 남기고 지운다.

종류별 기준: 점(좌표), 선(두 끝점, 방향 무관), 폴리선(닫힘·정점 수·정점·길이·면적, 방향 무관), 원(중심·반지름),
호(중심·반지름·각), 타원, 문자(내용·높이·각·위치), 블록(이름·위치·축척·각·속성 값), 솔리드·3D면(꼭짓점),
해치(무늬·축척·각·면적·위치), 치수(종류·정의점·문자), 스플라인(조정점).
지우지 않고 다른 레이어로 옮겨 확인할 수도 있다. 먼저 만든(핸들이 작은) 것을 남긴다.
duplicates()는 창 없이도 쓴다(MCP skill_run).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "DDE"
FIELDS = [
    ("대상", "검사할 종류 (쉼표, 비우면 모두)", "str",
     "POINT,LINE,LWPOLYLINE,POLYLINE,CIRCLE,ARC,ELLIPSE,TEXT,MTEXT,INSERT,SOLID,3DFACE,HATCH,DIMENSION,SPLINE", None),
    ("소수", "같다고 볼 좌표 소수 자리", "int", 4, None),
    ("잠긴레이어", "잠긴 레이어 객체도 지우기", "bool", False, None),
    ("레이어다르면제외", "레이어가 다르면 중복으로 보지 않기", "bool", True, None),
    ("옮기기", "지우지 않고 레이어만 옮기기", "bool", False, None),
    ("옮길레이어", "옮길 레이어", "str", "중복객체", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}

CODES = {"POINT": "10", "LINE": "10 11", "CIRCLE": "10 40", "ARC": "10 40 50 51", "ELLIPSE": "10 11 40 41 42",
         "TEXT": "1 40 50 10 11 72 73", "MTEXT": "1 40 50 10 71", "INSERT": "2 10 41 42 43 50",
         "SOLID": "10 11 12 13", "3DFACE": "10 11 12 13", "TRACE": "10 11 12 13", "HATCH": "2 41 52",
         "DIMENSION": "70 10 11 13 14 15 16 1 2", "SPLINE": "70 10", "LWPOLYLINE": "70 38", "POLYLINE": "70"}

DUMP_LISP = (
    '(defun _dde-v (v) (cond ((= (type v) (quote STR)) (vl-string-translate "\\t|\\n\\r" "    " v))'
    ' ((member (type v) (list (quote REAL) (quote INT))) (bc:rtos v 2 10))'
    ' ((= (type v) (quote LIST)) (apply (quote strcat) (mapcar (quote (lambda (x) (strcat (bc:rtos x 2 10) ","))) v))) (T "")))'
    '(defun _dde-lock (ly) (= 4 (logand 4 (cdr (assoc 70 (tblsearch "LAYER" ly))))))'
    '(foreach _en (bc:ss-list _ss) (setq _ed (entget _en) _ty (cdr (assoc 0 _ed)) _cs (cdr (assoc _ty _codes)) _out "")'
    ' (if _cs (progn'
    '  (foreach _g _ed (if (and (member (car _g) _cs) (/= (car _g) 1)) (setq _out (strcat _out "|" (itoa (car _g)) "=" (_dde-v (cdr _g))))))'
    '  (if (member _ty (list "TEXT" "MTEXT")) (setq _out (strcat _out "|1=" (_dde-v (bc:text-of _en)))))'
    '  (if (member _ty (list "DIMENSION")) (setq _out (strcat _out "|1=" (_dde-v (cdr (assoc 1 _ed))))))'
    '  (if (= _ty "INSERT") (progn (setq _a (entnext _en))'
    '   (while (and _a (= (cdr (assoc 0 (entget _a))) "ATTRIB"))'
    '    (setq _out (strcat _out "|A=" (_dde-v (cdr (assoc 2 (entget _a)))) ":" (_dde-v (cdr (assoc 1 (entget _a))))) _a (entnext _a)))))'
    '  (if (member _ty (list "LWPOLYLINE" "POLYLINE" "HATCH")) (progn'
    '   (setq _r (vl-catch-all-apply (quote vla-get-Area) (list (vlax-ename->vla-object _en))))'
    '   (setq _out (strcat _out "|AREA=" (if (vl-catch-all-error-p _r) "0" (bc:rtos _r 2 10))))))'
    '  (if (member _ty (list "LWPOLYLINE" "POLYLINE")) (progn'
    '   (setq _out (strcat _out "|LEN=" (bc:rtos (vlax-curve-getDistAtParam _en (vlax-curve-getEndParam _en)) 2 10)))'
    '   (foreach _p (bc:verts _en) (setq _out (strcat _out "|V=" (_dde-v _p))))))'
    '  (if (= _ty "HATCH") (progn (setq _b (bc:cr-box _en)) (setq _out (strcat _out "|BB=" (_dde-v (car _b)) (_dde-v (cadr _b))))))'
    '  (write-line (strcat "D" _d (cdr (assoc 5 _ed)) _d _ty _d (cdr (assoc 8 _ed)) _d (if (_dde-lock (cdr (assoc 8 _ed))) "1" "0")'
    '   _d _out) _fp))))')


def codes_lisp(types):
    return "(setq _codes (list %s))" % " ".join('(cons "%s" (list %s))' % (t, CODES[t]) for t in types if t in CODES)


def parse(rows):
    out = []
    for r in rows:
        c = r.split("\t")
        if c[0] == "D" and len(c) >= 6:
            out.append({"handle": c[1], "type": c[2], "layer": c[3], "locked": c[4] == "1", "data": c[5]})
    return out


def _tok(v, dec):
    """숫자(쉼표로 이은 좌표 포함)는 소수 dec 자리로, 글자는 그대로."""
    parts = [p for p in v.split(",") if p != ""] if "," in v else [v]
    res = []
    for p in parts:
        try:
            f = round(float(p), dec)
            res.append("%.*f" % (dec, 0.0 if f == 0 else f))
        except ValueError:
            return v
    return ",".join(res)


def signature(e, cfg):
    dec = int(cfg["소수"])
    items = [s.split("=", 1) for s in e["data"].split("|") if "=" in s]
    pts = [_tok(v, dec) for k, v in items if k == "V"]
    rest = [(k, _tok(v, dec) if k not in ("1", "2", "A") else v) for k, v in items if k != "V"]
    if e["type"] == "LINE":
        ends = sorted(v for k, v in rest if k in ("10", "11"))
        rest = [("E", ",".join(ends))]
    if pts:
        rest.append(("V", ";".join(sorted(pts))))  # 방향·시작점 무관
        rest.append(("N", str(len(pts))))
    key = (e["type"], tuple(sorted(rest)))
    return key + ((e["layer"],) if cfg["레이어다르면제외"] else ())


def duplicates(ents, cfg):
    """→ 지울(옮길) 핸들 목록. 잠긴 레이어 객체는 설정에 따라 뺀다(남기는 쪽은 상관없음)."""
    groups = {}
    for e in sorted(ents, key=lambda e: int(e["handle"], 16)):
        groups.setdefault(signature(e, cfg), []).append(e)
    out = []
    for g in groups.values():
        for e in g[1:]:
            if e["locked"] and not cfg["잠긴레이어"]:
                continue
            out.append(e["handle"])
    return out


def apply_lisp(handles, cfg):
    if not handles:
        return ""
    return each_lisp(handles, "(vla-put-Layer _o \"%s\")" % ls(cfg["옮길레이어"]) if cfg["옮기기"] else "(vla-Delete _o)",
                     ('(bc:ensure-layer "%s" 1)' % ls(cfg["옮길레이어"])) if cfg["옮기기"] else "")


def each_lisp(handles, action, head=""):
    """핸들마다 _o에 action — 잠긴 레이어면 잠깐 풀었다가 다시 잠근다."""
    return (head + '(setq _lys (vla-get-Layers (vla-get-ActiveDocument (vlax-get-acad-object))))'
            '(foreach _h (list %s) (setq _e (handent _h)) (if _e (progn (setq _o (vlax-ename->vla-object _e)'
            ' _ly (vla-Item _lys (vla-get-Layer _o)) _lk (vla-get-Lock _ly))'
            ' (if (= _lk :vlax-true) (vla-put-Lock _ly :vlax-false)) %s (if (= _lk :vlax-true) (vla-put-Lock _ly :vlax-true)))))'
            % (" ".join('"%s"' % h for h in handles), action))


def types_of(cfg):
    return [t.strip().upper() for t in str(cfg["대상"]).split(",") if t.strip()] or list(CODES)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "동일 중복 객체 정리", size="540x420")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="객체 선택 → 중복 삭제", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        ty = types_of(cfg)
        rows = self.in_cad(self.acad.lisp, '(princ "\\n검사할 객체 선택: ") (setq _ss (ssget (list (cons 0 "%s")))) %s %s'
                           % (",".join(ty), codes_lisp(ty), DUMP_LISP), A.PICK_TIMEOUT)
        if rows is None:
            return
        ents = parse(rows)
        hs = duplicates(ents, cfg)
        if hs and self.in_cad(self.acad.lisp_undo, apply_lisp(hs, cfg), 120) is None:
            return
        self.status("객체 %d개 중 중복 %d개를 %s." % (len(ents), len(hs), "옮겼습니다" if cfg["옮기기"] else "지웠습니다"))


def main():
    Window().mainloop()
