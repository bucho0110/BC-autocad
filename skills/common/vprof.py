# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""종단 공통(DRP·DCS·DLS·GSE): 종단 선형(VIP·종곡선) 계산과 종단면도(선·표·축척 막대) 작도.

VIP는 (누가거리, EL, 종곡선 길이) — 종곡선은 VIP 앞뒤 L/2씩 대칭 2차 포물선이다.
경사 g는 비율(0.02 = 2%), 변화 비율 K = L / |g2 − g1|(%) 이다.
"""

import math

from skills.common import coords as C
from skills.common import terrain as T
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)


def grades(vips):
    return [(vips[i + 1][1] - vips[i][1]) / (vips[i + 1][0] - vips[i][0]) for i in range(len(vips) - 1)]


def check_vips(vips):
    """VIP 순서·곡선 겹침 확인 → 문제 문장 목록."""
    bad = []
    for i in range(len(vips) - 1):
        if vips[i + 1][0] <= vips[i][0]:
            bad.append("VIP 누가거리가 커지지 않습니다: %s → %s" % (C.fmt(vips[i][0], 3), C.fmt(vips[i + 1][0], 3)))
    for i in range(1, len(vips) - 1):
        a = vips[i][0] - vips[i][2] / 2.0
        if a < vips[i - 1][0] + (vips[i - 1][2] / 2.0 if i - 1 > 0 else 0) - 1e-9:
            bad.append("종곡선이 앞 곡선과 겹칩니다: VIP %s (L=%s)" % (C.fmt(vips[i][0], 3), C.fmt(vips[i][2], 3)))
    return bad


def el_at(vips, d):
    """종단 계획고(종곡선 포함). 범위 밖이면 None."""
    if not vips or d < vips[0][0] - 1e-9 or d > vips[-1][0] + 1e-9:
        return None
    g = grades(vips)
    for i in range(1, len(vips) - 1):
        L = vips[i][2]
        if L > 0 and abs(d - vips[i][0]) <= L / 2.0 + 1e-12:
            b = vips[i][0] - L / 2.0
            zb = vips[i][1] - g[i - 1] * L / 2.0
            x = d - b
            return zb + g[i - 1] * x + (g[i] - g[i - 1]) / (2.0 * L) * x * x
    for i in range(len(vips) - 1):
        if d <= vips[i + 1][0] + 1e-12:
            return vips[i][1] + g[i] * (d - vips[i][0])
    return vips[-1][1]


def k_value(vips, i):
    g = grades(vips)
    a = abs(g[i] - g[i - 1]) * 100.0
    return vips[i][2] / a if a > 1e-12 else None


def plan_points(vips, step):
    """계획선 정점: VIP 사이 직선 + 종곡선 구간은 step 간격."""
    pts = [(vips[0][0], vips[0][1])]
    for i in range(1, len(vips)):
        L = vips[i][2] if i < len(vips) - 1 else 0.0
        if L > 0:
            b, e = vips[i][0] - L / 2.0, vips[i][0] + L / 2.0
            n = max(2, int(math.ceil(L / max(step, 1e-6))))
            for k in range(n + 1):
                d = b + L * k / n
                pts.append((d, el_at(vips, d)))
        else:
            pts.append((vips[i][0], vips[i][1]))
    out = []
    for p in pts:
        if not out or p[0] - out[-1][0] > 1e-9:
            out.append(p)
    return out


def interp(pts, d):
    """꺾은선 [(거리, EL)] 위 거리 d의 EL(범위 밖·끊김이면 None)."""
    for (d0, z0), (d1, z1) in zip(pts, pts[1:]):
        if d0 - 1e-9 <= d <= d1 + 1e-9:
            return z0 if d1 - d0 < 1e-12 else z0 + (z1 - z0) * (d - d0) / (d1 - d0)
    return None


def seg_interp(segs, d):
    """끊긴 선(구간 목록) 위 거리 d의 EL — 끊긴 곳(x 칸)이나 범위 밖은 None."""
    for seg in segs:
        z = interp(seg, d)
        if z is not None:
            return z
    return None


def vip_table(vips, start=0.0, mode="Station", chain=20.0):
    """[VIP 측점, 누가거리, EL, 종곡선 L, 앞 경사(%), 뒤 경사(%), K]."""
    g = grades(vips)
    out = []
    for i, (d, z, L) in enumerate(vips):
        k = k_value(vips, i) if 0 < i < len(vips) - 1 else None
        out.append([C.sta_str(start + d, mode, chain, 3), C.fmt(start + d, 3), C.fmt(z, 3), C.fmt(L, 3),
                    C.fmt(g[i - 1] * 100, 3) if i > 0 else "", C.fmt(g[i] * 100, 3) if i < len(g) else "",
                    C.fmt(k, 3) if k is not None else ""])
    return out


# ---------------------------------------------------------------- 종단면도 작도

PROFILE_FIELDS = [
    ("측점구분", "측점 표기 구분", "choice", "Station", ["Station", "Number"]),
    ("체인", "Number 측점 한 체인 길이 (m)", "real", 20.0, None),
    ("시작거리", "시작 누가거리 (숫자 또는 0+000, 표의 측점에 더함)", "str", "0", None),
    ("H축척", "종단 H 축척 (1000 = 1m가 도면 1)", "real", 1000.0, None),
    ("V축척", "종단 V 축척", "real", 200.0, None),
    ("계산간격", "종곡선 계산 간격 (m)", "real", 5.0, None),
    ("칸높이", "표 한 칸 높이 (도면 단위)", "real", 15.0, None),
    ("제목폭", "표 제목 칸 폭 (도면 단위)", "real", 40.0, None),
    ("문자높이", "표 내용 문자 높이", "real", 2.5, None),
    ("제목높이", "표 제목 문자 높이", "real", 3.0, None),
    ("소수", "표 EL·높이 소수 자리", "int", 2, None),
    ("측점소수", "+측점 소수 자리 (정수 측점은 소수 없이)", "int", 3, None),
    ("최하단지정", "종단 최하단(기준선) 높이 직접 지정", "bool", False, None),
    ("최하단높이", "최하단 높이 (m)", "real", 0.0, None),
    ("축척막대", "왼쪽에 EL 축척 막대 그리기", "bool", True, None),
    ("막대간격", "축척 막대 EL 간격 (m)", "real", 1.0, None),
    ("경사표기", "계획선 경사 문자 쓰기", "bool", True, None),
    ("K표기", "종곡선 L·K 값 쓰기", "bool", True, None),
    ("IP선", "계획선 IP 선 함께 그리기", "bool", False, None),
    ("절성고", "지반·계획이 모두 있으면 절토고·성토고 줄 추가", "bool", True, None),
    ("선레이어", "지반선 레이어", "str", "종단_지반선", None),
    ("계획레이어", "계획선 레이어", "str", "종단_계획선", None),
    ("표레이어", "표·세로선 레이어", "str", "종단_표", None),
    ("문자레이어", "문자 레이어", "str", "종단_문자", None),
]


def sta_label(d, cfg):
    dec = 0 if abs(d - round(d)) < 1e-9 else int(cfg["측점소수"])
    num = cfg["측점구분"] == "Number"
    return C.sta_str(d, cfg["측점구분"], float(cfg["체인"]), dec, prefix="No." if num else "")


def start_of(cfg):
    return C.station_to_dist(str(cfg["시작거리"] or "0"), cfg["측점구분"], float(cfg["체인"])) or 0.0


def plan_lisp(vips, cfg, X, Y, start, lp, lx, h):
    """계획선(종곡선 포함)·IP선·경사 문자·VIP 문자. X(d)·Y(z)는 도면 좌표 함수, lp·lx는 이스케이프한 레이어."""
    uh, uv = 1000.0 / cfg["H축척"], 1000.0 / cfg["V축척"]
    out = [T.lwpoly_lisp([(X(d), Y(z)) for d, z in plan_points(vips, float(cfg["계산간격"]))], False, lp)]

    def text(x, y, s, just, rot=0.0):
        out.append('(bc:text (list %.6f %.6f 0.0) "%s" %.6f "%s" "%s" %.10f)' % (x, y, ls(s), h, lx, just, rot))
    if cfg["IP선"]:
        out.append(T.lwpoly_lisp([(X(d), Y(z)) for d, z, _L in vips], False, lp))
    g = grades(vips)
    for i in range(len(vips) - 1):
        a, b = vips[i], vips[i + 1]
        if cfg["경사표기"]:
            dm = (a[0] + b[0]) / 2.0
            ang = math.atan2((b[1] - a[1]) * uv, (b[0] - a[0]) * uh)
            text(X(dm), Y(el_at(vips, dm)) + h, "S=%s%%" % C.fmt(g[i] * 100, 3), "BC", ang)
    for i in range(1, len(vips) - 1):
        d, z, L = vips[i]
        out.append('(bc:line (list %.6f %.6f 0.0) (list %.6f %.6f 0.0) "%s")' % (X(d), Y(z), X(d), Y(z) + 6 * h, lp))
        s = "VIP %s EL=%s" % (sta_label(start + d, cfg), C.fmt(z, 3))
        if cfg["K표기"] and L > 0:
            k = k_value(vips, i)
            s += " L=%s K=%s" % (C.fmt(L, 3), C.fmt(k, 1) if k else "-")
        text(X(d) - 0.5 * h, Y(z) + 6.5 * h, s, "BL", math.pi / 2)
    return "".join(out)


def build_profile(series, vips, marks, cfg, origin):
    """종단면도 LISP.
    series: [{"name", "pts": [(d, z) 또는 None(끊김)], "plan": bool}] — d는 시작거리 기준 0부터.
    vips: 계획 VIP [(d, z, L)] 또는 [] — 있으면 계획선을 종곡선으로 계산해 그린다.
    marks: 표에 쓸 세로선 거리 목록(정렬). origin = 기준선 왼쪽 끝(첫 거리, 최하단 높이).
    → (LISP, 표 행 [[측점, 누가거리, 값…]], 머리 [..])."""
    uh, uv = 1000.0 / cfg["H축척"], 1000.0 / cfg["V축척"]
    start = start_of(cfg)
    dec = int(cfg["소수"])
    lines = []
    for s in series:
        segs, cur = [], []
        for p in s["pts"]:
            if p is None:
                if len(cur) > 1:
                    segs.append(cur)
                cur = []
            else:
                cur.append(p)
        if len(cur) > 1:
            segs.append(cur)
        lines.append((s, segs))
    plan_pts = plan_points(vips, float(cfg["계산간격"])) if len(vips) >= 2 else []
    allz = [z for _s, segs in lines for seg in segs for _d, z in seg] + [z for _d, z in plan_pts]
    if not allz:
        raise ValueError("그릴 EL 값이 없습니다.")
    d0 = min([seg[0][0] for _s, segs in lines for seg in segs] + ([plan_pts[0][0]] if plan_pts else []) + marks[:1])
    d1 = max([seg[-1][0] for _s, segs in lines for seg in segs] + ([plan_pts[-1][0]] if plan_pts else []) + marks[-1:])
    dl = float(cfg["최하단높이"]) if cfg["최하단지정"] else float(math.floor(min(allz)) - 1)
    ox, oy = float(origin[0]), float(origin[1])
    lg, lp, lt, lx = ls(cfg["선레이어"]), ls(cfg["계획레이어"]), ls(cfg["표레이어"]), ls(cfg["문자레이어"])
    rh, tw, h, th = float(cfg["칸높이"]), float(cfg["제목폭"]), float(cfg["문자높이"]), float(cfg["제목높이"])

    def X(d):
        return ox + (d - d0) * uh

    def Y(z):
        return oy + (z - dl) * uv

    def line(x1, y1, x2, y2, lay):
        return '(bc:line (list %.6f %.6f 0.0) (list %.6f %.6f 0.0) "%s")' % (x1, y1, x2, y2, lay)

    def text(x, y, s, hh, just, rot=0.0):
        return '(bc:text (list %.6f %.6f 0.0) "%s" %.6f "%s" "%s" %.10f)' % (x, y, ls(s), hh, lx, just, rot)

    out = ['(bc:ensure-layer "%s" 3) (bc:ensure-layer "%s" 1) (bc:ensure-layer "%s" 7) (bc:ensure-layer "%s" 7)'
           % (lg, lp, lt, lx)]
    ground = plan = None
    for s, segs in lines:
        lay = lp if s.get("plan") else (ls(s["layer"]) if s.get("layer") else lg)
        if s.get("layer"):
            out.append('(bc:ensure-layer "%s" %d)' % (ls(s["layer"]), int(s.get("color") or 7)))
        for seg in segs:
            out.append(T.lwpoly_lisp([(X(d), Y(z)) for d, z in seg], False, lay))
        if s.get("plan") and plan is None:
            plan = s
        elif not s.get("plan") and ground is None:
            ground = s
    if plan_pts:
        out.append(plan_lisp(vips, cfg, X, Y, start, lp, lx, h))
    # 표
    gseries = [s for s, segs in lines if not s.get("plan")]
    segs_of = {id(s): segs for s, segs in lines}
    head = ["측점", "누가거리"] + [s["name"] for s in gseries]
    pfun = None
    if plan_pts:
        head.append("계획고")
        pfun = lambda d: el_at(vips, d)  # noqa: E731
    elif plan is not None:
        head.append(plan["name"])
        pfun = lambda d: seg_interp(segs_of[id(plan)], d)  # noqa: E731
    gfun = (lambda d: seg_interp(segs_of[id(ground)], d)) if ground is not None else None  # noqa: E731
    cutfill = bool(cfg["절성고"] and gfun and pfun)
    if cutfill:
        head += ["절토고", "성토고"]
    rows = []
    for d in marks:
        r = [sta_label(start + d, cfg), C.fmt(start + d, 3)]
        for s in gseries:
            z = seg_interp(segs_of[id(s)], d)
            r.append("" if z is None else C.fmt(z, dec))
        pz = pfun(d) if pfun else None
        if pfun:
            r.append("" if pz is None else C.fmt(pz, dec))
        if cutfill:
            gz = gfun(d)
            diff = None if gz is None or pz is None else pz - gz
            r += ["" if diff is None or diff >= 0 else C.fmt(-diff, dec), "" if diff is None or diff <= 0 else C.fmt(diff, dec)]
        rows.append(r)
    nrow = len(head)
    end_x = X(d1)
    out.append(line(X(d0), oy, end_x, oy, lt))
    out.append(text(X(d0) - 0.5, oy + 0.5, "DL = %s" % C.fmt(dl, 2), h, "BR"))
    for i in range(nrow + 1):
        out.append(line(X(d0) - tw, oy - i * rh, end_x, oy - i * rh, lt))
    for x in (X(d0) - tw, X(d0), end_x):
        out.append(line(x, oy, x, oy - nrow * rh, lt))
    # 표 칸은 위부터 EL 값들 → 누가거리 → 측점(기준선에서 먼 쪽이 측점)
    order = list(range(nrow - 1, -1, -1))
    for k, idx in enumerate(order):
        out.append(text(X(d0) - tw / 2, oy - (k + 0.5) * rh, head[idx], th, "MC"))
    for d, r in zip(marks, rows):
        x = X(d)
        tops = [z for z in ([seg_interp(segs_of[id(s)], d) for s in gseries] + [pfun(d) if pfun else None])
                if z is not None]
        out.append(line(x, oy - nrow * rh, x, Y(max(tops)) if tops else oy, lt))
        for k, idx in enumerate(order):
            if r[idx] != "":
                out.append(text(x - 0.5 - h / 2, oy - (k + 0.5) * rh, r[idx], h, "MC", math.pi / 2))
    if cfg["축척막대"]:
        top = max(allz)
        step = max(float(cfg["막대간격"]), 1e-6)
        bx = X(d0) - tw - 2 * h
        out.append(line(bx, oy, bx, Y(math.ceil(top / step) * step), lt))
        z = math.ceil(dl / step) * step
        while z <= math.ceil(top / step) * step + 1e-9:
            out.append(line(bx - h, Y(z), bx, Y(z), lt))
            out.append(text(bx - 1.3 * h, Y(z), C.fmt(z, 0 if abs(step - round(step)) < 1e-9 else 1), h, "MR"))
            z += step
    return "".join(out), rows, head


def default_marks(ds, interval, start=0.0):
    """측점 간격 정체인 + 자료의 거리(+체인)."""
    if not ds:
        return []
    a, b = min(ds), max(ds)
    out = set(round(d, 6) for d in ds)
    if interval > 0:
        k = math.ceil((start + a) / interval - 1e-9)
        while k * interval - start <= b + 1e-9:
            out.add(round(k * interval - start, 6))
            k += 1
    return sorted(out)
