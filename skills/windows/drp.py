# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""DRP 엑셀 표로 종단면도 작도 — 엑셀 표(첫 줄 머리)로 지반선·계획선·기타 선과 종단 표를 그린다.

머리 이름으로 열을 찾는다(순서 자유):
- '누가거리'(또는 '거리') 열이 거리, 없으면 '측점' 열(0+000·No.3+5)을 거리로 바꾼다.
- '계획' 열 + '종곡선'('곡선길이') 열이 있으면 계획 열 값은 VIP EL — 종곡선을 계산해 계획선을 그린다.
  종곡선 열이 없으면 계획 열 값을 그대로 잇는다.
- 그 밖의 숫자 열(지반고·제방고·HWL …)은 열마다 선 하나. 칸에 x를 넣으면 선을 끊는다.
- 머리 없이 숫자만이면 [누가거리, 지반고, 계획고(VIP), 종곡선 길이] 순서로 읽는다.
표에 쓰는 측점은 첫 선(보통 지반고)에 값이 있는 거리, 그리고 측점 간격 정체인.
parse_table()·build()는 창 없이도 쓴다(MCP skill_run).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui
from skills.common import vprof as V

CMD = "DRP"
FIELDS = V.PROFILE_FIELDS + [
    ("간격", "표 측점 간격 (m, 0=자료 거리만)", "real", 20.0, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def _num(v):
    f = X.to_float(v)
    return f


def _is_head(row):
    return any(isinstance(v, str) and v.strip() and _num(v) is None and v.strip().lower() != "x" for v in row)


def parse_table(rows, cfg):
    """→ (series [{name, pts, plan}], vips [(d, z, L)], marks [d…]). 거리는 시작거리 기준(0부터)."""
    rows = [list(r) for r in rows if r and any(v not in (None, "") for v in r)]
    if not rows:
        raise ValueError("표가 비어 있습니다.")
    if _is_head(rows[0]):
        head = [str(v or "").replace(" ", "").replace("\n", "") for v in rows[0]]
        body = rows[1:]
    else:
        head = ["누가거리", "지반고", "계획고", "종곡선"][:len(rows[0])]
        body = rows
    di = next((i for i, h in enumerate(head) if "누가" in h), None)
    if di is None:
        di = next((i for i, h in enumerate(head) if "거리" in h and "구간" not in h), None)
    si = next((i for i, h in enumerate(head) if "측점" in h), None)
    if di is None and si is None:
        raise ValueError("누가거리(또는 측점) 열을 찾지 못했습니다. 첫 줄 머리를 확인하세요.")
    li = next((i for i, h in enumerate(head) if "종곡선" in h or "곡선길이" in h or "곡선장" in h), None)
    pi = next((i for i, h in enumerate(head) if "계획" in h and i != li), None)
    start = V.start_of(cfg)
    ds = []
    for r in body:
        d = _num(r[di]) if di is not None and di < len(r) else None
        if d is None and si is not None and si < len(r) and r[si] not in (None, ""):
            d = C.station_to_dist(str(r[si]), cfg["측점구분"], float(cfg["체인"]))
        ds.append(None if d is None else d - start)
    skip = {di, si, li}
    series, vips = [], []
    for j, h in enumerate(head):
        if j in skip or not h:
            continue
        if j == pi and li is not None:
            for d, r in zip(ds, body):
                z = _num(r[j]) if j < len(r) else None
                if d is not None and z is not None:
                    L = _num(r[li]) if li < len(r) else None
                    vips.append((d, z, L or 0.0))
            continue
        pts, any_v = [], False
        for d, r in zip(ds, body):
            v = r[j] if j < len(r) else None
            if isinstance(v, str) and v.strip().lower() == "x":
                pts.append(None)
                continue
            z = _num(v)
            if d is not None and z is not None:
                pts.append((d, z))
                any_v = True
        if any_v:
            series.append({"name": h, "pts": pts, "plan": j == pi})
    if not series and not vips:
        raise ValueError("EL 값이 든 열이 없습니다.")
    vips.sort()
    if vips:
        vips[0] = (vips[0][0], vips[0][1], 0.0)
        vips[-1] = (vips[-1][0], vips[-1][1], 0.0)
    base = next((s for s in series if not s["plan"]), series[0] if series else None)
    ds_mark = [p[0] for p in base["pts"] if p] if base else [v[0] for v in vips]
    marks = V.default_marks(ds_mark, float(cfg["간격"]), start)
    if base:  # 첫 선 범위 밖 정체인은 빼고
        lo, hi = min(ds_mark), max(ds_mark)
        marks = [m for m in marks if lo - 1e-6 <= m <= hi + 1e-6]
    return series, vips, marks


def build(rows, cfg, origin):
    series, vips, marks = parse_table(rows, cfg)
    bad = V.check_vips(vips) if vips else []
    if bad:
        raise ValueError("; ".join(bad))
    code, table, head = V.build_profile(series, vips, marks, cfg, origin)
    vt = V.vip_table(vips, V.start_of(cfg), cfg["측점구분"], float(cfg["체인"])) if vips else []
    return code, [head] + table, vt


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "엑셀 표로 종단면도 작도", size="560x900")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Label(self, text="엑셀에서 머리 줄(누가거리·지반고·계획고·종곡선 …)을 포함해 범위를 고른 뒤 누르세요.",
                 bg=ui.BG, fg=ui.STATUS, font=ui.FONT, wraplength=520, justify="left").pack(fill="x", padx=10)
        tk.Button(self, text="엑셀 선택 범위 → 종단 넣을 점 지정", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
            S.save(CMD, cfg)
            rows = X.selection_values()
            parse_table(rows, cfg)
        except (ValueError, X.ExcelNotReady) as e:
            self.error(str(e))
            return
        pick = self.in_cad(self.acad.lisp, '(setq _o (getpoint "\\n종단 넣을 점(기준선 왼쪽 끝) 지정: "))'
                           ' (if _o (progn (setq _o (trans _o 1 0)) (write-line (strcat (bc:rtos (car _o) 2 10) _d'
                           ' (bc:rtos (cadr _o) 2 10)) _fp)))', A.PICK_TIMEOUT)
        if not pick:
            return
        try:
            code, table, vt = build(rows, cfg, [float(v) for v in pick[0].split("\t")])
        except ValueError as e:
            self.error(str(e))
            return
        if self.in_cad(self.acad.lisp_undo, code, 180) is None:
            return
        self.status("종단 측점 %d개, VIP %d개를 그렸습니다." % (len(table) - 1, len(vt)))


def main():
    Window().mainloop()
