# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""좌표 공통: LISP 덤프 해석, 토목/수학 좌표, 정렬, 측점 문자 해석."""

import re
from decimal import Decimal, ROUND_HALF_UP

TYPE_GROUPS = {
    "선": "LINE,LWPOLYLINE,POLYLINE",
    "문자": "TEXT,MTEXT",
    "점": "POINT",
    "블록": "INSERT",
    "원호": "CIRCLE,ARC",
}


def parse_dump(rows):
    """bc:dump-ent 결과 줄 → [{handle,type,layer,text,points:[(x,y,z)]}]"""
    out = []
    for r in rows:
        c = r.split("\t")
        if c[0] == "ENT":
            out.append({"handle": c[1], "type": c[2], "layer": c[3], "text": c[4] if len(c) > 4 else "",
                        "points": []})
        elif c[0] == "P" and out:
            out[-1]["points"].append((float(c[1]), float(c[2]), float(c[3])))
    return out


def civil(p, mode):
    """토목 좌표면 (X=CAD Y, Y=CAD X)."""
    x, y, z = p
    return (y, x, z) if mode == "토목" else (x, y, z)


SORTS = ["안 함", "X 좌→우", "X 우→좌", "Y 위→아래", "Y 아래→위",
         "위→아래 우선, 좌→우", "좌→우 우선, 아래→위", "좌→우 우선, 위→아래", "아래→위 우선, 좌→우",
         "내용 오름차순", "내용 내림차순"]


def _rows(items, key_major, key_minor, tol):
    """행(또는 열) 묶음 정렬: key_major로 묶고 그 안에서 key_minor."""
    items = sorted(items, key=key_major)
    groups = []
    for it in items:
        if groups and abs(key_major(it) - key_major(groups[-1][0])) <= tol:
            groups[-1].append(it)
        else:
            groups.append([it])
    out = []
    for g in groups:
        out.extend(sorted(g, key=key_minor))
    return out


def sort_points(items, how, tol=None, key=lambda it: it):
    """items 정렬. key(it) → (x, y, z) CAD 좌표. 행·열 묶음 허용오차 tol(없으면 범위의 1%)."""
    if how in ("안 함", "", None) or not items:
        return list(items)
    xs = [key(i)[0] for i in items]
    ys = [key(i)[1] for i in items]
    if tol is None:
        tol = max(max(xs) - min(xs), max(ys) - min(ys)) * 0.01
    X = lambda it: key(it)[0]
    Y = lambda it: key(it)[1]
    if how == "X 좌→우":
        return sorted(items, key=X)
    if how == "X 우→좌":
        return sorted(items, key=X, reverse=True)
    if how == "Y 위→아래":
        return sorted(items, key=Y, reverse=True)
    if how == "Y 아래→위":
        return sorted(items, key=Y)
    if how == "위→아래 우선, 좌→우":
        return _rows(items, lambda i: -Y(i), X, tol)
    if how == "아래→위 우선, 좌→우":
        return _rows(items, Y, X, tol)
    if how == "좌→우 우선, 아래→위":
        return _rows(items, X, Y, tol)
    if how == "좌→우 우선, 위→아래":
        return _rows(items, X, lambda i: -Y(i), tol)
    return list(items)


_STA = re.compile(r"^\s*(?:STA\.?|No\.?|NO\.?)?\s*([+-]?\d+)\s*\+\s*([\d.]+)\s*$", re.I)
_NO = re.compile(r"^\s*(?:No\.?|NO\.?)\s*(\d+)\s*$", re.I)


def station_to_dist(v, mode="Station", interval=20.0):
    """측점 → 누가거리(m).
    Station: '1+250.5' = 1250.5, 숫자는 그대로.  Number: 'No.12+5' = 12×간격+5, 'No.12' = 12×간격."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    # 뒤에 붙은 괄호 설명은 뗀다: 'NO.19+940(낙차공)', 'NO.13+742(풍운교(취입보))' → 'NO.…'
    s = re.sub(r"\s*\(.*$", "", str(v).strip().replace(",", ""))
    m = _STA.match(s)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        return (a * interval + b) if mode == "Number" else (a * 1000.0 + b)
    m = _NO.match(s)
    if m:
        return float(m.group(1)) * interval
    try:
        return float(s)
    except ValueError:
        return None


def fmt(v, dec):
    """소수 dec자리 문자. 반올림은 사사오입(7.125 → 7.13). 보이는 10진 값 기준이라 2진 오차로 내려가지 않는다."""
    dec = max(0, int(dec))
    q = Decimal(repr(float(v))).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)
    return format(q, "f")


def sta_str(d, mode="Station", interval=20.0, dec=0, keep000=True, prefix="", km_only=False, drop_plus0=False):
    """누가거리 → 측점 문자. LISP bc:sta-str과 같은 규칙.
    km_only(Station): 1km 단위가 아니면 'km+' 없이 m만(예: 1+000, 100, 200 … 2+000).
    drop_plus0(Number): 정체인 뒤 +0 생략(NO 3+0 → NO 3)."""
    neg = d < 0
    d = round(abs(d), int(dec))
    if mode == "Number":
        k = int((d + 1e-9) // interval)
        m = d - k * interval
        if m < 1e-9:
            m = 0.0
        s = "%d+%s" % (k, fmt(m, dec))
        if drop_plus0 and abs(m) < 1e-9:
            s = "%d" % k
    else:
        k = int((d + 1e-9) // 1000.0)
        m = d - k * 1000.0
        if m < 1e-9:
            m = 0.0
        ms = fmt(m, dec)
        if keep000:
            ip = ms.split(".")[0]
            ms = "0" * max(0, 3 - len(ip)) + ms
        if km_only and abs(m) > 1e-9:
            return ("-" if neg else "") + ms
        s = "%d+%s" % (k, ms)
    return prefix + ("-" if neg else "") + s
