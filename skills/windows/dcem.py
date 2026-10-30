"""DCEM 하천 횡단 레벨 표시 — 횡단면마다 좌·우에 EL 폴대(눈금·EL 숫자)를 그린다.

단면은 견본 한 단면으로 모두 찾는다(skills/common/xsec.py). build_lisp()는 창 없이도 쓴다(MCP run_skill).
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import settings as S
from skills.common import ui
from skills.common import xsec as X
from validators import lisp_str as ls

CMD = "DCEM"
FIELDS = [
    ("H축척", "횡단 수평 축척 (단면 아래 거리 눈금이 없을 때만, 글자 크기 기준)", "real", 1000.0, None),
    ("V축척", "횡단 수직 축척 (단면 왼쪽 EL 눈금이 없을 때만)", "real", 1000.0, None),
    ("간격", "EL 숫자 간격 (m)", "choice", 1.0, [1.0, 2.0, 5.0, 10.0]),
    ("하단맞춤", "EL 하단 맞춤 (m 단위)", "choice", 1.0, [1.0, 5.0, 10.0]),
    ("위치", "폴 표기 위치", "choice", "좌우", ["좌우", "좌", "우"]),
    ("거리", "횡단 중심~폴대 거리 (m)", "real", 30.0, None),
    ("높이", "문자 높이 (축척 1000 기준)", "real", 2.0, None),
    ("소수", "EL 소수 자리", "int", 0, None),
    ("머리말", "EL 머리말", "str", "", None),
    ("여유", "위·아래 여유 눈금 수", "int", 1, None),
    ("레이어", "레이어 (비우면 현재)", "str", "", None),
    ("측점구분", "측점 구분 (단면 순서용)", "choice", "Station", ["Station", "Number"]),
    ("측점간격", "Number 측점 간격 (m)", "real", 20.0, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def pole_lisp(sec, cfg) -> str:
    """단면 하나의 폴대 LISP."""
    if not X.usable(sec) or not sec["ground_pts"]:
        return ""
    V, H = float(cfg["V축척"]), float(cfg["H축척"])
    uh = 1000.0 / H
    h = float(cfg["높이"]) * uh
    els = [X.el_of(sec, p[1], V) for p in sec["ground_pts"]]
    iv, bu = float(cfg["간격"]), float(cfg["하단맞춤"])
    lo = math.floor(min(els) / bu) * bu - iv * int(cfg["여유"])
    hi = math.ceil(max(els) / iv) * iv + iv * int(cfg["여유"])
    lay = ls(cfg["레이어"])
    cx = sec["center"][0]
    sides = {"좌우": (-1, 1), "좌": (-1,), "우": (1,)}[cfg["위치"]]
    s = []
    for sd in sides:
        x = cx + sd * float(cfg["거리"]) * X.uh(sec, H)
        y0, y1 = X.y_of(sec, lo, V), X.y_of(sec, hi, V)
        s.append('(bc:line (list %.10f %.10f 0.0) (list %.10f %.10f 0.0) "%s")' % (x, y0, x, y1, lay))
        n = int(round((hi - lo) / iv))
        # 눈금 간격이 글자 높이의 1.5배보다 좁으면 숫자는 k칸마다(눈금은 모두 긋는다)
        gap = iv * X.uv(sec, V)
        k = max(1, int(math.ceil(1.5 * h / gap))) if gap > 0 else 1
        for i in range(n + 1):
            el = lo + i * iv
            y = X.y_of(sec, el, V)
            s.append('(bc:line (list %.10f %.10f 0.0) (list %.10f %.10f 0.0) "%s")' % (x, y, x + sd * h, y, lay))
            if i % k:
                continue
            txt = ls("%s%s" % (cfg["머리말"], C.fmt(el, cfg["소수"])))
            s.append('(bc:text (list %.10f %.10f 0.0) "%s" %.6f "%s" "%s" 0.0)'
                     % (x + sd * h * 1.4, y, txt, h, lay, "ML" if sd > 0 else "MR"))
    return "".join(s)


def build_lisp(sections, cfg) -> str:
    return "".join(pole_lisp(sec, cfg) for sec in sections)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "하천 횡단 레벨 표시", size="560x640")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        bar = tk.Frame(self, bg=ui.BG)
        bar.pack(fill="x", padx=10, pady=4)
        tk.Button(bar, text="견본 단면 등록", command=self.sample, bg="#383A3E", fg="#FFFFFF", relief="flat",
                  height=2, width=16).pack(side="left", padx=3)
        tk.Button(bar, text="모든 단면에 폴대 그리기", command=self.run, bg="#3E5879", fg="#FFFFFF", relief="flat",
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
        self.status("견본 등록: 측점 '%s', 지반고 '%s' (같은 견본을 HWLM 등에서도 씀)" % (sp["sample_station"], sp["sample_el"]))

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        sp = X.load_spec()
        if not sp:
            self.error("견본 단면을 먼저 등록하세요.")
            return
        rows = self.in_cad(self.acad.lisp, X.dump_body(sp), 120)
        if rows is None:
            return
        secs = X.find(sp, C.parse_dump(rows), cfg["측점구분"], float(cfg["측점간격"]))
        ok = [s for s in secs if X.usable(s)]
        if not ok:
            self.error("단면을 찾지 못했습니다(견본·문자 위치 확인). 찾은 중심선 %d개" % len(secs))
            return
        if self.in_cad(self.acad.lisp_undo, build_lisp(ok, cfg), 120) is not None:
            self.status("단면 %d개에 폴대를 그렸습니다(지반고·지반선을 못 찾은 단면 %d개 제외)." % (len(ok), len(secs) - len(ok)))


def main():
    Window().mainloop()
