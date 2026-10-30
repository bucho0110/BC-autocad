# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""CL 객체 길이 쓰기 — 선·폴리선·호·원·타원·스플라인의 길이를 객체 위에 쓴다.

길이 = 도면 길이 ÷ (1000 ÷ 축척) m (축척 1000 = m 도면, 1 = mm 도면). 반올림·올림·내림, 단위값(5 단위 등).
문자 자리: 객체 중간 점·시작점·끝점(선 방향으로, 위·아래), 폴리선은 꺾인 구간마다도 된다.
QCL은 이 설정으로 창 없이 바로 객체를 고른다. labels()·lisp()는 창 없이도 쓴다(MCP skill_run).
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import geo as G
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "CL"
PLACES = ["객체 중간 점", "선 시작점", "선 끝점"]
FIELDS = [
    ("축척", "산출 축척 (1000 = m 도면, 1 = mm 도면)", "real", 1000.0, None),
    ("소수", "소수 자리", "int", 2, None),
    ("천단위", "천 단위 구분 기호", "bool", False, None),
    ("소수적용", "소수 처리", "choice", "반올림", ["반올림", "올림", "내림"]),
    ("단위값", "단위값으로 처리 (0 = 안 함, 예 5)", "real", 0.0, None),
    ("머리말", "머리말", "str", "L=", None),
    ("꼬리말", "꼬리말", "str", "m", None),
    ("위치", "문자 위치", "choice", PLACES[0], PLACES),
    ("쪽", "선 위·아래", "choice", "위", ["위", "아래", "선 중심"]),
    ("수평", "문자를 수평으로 (끄면 선 방향)", "bool", False, None),
    ("간격", "선과 문자 간격 (문자 높이 배수)", "real", 0.5, None),
    ("높이", "문자 높이 (도면 단위)", "real", 2.5, None),
    ("구간마다", "폴리선은 꺾인 구간마다 쓰기", "bool", False, None),
    ("레이어표기", "객체 레이어 이름도 쓰기", "bool", False, None),
    ("사이문자", "레이어와 길이 사이 문자", "str", " : ", None),
    ("레이어", "문자 레이어 (비우면 현재)", "str", "", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
TYPES = "LINE,ARC,CIRCLE,LWPOLYLINE,POLYLINE,ELLIPSE,SPLINE"


def value_text(length, cfg, layer=""):
    v = G.round_mode(length / G.upm(cfg["축척"]), int(cfg["소수"]), cfg["소수적용"], float(cfg["단위값"]))
    u = float(cfg["단위값"])
    dec = int(cfg["소수"]) if u <= 0 else len(repr(u).rstrip("0").partition(".")[2])  # 단위값 5 → 0자리, 0.5 → 1자리
    s = "%s%s%s" % (cfg["머리말"], G.num_str(v, dec, cfg["천단위"]), cfg["꼬리말"])
    return ("%s%s%s" % (layer, cfg["사이문자"], s)) if cfg["레이어표기"] else s


def labels(ents, cfg):
    """→ [(x, y, 각, 문자, 길이 m)]."""
    out = []
    h = float(cfg["높이"])
    gap = float(cfg["간격"]) * h
    for e in ents:
        if not e["pieces"] or e["length"] <= 0:
            continue
        if cfg["구간마다"] and e["type"] in ("LWPOLYLINE", "POLYLINE") and len(e["pieces"]) > 1:
            parts = [([pc], G.piece_len(*pc)) for pc in e["pieces"]]
        else:
            parts = [(e["pieces"], e["length"])]
        for pcs, L in parts:
            if L <= 1e-12:
                continue
            t = {PLACES[1]: 0.0, PLACES[2]: L}.get(cfg["위치"], L / 2.0)
            (x, y), a = G.at_length(pcs, t)
            ang = 0.0 if cfg["수평"] else G.readable(a)
            if cfg["쪽"] != "선 중심":
                s = 1 if cfg["쪽"] == "위" else -1
                x, y = x - s * gap * math.sin(ang), y + s * gap * math.cos(ang)
            out.append((x, y, ang, value_text(L, cfg, e["layer"]), L / G.upm(cfg["축척"])))
    return out


def lisp(labs, cfg):
    lay = ls(cfg["레이어"])
    just = {"위": "BC", "아래": "TC"}.get(cfg["쪽"], "MC")
    if cfg["위치"] == PLACES[1]:
        just = just[0] + "L"
    elif cfg["위치"] == PLACES[2]:
        just = just[0] + "R"
    return "".join('(bc:text (list %.6f %.6f 0.0) "%s" %.6f "%s" "%s" %.10f)' % (x, y, ls(s), float(cfg["높이"]), lay, just, a)
                   for x, y, a, s, _L in labs)


def pick_and_write(acad, cfg):
    rows = acad.lisp('(princ "\\n길이 쓸 객체 선택: ") (setq _ss (ssget (list (cons 0 "%s")))) %s' % (TYPES, G.GEO_LISP),
                     A.PICK_TIMEOUT)
    if not rows:
        return None
    labs = labels(G.parse(rows), cfg)
    if labs:
        acad.lisp_undo(lisp(labs, cfg), 120)
    return labs


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "객체 길이 쓰기", size="520x700")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정 (QCL도 이 설정을 씁니다)", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="객체 선택 → 길이 쓰기", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        labs = self.in_cad(pick_and_write, self.acad, cfg)
        if labs is not None:
            self.status("%d곳에 썼습니다. 합계 %.3fm" % (len(labs), sum(L for *_x, L in labs)))


def main():
    Window().mainloop()
