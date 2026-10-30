# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""CMOB 지형 외곽 경계 — 점·블록·선 정점의 가장 바깥 점들을 잇는 닫힌 경계선.

삼각망을 만든 뒤 바깥 변이 '중간 변 길이 × 여유도'보다 긴 삼각형을 걷어내 오목한 외곽을 찾는다.
여유도가 작을수록 안쪽으로 파고든다(2 ~ 10). build()는 창 없이도 쓴다(MCP skill_run).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import settings as S
from skills.common import terrain as T
from skills.common import ui
from skills.windows import dtin
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "CMOB"
FIELDS = [
    ("대상점", "점(Point)", "bool", True, None),
    ("대상블록", "블록 삽입점", "bool", True, None),
    ("대상선", "선·폴리선 정점", "bool", True, None),
    ("대상문자", "문자 삽입점", "bool", False, None),
    ("여유도", "외곽선 여유도 (2 ~ 10, 작을수록 안쪽으로)", "real", 3.0, None),
    ("레이어", "경계선 레이어", "str", "지형외곽", None),
    ("색", "레이어 색 (ACI)", "int", 1, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def build(ents, cfg):
    """덤프 → (LISP, 요약)."""
    pts = [p for e in ents for p in e["points"]]
    P, tris = dtin.triangulate([(p[0], p[1], 0.0) for p in pts])
    if not tris:
        raise ValueError("경계를 만들 수 없습니다(점이 3개 미만이거나 한 줄 위).")
    slack = max(2.0, min(10.0, float(cfg["여유도"])))
    loops = T.boundary_loops(P, T.peel(P, tris, slack))
    lay = ls(cfg["레이어"])
    code = '(bc:ensure-layer "%s" %d)' % (lay, int(cfg["색"])) + "".join(T.lwpoly_lisp(lp, True, lay) for lp in loops)
    return code, {"points": len(P), "loops": len(loops), "vertices": [len(lp) for lp in loops]}


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "지형 외곽 경계 그리기", size="520x400")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="도면에서 객체 선택 → 외곽 경계 그리기", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        types = T.types_for(cfg)
        if not types:
            self.error("대상을 하나 이상 고르세요.")
            return
        body = '(princ "\\n외곽을 찾을 객체 선택: ") (setq _ss (ssget (list (cons 0 "%s")))) (bc:dump-ss _ss nil _fp)' % types
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
        if rows is None:
            return
        try:
            code, info = build(C.parse_dump(rows), cfg)
        except ValueError as e:
            self.error(str(e))
            return
        if self.in_cad(self.acad.lisp_undo, code, 120) is None:
            return
        self.status("점 %d개로 외곽 경계 %d개를 그렸습니다." % (info["points"], info["loops"]))


def main():
    Window().mainloop()
