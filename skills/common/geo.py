# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""객체 기하 덤프 공통(CL·QCL·TLAE·HAR·SEAT·DOE·JJJ·DMT): 길이·면적·중간점과 구간(선분·호) 목록.

선택 집합 _ss → 객체마다
  G<탭>핸들<탭>종류<탭>레이어<탭>색(256=ByLayer)<탭>닫힘<탭>길이<탭>면적<탭>시작x<탭>y<탭>끝x<탭>y<탭>고도<탭>해치 무늬
  K<탭>x1<탭>y1<탭>x2<탭>y2<탭>bulge   (선·폴리선 구간·호·원(반원 둘)) — WCS, 평면(XY)
길이·면적은 도면 단위. 면적은 닫을 수 있는 객체(원·타원·폴리선·스플라인·해치·영역)만, 아니면 0.
"""

import math

GEO_LISP = (
    '(defun _geo-len (o / r) (setq r (vl-catch-all-apply (quote vlax-curve-getDistAtParam)'
    ' (list o (vlax-curve-getEndParam o)))) (if (vl-catch-all-error-p r) 0.0 r))'
    '(defun _geo-area (o / r) (setq r (vl-catch-all-apply (quote vla-get-Area) (list (vlax-ename->vla-object o))))'
    ' (if (vl-catch-all-error-p r) 0.0 r))'
    '(defun _geo-k (a b bu) (write-line (strcat "K" _d (bc:rtos (car a) 2 10) _d (bc:rtos (cadr a) 2 10) _d'
    ' (bc:rtos (car b) 2 10) _d (bc:rtos (cadr b) 2 10) _d (bc:rtos bu 2 12)) _fp))'
    '(foreach _en (bc:ss-list _ss) (setq _ed (entget _en) _ty (cdr (assoc 0 _ed)))'
    ' (setq _cv (member _ty (list "LINE" "ARC" "CIRCLE" "LWPOLYLINE" "POLYLINE" "ELLIPSE" "SPLINE")))'
    ' (setq _p0 (if _cv (vlax-curve-getStartPoint _en) (list 0.0 0.0 0.0)) _p1 (if _cv (vlax-curve-getEndPoint _en) _p0))'
    ' (write-line (strcat "G" _d (cdr (assoc 5 _ed)) _d _ty _d (cdr (assoc 8 _ed)) _d'
    '  (itoa (if (assoc 62 _ed) (cdr (assoc 62 _ed)) 256)) _d'
    '  (if (or (member _ty (list "CIRCLE" "ELLIPSE" "HATCH" "REGION")) (and (assoc 70 _ed) (member _ty (list "LWPOLYLINE" "POLYLINE" "SPLINE"))'
    '   (= 1 (logand 1 (cdr (assoc 70 _ed)))))) "1" "0") _d'
    '  (bc:rtos (if _cv (_geo-len _en) 0.0) 2 10) _d'
    '  (bc:rtos (if (member _ty (list "CIRCLE" "ELLIPSE" "LWPOLYLINE" "POLYLINE" "SPLINE" "HATCH" "REGION")) (_geo-area _en) 0.0) 2 10) _d'
    '  (bc:rtos (car _p0) 2 10) _d (bc:rtos (cadr _p0) 2 10) _d (bc:rtos (car _p1) 2 10) _d (bc:rtos (cadr _p1) 2 10) _d'
    '  (bc:rtos (cond ((= _ty "LWPOLYLINE") (if (assoc 38 _ed) (cdr (assoc 38 _ed)) 0.0)) (_cv (caddr _p0)) (T 0.0)) 2 10) _d'
    '  (if (= _ty "HATCH") (cdr (assoc 2 _ed)) "")) _fp)'
    ' (cond ((= _ty "LINE") (_geo-k (cdr (assoc 10 _ed)) (cdr (assoc 11 _ed)) 0.0))'
    '  ((= _ty "ARC") (setq _c (cdr (assoc 10 _ed)) _r (cdr (assoc 40 _ed)) _a0 (cdr (assoc 50 _ed)) _a1 (cdr (assoc 51 _ed)))'
    '   (if (< _a1 _a0) (setq _a1 (+ _a1 (* 2 pi))))'
    '   (_geo-k (trans (polar _c _a0 _r) _en 0) (trans (polar _c _a1 _r) _en 0)'
    '    (* (if (< (caddr (trans (list 0 0 1) _en 0 T)) 0) -1 1) (/ (sin (/ (- _a1 _a0) 4)) (cos (/ (- _a1 _a0) 4))))))'
    '  ((= _ty "CIRCLE") (setq _c (cdr (assoc 10 _ed)) _r (cdr (assoc 40 _ed)))'
    '   (_geo-k (trans (polar _c 0 _r) _en 0) (trans (polar _c pi _r) _en 0) 1.0)'
    '   (_geo-k (trans (polar _c pi _r) _en 0) (trans (polar _c 0 _r) _en 0) 1.0))'
    '  ((= _ty "LWPOLYLINE") (setq _v nil)'
    '   (foreach _g _ed (cond ((= (car _g) 10) (setq _v (cons (list (trans (list (cadr _g) (caddr _g) 0.0) _en 0) 0.0) _v)))'
    '                         ((and (= (car _g) 42) _v) (setq _v (cons (list (car (car _v)) (cdr _g)) (cdr _v))))))'
    '   (setq _v (reverse _v))'
    '   (if (= 1 (logand 1 (cdr (assoc 70 _ed)))) (setq _v (append _v (list (list (car (car _v)) 0.0)))))'
    '   (setq _sg (if (< (caddr (cdr (assoc 210 _ed))) 0) -1 1))'
    '   (while (cdr _v) (_geo-k (car (car _v)) (car (cadr _v)) (* _sg (cadr (car _v)))) (setq _v (cdr _v))))'
    '  ((= _ty "POLYLINE") (setq _v nil _x (entnext _en))'
    '   (while (and _x (= (cdr (assoc 0 (entget _x))) "VERTEX"))'
    '    (if (zerop (logand 16 (cdr (assoc 70 (entget _x)))))'
    '     (setq _v (cons (list (trans (cdr (assoc 10 (entget _x))) _en 0) (if (assoc 42 (entget _x)) (cdr (assoc 42 (entget _x))) 0.0)) _v)))'
    '    (setq _x (entnext _x)))'
    '   (setq _v (reverse _v))'
    '   (if (= 1 (logand 1 (cdr (assoc 70 _ed)))) (setq _v (append _v (list (list (car (car _v)) 0.0)))))'
    '   (while (cdr _v) (_geo-k (car (car _v)) (car (cadr _v)) (cadr (car _v))) (setq _v (cdr _v))))))')


def parse(rows):
    """→ [{handle, type, layer, color, closed, length, area, start, end, elev, pattern, pieces [(p, q, bulge)]}]"""
    out = []
    for r in rows:
        c = r.split("\t")
        if c[0] == "G" and len(c) >= 14:
            out.append({"handle": c[1], "type": c[2], "layer": c[3], "color": int(c[4]), "closed": c[5] == "1",
                        "length": float(c[6]), "area": abs(float(c[7])), "start": (float(c[8]), float(c[9])),
                        "end": (float(c[10]), float(c[11])), "elev": float(c[12]),
                        "pattern": c[13] if len(c) > 13 else "", "pieces": []})
        elif c[0] == "K" and out and len(c) == 6:
            out[-1]["pieces"].append(((float(c[1]), float(c[2])), (float(c[3]), float(c[4])), float(c[5])))
    return out


def arc_of(p, q, b):
    """bulge 구간 → (중심, 반지름, 시작각, 사이각(부호 있음))."""
    th = 4 * math.atan(b)
    dx, dy = q[0] - p[0], q[1] - p[1]
    c = math.hypot(dx, dy)
    r = c / (2 * math.sin(abs(th) / 2))
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    h = r * math.cos(abs(th) / 2)
    nx, ny = -dy / c, dx / c
    sgn = 1 if b > 0 else -1  # 반원 넘는 호는 h가 음수라 중심이 저절로 반대쪽
    cx, cy = mx + sgn * nx * h, my + sgn * ny * h
    return (cx, cy), r, math.atan2(p[1] - cy, p[0] - cx), th


def piece_len(p, q, b):
    if abs(b) < 1e-12:
        return math.hypot(q[0] - p[0], q[1] - p[1])
    _c, r, _a, th = arc_of(p, q, b)
    return abs(th) * r


def piece_point(p, q, b, t):
    """구간 위 비율 t(0~1) 점과 진행 방향 각."""
    if abs(b) < 1e-12:
        return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t), math.atan2(q[1] - p[1], q[0] - p[0])
    c, r, a0, th = arc_of(p, q, b)
    a = a0 + th * t
    return (c[0] + r * math.cos(a), c[1] + r * math.sin(a)), a + (math.pi / 2 if th > 0 else -math.pi / 2)


def at_length(pieces, s):
    """구간 목록 위 처음부터 거리 s의 점과 방향 각."""
    acc = 0.0
    for p, q, b in pieces:
        L = piece_len(p, q, b)
        if acc + L >= s - 1e-12 and L > 0:
            return piece_point(p, q, b, (s - acc) / L)
        acc += L
    p, q, b = pieces[-1]
    return piece_point(p, q, b, 1.0)


def polygon(pieces, step_deg=5.0):
    """구간 목록 → 꼭짓점 목록(호는 잘게 나눈다)."""
    pts = []
    for p, q, b in pieces:
        pts.append(p)
        if abs(b) > 1e-12:
            _c, _r, _a, th = arc_of(p, q, b)
            n = max(2, int(abs(math.degrees(th)) / step_deg))
            pts += [piece_point(p, q, b, k / n)[0] for k in range(1, n)]
    return pts


def readable(a):
    """문자 각을 읽기 좋은 방향(−90°초과 ~ 90°이하)으로."""
    a = math.atan2(math.sin(a), math.cos(a))
    if a > math.pi / 2 + 1e-9:
        a -= math.pi
    elif a <= -math.pi / 2 + 1e-9:
        a += math.pi
    return a


def round_mode(v, dec, how="반올림", unit=0.0):
    """반올림·올림·내림(소수 자리, 또는 단위값)."""
    from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
    mode = {"올림": ROUND_CEILING, "내림": ROUND_FLOOR}.get(how, ROUND_HALF_UP)
    if unit and unit > 0:
        q = (Decimal(repr(float(v))) / Decimal(repr(float(unit)))).quantize(Decimal(1), rounding=mode)
        return float(q * Decimal(repr(float(unit))))
    return float(Decimal(repr(float(v))).quantize(Decimal(1).scaleb(-int(dec)), rounding=mode))


def num_str(v, dec, thousands=False):
    s = "%.*f" % (max(0, int(dec)), v)
    if thousands:
        ip, _, fp = s.partition(".")
        neg = ip.startswith("-")
        ip = "{:,}".format(int(ip.lstrip("-")))
        s = ("-" if neg else "") + ip + ("." + fp if fp else "")
    return s


AREA_UNITS = ["㎡", "py", "a", "ha", "㎢"]


def area_in(a_m2, unit):
    return {"py": a_m2 / 3.305785, "a": a_m2 / 100.0, "ha": a_m2 / 10000.0, "㎢": a_m2 / 1e6}.get(unit, a_m2)


def upm(scale):
    """1m가 도면 몇 단위인지(축척 1000 = m 도면 1, 축척 1 = mm 도면 1000)."""
    return 1000.0 / (float(scale) if float(scale) > 0 else 1000.0)
