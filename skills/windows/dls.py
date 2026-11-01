# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""DLS 종곡선 계산·계획선 작도 — 종단면도에 그려 둔 IP 선(폴리선 정점 = 시점·VIP·종점)으로 종곡선을 계산해 계획선을 그린다.

EL은 높이를 아는 점(축척 막대 눈금, 세로선 맨 아래) 하나와 그 EL로, 측점은 IP 선 첫 정점 = 시작 거리로 정한다.
종곡선 길이는 VIP마다(쉼표 목록) 또는 모두 같은 값. 결과: 계획선 폴리선·경사·VIP(L·K) 문자, VIP 표.
compute()·build_lisp()는 창 없이도 쓴다(MCP skill_run).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import settings as S
from skills.common import ui
from skills.common import vprof as V
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "DLS"
FIELDS = [
    ("측점구분", "측점 표기 구분", "choice", "Station", ["Station", "Number"]),
    ("체인", "Number 측점 한 체인 길이 (m)", "real", 20.0, None),
    ("시작거리", "IP 선 첫 정점의 측점 (숫자 또는 0+000)", "str", "0", None),
    ("H축척", "종단 H 축척 (1000 = 1m가 도면 1)", "real", 1000.0, None),
    ("V축척", "종단 V 축척", "real", 200.0, None),
    ("곡선길이", "종곡선 길이 (m, VIP마다 같을 때)", "real", 60.0, None),
    ("곡선목록", "VIP별 종곡선 길이 (쉼표, 비우면 위 값)", "str", "", None),
    ("계산간격", "종곡선 계산 간격 (m)", "real", 5.0, None),
    ("경사표기", "경사 문자 쓰기", "bool", True, None),
    ("K표기", "VIP 문자에 L·K 쓰기", "bool", True, None),
    ("IP선", "IP 선을 한 번 더 그리기", "bool", False, None),
    ("측점소수", "+측점 소수 자리", "int", 3, None),
    ("문자높이", "문자 높이", "real", 2.5, None),
    ("계획레이어", "계획선 레이어", "str", "종단_계획선", None),
    ("문자레이어", "문자 레이어", "str", "종단_문자", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
VERTS_LISP = '(foreach _p (bc:verts _ip) (write-line (strcat "V" _d (bc:rtos (car _p) 2 10) _d (bc:rtos (cadr _p) 2 10)) _fp))'


def lengths(cfg, n):
    """VIP n개(시점·종점 제외)의 종곡선 길이."""
    s = str(cfg["곡선목록"]).strip()
    if s:
        vals = [float(v) for v in s.replace(" ", "").split(",") if v != ""]
        if len(vals) == n + 2:  # 시점·종점 0까지 적었으면
            vals = vals[1:-1]
        if len(vals) != n:
            raise ValueError("곡선 목록 %d개 — VIP는 %d개입니다(시점·종점 제외)." % (len(vals), n))
        return vals
    return [float(cfg["곡선길이"])] * n


def compute(verts, base_point, base_el, cfg, Ls=None):
    """IP 선 정점(도면) → VIP [(d, z, L)]. d는 첫 정점부터(m)."""
    uh, uv = 1000.0 / cfg["H축척"], 1000.0 / cfg["V축척"]
    pts = sorted(verts)
    if len(pts) < 3:
        raise ValueError("IP 선 정점이 3개 이상이어야 합니다(시점·VIP·종점).")
    x0 = pts[0][0]
    Ls = list(Ls) if Ls is not None else lengths(cfg, len(pts) - 2)
    if len(Ls) != len(pts) - 2:
        raise ValueError("종곡선 길이 %d개 — VIP는 %d개입니다." % (len(Ls), len(pts) - 2))
    vips = [((x - x0) / uh, float(base_el) + (y - float(base_point[1])) / uv, 0.0) for x, y in pts]
    vips = [vips[0]] + [(d, z, float(L)) for (d, z, _l), L in zip(vips[1:-1], Ls)] + [vips[-1]]
    bad = V.check_vips(vips)
    if bad:
        raise ValueError("; ".join(bad))
    return vips, x0


def build_lisp(vips, x0, base_point, base_el, cfg):
    uh, uv = 1000.0 / cfg["H축척"], 1000.0 / cfg["V축척"]
    lp, lx = ls(cfg["계획레이어"]), ls(cfg["문자레이어"])
    start = V.start_of(cfg)
    return ('(bc:ensure-layer "%s" 1) (bc:ensure-layer "%s" 7)' % (lp, lx) +
            V.plan_lisp(vips, cfg, lambda d: x0 + d * uh, lambda z: float(base_point[1]) + (z - float(base_el)) * uv,
                        start, lp, lx, float(cfg["문자높이"])))


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "종곡선 계산·계획선 작도", size="540x700")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="IP 선 선택 → EL 아는 점 → EL 입력 → 계획선 그리기", command=self.run, bg="#3E5879",
                  fg="#FFFFFF", relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        body = ('(setq _s (entsel "\\nIP 선(폴리선) 선택: ")) (if _s (progn (setq _ip (car _s)) %s'
                ' (setq _b (getpoint "\\nEL을 아는 점 지정: ")) (if _b (progn (setq _b (trans _b 1 0))'
                ' (setq _z (getreal "\\n그 점의 EL: ")) (if _z (write-line (strcat "B" _d (bc:rtos (car _b) 2 10) _d'
                ' (bc:rtos (cadr _b) 2 10) _d (bc:rtos _z 2 10)) _fp))))))' % VERTS_LISP)
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
        b = [r.split("\t") for r in rows or [] if r.startswith("B\t")]
        if not b:
            return
        verts = [(float(c[1]), float(c[2])) for c in (r.split("\t") for r in rows) if c[0] == "V"]
        try:
            vips, x0 = compute(verts, (float(b[0][1]), float(b[0][2])), float(b[0][3]), cfg)
        except ValueError as e:
            self.error(str(e))
            return
        code = build_lisp(vips, x0, (float(b[0][1]), float(b[0][2])), float(b[0][3]), cfg)
        if self.in_cad(self.acad.lisp_undo, code, 120) is not None:
            self.status("VIP %d개 종곡선을 그렸습니다." % (len(vips) - 2))


def main():
    Window().mainloop()
