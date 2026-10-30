"""횡단면 찾기 — 도면에 늘어선 하천 횡단면을 한 단면 견본으로 모두 찾는다.

견본(spec): 사용자가 단면 하나에서 고른 것
  ground_layer   지반선 레이어
  center_layer   단면 중심선 레이어, center_len 길이(같은 길이의 세로선만 중심선으로 본다)
  sta_off        중심선 아래 끝 → 측점 문자 위치(dx, dy)
  el_off         중심선 아래 끝 → 지반고 문자 위치(dx, dy) — 중심에서 지반 EL을 알려 주는 문자
  tol            문자를 찾는 반경(도면 단위)
  sta_layer, el_layer  견본 문자 레이어 — 있으면 같은 세로줄·같은 레이어에서 가장 가까운 문자를 쓴다

단면(section): center(x, y0, y1), station(문자), dist(누가거리 m), ground(핸들), y_g(중심 X에서 지반선 Y — 보간),
  el_g(지반고 문자 숫자). 높이 Y ↔ EL 변환: y = y_ref + (EL − el_g) × uv, uv = 1m당 세로 도면 단위(눈금 기울기, 없으면 1000 / V).
  axis: 단면 왼쪽 세로 눈금 숫자(EL)로 맞춘 (a, b) — y ≈ a + b × EL. 있으면 기울기 b(1m당 도면 단위)를 V축척 대신 쓴다
  (설계 프로그램이 그린 횡단면도는 단면마다 세로 축척이 다르기도 하다: 실제 하천 도면 1/200·1/500·1/1000 혼재).
  y_ref: 지반고 문자 EL이 가리키는 높이. 보통 y_g이지만, 도면 단면 대부분에서 지반선이 중심바 한가운데를 지나면
  중심바 가운데로 둔다 — 지반선을 나중에 고쳐 중심바와 어긋난 단면에서도 지반고 문자·기존 표기와 맞게.
  그런 단면은 bar_off(지반선 − 중심바 가운데, 도면 단위)로 알 수 있다.
  haxis: 단면 아래 거리 눈금(0을 가운데로 양쪽 10·20…)으로 맞춘 (x0, b) — 1m가 가로 도면 b단위. 가로 축척도 단면마다
  다르다(실제 하천 도면 1/200·1/2000 혼재). 있으면 H축척 대신 쓴다(uh). 글자 높이는 단면과 상관없이 설정 H축척으로 둔다. 높이 기준은 여전히 지반고 문자이고,
  눈금 숫자는 글자 자리라 눈금선과 반 글자 어긋나므로 a는 지반고 문자가 없을 때만 쓴다.
기준: 위치는 문자 삽입점이 아니라 중심선 X, 지반 높이는 지반선 선형 보간.
"""

import json
import math
import re

from . import coords as C
from . import settings as S

SPEC_KEY = "XSEC"


def save_spec(spec: dict):
    S.save(SPEC_KEY, {"json": json.dumps(spec, ensure_ascii=False)})


def load_spec():
    v = S.load(SPEC_KEY, {"json": ""})["json"]
    return json.loads(v) if v else None


SAMPLE_BODY = (
    '(setq _g (entsel "\\n견본 단면의 지반선 선택: "))'
    ' (setq _c (if _g (entsel "\\n견본 단면의 중심선(세로선) 선택: ")))'
    ' (setq _s (if _c (entsel "\\n견본 단면의 측점 문자 선택: ")))'
    ' (setq _e (if _s (entsel "\\n견본 단면의 지반고(중심 EL) 문자 선택: ")))'
    ' (if _e (progn'
    '  (setq _ce (entget (car _c)) _vv (bc:verts (car _c)) _p0 (car _vv) _p1 (last _vv))'
    '  (if (> (cadr _p0) (cadr _p1)) (setq _t _p0 _p0 _p1 _p1 _t))'
    '  (write-line (strcat "G" _d (cdr (assoc 8 (entget (car _g))))) _fp)'
    '  (write-line (strcat "C" _d (cdr (assoc 8 _ce)) _d (bc:rtos (car _p0) 2 8) _d (bc:rtos (cadr _p0) 2 8) _d (bc:rtos (cadr _p1) 2 8)) _fp)'
    '  (setq _sp (car (bc:ent-points (car _s) T)) _ep (car (bc:ent-points (car _e) T)))'
    '  (write-line (strcat "S" _d (bc:rtos (car _sp) 2 8) _d (bc:rtos (cadr _sp) 2 8) _d (bc:text-of (car _s)) _d (cdr (assoc 8 (entget (car _s))))) _fp)'
    '  (write-line (strcat "E" _d (bc:rtos (car _ep) 2 8) _d (bc:rtos (cadr _ep) 2 8) _d (bc:text-of (car _e)) _d (cdr (assoc 8 (entget (car _e))))) _fp)'
    '  (write-line (strcat "H" _d (bc:rtos (cdr (assoc 40 (entget (car _s)))) 2 6)) _fp)))'
)


def sample_body_from_handles(hs) -> str:
    """견본 등록을 사람이 찍지 않고 핸들 4개(지반선·중심선·측점 문자·지반고 문자)로 — MCP용. 결과 줄은 SAMPLE_BODY와 같다."""
    from validators import lisp_str
    g, c, s, e = (lisp_str(str(h)) for h in hs)
    head = ('(setq _g (list (handent "%s")) _c (list (handent "%s")) _s (list (handent "%s")) _e (list (handent "%s")))'
            % (g, c, s, e))
    return head + SAMPLE_BODY[SAMPLE_BODY.index(" (if _e (progn"):]


def section_report(secs) -> list:
    """단면 인식 결과를 AI가 확인할 수 있는 표로(그리기 전에 보는 용도)."""
    seen, out = {}, []
    for s in secs:
        key = round(s["dist"], 4) if s["dist"] is not None else None
        out.append({"station": s["station"], "dist": s["dist"], "el_g": s["el_g"], "usable": usable(s),
                    "v_scale": round(1000.0 / s["axis"][1]) if s.get("axis") else None,
                    "h_scale": round(1000.0 / s["haxis"][1]) if s.get("haxis") else None,
                    "center_x": round(s["center"][0], 4), "center_y": round(s["center"][1], 4),
                    "duplicate": key is not None and key in seen})
        if key is not None:
            seen[key] = True
    return out


def spec_from_rows(rows):
    d = {}
    for r in rows:
        c = r.split("\t")
        d[c[0]] = c[1:]
    if not all(k in d for k in "GCSE"):
        return None
    cx, y0, y1 = float(d["C"][1]), float(d["C"][2]), float(d["C"][3])
    h = float(d.get("H", ["2.5"])[0] or 2.5)
    return {"ground_layer": d["G"][0], "center_layer": d["C"][0], "center_len": y1 - y0,
            "sta_off": [float(d["S"][0]) - cx, float(d["S"][1]) - y0],
            "el_off": [float(d["E"][0]) - cx, float(d["E"][1]) - y0],
            "tol": max(h * 4.0, 2.0), "sample_station": d["S"][2], "sample_el": d["E"][2],
            "sta_layer": d["S"][3] if len(d["S"]) > 3 else "", "el_layer": d["E"][3] if len(d["E"]) > 3 else ""}


def dump_body(spec) -> str:
    """중심선 레이어의 LINE, 지반선 레이어의 폴리선 정점, 모든 문자 위치·내용."""
    from validators import lisp_str, wild_escape
    cl = lisp_str(wild_escape(spec["center_layer"]))
    gl = lisp_str(wild_escape(spec["ground_layer"]))
    return ('(bc:dump-ss (ssget "_X" (list (cons 0 "LINE,LWPOLYLINE") (cons 8 "%s") (cons 410 "Model"))) nil _fp)'
            ' (bc:dump-ss (ssget "_X" (list (cons 0 "LWPOLYLINE,POLYLINE,LINE") (cons 8 "%s") (cons 410 "Model"))) nil _fp)'
            ' (bc:dump-ss (ssget "_X" (list (cons 0 "TEXT,MTEXT") (cons 410 "Model"))) T _fp)' % (cl, gl))


def _num(s):
    """문자의 맨 뒤 숫자(LISP bc:num-in-text와 같은 규칙, (−) 부호)."""
    m = list(re.finditer(r"(\(-\)|-)?(\d+(?:\.\d+)?)", (s or "").replace(",", "")))
    if not m:
        return None
    return float(m[-1].group(2)) * (-1.0 if m[-1].group(1) else 1.0)


def _ground_y(pts, x):
    """폴리선 점들(X 정렬)에서 x의 Y(선형 보간). 범위 밖이면 None."""
    for (x0, y0, _z0), (x1, y1, _z1) in zip(pts, pts[1:]):
        if min(x0, x1) - 1e-9 <= x <= max(x0, x1) + 1e-9 and abs(x1 - x0) > 1e-12:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return None


_PURE = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*$")


def _axis(nums, gpts):
    """단면 왼쪽 세로 눈금 숫자 → (a, b): y = a + b·EL. 지반선 높이에 가장 가까운 눈금이 든, 간격이 고른 한 줄만 쓴다."""
    if not gpts:
        return None
    xmin, xmax = gpts[0][0], gpts[-1][0]
    ys = [p[1] for p in gpts]
    W, ymin, ymax = xmax - xmin, min(ys), max(ys)
    # 낮은 단면(보·낙차공)은 지반선 높이 폭이 좁아 눈금이 몇 개 안 걸리므로 폭의 절반만큼은 위아래로 더 본다
    H = max(ymax - ymin, 0.5 * W, 1.0)
    cols = {}
    for (x, y), v in nums:
        if xmin - 1.5 * W <= x <= xmin + 1e-6 and ymin - H <= y <= ymax + H:
            cols.setdefault(round(x, 2), []).append((y, v))
    best = None
    for x, col in cols.items():
        col.sort()
        # 고른 간격의 연속 구간으로 나눈다(다른 단면 눈금이 섞이면 끊긴다)
        runs, cur = [], [col[0]]
        for q in col[1:]:
            if len(cur) >= 2:
                b0 = (cur[-1][0] - cur[-2][0]) / (cur[-1][1] - cur[-2][1]) if cur[-1][1] != cur[-2][1] else None
                b1 = (q[0] - cur[-1][0]) / (q[1] - cur[-1][1]) if q[1] != cur[-1][1] else None
                if b0 is None or b1 is None or abs(b1 - b0) > 1e-6 * abs(b0):
                    runs.append(cur)
                    cur = [cur[-1]]
            cur.append(q)
        runs.append(cur)
        for r in runs:
            if len(r) < 3 or r[-1][1] == r[0][1]:
                continue
            b = (r[-1][0] - r[0][0]) / (r[-1][1] - r[0][1])
            if b <= 0:
                continue
            if not r[0][0] - b <= (ymin + ymax) / 2 <= r[-1][0] + b * 10:
                continue
            key = (xmin - x, -len(r))
            if best is None or key < best[0]:
                best = (key, (r[0][0] - b * r[0][1], b))
    return best[1] if best else None


def _haxis(nums, gpts):
    """단면 아래 거리 눈금 → (x0, b). '0'이 있고 양쪽 숫자가 0에서의 거리에 비례(같은 b)하는 가로 한 줄."""
    if not gpts:
        return None
    xmin, xmax = gpts[0][0], gpts[-1][0]
    ymin = min(p[1] for p in gpts)
    W = xmax - xmin
    rows = {}
    for (x, y), v in nums:
        if xmin - 0.2 * W <= x <= xmax + 0.2 * W and ymin - 0.5 * W <= y < ymin:
            rows.setdefault(round(y, 2), []).append((x, v))
    best = None
    for y, row in rows.items():
        zeros = [x for x, v in row if v == 0]
        others = [(x, v) for x, v in row if v > 0]
        if len(zeros) != 1 or len(others) < 2:
            continue
        x0 = zeros[0]
        bs = [abs(x - x0) / v for x, v in others]
        b = bs[0]
        if b <= 0 or any(abs(bb - b) > 1e-6 * b for bb in bs):
            continue
        key = (ymin - y, -len(row))
        if best is None or key < best[0]:
            best = (key, (x0, b))
    return best[1] if best else None


def find(spec, ents, sta_mode="Station", interval=20.0):
    """덤프 객체(parse_dump) → 단면 목록(측점 거리순)."""
    L = spec["center_len"]
    centers, grounds, texts = [], [], []
    for e in ents:
        # 중심선: 같은 레이어의 세로 LINE 또는 꼭짓점 2개짜리 폴리선(횡단면도의 '중심바')
        if e["type"] in ("LINE", "LWPOLYLINE") and e["layer"] == spec["center_layer"] and len(e["points"]) == 2:
            (x0, y0, _), (x1, y1, _) = e["points"]
            if abs(x1 - x0) < 1e-6 and abs(abs(y1 - y0) - L) <= max(1e-6, L * 0.01):
                centers.append((x0, min(y0, y1), max(y0, y1), e["handle"]))
        if e["layer"] == spec["ground_layer"] and e["type"] in ("LWPOLYLINE", "POLYLINE", "LINE"):
            grounds.append((e["handle"], sorted(e["points"], key=lambda p: p[0])))
        if e["type"] in ("TEXT", "MTEXT") and e["points"]:
            texts.append((e["points"][0], e["text"], e["layer"]))
    nums = [((p[0], p[1]), float(t)) for (p, t, _ly) in texts if _PURE.match(t or "")]

    def near(x, y, layer):
        # 견본 문자와 같은 레이어의 문자만(다른 문자가 가까이 있어도 잡지 않게). 레이어를 모르면 모두.
        best, bd = None, spec["tol"]
        for (p, t, ly) in texts:
            if layer and ly != layer:
                continue
            d = math.hypot(p[0] - x, p[1] - y)
            if d <= bd:
                best, bd = t, d
        return best

    def below(x, y0, off, layer, xr):
        # 중심선은 지반 높이에 놓이고 측점 문자는 단면 틀 가운데에 놓여, 단면마다 문자까지의 거리가 다르다(실제 하천 도면 횡단면도 실측).
        # 레이어를 알면: 그 단면 지반선의 X 범위(없으면 견본 dx ± tol) 안에서 견본과 같은 쪽(위/아래)의 가장 가까운 문자.
        best, bd = None, None
        up = off[1] > 0
        lo, hi = xr if xr else (x + off[0] - spec["tol"], x + off[0] + spec["tol"])
        for (p, t, ly) in texts:
            if ly != layer or not lo <= p[0] <= hi:
                continue
            dy = p[1] - y0
            if (dy > 0) != up:
                continue
            if bd is None or abs(dy) < bd:
                best, bd = t, abs(dy)
        return best

    def pick(x, y0, off, layer, xr):
        return below(x, y0, off, layer, xr) if layer else near(x + off[0], y0 + off[1], "")

    out = []
    for cx, y0, y1, h in centers:
        gy, gh, gpts = None, None, None
        for gh_, pts in grounds:
            y = _ground_y(pts, cx)
            if y is not None and y0 - 1e-6 <= y <= y1 + 1e-6:
                gy, gh, gpts = y, gh_, pts
                break
        if gpts is None:
            # 보·낙차공 단면은 중심바가 마루 위에 서 있어 지반선이 바를 지나지 않기도 한다 —
            # 바 X를 덮는 지반선 중 높이 범위가 바에서 가장 가까운 것(바 길이 5배 안). y_g는 None 그대로.
            m, cand = (y0 + y1) / 2, None
            for gh_, pts in grounds:
                if _ground_y(pts, cx) is None:
                    continue
                ys = [p[1] for p in pts]
                d = max(min(ys) - m, m - max(ys), 0.0)
                if d <= 5 * (y1 - y0) and (cand is None or d < cand[0]):
                    cand = (d, gh_, pts)
            if cand:
                gh, gpts = cand[1], cand[2]
        xr = (gpts[0][0], gpts[-1][0]) if gpts else None
        st = pick(cx, y0, spec["sta_off"], spec.get("sta_layer", ""), xr)
        et = pick(cx, y0, spec["el_off"], spec.get("el_layer", ""), xr)
        dist = C.station_to_dist(st, sta_mode, interval) if st else None
        out.append({"center": [cx, y0, y1], "center_handle": h, "station": st, "dist": dist,
                    "el_text": et, "el_g": _num(et), "ground": gh, "y_g": gy,
                    "ground_pts": [[p[0], p[1]] for p in (gpts or [])], "axis": _axis(nums, gpts),
                    "haxis": _haxis(nums, gpts)})
    on = [s for s in out if s["y_g"] is not None]
    mid = bool(on) and sum(1 for s in on if abs(s["y_g"] - (s["center"][1] + s["center"][2]) / 2) < 1e-3) > len(on) / 2
    for s in out:
        m = (s["center"][1] + s["center"][2]) / 2
        s["y_ref"] = m if (mid and s["ground_pts"]) else s["y_g"]
        s["bar_off"] = ((s["y_g"] - m) if s["y_g"] is not None else None) if mid else 0.0
    out.sort(key=lambda s: (s["dist"] is None, s["dist"] or 0.0, s["center"][0]))
    return out


def uh(sec, hscale):
    """1m가 도면 몇 단위인지(가로). 거리 눈금을 찾은 단면은 그 단면의 축척."""
    ax = sec.get("haxis")
    return ax[1] if ax else 1000.0 / hscale


def uv(sec, vscale):
    """1m가 도면 몇 단위인지(세로). 눈금을 찾은 단면은 그 단면의 축척."""
    ax = sec.get("axis")
    return ax[1] if ax else 1000.0 / vscale


def y_of(sec, el, vscale):
    ax = sec.get("axis")
    if sec["el_g"] is None:
        return ax[0] + ax[1] * el  # 눈금 숫자만으로(반 글자 어긋날 수 있다)
    return sec.get("y_ref", sec["y_g"]) + (el - sec["el_g"]) * uv(sec, vscale)


def el_of(sec, y, vscale):
    ax = sec.get("axis")
    if sec["el_g"] is None:
        return (y - ax[0]) / ax[1]
    return sec["el_g"] + (y - sec.get("y_ref", sec["y_g"])) / uv(sec, vscale)


def usable(sec):
    return sec.get("y_ref", sec["y_g"]) is not None and (sec["el_g"] is not None or bool(sec.get("axis")))
