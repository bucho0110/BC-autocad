# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""지형 단면 공통(GRP 종단·CFM 횡단): 선형(직선·호)과 지형 선분(삼각망 3D면 변, 등고선, 3D 선)의 교점을 계산한다.

선형은 (p1, p2, bulge) 요소 목록이다(LINE·LWPOLYLINE·ARC). 호는 근사하지 않고 원으로 계산한다.
지형 선분은 (x1, y1, z1, x2, y2, z2). 교점의 Z는 선분 위 선형 보간이다.
"""

import math

# 선형 덤프: S<탭>x1<탭>y1<탭>x2<탭>y2<탭>bulge (WCS)
ALIGN_LISP = (
    '(setq _ed (entget _al) _ty (cdr (assoc 0 _ed)))'
    '(cond ((= _ty "LINE") (write-line (strcat "S" _d (bc:rtos (cadr (assoc 10 _ed)) 2 10) _d (bc:rtos (caddr (assoc 10 _ed)) 2 10)'
    '  _d (bc:rtos (cadr (assoc 11 _ed)) 2 10) _d (bc:rtos (caddr (assoc 11 _ed)) 2 10) _d "0") _fp))'
    ' ((= _ty "ARC") (setq _c (cdr (assoc 10 _ed)) _r (cdr (assoc 40 _ed)) _a0 (cdr (assoc 50 _ed)) _a1 (cdr (assoc 51 _ed)))'
    '  (if (< _a1 _a0) (setq _a1 (+ _a1 (* 2 pi))))'
    '  (setq _p (trans (polar _c _a0 _r) _al 0) _q (trans (polar _c _a1 _r) _al 0))'
    '  (write-line (strcat "S" _d (bc:rtos (car _p) 2 10) _d (bc:rtos (cadr _p) 2 10) _d (bc:rtos (car _q) 2 10) _d'
    '   (bc:rtos (cadr _q) 2 10) _d (bc:rtos (* (if (< (caddr (trans (list 0 0 1) _al 0 T)) 0) -1 1) (/ (sin (/ (- _a1 _a0) 4))'
    '   (cos (/ (- _a1 _a0) 4)))) 2 12)) _fp))'
    ' ((= _ty "LWPOLYLINE") (setq _v nil)'
    '  (foreach _g _ed (cond ((= (car _g) 10) (setq _v (cons (list (trans (list (cadr _g) (caddr _g) 0.0) _al 0) 0.0) _v)))'
    '                        ((and (= (car _g) 42) _v) (setq _v (cons (list (car (car _v)) (cdr _g)) (cdr _v))))))'
    '  (setq _v (reverse _v))'
    '  (if (= 1 (logand 1 (cdr (assoc 70 _ed)))) (setq _v (append _v (list (list (car (car _v)) 0.0)))))'
    '  (while (cdr _v) (setq _p (car (car _v)) _q (car (cadr _v)))'
    '   (write-line (strcat "S" _d (bc:rtos (car _p) 2 10) _d (bc:rtos (cadr _p) 2 10) _d (bc:rtos (car _q) 2 10) _d'
    '    (bc:rtos (cadr _q) 2 10) _d (bc:rtos (* (if (< (caddr (cdr (assoc 210 _ed))) 0) -1 1) (cadr (car _v))) 2 12)) _fp)'
    '   (setq _v (cdr _v)))))')

# 지형 덤프(선택 집합 _ss, 목록 _skip의 객체(선형·횡단선)는 뺀다): E<탭>x1<탭>y1<탭>z1<탭>x2<탭>y2<탭>z2
TERRAIN_LISP = (
    '(defun _gp-e (_a _b) (write-line (strcat "E" _d (bc:rtos (car _a) 2 10) _d (bc:rtos (cadr _a) 2 10) _d'
    ' (bc:rtos (caddr _a) 2 10) _d (bc:rtos (car _b) 2 10) _d (bc:rtos (cadr _b) 2 10) _d (bc:rtos (caddr _b) 2 10)) _fp))'
    '(if _ss (progn (setq _i 0) (while (< _i (sslength _ss)) (setq _en (ssname _ss _i) _ed (entget _en) _i (1+ _i))'
    ' (if (not (member _en _skip)) (cond'
    '  ((= (cdr (assoc 0 _ed)) "3DFACE") (setq _v (mapcar (quote (lambda (g) (cdr (assoc g _ed)))) (list 10 11 12 13)))'
    '   (if (equal (nth 2 _v) (nth 3 _v) 1e-9) (setq _v (list (nth 0 _v) (nth 1 _v) (nth 2 _v))))'
    '   (write-line (apply (quote strcat) (cons "T" (mapcar (quote (lambda (p) (strcat _d (bc:rtos (car p) 2 10) _d'
    '    (bc:rtos (cadr p) 2 10) _d (bc:rtos (caddr p) 2 10)))) _v))) _fp)'
    '   (setq _v (append _v (list (car _v)))) (while (cdr _v) (_gp-e (car _v) (cadr _v)) (setq _v (cdr _v))))'
    '  ((member (cdr (assoc 0 _ed)) (list "LINE" "LWPOLYLINE" "POLYLINE")) (setq _v (bc:verts _en))'
    '   (if (and (assoc 70 _ed) (= 1 (logand 1 (cdr (assoc 70 _ed))))) (setq _v (append _v (list (car _v)))))'
    '   (while (cdr _v) (_gp-e (car _v) (cadr _v)) (setq _v (cdr _v)))))))))')
TERRAIN_TYPES = "3DFACE,LINE,LWPOLYLINE,POLYLINE"


def parse_align(rows):
    return [((float(c[1]), float(c[2])), (float(c[3]), float(c[4])), float(c[5]))
            for c in (r.split("\t") for r in rows) if c[0] == "S" and len(c) == 6]


def parse_edges(rows, z0_exclude=True):
    """지형 선분(같은 변은 한 번). z0_exclude면 한 끝이라도 Z ≤ 0인 선분은 뺀다."""
    out, seen = [], set()
    for r in rows:
        c = r.split("\t")
        if c[0] != "E" or len(c) != 7:
            continue
        e = tuple(float(v) for v in c[1:])
        if z0_exclude and (e[2] <= 0 or e[5] <= 0):
            continue
        a, b = (round(e[0], 6), round(e[1], 6), round(e[2], 6)), (round(e[3], 6), round(e[4], 6), round(e[5], 6))
        k = (a, b) if a <= b else (b, a)
        if k in seen or (a[0] == b[0] and a[1] == b[1]):
            continue
        seen.add(k)
        out.append(e)
    return out


def parse_faces(rows, z0_exclude=True):
    """3D면 → 삼각형 [((x,y,z)×3)]. 사각 면은 두 삼각형."""
    out = []
    for r in rows:
        c = r.split("\t")
        if c[0] != "T" or len(c) not in (10, 13):
            continue
        v = [tuple(float(x) for x in c[i:i + 3]) for i in range(1, len(c), 3)]
        for t in ([v] if len(v) == 3 else [v[:3], [v[0], v[2], v[3]]]):
            if not (z0_exclude and min(p[2] for p in t) <= 0):
                out.append(t)
    return out


def face_z(faces, x, y):
    """점 (x, y)를 품은 3D면의 높이(평면 보간). 없으면 None."""
    for (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) in faces:
        d = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
        if abs(d) < 1e-15:
            continue
        a = ((y2 - y3) * (x - x3) + (x3 - x2) * (y - y3)) / d
        b = ((y3 - y1) * (x - x3) + (x1 - x3) * (y - y3)) / d
        c = 1 - a - b
        if a >= -1e-9 and b >= -1e-9 and c >= -1e-9:
            return a * z1 + b * z2 + c * z3
    return None


def reverse_elems(elems):
    return [(q, p, -b) for p, q, b in reversed(elems)]


def _arc(p, q, b):
    """bulge 호 → (중심, 반지름, 시작각, 부호 있는 사이각)."""
    c = math.hypot(q[0] - p[0], q[1] - p[1])
    th = 4 * math.atan(b)
    r = c / (2 * math.sin(abs(th) / 2))
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    ux, uy = (q[0] - p[0]) / c, (q[1] - p[1]) / c
    d = c * (1 - b * b) / (4 * b)  # 현 가운데에서 중심까지(왼쪽 +)
    cx, cy = mx - d * uy, my + d * ux
    return (cx, cy), r, math.atan2(p[1] - cy, p[0] - cx), th


def elem_len(p, q, b):
    if abs(b) < 1e-12:
        return math.hypot(q[0] - p[0], q[1] - p[1])
    _c, r, _a0, th = _arc(p, q, b)
    return r * abs(th)


def total_len(elems):
    return sum(elem_len(*e) for e in elems)


def point_at(elems, s):
    """선형 처음부터 거리 s인 점과 그 점의 진행 방향 각(라디안). 범위 밖이면 끝 요소를 늘인다."""
    acc = 0.0
    for i, (p, q, b) in enumerate(elems):
        L = elem_len(p, q, b)
        if s <= acc + L + 1e-9 or i == len(elems) - 1:
            t = s - acc
            if abs(b) < 1e-12:
                ang = math.atan2(q[1] - p[1], q[0] - p[0])
                return (p[0] + t * math.cos(ang), p[1] + t * math.sin(ang)), ang
            (cx, cy), r, a0, th = _arc(p, q, b)
            a = a0 + math.copysign(t / r, th)
            return (cx + r * math.cos(a), cy + r * math.sin(a)), a + math.copysign(math.pi / 2, th)
        acc += L
    return None, None


def _seg_hits(p, q, b, e):
    """선형 요소와 지형 선분 e의 교점 → [(요소 안 거리, z)]."""
    x1, y1, z1, x2, y2, z2 = e
    dx, dy = x2 - x1, y2 - y1
    out = []
    if abs(b) < 1e-12:
        ex, ey = q[0] - p[0], q[1] - p[1]
        den = ex * dy - ey * dx
        if abs(den) < 1e-15:
            return out
        t = ((x1 - p[0]) * dy - (y1 - p[1]) * dx) / den   # 선형 요소 위
        u = ((x1 - p[0]) * ey - (y1 - p[1]) * ex) / den   # 지형 선분 위
        if -1e-12 <= t <= 1 + 1e-12 and -1e-12 <= u <= 1 + 1e-12:
            out.append((t * math.hypot(ex, ey), z1 + u * (z2 - z1)))
        return out
    (cx, cy), r, a0, th = _arc(p, q, b)
    fx, fy = x1 - cx, y1 - cy
    A = dx * dx + dy * dy
    if A < 1e-24:
        return out
    B = 2 * (fx * dx + fy * dy)
    C = fx * fx + fy * fy - r * r
    disc = B * B - 4 * A * C
    if disc < 0:
        return out
    for u in ((-B - math.sqrt(disc)) / (2 * A), (-B + math.sqrt(disc)) / (2 * A)):
        if -1e-12 <= u <= 1 + 1e-12:
            a = math.atan2(fy + u * dy, fx + u * dx)
            sw = (a - a0) if th > 0 else (a0 - a)
            sw %= 2 * math.pi
            if sw > 2 * math.pi - 1e-9:
                sw = 0.0
            if sw <= abs(th) + 1e-9:
                out.append((r * sw, z1 + u * (z2 - z1)))
    return out


def ground(elems, edges, faces=None):
    """선형을 따라 지형 교점 [(선형 처음부터 거리, z)] (거리순, 같은 거리는 하나).
    faces(3D면)가 있으면 시·종점이 면 안에 있을 때 그 면의 높이를 시·종점 값으로 넣는다(면 안은 평면이라 정확하다)."""
    hits, acc = [], 0.0
    if faces:
        for s in (0.0, total_len(elems)):
            p, _a = point_at(elems, s)
            z = face_z(faces, p[0], p[1])
            if z is not None:
                hits.append((s, z))
    for p, q, b in elems:
        xs = (min(p[0], q[0]), max(p[0], q[0]), min(p[1], q[1]), max(p[1], q[1]))
        if abs(b) >= 1e-12:
            (cx, cy), r, _a, _t = _arc(p, q, b)
            xs = (cx - r, cx + r, cy - r, cy + r)
        for e in edges:
            if max(e[0], e[3]) < xs[0] - 1e-9 or min(e[0], e[3]) > xs[1] + 1e-9 or \
                    max(e[1], e[4]) < xs[2] - 1e-9 or min(e[1], e[4]) > xs[3] + 1e-9:
                continue
            hits += [(acc + s, z) for s, z in _seg_hits(p, q, b, e)]
        acc += elem_len(p, q, b)
    hits.sort()
    out = []
    for s, z in hits:
        if out and abs(s - out[-1][0]) < 1e-6:
            continue
        out.append((s, z))
    return out


def project(elems, x, y):
    """점 (x, y)에서 선형에 내린 가장 가까운 곳 → (선형 거리, 부호 있는 이격: 진행 방향 왼쪽 +)."""
    best, acc = None, 0.0
    for p, q, b in elems:
        L = elem_len(p, q, b)
        if abs(b) < 1e-12:
            ex, ey = q[0] - p[0], q[1] - p[1]
            t = max(0.0, min(1.0, ((x - p[0]) * ex + (y - p[1]) * ey) / (ex * ex + ey * ey or 1e-24)))
            cx, cy = p[0] + t * ex, p[1] + t * ey
            s, side = acc + t * L, ex * (y - p[1]) - ey * (x - p[0])
        else:
            (ox, oy), r, a0, th = _arc(p, q, b)
            sw = ((math.atan2(y - oy, x - ox) - a0) * (1 if th > 0 else -1)) % (2 * math.pi)
            if sw > abs(th):
                sw = abs(th) if sw - abs(th) < 2 * math.pi - sw else 0.0
            a = a0 + math.copysign(sw, th)
            cx, cy = ox + r * math.cos(a), oy + r * math.sin(a)
            s = acc + r * sw
            # 반시계 호(th>0)면 중심 쪽이 왼쪽
            side = (r - math.hypot(x - ox, y - oy)) * (1 if th > 0 else -1)
        d = math.hypot(x - cx, y - cy)
        if best is None or d < best[0] - 1e-12:
            best = (d, s, math.copysign(d, side) if side else 0.0)
        acc += L
    return (best[1], best[2]) if best else (None, None)


def polygon(elems, step_deg=2.0):
    """닫힌 요소 목록 → 점 목록(호는 step_deg마다 나눈다). 점 포함 판정·가운데 찾기용."""
    pts = []
    for p, q, b in elems:
        pts.append(p)
        if abs(b) >= 1e-12:
            (cx, cy), r, a0, th = _arc(p, q, b)
            n = max(2, int(math.degrees(abs(th)) / step_deg))
            pts += [(cx + r * math.cos(a0 + th * k / n), cy + r * math.sin(a0 + th * k / n)) for k in range(1, n)]
    return pts


def area(elems):
    """닫힌 요소 목록의 부호 있는 면적(반시계 +). 호는 활꼴 면적을 더한다(정확)."""
    a = 0.0
    for p, q, b in elems:
        a += (p[0] * q[1] - q[0] * p[1]) / 2
        if abs(b) >= 1e-12:
            _c, r, _a0, th = _arc(p, q, b)
            a += math.copysign(r * r / 2 * (abs(th) - math.sin(abs(th))), b)
    return a


def inside(pts, x, y):
    c = False
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def label_point(pts, holes=()):
    """도형 안쪽 이름표 자리: 무게중심이 안(구멍 밖)에 있고 가장자리에서 떨어져 있으면 그것,
    아니면 여러 높이의 가로줄에서 가장 긴 안쪽 구간(구멍 제외) 가운데."""
    if holes:
        ys = [p[1] for p in pts]
        best = None
        # 가운데 줄부터(같은 폭이면 가운데 쪽). 줄은 칸 사이(k + 0.5)라 꼭짓점 높이를 비켜 간다
        for k in sorted(range(20), key=lambda k: abs(k - 9.5)):
            y = min(ys) + (max(ys) - min(ys)) * (k + 0.5) / 20
            xs = sorted(x1 + (y - y1) * (x2 - x1) / (y2 - y1) for ring in [pts] + list(holes)
                        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]) if (y1 > y) != (y2 > y))
            for i in range(0, len(xs) - 1, 2):
                if best is None or xs[i + 1] - xs[i] > best[0]:
                    best = (xs[i + 1] - xs[i], ((xs[i] + xs[i + 1]) / 2, y))
        if best:
            return best[1]
    n = len(pts)
    A = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        f = x1 * y2 - x2 * y1
        A += f
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    if abs(A) < 1e-15:
        return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)
    cx, cy = cx / (3 * A), cy / (3 * A)
    if inside(pts, cx, cy):
        return (cx, cy)
    xs = sorted(x1 + (cy - y1) * (x2 - x1) / (y2 - y1) for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1])
                if (y1 > cy) != (y2 > cy))
    seg = max(((xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)), key=lambda t: t[1] - t[0], default=None)
    return ((seg[0] + seg[1]) / 2, cy) if seg else (cx, cy)


def cross_at(elems, a, b):
    """선분 a-b가 선형과 만나는 곳의 선형 거리(처음 만나는 곳). 안 만나면 None."""
    acc = 0.0
    for p, q, bu in elems:
        h = _seg_hits(p, q, bu, (a[0], a[1], 0.0, b[0], b[1], 0.0))
        if h:
            return acc + min(s for s, _z in h)
        acc += elem_len(p, q, bu)
    return None


def thin(prof, ds=0.0, dz=0.0, same=False):
    """정점 줄이기: 앞 점과 거리 ds 이하이면서 높이 차 dz 이하면 빼고, same이면 앞 점과 높이가 같은 점을 뺀다.
    처음·끝 점은 남긴다."""
    if len(prof) < 3:
        return list(prof)
    out = [prof[0]]
    for s, z in prof[1:-1]:
        ps, pz = out[-1]
        if (ds > 0 or dz > 0) and s - ps <= ds and abs(z - pz) <= dz:
            continue
        if same and z == pz:
            continue
        out.append((s, z))
    out.append(prof[-1])
    return out


def z_at(prof, s):
    """거리 s의 지반고(선형 보간). 지형 밖이면 None."""
    if not prof or s < prof[0][0] - 1e-9 or s > prof[-1][0] + 1e-9:
        return None
    for (s0, z0), (s1, z1) in zip(prof, prof[1:]):
        if s0 - 1e-9 <= s <= s1 + 1e-9:
            return z0 if s1 - s0 < 1e-12 else z0 + (z1 - z0) * (s - s0) / (s1 - s0)
    return prof[-1][1] if abs(s - prof[-1][0]) < 1e-9 else prof[0][1]
