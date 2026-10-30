# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""DDGP 횡단 계획선 일괄 작도 — 엑셀의 측점별 하상고·계획고·하폭·제방폭·경사로 횡단면마다 제방 계획선.

한 쪽(좌·우) 계획선: 하폭 끝(법선, 하상고) → 제외지(앞비탈) 경사로 계획고까지(호안 경사가 있으면 H.W.L까지는 호안 경사)
→ 둑마루 폭 수평 → 제내지(뒷비탈) 경사로 내려가 지반선과 만나는 곳까지. 하상선은 좌·우 법선 사이(지반이 하상보다 낮은 곳은 끊기 선택).
엑셀은 머리글 이름으로 열을 찾는다(순서 무관). 좌·우를 같이 그릴 때는 머리글에 '좌'·'우'가 있어야 한다.
단면은 견본 한 단면으로 찾는다(skills/common/xsec.py). build_lisp()는 창 없이도 쓴다(MCP run_skill).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as XL
from skills.common import settings as S
from skills.common import ui
from skills.common import xsec as X
from skills.windows import hwlm
from validators import lisp_str as ls

CMD = "DDGP"
FIELDS = [
    ("계획구분", "계획 구분", "choice", "좌우", ["좌우", "좌안", "우안"]),
    ("H축척", "횡단 수평 축척 (단면 아래 거리 눈금이 없을 때만, 글자 크기 기준)", "real", 1000.0, None),
    ("V축척", "횡단 수직 축척 (단면 왼쪽 EL 눈금이 없을 때만)", "real", 1000.0, None),
    ("측점구분", "측점 구분", "choice", "Station", ["Station", "Number"]),
    ("측점간격", "Number 측점 간격 (m)", "real", 20.0, None),
    ("하상끊기", "지반이 하상보다 낮은 곳은 하상선 끊기", "bool", True, None),
    ("수위표기", "HWL·SWL 기호 표기(HWLM 설정 따름)", "bool", True, None),
    ("수평선", "여유고·HWL·SWL 수평선", "bool", False, None),
    ("레이어", "계획선 레이어 (비우면 현재)", "str", "", None),
    ("하상레이어", "하상선 레이어 (비우면 계획선 레이어)", "str", "", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}

# 머리글 인식: (키, 포함 단어들) — 앞에서 먼저 맞는 것
KEYS = [
    ("측점", ("누가거리", "측점")),
    ("하상", ("하상",)),
    ("계획고", ("계획고", "제방고")),
    ("하폭", ("하폭",)),
    ("제방폭", ("제방폭", "둑마루폭")),
    ("제내지경사", ("제내지경사", "뒷비탈경사")),
    ("제외지경사", ("제외지경사", "앞비탈경사")),
    ("호안경사", ("호안경사",)),
    ("여유고", ("여유",)),
    ("HWL", ("HWL", "H.W.L", "홍수위")),
    ("SWL", ("SWL", "S.W.L", "일제관측수위")),
    ("제방경사", ("제방경사",)),
]
# 고수부지 키는 '고수'가 들어간 머리글만 따로 본다(일반 키보다 먼저)
TERRACE_KEYS = [
    ("고수부지고", ("고수부지고", "둔치계획고")),
    ("고수호안폭", ("고수호안폭", "둔치호안폭")),
    ("저수호안경사", ("저수호안경사",)),
    ("고수부지경사", ("고수부지경사", "둔치경사")),
]


def header_map(head):
    """머리글 → {(키, 쪽): 열번호}. 쪽은 'L'·'R'·'' (좌·우 없음)."""
    out = {}
    for i, h in enumerate(head):
        t = str(h or "").replace(" ", "").upper().replace("ＨＷＬ", "HWL")
        if not t:
            continue
        side = "L" if "좌" in t else ("R" if "우" in t else "")
        tt = t.replace("좌", "").replace("우", "")
        hit = False
        for key, words in TERRACE_KEYS:
            if any(w in tt for w in words):
                out.setdefault((key, side), i)
                hit = True
                break
        if hit:
            continue
        for key, words in KEYS:
            if any(w.upper() in tt for w in words):
                if key == "하폭" and "제방" in tt:
                    continue
                out.setdefault((key, side), i)
                break
    return out


def parse_table(rows, cfg):
    """엑셀 범위(첫 행 머리글) → {누가거리(소수 4자리): {(키, 쪽): 값}}"""
    if not rows:
        return {}
    hm = header_map(rows[0])
    if ("측점", "") not in hm:
        raise ValueError("엑셀 머리글에 '측점' 또는 '누가거리'가 없습니다(첫 행이 머리글이어야 합니다).")
    out = {}
    for r in rows[1:]:
        d = C.station_to_dist(r[hm[("측점", "")]], cfg["측점구분"], float(cfg["측점간격"]))
        if d is None:
            continue
        rec = {}
        for (k, sd), i in hm.items():
            if k != "측점" and i < len(r):
                rec[(k, sd)] = XL.to_float(r[i])
        out[round(d, 4)] = rec
    return out


def _get(rec, key, side):
    """좌·우 값이 없으면 쪽 없는 값(한쪽 데이터)을 쓴다."""
    v = rec.get((key, side))
    return v if v is not None else rec.get((key, ""))


def _ray_ground(p, d, pts):
    """p에서 방향 d(단위 벡터)로 나가며 지반선(점 목록)과 처음 만나는 점."""
    best, bt = None, None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        ex, ey = x1 - x0, y1 - y0
        den = d[0] * ey - d[1] * ex
        if abs(den) < 1e-12:
            continue
        t = ((x0 - p[0]) * ey - (y0 - p[1]) * ex) / den
        u = ((x0 - p[0]) * d[1] - (y0 - p[1]) * d[0]) / den
        if t > 1e-9 and -1e-9 <= u <= 1 + 1e-9 and (bt is None or t < bt):
            best, bt = (p[0] + t * d[0], p[1] + t * d[1]), t
    return best


def side_points(sec, rec, side, cfg):
    """한 쪽 계획선 꼭짓점 [(x, y)] 또는 (None, 이유)."""
    V = float(cfg["V축척"])
    uh, uv = X.uh(sec, float(cfg["H축척"])), X.uv(sec, V)
    bed, top, half = _get(rec, "하상", side), _get(rec, "계획고", side), _get(rec, "하폭", side)
    cw, n_in, n_out = _get(rec, "제방폭", side), _get(rec, "제내지경사", side), _get(rec, "제외지경사", side)
    miss = [k for k, v in (("하상고", bed), ("계획고", top), ("하폭", half), ("제방폭", cw), ("제내지경사", n_in), ("제외지경사", n_out))
            if v is None]
    if miss:
        return None, "값 없음: " + ", ".join(miss)
    sg = -1.0 if side == "L" else 1.0
    cx = sec["center"][0]
    t_el, t_w, n_lw = _get(rec, "고수부지고", side), _get(rec, "고수호안폭", side), _get(rec, "저수호안경사", side)
    hwl = _get(rec, "HWL", side)
    if t_el is not None and t_w is not None and n_lw is not None and bed < t_el < top:
        # 고수부지: 저수로 법선(하상) → 저수호안 경사로 고수부지고(중심에서 고수호안폭) → 고수부지(경사 %) → 제방 법선(하폭)
        pts = [(cx + sg * (t_w - n_lw * (t_el - bed)) * uh, X.y_of(sec, bed, V)),
               (cx + sg * t_w * uh, X.y_of(sec, t_el, V))]
        t_slope = _get(rec, "고수부지경사", side) or 0.0
        el = t_el + t_slope / 100.0 * max(0.0, half - t_w)
        p = (cx + sg * half * uh, X.y_of(sec, el, V))
        pts.append(p)
    else:
        p = (cx + sg * half * uh, X.y_of(sec, bed, V))
        pts = [p]
        el = bed
    n_rev = _get(rec, "호안경사", side)
    if n_rev is not None and hwl is not None and el < hwl < top:
        p = (p[0] + sg * n_rev * (hwl - el) * uh, X.y_of(sec, hwl, V))
        pts.append(p)
        el = hwl
    p = (p[0] + sg * n_out * (top - el) * uh, X.y_of(sec, top, V))
    pts.append(p)
    # 둑마루: 제방경사(%)가 있으면 제내지 쪽으로 내려간다
    crown = _get(rec, "제방경사", "") or 0.0
    p = (p[0] + sg * cw * uh, p[1] - crown / 100.0 * cw * uv)
    pts.append(p)
    # 뒷비탈: 1:n_in 으로 바깥쪽 아래로, 지반선과 만나는 곳까지
    dx, dy = sg * n_in * uh, -1.0 * uv
    L = (dx * dx + dy * dy) ** 0.5
    hit = _ray_ground(p, (dx / L, dy / L), sec["ground_pts"])
    if hit:
        pts.append(hit)
    else:
        pts.append((p[0] + dx * 30, p[1] + dy * 30))
    return pts, None


def bed_segments(sec, xl, xr, ybed, cut):
    """하상선 [xl, xr] — cut이면 지반이 하상보다 낮은(지반선 아래로 파고들지 않는) 구간은 뺀다."""
    if not cut:
        return [(xl, xr)]
    pts = [p for p in sec["ground_pts"]]
    xs = sorted({xl, xr} | {x for x, _y in pts if xl < x < xr} |
                {x0 + (x1 - x0) * (ybed - y0) / (y1 - y0) for (x0, y0), (x1, y1) in zip(pts, pts[1:])
                 if (y0 - ybed) * (y1 - ybed) < 0 and xl < x0 + (x1 - x0) * (ybed - y0) / (y1 - y0) < xr})
    segs = []
    for a, b in zip(xs, xs[1:]):
        m = (a + b) / 2.0
        gy = X._ground_y([(x, y, 0.0) for x, y in pts], m)
        if gy is None or gy >= ybed - 1e-9:
            if segs and abs(segs[-1][1] - a) < 1e-9:
                segs[-1] = (segs[-1][0], b)
            else:
                segs.append((a, b))
    return segs


def build_lisp(sections, table, cfg):
    """반환 (LISP, 그린 단면 수, 엑셀에 없는 단면, 값이 모자란 단면 [(측점, 이유)])."""
    s, n, miss, bad = [], 0, [], []
    lay = ls(cfg["레이어"])
    blay = ls(cfg["하상레이어"] or cfg["레이어"])
    sides = {"좌우": ("L", "R"), "좌안": ("L",), "우안": ("R",)}[cfg["계획구분"]]
    V = float(cfg["V축척"])
    for sec in sections:
        if not X.usable(sec) or sec["dist"] is None:
            continue
        rec = table.get(round(sec["dist"], 4))
        if rec is None:
            miss.append(sec["station"])
            continue
        made = {}
        for sd in sides:
            pts, why = side_points(sec, rec, sd, cfg)
            if pts is None:
                bad.append((sec["station"], ("좌" if sd == "L" else "우") + " " + why))
                continue
            made[sd] = pts
            s.append('(bc:pline (list %s) nil "%s")' % (" ".join("(list %.10f %.10f)" % p for p in pts), lay))
        if "L" in made and "R" in made:
            ybed = made["L"][0][1]
            for a, b in bed_segments(sec, made["L"][0][0], made["R"][0][0], ybed, cfg["하상끊기"]):
                s.append('(bc:line (list %.10f %.10f 0.0) (list %.10f %.10f 0.0) "%s")' % (a, ybed, b, ybed, blay))
        if made:
            n += 1
            hcfg = dict(S.load("HWLM", hwlm.DEFAULTS), H축척=cfg["H축척"], V축척=cfg["V축척"], 수면선=cfg["수평선"])
            hwl, swl = _get(rec, "HWL", ""), _get(rec, "SWL", "")
            if cfg["수위표기"] and hwl is not None:
                s.append(hwlm.mark_lisp(sec, hwl, hcfg["HWL머리"], hcfg))
            if cfg["수위표기"] and swl is not None:
                s.append(hwlm.mark_lisp(sec, swl, hcfg["SWL머리"], hcfg))
            fb = _get(rec, "여유고", "")
            if cfg["수평선"] and hwl is not None and fb is not None:
                y = X.y_of(sec, hwl + fb, V)
                sp = hwlm._water_span(sec, y)
                if sp:
                    s.append('(bc:line (list %.10f %.10f 0.0) (list %.10f %.10f 0.0) "%s")' % (sp[0], y, sp[1], y, lay))
    return "".join(s), n, miss, bad


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "횡단 계획선 일괄 작도", size="580x600")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Label(body, text="엑셀: 첫 행 머리글(측점·하상고·좌계획고·우계획고·좌하폭·우하폭·좌제방폭·우제방폭·\n"
                            "좌제내지경사·…·제외지경사·호안경사·HWL·SWL·여유고)을 포함해 범위 선택", bg=ui.PANEL, fg=ui.FG,
                 font=ui.FONT, justify="left").pack(fill="x", padx=8, pady=4)
        bar = tk.Frame(self, bg=ui.BG)
        bar.pack(fill="x", padx=10, pady=4)
        tk.Button(bar, text="견본 단면 등록", command=self.sample, bg="#383A3E", fg="#FFFFFF", relief="flat",
                  height=2, width=16).pack(side="left", padx=3)
        tk.Button(bar, text="엑셀 범위 선택 후 → 일괄 작도", command=self.run, bg="#3E5879", fg="#FFFFFF", relief="flat",
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
            S.save(CMD, cfg)
            table = parse_table(XL.selection_values(), cfg)
        except (ValueError, XL.ExcelNotReady) as e:
            self.error(str(e))
            return
        sp = X.load_spec()
        if not sp:
            self.error("견본 단면을 먼저 등록하세요.")
            return
        rows = self.in_cad(self.acad.lisp, X.dump_body(sp), 120)
        if rows is None:
            return
        secs = X.find(sp, C.parse_dump(rows), cfg["측점구분"], float(cfg["측점간격"]))
        body, n, miss, bad = build_lisp(secs, table, cfg)
        if not n:
            self.error("그릴 단면이 없습니다. 엑셀에 없는 단면 %d, 값 모자란 단면 %d" % (len(miss), len(bad)))
            return
        if self.in_cad(self.acad.lisp_undo, body, 120) is not None:
            self.status("단면 %d개 작도. 엑셀에 없음 %d, 값 모자람 %d: %s" % (n, len(miss), len(bad), "; ".join("%s %s" % b for b in bad[:4])))


def main():
    Window().mainloop()
