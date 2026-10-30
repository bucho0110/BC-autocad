# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""DRRE 호안 전개도 — 측점별 호안 경사·길이(높이)·밑다짐으로 전개도와 수량표를 그린다(곡선부 연장 보정).

1) 양식 만들기: 선형(LWPOLYLINE)을 고르면 측점 간격마다 + 곡선 BC·EC(반지름 R, 왼쪽 곡선 +/오른쪽 −) 행을 엑셀에 쓴다.
   사람이 호안경사(1:n의 n)·길이(높이)·밑다짐폭·중심~호안머리 거리(곡선부)를 채운다.
2) 전개도: 비탈 길이 S = 경사가 1:1보다 완만하면 입력 길이, 1:1 이하(급)면 입력은 높이 → S = H×√(1+n²).
   곡선부 연장 = 중심선 연장 × (R ± 거리)/R. 호안머리 거리 d, 기초 거리 d ± w(w = S의 수평 성분), 밑다짐 중심 d ± (w + 밑다짐/2).
   ± 는 호안이 곡선 안쪽이면 −(반지름 작아짐), 바깥쪽이면 +. 선형 구분이 '하천중심'이면 기초가 중심 쪽으로(d − w).
   면적 = 평균 비탈 길이 × 평균(머리·기초) 연장. 밑다짐 면적 = 밑다짐폭 × 밑다짐 연장.
compute()·draw_lisp()는 창 없이도 쓴다(MCP run_skill).
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as XL
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls

CMD = "DRRE"
HEAD = ["누가거리", "구분", "R", "호안경사", "길이(높이)", "밑다짐폭", "중심~호안머리"]
FIELDS = [
    ("측점구분", "측점 구분", "choice", "Station", ["Station", "Number"]),
    ("측점간격", "측점(양식) 간격 (m)", "real", 20.0, None),
    ("시작거리", "선형 시작 거리", "str", "0", None),
    ("평면축척", "선형 도면 축척 (1000 = 1m가 도면 1)", "real", 1000.0, None),
    ("호안위치", "호안 위치 (선형 진행 방향 기준)", "choice", "좌", ["좌", "우"]),
    ("선형구분", "선형 구분", "choice", "제방선형", ["제방선형", "하천중심"]),
    ("H축척", "전개도 수평 축척", "real", 1000.0, None),
    ("V축척", "전개도 수직 축척", "real", 100.0, None),
    ("높이", "전개도·표 문자 높이 (도면 단위)", "real", 2.0, None),
    ("레이어", "레이어 (비우면 현재)", "str", "", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


# ---------------------------------------------------------------- 선형 곡선

def curves_from_segs(segs, up):
    """LWPOLYLINE 구간 [(p1, p2, bulge)] → 곡선 [(BC 도면거리, EC 도면거리, R(도면), 부호 +왼쪽/−오른쪽)]"""
    out, d = [], 0.0
    for p1, p2, b in segs:
        c = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if abs(b) > 1e-12:
            th = 4.0 * math.atan(abs(b))
            r = c / (2.0 * math.sin(th / 2.0))
            L = r * th
            out.append((d, d + L, r, 1 if b > 0 else -1))
            d += L
        else:
            d += c
    return out


SEG_BODY = ('(setq _a (bc:pick-align "호안 선형(LWPOLYLINE) 선택"))'
            ' (if _a (progn (write-line (strcat "A\\t" (if (cadr _a) "1" "0") "\\t" (bc:rtos (bc:curve-len (car _a)) 2 10)) _fp)'
            ' (foreach _s (bc:lw-segs (car _a)) (write-line (strcat "G\\t" (bc:rtos (car (car _s)) 2 10) "\\t" (bc:rtos (cadr (car _s)) 2 10)'
            ' "\\t" (bc:rtos (car (cadr _s)) 2 10) "\\t" (bc:rtos (cadr (cadr _s)) 2 10) "\\t" (bc:rtos (caddr _s) 2 12)) _fp))))')


def template_rows(L_units, rev, segs, cfg):
    """양식 행(머리글 포함). 반대 방향이면 곡선 순서·부호를 뒤집는다."""
    up = 1000.0 / float(cfg["평면축척"])
    d0 = C.station_to_dist(cfg["시작거리"], cfg["측점구분"], float(cfg["측점간격"])) or 0.0
    cv = curves_from_segs(segs, up)
    if rev:
        cv = [(L_units - e, L_units - b, r, -sg) for b, e, r, sg in reversed(cv)]
    iv = float(cfg["측점간격"])
    rows = {}
    total = L_units / up
    k = 0
    while k * iv <= total + 1e-9:
        rows[round(d0 + k * iv, 4)] = ("", "")
        k += 1
    rows[round(d0 + total, 4)] = ("", "")
    for b, e, r, sg in cv:
        rows[round(d0 + b / up, 4)] = ("BC", sg * r / up)
        rows[round(d0 + e / up, 4)] = ("EC", sg * r / up)
    out = [HEAD]
    for d in sorted(rows):
        kind, R = rows[d]
        out.append([d, kind, R if R != "" else "", "", "", "", ""])
    return out


# ---------------------------------------------------------------- 계산

def parse_rows(rows):
    """엑셀 [누가거리, 구분, R, 경사, 길이(높이), 밑다짐, 중심~호안머리] (머리글 있으면 건너뜀)"""
    out = []
    for r in rows:
        r = list(r) + [None] * 7
        d = XL.to_float(r[0])
        if d is None:
            continue
        out.append({"d": d, "kind": str(r[1] or "").strip().upper(), "R": XL.to_float(r[2]), "n": XL.to_float(r[3]),
                    "v": XL.to_float(r[4]), "mat": XL.to_float(r[5]) or 0.0, "off": XL.to_float(r[6])})
    out.sort(key=lambda x: x["d"])
    return out


def slope_len(n, v):
    """비탈 길이와 수평 폭. 1:1보다 완만(n>1)하면 v가 길이, 아니면 v가 높이."""
    if n is None or v is None:
        return None, None
    k = math.sqrt(1.0 + n * n)
    S_ = v if n > 1.0 else v * k
    return S_, S_ * n / k


def _fill(recs):
    """BC·EC 행의 비어 있는 경사·길이는 앞뒤 측점 값으로 보간(앞 값 우선)."""
    for i, r in enumerate(recs):
        for key in ("n", "v"):
            if r[key] is None:
                prv = next((recs[j][key] for j in range(i - 1, -1, -1) if recs[j][key] is not None), None)
                nxt = next((recs[j][key] for j in range(i + 1, len(recs)) if recs[j][key] is not None), None)
                if prv is not None and nxt is not None:
                    r[key] = (prv + nxt) / 2.0
                else:
                    r[key] = prv if prv is not None else nxt
    return recs


def compute(rows, cfg):
    """반환: {"segs": [구간…], "pts": [(d, S)], "total": {...}}. 구간: 번호·시점·종점·연장(머리·기초·밑다짐)·평균 S·면적."""
    recs = _fill(parse_rows(rows))
    side = 1 if cfg["호안위치"] == "좌" else -1
    river_center = cfg["선형구분"] == "하천중심"
    curves, cur = [], None
    for r in recs:
        if r["kind"] == "BC":
            cur = (r["d"], r["R"], r["off"] or 0.0)
        elif r["kind"] == "EC" and cur:
            curves.append((cur[0], r["d"], cur[1], cur[2] if cur[2] else (r["off"] or 0.0)))
            cur = None
    segs, pts = [], []
    no = 0
    for a, b in zip(recs, recs[1:]):
        L = b["d"] - a["d"]
        if L <= 1e-9:
            continue
        Sa, wa = slope_len(a["n"], a["v"])
        Sb, wb = slope_len(b["n"], b["v"])
        if Sa is None or Sb is None:
            continue
        if Sa == 0 and Sb == 0:   # 길이 0 = 끊는 구간
            continue
        mid = (a["d"] + b["d"]) / 2.0
        f_top = f_bot = f_mat = 1.0
        for bc, ec, R, off in curves:
            if bc - 1e-9 <= mid <= ec + 1e-9 and R:
                inner = (R > 0 and side > 0) or (R < 0 and side < 0)   # 호안이 곡선 안쪽
                sg = -1.0 if inner else 1.0
                w = (wa + wb) / 2.0
                mat = (a["mat"] + b["mat"]) / 2.0
                d_bot = off - w if river_center else off + w
                d_mat = d_bot - mat / 2.0 if river_center else d_bot + mat / 2.0
                Ra = abs(R)
                f_top, f_bot, f_mat = (Ra + sg * off) / Ra, (Ra + sg * d_bot) / Ra, (Ra + sg * d_mat) / Ra
        no += 1
        Lt, Lb, Lm = L * f_top, L * f_bot, L * f_mat
        Sm = (Sa + Sb) / 2.0
        mat = (a["mat"] + b["mat"]) / 2.0
        segs.append({"no": no, "from": a["d"], "to": b["d"], "L": L, "L_top": Lt, "L_bot": Lb, "S": Sm,
                     "area": Sm * (Lt + Lb) / 2.0, "mat_area": mat * Lm, "curve": f_top != 1.0})
    for r in recs:
        S_, _w = slope_len(r["n"], r["v"])
        if S_ is not None:
            pts.append((r["d"], S_, r["kind"]))
    tot = {k: sum(s[k] for s in segs) for k in ("L", "L_top", "L_bot", "area", "mat_area")}
    return {"segs": segs, "pts": pts, "total": tot}


# ---------------------------------------------------------------- 그리기

def draw_lisp(res, cfg, origin):
    """전개도(위 = 호안머리, 아래로 비탈 길이)와 그 아래 수량표."""
    if not res["pts"]:
        return ""
    uh, uv = 1000.0 / float(cfg["H축척"]), 1000.0 / float(cfg["V축척"])
    h = float(cfg["높이"])
    lay = ls(cfg["레이어"])
    x0, y0 = origin
    d0 = res["pts"][0][0]
    s = []
    X_ = lambda d: x0 + (d - d0) * uh
    top = [(X_(d), y0) for d, _S, _k in res["pts"]]
    bot = [(X_(d), y0 - S_ * uv) for d, S_, _k in res["pts"]]
    s.append('(bc:pline (list %s) nil "%s")' % (" ".join("(list %.10f %.10f)" % p for p in top), lay))
    s.append('(bc:pline (list %s) nil "%s")' % (" ".join("(list %.10f %.10f)" % p for p in bot), lay))
    for (d, S_, kind), (x, yb) in zip(res["pts"], bot):
        s.append('(bc:line (list %.10f %.10f 0.0) (list %.10f %.10f 0.0) "%s")' % (x, y0, x, yb, lay))
        s.append('(bc:text (list %.10f %.10f 0.0) "%s" %.6f "%s" "ML" %.12f)'
                 % (x, y0 + h * 0.6, ls(C.fmt(d, 2) + ((" " + kind) if kind else "")), h * 0.8, lay, math.pi / 2))
        s.append('(bc:text (list %.10f %.10f 0.0) "%s" %.6f "%s" "TC" 0.0)' % (x, yb - h * 0.4, ls(C.fmt(S_, 2)), h * 0.8, lay))
    for sg in res["segs"]:
        xm = (X_(sg["from"]) + X_(sg["to"])) / 2.0
        s.append('(bc:circle (list %.10f %.10f 0.0) %.6f "%s")' % (xm, y0 - h * 1.5, h * 0.8, lay))
        s.append('(bc:text (list %.10f %.10f 0.0) "%d" %.6f "%s" "MC" 0.0)' % (xm, y0 - h * 1.5, sg["no"], h, lay))
    # 수량표
    cols = [("번호", 6), ("구간", 22), ("연장(머리)", 12), ("연장(기초)", 12), ("비탈길이", 11), ("면적", 12), ("밑다짐면적", 12)]
    ty = min(p[1] for p in bot) - h * 6
    rh = h * 2.0
    rows = [[c for c, _w in cols]]
    for sg in res["segs"]:
        rows.append([str(sg["no"]), "%s~%s%s" % (C.fmt(sg["from"], 2), C.fmt(sg["to"], 2), " (곡선)" if sg["curve"] else ""),
                     C.fmt(sg["L_top"], 2), C.fmt(sg["L_bot"], 2), C.fmt(sg["S"], 2), C.fmt(sg["area"], 2), C.fmt(sg["mat_area"], 2)])
    t = res["total"]
    rows.append(["계", "", C.fmt(t["L_top"], 2), C.fmt(t["L_bot"], 2), "", C.fmt(t["area"], 2), C.fmt(t["mat_area"], 2)])
    widths = [w * h for _c, w in cols]
    W = sum(widths)
    for i, row in enumerate(rows):
        yy = ty - i * rh
        x = x0
        for (txt, w) in zip(row, widths):
            s.append('(bc:text (list %.10f %.10f 0.0) "%s" %.6f "%s" "MC" 0.0)' % (x + w / 2.0, yy - rh / 2.0, ls(txt), h * 0.8, lay))
            x += w
    for i in range(len(rows) + 1):
        yy = ty - i * rh
        s.append('(bc:line (list %.10f %.10f 0.0) (list %.10f %.10f 0.0) "%s")' % (x0, yy, x0 + W, yy, lay))
    x = x0
    for w in [0.0] + widths:
        x += w
        s.append('(bc:line (list %.10f %.10f 0.0) (list %.10f %.10f 0.0) "%s")' % (x, ty, x, ty - len(rows) * rh, lay))
    return "".join(s)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "호안 전개도 작도", size="560x600")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        bar = tk.Frame(self, bg=ui.BG)
        bar.pack(fill="x", padx=10, pady=4)
        tk.Button(bar, text="1. 양식 만들기 (엑셀 첫 셀 선택 후)", command=self.make_template, bg="#383A3E", fg="#FFFFFF",
                  relief="flat", height=2).pack(side="left", padx=3, expand=True, fill="x")
        tk.Button(bar, text="2. 전개도 그리기 (양식 범위 선택 후)", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(side="left", padx=3, expand=True, fill="x")

    def make_template(self):
        try:
            cfg = self.form.values()
            S.save(CMD, cfg)
            ws, r0, c0 = XL.active_cell()
        except (ValueError, XL.ExcelNotReady) as e:
            self.error(str(e))
            return
        rows = self.in_cad(self.acad.lisp, SEG_BODY, A.PICK_TIMEOUT) or []
        a = [x.split("\t") for x in rows if x.startswith("A\t")]
        if not a:
            return
        segs = [((float(c[1]), float(c[2])), (float(c[3]), float(c[4])), float(c[5])) for c in (x.split("\t") for x in rows) if c[0] == "G"]
        out = template_rows(float(a[0][2]), a[0][1] == "1", segs, cfg)
        XL.write_rows(ws, r0, c0, out)
        self.status("양식 %d행을 썼습니다. 호안경사·길이(높이)·밑다짐폭·중심~호안머리(곡선부)를 채운 뒤 2번을 누르세요." % (len(out) - 1))

    def run(self):
        try:
            cfg = self.form.values()
            S.save(CMD, cfg)
            res = compute(XL.selection_values(), cfg)
        except (ValueError, XL.ExcelNotReady) as e:
            self.error(str(e))
            return
        if not res["segs"]:
            self.error("계산할 구간이 없습니다(경사·길이 확인).")
            return
        rows = self.in_cad(self.acad.lisp, '(setq _p (getpoint "\\n전개도 왼쪽 위 점 지정: ")) (if _p (progn (setq _p (trans _p 1 0))'
                                           ' (write-line (strcat "P\\t" (bc:rtos (car _p) 2 10) "\\t" (bc:rtos (cadr _p) 2 10)) _fp)))',
                           A.PICK_TIMEOUT) or []
        p = [r.split("\t") for r in rows if r.startswith("P\t")]
        if not p:
            return
        if self.in_cad(self.acad.lisp_undo, draw_lisp(res, cfg, (float(p[0][1]), float(p[0][2]))), 120) is not None:
            t = res["total"]
            self.status("구간 %d개, 면적 %.2f㎡, 밑다짐 %.2f㎡를 그렸습니다." % (len(res["segs"]), t["area"], t["mat_area"]))


def main():
    Window().mainloop()
