# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""지형 공통: Z 점 모으기, 삼각망 바깥 다듬기, 등고선 추출, 외곽선, 선 단순화. 표준 라이브러리만 쓴다.

삼각망은 skills.windows.dtin.triangulate(들로네)를 쓴다.
"""

import heapq
import math
import re

_NUM = re.compile(r"(\(-\)|-)?(\d+(?:\.\d+)?)")
TYPE_KEYS = (("대상점", "POINT"), ("대상블록", "INSERT"), ("대상선", "LINE,LWPOLYLINE,POLYLINE"), ("대상문자", "TEXT,MTEXT"))


def types_for(cfg) -> str:
    return ",".join(t for k, t in TYPE_KEYS if cfg.get(k))


def z_points(ents, cfg):
    """덤프 → [(x, y, z)]. 문자는 맨 뒤 숫자를 Z로. 'Z0제외'면 Z ≤ 0 제외."""
    pts = []
    for e in ents:
        if e["type"] in ("TEXT", "MTEXT"):
            if not cfg.get("대상문자"):
                continue
            m = list(_NUM.finditer(e["text"].replace(",", "")))
            if not m:
                continue
            z = float(m[-1].group(2)) * (-1.0 if m[-1].group(1) else 1.0)
            pts += [(p[0], p[1], z) for p in e["points"]]
        else:
            pts += e["points"]
    if cfg.get("Z0제외"):
        pts = [p for p in pts if p[2] > 0]
    return pts


def _len(P, a, b):
    return math.hypot(P[a][0] - P[b][0], P[a][1] - P[b][1])


def median_edge(P, tris):
    ls = sorted(_len(P, t[i], t[(i + 1) % 3]) for t in tris for i in range(3))
    return ls[len(ls) // 2] if ls else 0.0


def peel(P, tris, slack):
    """바깥 다듬기(오목 외곽): 바깥 변이 '중간 변 길이 × slack'보다 길면 그 삼각형을 걷어낸다.
    걷어낼 삼각형의 맞은편 꼭짓점이 이미 바깥에 있으면(목이 끊어짐) 걷지 않는다. 긴 변부터."""
    if not tris or not slack or slack <= 0:
        return list(tris)
    thr = median_edge(P, tris) * float(slack)
    alive = set(range(len(tris)))
    owner = {}
    for i, t in enumerate(tris):
        for j in range(3):
            owner.setdefault(tuple(sorted((t[j], t[(j + 1) % 3]))), []).append(i)

    def boundary(e):
        return len([i for i in owner[e] if i in alive]) == 1

    on_bnd = {}
    heap = []
    for e, ow in owner.items():
        if len(ow) == 1:
            for v in e:
                on_bnd[v] = on_bnd.get(v, 0) + 1
            heapq.heappush(heap, (-_len(P, *e), e))
    while heap:
        neg, e = heapq.heappop(heap)
        if -neg <= thr:
            break
        if not boundary(e):
            continue
        ti = [i for i in owner[e] if i in alive][0]
        t = tris[ti]
        c = [v for v in t if v not in e][0]
        if on_bnd.get(c, 0) > 0:
            continue
        alive.discard(ti)
        for v in e:
            on_bnd[v] -= 1
        for f in (tuple(sorted((e[0], c))), tuple(sorted((e[1], c)))):
            if boundary(f):
                for v in f:
                    on_bnd[v] = on_bnd.get(v, 0) + 1
                heapq.heappush(heap, (-_len(P, *f), f))
    return [tris[i] for i in sorted(alive)]


def boundary_loops(P, tris):
    """삼각망 바깥 변을 이어 닫힌 고리 목록 [[(x, y)…]]. 큰 고리부터."""
    cnt = {}
    for t in tris:
        for j in range(3):
            e = (t[j], t[(j + 1) % 3])
            cnt[tuple(sorted(e))] = cnt.get(tuple(sorted(e)), 0) + 1
    nxt = {}
    for t in tris:  # 반시계 삼각형의 바깥 변은 방향 그대로 이으면 바깥 고리가 반시계로 돈다
        for j in range(3):
            a, b = t[j], t[(j + 1) % 3]
            if cnt[tuple(sorted((a, b)))] == 1:
                nxt.setdefault(a, []).append(b)
    loops = []
    while any(nxt.values()):
        start = next(a for a, bs in nxt.items() if bs)
        loop, a = [start], start
        while True:
            b = nxt[a].pop()
            if b == start:
                break
            loop.append(b)
            a = b
            if not nxt.get(a):
                break
        loops.append([(P[i][0], P[i][1]) for i in loop])

    def area(lp):
        return abs(sum(lp[i][0] * lp[i - 1][1] - lp[i - 1][0] * lp[i][1] for i in range(len(lp)))) / 2
    return sorted(loops, key=area, reverse=True)


def levels(zmin, zmax, interval, only=None):
    """등고선 높이 목록. only가 있으면 그 높이만(범위 안)."""
    if only:
        return sorted(v for v in only if zmin <= v <= zmax)
    if interval <= 0:
        return []
    k0, k1 = math.ceil(zmin / interval - 1e-9), math.floor(zmax / interval + 1e-9)
    return [round(k * interval, 6) for k in range(k0, k1 + 1)]


def contours(P, tris, lv):
    """높이 lv 등고선 → [(점 목록 [(x, y)…], 닫힘)]. 꼭짓점 높이가 lv와 같으면 아주 조금 올려 본다."""
    eps = 1e-9

    def z(i):
        v = P[i][2]
        return v + eps if v == lv else v

    def cut(a, b):
        za, zb = z(a), z(b)
        t = (lv - za) / (zb - za)
        return (P[a][0] + t * (P[b][0] - P[a][0]), P[a][1] + t * (P[b][1] - P[a][1]))

    seg_of, segs = {}, []
    for t in tris:
        es = []
        for j in range(3):
            a, b = t[j], t[(j + 1) % 3]
            if (z(a) - lv) * (z(b) - lv) < 0:
                es.append(tuple(sorted((a, b))))
        if len(es) == 2:
            k = len(segs)
            segs.append(es)
            for e in es:
                seg_of.setdefault(e, []).append(k)
    used = [False] * len(segs)
    out = []
    for k in range(len(segs)):
        if used[k]:
            continue
        used[k] = True
        chain = list(segs[k])
        for end in (1, 0):  # 뒤로 늘리고, 앞으로 늘린다
            while True:
                e = chain[-1] if end else chain[0]
                nk = [s for s in seg_of[e] if not used[s]]
                if not nk:
                    break
                used[nk[0]] = True
                o = [x for x in segs[nk[0]] if x != e][0]
                chain.append(o) if end else chain.insert(0, o)
        closed = len(chain) > 2 and chain[0] == chain[-1]
        if closed:
            chain.pop()
        out.append(([cut(*e) for e in chain], closed))
    return out


def simplify(pts, tol, closed=False):
    """더글러스-포커 단순화(tol 도면 단위, 0이면 그대로)."""
    if tol <= 0 or len(pts) < 3:
        return pts
    if closed:
        half = len(pts) // 2
        a = simplify(pts[:half + 1], tol)
        b = simplify(pts[half:] + [pts[0]], tol)
        return a[:-1] + b[:-1]

    def rec(i, j, keep):
        (x1, y1), (x2, y2) = pts[i], pts[j]
        L = math.hypot(x2 - x1, y2 - y1) or 1e-12
        best, bi = -1.0, -1
        for k in range(i + 1, j):
            d = abs((x2 - x1) * (y1 - pts[k][1]) - (x1 - pts[k][0]) * (y2 - y1)) / L
            if d > best:
                best, bi = d, k
        if best > tol:
            keep[bi] = True
            rec(i, bi, keep)
            rec(bi, j, keep)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    rec(0, len(pts) - 1, keep)
    return [p for p, k in zip(pts, keep) if k]


def lwpoly_lisp(pts, closed, layer, elev=0.0, color=None) -> str:
    """LWPOLYLINE(고도 elev) entmake 식. layer는 이미 이스케이프된 이름."""
    vs = " ".join("(list 10 %.6f %.6f)" % (x, y) for x, y in pts)
    col = " (cons 62 %d)" % color if color is not None else ""
    return ('(entmake (list (quote (0 . "LWPOLYLINE")) (quote (100 . "AcDbEntity")) (cons 8 "%s")%s'
            ' (quote (100 . "AcDbPolyline")) (cons 90 %d) (cons 70 %d) (cons 38 %.6f) %s))'
            % (layer, col, len(pts), 1 if closed else 0, elev, vs))
