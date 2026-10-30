# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""RCSE 하천 평면 대횡단 — 횡단면도의 지반 EL을 평면 선형의 측점 수직선 위에 EL 간격마다 문자로 옮겨 쓴다.

횡단과 선형이 같은 도면에 있을 때. 단면은 견본으로 찾고(skills/common/xsec.py), 측점(누가거리)으로 선형 위 위치를 정한다.
중심에서 'EL 간격'마다 지반선 높이를 선형 보간해 평면에 EL 문자를 쓰고, 측점 문자·횡단 선을 함께 그린다.
build_lisp()는 창 없이도 쓴다(MCP run_skill).
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import settings as S
from skills.common import ui
from skills.common import xsec as X
from validators import lisp_str as ls

CMD = "RCSE"
FIELDS = [
    ("측점구분", "측점 구분", "choice", "Station", ["Station", "Number"]),
    ("측점간격", "Number 측점 간격 (m)", "real", 20.0, None),
    ("시작거리", "선형 시작 거리 (숫자 또는 0+000)", "str", "0", None),
    ("평면축척", "평면 축척 (1000 = 1m가 도면 1)", "real", 1000.0, None),
    ("H축척", "횡단 수평 축척 (단면 아래 거리 눈금이 없을 때만, 글자 크기 기준)", "real", 1000.0, None),
    ("V축척", "횡단 수직 축척 (단면 왼쪽 EL 눈금이 없을 때만)", "real", 1000.0, None),
    ("EL간격", "EL 간격 (m, 중심부터)", "real", 5.0, None),
    ("소수", "EL 소수 자리", "int", 1, None),
    ("높이", "EL 문자 높이 (도면 단위)", "real", 1.0, None),
    ("측점높이", "측점 문자 높이 (0 = 안 씀)", "real", 2.0, None),
    ("횡단선", "평면에 횡단 선 그리기", "bool", True, None),
    ("좌우반대", "선형 진행 방향과 횡단 좌·우 반대", "bool", False, None),
    ("레이어", "EL 문자 레이어 (비우면 현재)", "str", "", None),
    ("측점레이어", "측점·횡단 선 레이어 (비우면 EL 레이어)", "str", "", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def offsets_els(sec, cfg):
    """[(중심에서 거리 m, EL)] — 중심 0부터 양쪽으로 EL 간격마다, 지반선이 있는 곳만."""
    pts = [(p[0], p[1], 0.0) for p in sec["ground_pts"]]
    if not pts:
        return []
    uh, V = X.uh(sec, float(cfg["H축척"])), float(cfg["V축척"])
    cx = sec["center"][0]
    step = float(cfg["EL간격"])
    out = []
    for sgn in (-1, 1):
        k = 0 if sgn > 0 else 1
        while True:
            o = sgn * k * step
            y = X._ground_y(pts, cx + o * uh)
            if y is None:
                break
            out.append((o, X.el_of(sec, y, V)))
            k += 1
            if k > 100000:
                break
    return sorted(out)


def sample_body(handle, rev, dds) -> str:
    return '(bc:samples (handent "%s") %s (list %s) _fp)' % (handle, "T" if rev else "nil", " ".join("%.10f" % d for d in dds))


def build_lisp(sections, samples, cfg):
    """samples {선형 도면거리(소수6): (x, y, 진행각)} → (LISP, 표기 단면 수)"""
    up = 1000.0 / float(cfg["평면축척"])
    lay = ls(cfg["레이어"])
    slay = ls(cfg["측점레이어"] or cfg["레이어"])
    h, sh = float(cfg["높이"]), float(cfg["측점높이"])
    s, n = [], 0
    for sec, dd in sections:
        sm = samples.get(round(dd, 6))
        if sm is None:
            continue
        x, y, a = sm
        nrm = a + math.pi / 2 * (-1 if cfg["좌우반대"] else 1)
        # 횡단 왼쪽(o<0)이 선형 왼쪽(nrm 쪽)
        def at(o):
            return x - o * up * math.cos(nrm), y - o * up * math.sin(nrm)
        oe = offsets_els(sec, cfg)
        if not oe:
            continue
        # 글자가 거꾸로 읽히지 않게 방향을 맞춘다
        rot = nrm + math.pi if math.cos(nrm) < -1e-9 or (abs(math.cos(nrm)) < 1e-9 and math.sin(nrm) < 0) else nrm
        for o, el in oe:
            px, py = at(o)
            s.append('(bc:text (list %.10f %.10f 0.0) "%s" %.6f "%s" "MC" %.12f)'
                     % (px, py, ls(C.fmt(el, cfg["소수"])), h, lay, rot))
        if cfg["횡단선"]:
            p0, p1 = at(oe[0][0]), at(oe[-1][0])
            s.append('(bc:line (list %.10f %.10f 0.0) (list %.10f %.10f 0.0) "%s")' % (p0[0], p0[1], p1[0], p1[1], slay))
        if sh > 0 and sec["station"]:
            pe = at(oe[-1][0] + 2.0 * sh / up)
            s.append('(bc:text (list %.10f %.10f 0.0) "%s" %.6f "%s" "MC" %.12f)' % (pe[0], pe[1], ls(sec["station"]), sh, slay, rot))
        n += 1
    return "".join(s), n


def plan_items(secs, L, cfg):
    """단면 → (단면, 선형 도면거리). 선형 길이 밖은 뺀다."""
    up = 1000.0 / float(cfg["평면축척"])
    d0 = C.station_to_dist(cfg["시작거리"], cfg["측점구분"], float(cfg["측점간격"])) or 0.0
    out, seen = [], set()
    for sec in secs:
        if not X.usable(sec) or sec["dist"] is None:
            continue
        # 같은 측점 단면이 여러 벌(도곽에 배치한 사본 등)이면 첫 단면만 — 평면 같은 자리에 겹쳐 쓰지 않게
        key = round(sec["dist"], 4)
        if key in seen:
            continue
        seen.add(key)
        dd = (sec["dist"] - d0) * up
        if -1e-6 <= dd <= L + 1e-6:
            out.append((sec, min(max(dd, 0.0), L)))
    return out


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "하천 평면 대횡단", size="560x700")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        bar = tk.Frame(self, bg=ui.BG)
        bar.pack(fill="x", padx=10, pady=4)
        tk.Button(bar, text="견본 단면 등록", command=self.sample, bg="#383A3E", fg="#FFFFFF", relief="flat",
                  height=2, width=16).pack(side="left", padx=3)
        tk.Button(bar, text="평면 선형 선택 → 대횡단 표기", command=self.run, bg="#3E5879", fg="#FFFFFF", relief="flat",
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
        body = ('(setq _a (bc:pick-align "평면 선형(중심선) 선택"))'
                ' (if _a (write-line (strcat "A\\t" (cdr (assoc 5 (entget (car _a)))) "\\t" (if (cadr _a) "1" "0")'
                ' "\\t" (bc:rtos (bc:curve-len (car _a)) 2 10)) _fp))')
        al = [r.split("\t") for r in (self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT) or []) if r.startswith("A\t")]
        if not al:
            return
        h, rev, L = al[0][1], al[0][2] == "1", float(al[0][3])
        items = plan_items(secs, L, cfg)
        if not items:
            self.error("선형 범위 안에 맞는 단면이 없습니다(시작 거리·측점 구분 확인). 찾은 단면 %d개" % len(secs))
            return
        rows = self.in_cad(self.acad.lisp, sample_body(h, rev, [d for _s, d in items]), 120) or []
        sm = {round(float(c[1]), 6): (float(c[2]), float(c[3]), float(c[4])) for c in (r.split("\t") for r in rows) if c[0] == "S"}
        lisp, n = build_lisp(items, sm, cfg)
        if self.in_cad(self.acad.lisp_undo, lisp, 120) is not None:
            self.status("단면 %d개를 평면에 표기했습니다(찾은 단면 %d개)." % (n, len(secs)))


def main():
    Window().mainloop()
