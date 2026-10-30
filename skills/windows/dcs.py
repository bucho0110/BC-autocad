# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""DCS 종단·횡단 그리기 — 종단 자료(엑셀 표, DRP와 같은 형식)와 횡단 자료(엑셀)로 종단면도와 횡단면도를 그린다.

횡단 엑셀 형식(첫 줄 머리 없이 자료만, 측점은 누가거리 또는 0+000·No.3+5):
① 중심 기준 1열  [측점, 거리, EL] — 측점은 단면 첫 줄에만 써도 된다. 거리는 중심에서 좌 −, 우 +(절대/절대).
② 왼쪽부터 1열   [측점, 거리, EL] — 맨 왼쪽 점이 중심(0)이 되어 오른쪽으로 그린다.
   거리 절대 = 왼쪽 끝부터, 상대 = 앞 점부터. EL 절대 또는 상대(앞 점과 차, 첫 점은 절대).
③ 좌우 구분     [좌 거리, 좌 EL, 측점, 우 거리, 우 EL] — 단면 첫 줄 가운데 칸에 측점, 둘째 줄 가운데 칸에 중심 지반고.
   좌·우 모두 중심에서 바깥쪽으로 적는다. 거리 절대 = 중심부터(양수), 상대 = 앞 점부터. EL 절대 또는 상대(앞 점과 차).
계획고는 종단 자료(계획 VIP·종곡선 또는 계획 열)에서 측점마다 계산해 횡단 중심에 표시하고 절토고·성토고를 쓴다.
parse_sections()·sections_lisp()는 창 없이도 쓴다(MCP skill_run).
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as X
from skills.common import settings as S
from skills.common import terrain as T
from skills.common import ui
from skills.common import vprof as V
from skills.windows import drp
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "DCS"
FORMS = ["중심 기준 1열", "왼쪽부터 1열", "좌우 구분"]
DIST_EL = ["절대거리/절대EL", "상대거리/상대EL", "상대거리/절대EL"]
FIELDS = drp.FIELDS + [
    ("횡단형식", "횡단 엑셀 형식", "choice", FORMS[0], FORMS),
    ("거리높이", "횡단 거리/EL 입력 방식 (① 형식은 절대/절대만)", "choice", DIST_EL[0], DIST_EL),
    ("횡단H축척", "횡단 H 축척 (1000 = 1m가 도면 1)", "real", 1000.0, None),
    ("횡단V축척", "횡단 V 축척", "real", 1000.0, None),
    ("열수", "한 열에 놓을 횡단 수", "int", 5, None),
    ("세로간격", "횡단 사이 세로 간격 (도면 단위)", "real", 50.0, None),
    ("가로간격", "열 사이 가로 간격 (도면 단위)", "real", 150.0, None),
    ("횡단문자높이", "횡단 문자 높이", "real", 2.5, None),
    ("횡단지반레이어", "횡단 지반선 레이어", "str", "횡단_지반선", None),
    ("횡단계획레이어", "횡단 계획고 표시 레이어", "str", "횡단_계획", None),
    ("횡단기준레이어", "횡단 기준선·중심선 레이어", "str", "횡단_기준", None),
    ("횡단문자레이어", "횡단 문자 레이어", "str", "횡단_문자", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def _f(v):
    return X.to_float(v)


def _sta(v, cfg):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return C.station_to_dist(str(v).strip(), cfg["측점구분"], float(cfg["체인"]))


def parse_sections(rows, cfg):
    """→ [{dist(누가거리), ground [(중심 기준 거리, EL)], center_el}] 측점 순."""
    form, mode = cfg["횡단형식"], cfg["거리높이"]
    rel_d, rel_z = mode in DIST_EL[1:], mode == DIST_EL[1]
    rows = [list(r) + [None] * 5 for r in rows if r and any(v not in (None, "") for v in r)]
    secs = []
    if form in FORMS[:2]:
        cur = None
        for r in rows:
            s = _sta(r[0], cfg)
            if s is not None and (cur is None or abs(s - cur["dist"]) > 1e-9):
                cur = {"dist": s, "raw": []}
                secs.append(cur)
            d, z = _f(r[1]), _f(r[2])
            if cur is not None and d is not None and z is not None:
                cur["raw"].append((d, z))
        for sec in secs:
            pts = []
            if form == FORMS[0]:
                pts = sorted(sec["raw"])
            else:
                x = zz = None
                for d, z in sec["raw"]:
                    x = d if x is None or not rel_d else x + d
                    zz = z if zz is None or not rel_z else zz + z
                    pts.append((x, zz))
                x0 = pts[0][0] if pts else 0.0
                pts = [(p[0] - x0, p[1]) for p in pts]
            sec["ground"] = pts
            sec["center_el"] = V.interp(pts, 0.0) if pts else None
    else:
        k = 0
        while k < len(rows):
            s = _sta(rows[k][2], cfg)
            if s is None:
                k += 1
                continue
            zc = _f(rows[k + 1][2]) if k + 1 < len(rows) else None
            if zc is None:
                raise ValueError("좌우 구분 형식: 측점 %s 아래 칸에 중심 지반고가 없습니다." % rows[k][2])
            e = k + 1
            while e + 1 < len(rows) and _sta(rows[e + 1][2], cfg) is None:
                e += 1
            block = rows[k:e + 1]
            side = {}
            for sgn, (ci, cz) in ((-1, (0, 1)), (1, (3, 4))):
                x, zz, pts = 0.0, zc, []
                for r in block:
                    d, z = _f(r[ci]), _f(r[cz])
                    if d is None or z is None:
                        continue
                    x = (x + d) if rel_d else d
                    zz = (zz + z) if rel_z else z
                    pts.append((sgn * x, zz))
                side[sgn] = pts
            pts = sorted(side[-1]) + [(0.0, zc)] + sorted(side[1])
            secs.append({"dist": s, "ground": pts, "center_el": zc})
            k = e + 1
    out = [s for s in secs if len(s.get("ground") or []) >= 2]
    out.sort(key=lambda s: s["dist"])
    for s in out:
        s.pop("raw", None)
    return out


def plan_of(profile_rows, cfg):
    """종단 표에서 계획고 함수(측점 누가거리 → EL). 계획 자료가 없으면 None."""
    if not profile_rows:
        return None
    series, vips, _m = drp.parse_table(profile_rows, cfg)
    start = V.start_of(cfg)
    if len(vips) >= 2:
        return lambda d: V.el_at(vips, d - start)
    plan = next((s for s in series if s["plan"]), None)
    if plan:
        pts = [p for p in plan["pts"] if p]
        return lambda d: V.interp(pts, d - start)
    return None


def sections_lisp(secs, base, cfg, plan=None):
    """횡단 k: 열 k // 열수, 행 k % 열수. 중심 기준선(DL) 위치 = 기준점 + (열 × 가로간격, −행 × 세로간격).
    → (LISP, 결과 [{station, center_el, plan_el, cut, fill}])."""
    uh, uv = 1000.0 / cfg["횡단H축척"], 1000.0 / cfg["횡단V축척"]
    lg, lp, lb, lx = (ls(cfg[k]) for k in ("횡단지반레이어", "횡단계획레이어", "횡단기준레이어", "횡단문자레이어"))
    h = float(cfg["횡단문자높이"])
    dec = int(cfg["소수"])
    n = max(1, int(cfg["열수"]))
    out = ['(bc:ensure-layer "%s" 3) (bc:ensure-layer "%s" 1) (bc:ensure-layer "%s" 7) (bc:ensure-layer "%s" 7)'
           % (lg, lp, lb, lx)]
    res = []

    def line(x1, y1, x2, y2, lay):
        out.append('(bc:line (list %.6f %.6f 0.0) (list %.6f %.6f 0.0) "%s")' % (x1, y1, x2, y2, lay))

    def text(x, y, s, just):
        out.append('(bc:text (list %.6f %.6f 0.0) "%s" %.6f "%s" "%s" 0.0)' % (x, y, ls(s), h, lx, just))

    for k, sec in enumerate(secs):
        bx = float(base[0]) + (k // n) * float(cfg["가로간격"])
        by = float(base[1]) - (k % n) * float(cfg["세로간격"])
        pz = plan(sec["dist"]) if plan else None
        zs = [z for _d, z in sec["ground"]] + ([pz] if pz is not None else [])
        dl = math.floor(min(zs)) - 1.0
        top = max(zs)

        def P(d, z):
            return bx + d * uh, by + (z - dl) * uv
        out.append(T.lwpoly_lisp([P(d, z) for d, z in sec["ground"]], False, lg))
        x0, x1 = P(sec["ground"][0][0], dl)[0], P(sec["ground"][-1][0], dl)[0]
        line(x0, by, x1, by, lb)
        line(bx, by, bx, P(0, top)[1] + 4 * h, lb)
        text(x0, by - 0.5 * h, "DL=%s" % C.fmt(dl, 2), "TL")
        text(bx, by - 2.5 * h, V.sta_label(sec["dist"], cfg), "TC")
        gz = sec["center_el"]
        lab = ["G.H=%s" % C.fmt(gz, dec)] if gz is not None else []
        r = {"station": V.sta_label(sec["dist"], cfg), "dist": round(sec["dist"], 4),
             "center_el": None if gz is None else round(gz, 4), "plan_el": None, "cut": None, "fill": None}
        if pz is not None:
            px, py = P(0, pz)
            line(px - 2 * h, py, px + 2 * h, py, lp)
            out.append('(bc:pline (list (list %.6f %.6f) (list %.6f %.6f) (list %.6f %.6f)) T "%s")'
                       % (px, py, px - 0.6 * h, py + h, px + 0.6 * h, py + h, lp))
            lab.append("F.H=%s" % C.fmt(pz, dec))
            r["plan_el"] = round(pz, 4)
            if gz is not None:
                diff = pz - gz
                key = "fill" if diff > 0 else "cut"
                lab.append(("성토고=%s" if diff > 0 else "절토고=%s") % C.fmt(abs(diff), dec))
                r[key] = round(abs(diff), 4)
        ty = P(0, top)[1] + 4 * h
        for i, s in enumerate(reversed(lab)):
            text(bx + 0.5 * h, ty + (i + 0.3) * 1.6 * h, s, "BL")
        res.append(r)
    return "".join(out), res


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "종단·횡단 그리기", size="580x940")
        self.acad = A.Acad()
        self.prof = None
        self.secs = None
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        row = tk.Frame(self, bg=ui.BG)
        row.pack(fill="x", padx=10, pady=2)
        for t, fn in (("종단 자료 가져오기(엑셀 범위)", self.get_prof), ("횡단 자료 가져오기(엑셀 범위)", self.get_secs)):
            tk.Button(row, text=t, command=fn, bg="#3E5879", fg="#FFFFFF", relief="flat").pack(
                side="left", expand=True, fill="x", padx=1)
        row = tk.Frame(self, bg=ui.BG)
        row.pack(fill="x", padx=10, pady=4)
        for t, fn in (("종단 그리기", self.draw_prof), ("횡단 그리기", self.draw_secs)):
            tk.Button(row, text=t, command=fn, bg="#3E5879", fg="#FFFFFF", relief="flat", height=2).pack(
                side="left", expand=True, fill="x", padx=1)

    def _cfg(self):
        cfg = self.form.values()
        S.save(CMD, cfg)
        return cfg

    def get_prof(self):
        try:
            cfg = self._cfg()
            rows = X.selection_values()
            drp.parse_table(rows, cfg)
        except (ValueError, X.ExcelNotReady) as e:
            self.error(str(e))
            return
        self.prof = rows
        self.status("종단 자료 %d줄을 가져왔습니다." % len(rows))

    def get_secs(self):
        try:
            secs = parse_sections(X.selection_values(), self._cfg())
        except (ValueError, X.ExcelNotReady) as e:
            self.error(str(e))
            return
        if not secs:
            self.error("횡단을 읽지 못했습니다(횡단 형식·거리높이 설정 확인).")
            return
        self.secs = secs
        self.status("횡단 %d개를 가져왔습니다." % len(secs))

    def _pick(self, msg):
        rows = self.in_cad(self.acad.lisp, '(setq _o (getpoint "\\n%s: ")) (if _o (progn (setq _o (trans _o 1 0))'
                           ' (write-line (strcat (bc:rtos (car _o) 2 10) _d (bc:rtos (cadr _o) 2 10)) _fp)))' % msg,
                           A.PICK_TIMEOUT)
        return [float(v) for v in rows[0].split("\t")] if rows else None

    def draw_prof(self):
        if not self.prof:
            self.error("먼저 [종단 자료 가져오기]를 하세요.")
            return
        o = self._pick("종단 넣을 점(기준선 왼쪽 끝) 지정")
        if not o:
            return
        try:
            code, table, vt = drp.build(self.prof, self._cfg(), o)
        except ValueError as e:
            self.error(str(e))
            return
        if self.in_cad(self.acad.lisp_undo, code, 180) is not None:
            self.status("종단 측점 %d개, VIP %d개를 그렸습니다." % (len(table) - 1, len(vt)))

    def draw_secs(self):
        if not self.secs:
            self.error("먼저 [횡단 자료 가져오기]를 하세요.")
            return
        o = self._pick("첫 횡단 중심 기준선 위치 지정")
        if not o:
            return
        try:
            cfg = self._cfg()
            code, res = sections_lisp(self.secs, o, cfg, plan_of(self.prof, cfg))
        except ValueError as e:
            self.error(str(e))
            return
        if self.in_cad(self.acad.lisp_undo, code, 180) is not None:
            self.status("횡단 %d개를 그렸습니다." % len(res))


def main():
    Window().mainloop()
