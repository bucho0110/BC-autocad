# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""TLAE 객체 길이·면적 합산 조회 — 고른 선·폴리선·호·원·타원·스플라인의 길이와 면적을 더해 보여 준다.

고를 때마다 합계에 더하고(창의 [더 고르기]), 결과를 클립보드에 넣어 엑셀에 붙일 수 있다.
totals()는 창 없이도 쓴다(MCP skill_run).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import geo as G
from skills.common import settings as S
from skills.common import ui

CMD = "TLAE"
COPY = ["면적 길이", "길이 면적", "길이", "면적", "복사 안 함"]
FIELDS = [
    ("축척", "산출 축척 (1000 = m 도면, 1 = mm 도면)", "real", 1000.0, None),
    ("길이소수", "길이 소수 자리", "int", 3, None),
    ("면적소수", "면적 소수 자리", "int", 3, None),
    ("닫힌것만", "닫힌 객체만 면적 산출", "bool", True, None),
    ("복사", "합계를 클립보드에 (엑셀 붙여 넣기용, 탭 구분)", "choice", COPY[0], COPY),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
TYPES = "LINE,ARC,CIRCLE,LWPOLYLINE,POLYLINE,ELLIPSE,SPLINE"


def totals(ents, cfg):
    k = G.upm(cfg["축척"])
    L = sum(e["length"] for e in ents) / k
    A_ = sum(e["area"] for e in ents if e["closed"] or not cfg["닫힌것만"]) / (k * k)
    return {"count": len(ents), "length": round(L, int(cfg["길이소수"])), "area": round(A_, int(cfg["면적소수"])),
            "by_type": {t: sum(1 for e in ents if e["type"] == t) for t in sorted({e["type"] for e in ents})}}


def clip_text(t, cfg):
    l, a = G.num_str(t["length"], cfg["길이소수"]), G.num_str(t["area"], cfg["면적소수"])
    return {"면적 길이": a + "\t" + l, "길이 면적": l + "\t" + a, "길이": l, "면적": a}.get(cfg["복사"], "")


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "객체 길이·면적 합산 조회", size="460x470")
        self.acad = A.Acad()
        self.ents = {}
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        self.var = tk.StringVar(value="객체를 고르면 합계가 여기에 나옵니다.")
        tk.Label(body, textvariable=self.var, bg=ui.PANEL, fg=ui.ACCENT, font=ui.FONT_B, anchor="w",
                 justify="left").pack(fill="x", pady=8)
        row = tk.Frame(self, bg=ui.BG)
        row.pack(fill="x", padx=10, pady=4)
        for t, fn in (("더 고르기", self.pick), ("합계 지우기", self.clear)):
            tk.Button(row, text=t, command=fn, bg="#3E5879", fg="#FFFFFF", relief="flat", height=2).pack(
                side="left", expand=True, fill="x", padx=1)

    def clear(self):
        self.ents = {}
        self.var.set("합계를 지웠습니다.")

    def pick(self):
        cfg = self.form.values()
        S.save(CMD, cfg)
        rows = self.in_cad(self.acad.lisp, '(princ "\\n길이·면적 볼 객체 선택: ") (setq _ss (ssget (list (cons 0 "%s")))) %s'
                           % (TYPES, G.GEO_LISP), A.PICK_TIMEOUT)
        for e in G.parse(rows or []):
            self.ents[e["handle"]] = e  # 같은 객체를 두 번 골라도 한 번만
        t = totals(list(self.ents.values()), cfg)
        self.var.set("객체 %d개\n길이 합계  %s m\n면적 합계  %s ㎡" % (t["count"], G.num_str(t["length"], cfg["길이소수"], True),
                                                         G.num_str(t["area"], cfg["면적소수"], True)))
        s = clip_text(t, cfg)
        if s:
            self.clipboard_clear()
            self.clipboard_append(s)


def main():
    Window().mainloop()
