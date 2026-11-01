# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""CTS 문자 그림자 — ① 문자 외곽선: 글자 윤곽을 따라 폭 있는 폴리선 ② 문자 복사: 조금 비켜 복사. 그림자는 원본 뒤로.

외곽선은 트루타입 글꼴 스타일의 TEXT만 된다(SHX 글꼴·MTEXT는 건너뛰고 알린다).
윤곽선은 AutoCAD 글자 상자(textbox)에 맞춰 크기·자리를 정하므로 폭 비율도 따른다(기울기는 반영 안 함).
build_outline()은 창 없이도 쓴다(MCP skill_run).
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import fontoutline as F
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "CTS"
MODES = ["문자 외곽선", "문자 복사"]
FIELDS = [
    ("방식", "그림자 모양", "choice", MODES[0], MODES),
    ("정밀도", "외곽선: 곡선 한 마디 나눌 수 (1~10)", "int", 4, None),
    ("두께", "외곽선: 선 두께 (문자 높이의 %)", "real", 10.0, None),
    ("X", "복사: 그림자 X 이격 (문자 높이 배수)", "real", 0.08, None),
    ("Y", "복사: 그림자 Y 이격 (문자 높이 배수)", "real", -0.08, None),
    ("그림자색", "그림자 색 (ACI)", "int", 8, None),
    ("원본색", "원본 문자 색 바꾸기 (ACI, 0=변경 없음)", "int", 0, None),
    ("레이어", "그림자 레이어 (비우면 원본과 같게)", "str", "", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}

# 선택 집합 _ss의 문자 정보: TX<탭>핸들<탭>종류<탭>내용<탭>x<탭>y<탭>회전<탭>높이<탭>글꼴 이름<탭>상자 x0 y0 x1 y1<탭>레이어
INFO_LISP = (
    '(foreach _en (bc:ss-list _ss) (setq _ed (entget _en) _o (vlax-ename->vla-object _en)'
    ' _st (vla-Item (vla-get-TextStyles (vla-get-ActiveDocument (vlax-get-acad-object))) (cdr (assoc 7 _ed))))'
    ' (vla-GetFont _st (quote _tf) (quote _b) (quote _it) (quote _cs) (quote _pf))'
    ' (setq _p (trans (cdr (assoc 10 _ed)) _en 0) _tb (if (= (cdr (assoc 0 _ed)) "TEXT") (textbox _ed)))'
    ' (write-line (strcat "TX" _d (cdr (assoc 5 _ed)) _d (cdr (assoc 0 _ed)) _d'
    '  (vl-string-translate "\\t\\n\\r" "   " (if (= (cdr (assoc 0 _ed)) "TEXT") (cdr (assoc 1 _ed)) (bc:text-of _en))) _d'
    '  (bc:rtos (car _p) 2 10) _d (bc:rtos (cadr _p) 2 10) _d (bc:rtos (if (assoc 50 _ed) (cdr (assoc 50 _ed)) 0.0) 2 12) _d'
    '  (bc:rtos (cdr (assoc 40 _ed)) 2 10) _d _tf _d'
    '  (if _tb (strcat (bc:rtos (caar _tb) 2 10) " " (bc:rtos (cadar _tb) 2 10) " " (bc:rtos (caadr _tb) 2 10) " "'
    '   (bc:rtos (cadadr _tb) 2 10)) "") _d (cdr (assoc 8 _ed)) _d (bc:rtos (if (assoc 41 _ed) (cdr (assoc 41 _ed)) 1.0) 2 10)) _fp))')


def parse_info(rows):
    out = []
    for r in rows:
        c = r.split("\t")
        if c[0] != "TX" or len(c) < 11:
            continue
        out.append({"handle": c[1], "type": c[2], "text": c[3], "x": float(c[4]), "y": float(c[5]), "rot": float(c[6]),
                    "h": float(c[7]), "typeface": c[8], "box": [float(v) for v in c[9].split()] if c[9] else None,
                    "layer": c[10], "wf": float(c[11]) if len(c) > 11 else 1.0})
    return out


def build_outline(items, cfg):
    """→ (LISP, 만든 문자 수, 건너뛴 [(핸들, 이유)])."""
    lay = ls(cfg["레이어"])
    out = ['(setq _doc (vla-get-ActiveDocument (vlax-get-acad-object)))']
    if cfg["레이어"]:
        out.append('(bc:ensure-layer "%s" 7)' % lay)
    made, skipped = 0, []
    for it in items:
        if it["type"] != "TEXT":
            skipped.append((it["handle"], "MTEXT는 외곽선 미지원"))
            continue
        if not it["typeface"]:
            skipped.append((it["handle"], "SHX 글꼴(트루타입 아님)"))
            continue
        font = F.find_font(it["typeface"])
        if not font:
            skipped.append((it["handle"], "글꼴 파일을 찾지 못함: %s" % it["typeface"]))
            continue
        cons, fb = F.outlines(it["text"], font, max(1, min(10, int(cfg["정밀도"]))))
        if not fb or not it["box"] or fb[2] <= fb[0] or fb[3] <= fb[1]:
            skipped.append((it["handle"], "그릴 글자 없음"))
            continue
        # 세로는 글자 상자 높이에 윤곽 높이를 맞추고(실측 일치), 가로는 같은 배율 × 폭 비율로 삽입점(펜 원점)부터 —
        # AutoCAD 글자 상자의 왼쪽은 잉크가 아니라 펜 원점이라 상자 너비에 맞추면 0.2(높이 2) 어긋났다
        _bx0, by0, _bx1, by1 = it["box"]
        sy = (by1 - by0) / (fb[3] - fb[1])
        sx = sy * it["wf"]
        c, s = math.cos(it["rot"]), math.sin(it["rot"])
        w = it["h"] * float(cfg["두께"]) / 100.0
        L = lay or ls(it["layer"])
        polys = []
        for con in cons:
            pts = []
            for fx, fy in con:
                lx, ly = fx * sx, by0 + (fy - fb[1]) * sy
                pts.append((it["x"] + lx * c - ly * s, it["y"] + lx * s + ly * c))
            vs = " ".join("(list 10 %.8f %.8f)" % p for p in pts)
            polys.append('(entmake (list (quote (0 . "LWPOLYLINE")) (quote (100 . "AcDbEntity")) (cons 8 "%s") (cons 62 %d)'
                         ' (quote (100 . "AcDbPolyline")) (cons 90 %d) (cons 70 1) (cons 43 %.8f) %s))'
                         ' (setq _sh (cons (vlax-ename->vla-object (entlast)) _sh))'
                         % (L, int(cfg["그림자색"]), len(pts), w, vs))
        out.append('(setq _sh nil) %s (setq _o (vlax-ename->vla-object (handent "%s")))'
                   ' (vlax-invoke (bc:sortents (vla-ObjectIDToObject _doc (vla-get-OwnerID _o))) (quote MoveBelow) _sh _o)'
                   % ("".join(polys), ls(it["handle"])))
        if int(cfg["원본색"]) > 0:
            out.append('(vla-put-Color _o %d)' % int(cfg["원본색"]))
        made += 1
    return "".join(out), made, skipped


def copy_lisp(handles, cfg):
    cl = "(list %s)" % " ".join('(cons "%s" %s)' % (k, ('"%s"' % ls(v)) if isinstance(v, str) else repr(v))
                                for k, v in (("X", float(cfg["X"])), ("Y", float(cfg["Y"])), ("그림자색", int(cfg["그림자색"])),
                                             ("원본색", int(cfg["원본색"])), ("레이어", cfg["레이어"])))
    return '(write-line (itoa (bc:cts-core (mapcar (quote handent) (list %s)) %s)) _fp)' % (
        " ".join('"%s"' % ls(h) for h in handles), cl)


def run_core(lisp_read, lisp_write, handles_or_rows, cfg):
    """→ {made, skipped}. 외곽선은 덤프 줄(rows), 복사는 핸들 목록을 받는다."""
    if cfg["방식"] == MODES[1]:
        r = lisp_write(copy_lisp(handles_or_rows, cfg))
        return {"made": int(r[0]) if r else 0, "skipped": []}
    code, made, skipped = build_outline(parse_info(handles_or_rows), cfg)
    if made:
        lisp_write(code)
    return {"made": made, "skipped": [{"handle": h, "reason": w} for h, w in skipped]}


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "문자 뒤 그림자 만들기", size="520x420")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="도면에서 문자 선택 → 그림자 만들기", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        rows = self.in_cad(self.acad.lisp, '(princ "\\n그림자 넣을 문자 선택: ") (setq _ss (ssget (quote ((0 . "TEXT,MTEXT")))))'
                           + INFO_LISP, A.PICK_TIMEOUT)
        if not rows:
            self.status("고른 문자가 없습니다.")
            return
        src = [r.split("\t")[1] for r in rows if r.startswith("TX\t")] if cfg["방식"] == MODES[1] else rows
        res = self.in_cad(run_core, lambda c: self.acad.lisp(c), lambda c: self.acad.lisp_undo(c, 180), src, cfg)
        if res is None:
            return
        msg = "그림자 %d개를 만들었습니다." % res["made"]
        if res["skipped"]:
            msg += " 건너뜀 %d개(%s)" % (len(res["skipped"]), res["skipped"][0]["reason"])
        self.status(msg)


def main():
    Window().mainloop()
