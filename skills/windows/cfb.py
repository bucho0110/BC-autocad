# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""CFB 횡단 지반선을 야장 엑셀로 — 횡단 지반선 정점의 거리·EL을 엑셀(야장)로 내보내거나 정점마다 문자로 쓴다.

일괄: 견본 단면 하나(지반선·중심선·측점 문자·지반고 문자 — DCEM과 같은 견본)로 도면의 모든 횡단을 찾는다.
하나씩: 지반선 선택 → 중심 점(EL 아는 높이) 지정 → 측점·EL 입력.
야장 형식(DCS 횡단 형식과 같다): ① 중심 기준 1열 [측점, 거리(좌 −), EL] ② 왼쪽부터 1열 ③ 좌우 구분.
거리/EL은 절대(중심·왼쪽 끝부터, EL 그대로) 또는 상대(앞 점부터).
section_points()·to_rows()·labels_lisp()는 창 없이도 쓴다(MCP skill_run).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui
from skills.common import vprof as V
from skills.common import xsec as XS
from skills.windows.dcs import DIST_EL, FORMS
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "CFB"
FIELDS = [
    ("양식", "야장 형식", "choice", FORMS[0], FORMS),
    ("거리높이", "거리/EL 방식", "choice", DIST_EL[0], DIST_EL),
    ("측점구분", "측점 구분", "choice", "Station", ["Station", "Number"]),
    ("측점간격", "Number 측점 간격 (m)", "real", 20.0, None),
    ("측점그대로", "측점은 도면 문자 그대로 (끄면 누가거리 숫자)", "bool", True, None),
    ("H축척", "횡단 H 축척 (1000 = 1m가 도면 1)", "real", 1000.0, None),
    ("V축척", "횡단 V 축척", "real", 1000.0, None),
    ("거리소수", "거리 소수 자리", "int", 3, None),
    ("높이소수", "EL 소수 자리", "int", 3, None),
    ("여유행", "측점 사이 빈 줄 수", "int", 1, None),
    ("도면표기", "정점마다 거리/EL 문자 쓰기", "bool", False, None),
    ("표기", "도면 문자 내용", "choice", "거리/EL", ["거리/EL", "거리", "EL"]),
    ("문자높이", "도면 문자 높이", "real", 1.0, None),
    ("레이어", "도면 문자 레이어", "str", "횡단_야장", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def section_points(verts, cx, to_el, uh):
    """지반선 정점 [(x, y)] → [(중심 기준 거리, EL)] (거리 순)."""
    return sorted(((x - cx) / uh, to_el(y)) for x, y in verts)


def to_rows(secs, cfg):
    """secs [{station, dist, points [(off, el)]}] → 엑셀 행."""
    dd, dz = int(cfg["거리소수"]), int(cfg["높이소수"])
    rel_d, rel_z = cfg["거리높이"] in DIST_EL[1:], cfg["거리높이"] == DIST_EL[1]
    out = []

    def sta(s):
        return s["station"] if cfg["측점그대로"] else C.fmt(s["dist"], 3)

    def seq(pts, origin_d, origin_z):
        """바깥쪽(또는 오른쪽)으로 적을 점 → [(거리, EL)] 문자."""
        res, pd, pz = [], origin_d, origin_z
        for d, z in pts:
            a = abs(d - pd) if rel_d else abs(d - origin_d)
            b = (z - pz) if rel_z else z
            res.append((C.fmt(a, dd), C.fmt(b, dz)))
            pd, pz = d, z
        return res

    for s in secs:
        pts = s["points"]
        if cfg["양식"] == FORMS[0]:
            for i, (d, z) in enumerate(pts):
                out.append([sta(s) if i == 0 else "", C.fmt(d, dd), C.fmt(z, dz)])
        elif cfg["양식"] == FORMS[1]:
            x0 = pts[0][0]
            res = [(C.fmt(0, dd), C.fmt(pts[0][1], dz))]
            pd, pz = x0, pts[0][1]
            for d, z in pts[1:]:
                res.append((C.fmt(d - (pd if rel_d else x0), dd), C.fmt(z - pz if rel_z else z, dz)))
                pd, pz = d, z
            for i, (a, b) in enumerate(res):
                out.append([sta(s) if i == 0 else "", a, b])
        else:
            zc = V.interp(pts, 0.0)  # 중심 지반고(지반선 보간)
            if zc is None:
                zc = s.get("center_el")
            left = sorted([p for p in pts if p[0] < -1e-9], key=lambda p: -p[0])
            right = [p for p in pts if p[0] > 1e-9]
            L, R = seq(left, 0.0, zc), seq(right, 0.0, zc)
            n = max(len(L), len(R), 2)
            for i in range(n):
                a = L[i] if i < len(L) else ("", "")
                b = R[i] if i < len(R) else ("", "")
                mid = sta(s) if i == 0 else (C.fmt(zc, dz) if i == 1 and zc is not None else "")
                out.append([a[0], a[1], mid, b[0], b[1]])
        out += [[""] * (5 if cfg["양식"] == FORMS[2] else 3) for _ in range(int(cfg["여유행"]))]
    return out


def labels_lisp(sec_draw, cfg):
    """sec_draw [(x, y, 거리, EL)] → 정점 위 문자."""
    lay, h = ls(cfg["레이어"]), float(cfg["문자높이"])
    out = ['(bc:ensure-layer "%s" 4)' % lay]
    for x, y, d, z in sec_draw:
        s = {"거리": C.fmt(d, int(cfg["거리소수"])), "EL": C.fmt(z, int(cfg["높이소수"]))}.get(
            cfg["표기"], "%s/%s" % (C.fmt(d, int(cfg["거리소수"])), C.fmt(z, int(cfg["높이소수"]))))
        out.append('(bc:text (list %.6f %.6f 0.0) "%s" %.6f "%s" "BL" 1.5707963268)' % (x + 0.4 * h, y + 0.5 * h, ls(s), h, lay))
    return "".join(out)


def batch(spec, rows, cfg):
    """견본으로 찾은 단면 → (secs, 문자 표기 점)."""
    ents = C.parse_dump(rows)
    pts_of = {e["handle"]: [(p[0], p[1]) for p in e["points"]] for e in ents}
    secs, marks = [], []
    for sec in XS.find(spec, ents, cfg["측점구분"], float(cfg["측점간격"])):
        if not XS.usable(sec) or sec["ground"] not in pts_of:
            continue
        uh = XS.uh(sec, float(cfg["H축척"]))
        cx = sec["center"][0]
        verts = pts_of[sec["ground"]]
        pts = section_points(verts, cx, lambda y, s=sec: XS.el_of(s, y, float(cfg["V축척"])), uh)
        secs.append({"station": sec["station"], "dist": sec["dist"] or 0.0, "points": pts,
                     "center_el": XS.el_of(sec, sec["y_g"], float(cfg["V축척"])) if sec["y_g"] is not None else None})
        marks += [(x, y, (x - cx) / uh, XS.el_of(sec, y, float(cfg["V축척"]))) for x, y in verts]
    secs.sort(key=lambda s: s["dist"])
    return secs, marks


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "횡단 지반선을 야장 엑셀로", size="540x700")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Label(self, text="엑셀에서 결과를 쓸 첫 칸을 고른 뒤 실행하세요. 일괄은 견본 단면을 먼저 등록합니다(DCEM과 같은 견본).",
                 bg=ui.BG, fg=ui.STATUS, font=ui.FONT, wraplength=500, justify="left").pack(fill="x", padx=10)
        row = tk.Frame(self, bg=ui.BG)
        row.pack(fill="x", padx=10, pady=4)
        for t, fn in (("견본 단면 등록", self.sample), ("일괄 내보내기", self.run_batch), ("단면 하나씩", self.run_one)):
            tk.Button(row, text=t, command=fn, bg="#3E5879", fg="#FFFFFF", relief="flat", height=2).pack(
                side="left", expand=True, fill="x", padx=1)

    def _cfg(self):
        cfg = self.form.values()
        S.save(CMD, cfg)
        return cfg

    def sample(self):
        rows = self.in_cad(self.acad.lisp, XS.SAMPLE_BODY, A.PICK_TIMEOUT)
        sp = XS.spec_from_rows(rows or [])
        if sp:
            XS.save_spec(sp)
            self.status("견본 단면을 등록했습니다.")

    def _write(self, secs, marks, cfg):
        if cfg["도면표기"] and marks:
            self.in_cad(self.acad.lisp_undo, labels_lisp(marks, cfg), 120)
        try:
            ws, r0, c0 = X.active_cell()
            X.write_rows(ws, r0, c0, to_rows(secs, cfg))
        except X.ExcelNotReady as e:
            self.error(str(e))
            return
        self.status("횡단 %d개를 엑셀로 내보냈습니다." % len(secs))

    def run_batch(self):
        cfg = self._cfg()
        spec = XS.load_spec()
        if not spec:
            self.error("먼저 [견본 단면 등록]을 하세요.")
            return
        rows = self.in_cad(self.acad.lisp, XS.dump_body(spec), 120)
        if rows is None:
            return
        secs, marks = batch(spec, rows, cfg)
        if not secs:
            self.error("견본과 같은 단면을 찾지 못했습니다.")
            return
        self._write(secs, marks, cfg)

    def run_one(self):
        cfg = self._cfg()
        body = ('(setq _s (entsel "\\n횡단 지반선 선택: ")) (if _s (progn (setq _g (car _s))'
                ' (foreach _p (bc:verts _g) (write-line (strcat "V" _d (bc:rtos (car _p) 2 10) _d (bc:rtos (cadr _p) 2 10)) _fp))'
                ' (setq _c (getpoint "\\n중심 점(EL을 아는 높이) 지정: ")) (if _c (progn (setq _c (trans _c 1 0))'
                ' (setq _z (getreal "\\n그 점의 EL: ")) (setq _t (getstring T "\\n측점: "))'
                ' (if _z (write-line (strcat "C" _d (bc:rtos (car _c) 2 10) _d (bc:rtos (cadr _c) 2 10) _d (bc:rtos _z 2 10)'
                ' _d _t) _fp))))))')
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
        c = [r.split("\t") for r in rows or [] if r.startswith("C\t")]
        if not c:
            return
        cx, cy, cz, st = float(c[0][1]), float(c[0][2]), float(c[0][3]), c[0][4] if len(c[0]) > 4 else ""
        uh, uv = 1000.0 / cfg["H축척"], 1000.0 / cfg["V축척"]
        verts = [(float(x[1]), float(x[2])) for x in (r.split("\t") for r in rows) if x[0] == "V"]
        to_el = lambda y: cz + (y - cy) / uv  # noqa: E731
        pts = section_points(verts, cx, to_el, uh)
        d = C.station_to_dist(st, cfg["측점구분"], float(cfg["측점간격"])) if st else 0.0
        secs = [{"station": st, "dist": d or 0.0, "points": pts, "center_el": cz}]
        self._write(secs, [(x, y, (x - cx) / uh, to_el(y)) for x, y in verts], cfg)


def main():
    Window().mainloop()
