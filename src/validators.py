"""입력 검사 — 도구 인자가 AutoCAD에 닿기 전에 걸러 낸다(순수 파이썬, COM 없음).

LISP 소스는 한 번 토막(_lisp_tokens)으로 나눠 두고, 괄호 검사·금지 함수 검사·한 줄 만들기가
모두 같은 토막을 쓴다. 문자열·주석을 각자 따로 세다가 셋이 서로 다르게 판단하는 일을 막는다.
"""

import json
import math
import re
from typing import Iterator, List, Optional, Tuple

# ---------------------------------------------------------------- 개체 종류 이름

# ssget (cons 0 ...)은 DXF 이름만 알아듣는다. 사람·AI는 ActiveX 이름(AcDbLine 등)도 쓰므로 둘 다 받는다.
_DXF_NAMES = {
    "LINE": ("line", "acdbline"),
    "TEXT": ("text", "acdbtext"),
    "MTEXT": ("mtext", "acdbmtext"),
    "LWPOLYLINE": ("lwpolyline", "lightweightpolyline", "acdbpolyline"),
    "POLYLINE": ("polyline", "acdb2dpolyline", "acdb3dpolyline"),
    "CIRCLE": ("circle", "acdbcircle"),
    "ARC": ("arc", "acdbarc"),
    "INSERT": ("insert", "blockreference", "acdbblockreference"),
    "POINT": ("point", "acdbpoint"),
    "HATCH": ("hatch", "acdbhatch"),
    "ATTDEF": ("attdef", "attributedefinition", "acdbattributedefinition"),
    "ELLIPSE": ("ellipse", "acdbellipse"),
    "SPLINE": ("spline", "acdbspline"),
    "SOLID": ("solid", "acdbtrace"),
    "DIMENSION": ("dimension", "acdbdimension", "acdbaligneddimension", "acdbrotateddimension"),
    "LEADER": ("leader", "acdbleader"),
    "MULTILEADER": ("multileader", "mleader", "acdbmleader"),
}
_ALIAS_TO_DXF = {alias: dxf for dxf, aliases in _DXF_NAMES.items() for alias in aliases}


def dxf_type(t: str) -> str:
    """종류 이름(여러 개면 쉼표로)을 DXF 이름으로. 모르는 이름은 대문자로만 바꿔 그대로 넘긴다."""
    names = (x.strip() for x in str(t).split(","))
    return ",".join(_ALIAS_TO_DXF.get(x.lower(), x.upper()) for x in names if x)


# ---------------------------------------------------------------- LISP에 넣을 문자열

def lisp_str(s: str) -> str:
    """LISP "..." 안에 그대로 넣을 수 있게 \\ 와 " 앞에 \\ 를 붙인다."""
    out = []
    for ch in str(s):
        if ch in '\\"':
            out.append("\\")
        out.append(ch)
    return "".join(out)


# AutoCAD wcmatch(ssget 필터)에서 뜻이 있는 글자. 글자 그대로 맞추려면 앞에 역따옴표(`)를 붙인다(실측).
WCMATCH_SPECIAL = frozenset("#@.*?~[]-,`")


def wild_escape(s: str) -> str:
    """레이어 이름 같은 값을 ssget 필터에서 글자 그대로 맞추게 만든다."""
    return "".join(("`" + ch) if ch in WCMATCH_SPECIAL else ch for ch in s)


# ---------------------------------------------------------------- 숫자·점·색

def num(v, name: str) -> float:
    """유한한 실수만. NaN·무한대는 LISP에 nan으로 찍혀 식 전체가 깨지고, True/False는 숫자로 보지 않는다."""
    bad = isinstance(v, bool)
    if not bad:
        try:
            x = float(v)
        except (TypeError, ValueError):
            bad = True
    if bad:
        raise ValueError("%s 가 숫자가 아닙니다: %r" % (name, v))
    if math.isnan(x) or math.isinf(x):
        raise ValueError("%s 가 유한수가 아닙니다: %r" % (name, v))
    return x


def positive(v, name: str) -> float:
    """0보다 큰 수(반지름·문자 높이·축척)."""
    x = num(v, name)
    if not x > 0:
        raise ValueError("%s 는 0보다 커야 합니다: %r" % (name, v))
    return x


def aci(v, name: str = "color") -> int:
    """ACI 색 0~256 정수(0 = ByBlock, 256 = ByLayer)."""
    x = num(v, name)
    if x.is_integer() and 0 <= x <= 256:
        return int(x)
    raise ValueError("%s 는 0~256 정수여야 합니다(0=ByBlock, 256=ByLayer): %r" % (name, v))


def rgb(v, name: str = "true_color") -> Tuple[int, int, int]:
    """'R,G,B' 또는 [R, G, B] → 0~255 정수 셋."""
    items = v.split(",") if isinstance(v, str) else list(v) if isinstance(v, (list, tuple)) else None
    try:
        vals = tuple(int(str(c).strip()) for c in items)
    except (TypeError, ValueError):
        raise ValueError('%s 는 "R,G,B" 형식이어야 합니다: %r' % (name, v)) from None
    if len(vals) == 3 and min(vals) >= 0 and max(vals) <= 255:
        return vals
    raise ValueError('%s 는 0~255 정수 3개 "R,G,B" 여야 합니다: %r' % (name, v))


def point(pt, name: str) -> Tuple[float, float, float]:
    """[x, y] 또는 [x, y, z] → (x, y, z). z가 없으면 0."""
    if isinstance(pt, (list, tuple)) and len(pt) in (2, 3):
        x, y, *rest = (num(c, name) for c in pt)
        return x, y, (rest[0] if rest else 0.0)
    raise ValueError("%s 는 [x, y] 또는 [x, y, z] 여야 합니다: %r" % (name, pt))


def json_points(points, name: str = "points", minimum: int = 2) -> List[Tuple[float, float, float]]:
    """점 배열(목록 또는 JSON 문자열). 최소 개수를 넘지 못하면 막는다."""
    if isinstance(points, str):
        try:
            points = json.loads(points)
        except ValueError:
            raise ValueError("%s 는 JSON 배열이어야 합니다. 예: [[0,0],[10,0]]" % name) from None
    if isinstance(points, list) and len(points) >= minimum:
        return [point(p, "%s[%d]" % (name, k)) for k, p in enumerate(points)]
    raise ValueError("%s 는 점 %d개 이상의 배열이어야 합니다: %r" % (name, minimum, points))


_HEX = re.compile(r"^[0-9A-Fa-f]+$")


def parse_handles(handles) -> List[str]:
    """핸들 배열(목록 또는 JSON 문자열) → 대문자 핸들 목록.
    '"2F3"'처럼 문자열 하나를 주면 글자마다 돌아 엉뚱한 개체를 건드리므로, 문자열 배열만 받는다."""
    seq = handles
    if not isinstance(seq, list):
        try:
            seq = json.loads(handles)
        except (TypeError, ValueError):
            seq = None
    ok = isinstance(seq, list) and all(isinstance(h, str) and h.strip() for h in seq)
    if not ok:
        raise ValueError('handles는 비어 있지 않은 핸들 문자열의 JSON 배열이어야 합니다. '
                         '예: ["2F3","2F4"] (받은 값: %s)' % (handles,))
    clean = [h.strip() for h in seq]
    wrong = [h for h in clean if not _HEX.match(h)]
    if wrong:
        raise ValueError("핸들은 16진수 문자열이어야 합니다: %s" % wrong[:5])
    return [h.upper() for h in clean]


def bbox_args(x1, y1, x2, y2) -> Optional[Tuple[float, float, float, float]]:
    """영역 네 값. 모두 0이면 영역 없음(None), 아니면 (작은 x, 작은 y, 큰 x, 큰 y)."""
    xa, ya, xb, yb = (num(v, k) for v, k in ((x1, "bbox_x1"), (y1, "bbox_y1"), (x2, "bbox_x2"), (y2, "bbox_y2")))
    if xa == ya == xb == yb == 0:
        return None
    return min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)


# ---------------------------------------------------------------- LISP 소스 토막

def _lisp_tokens(code: str) -> Iterator[Tuple[str, str]]:
    """LISP 소스를 (종류, 글자) 토막으로. 종류: str(닫힌 문자열) open_str(끝까지 안 닫힌 문자열)
    note(; 줄 주석) block(;| |; 주석) open_block(끝까지 안 닫힌 블록 주석) ( ) word(그 밖의 글자 덩어리)."""
    pos, end = 0, len(code)
    while pos < end:
        ch = code[pos]
        if ch == '"':
            k = pos + 1
            while k < end and code[k] != '"':
                k += 2 if code[k] == "\\" else 1
            if k >= end:
                yield "open_str", code[pos:]
                return
            yield "str", code[pos:k + 1]
            pos = k + 1
        elif ch == ";":
            if code.startswith(";|", pos):
                close = code.find("|;", pos + 2)
                stop = end if close < 0 else close + 2
                yield ("open_block" if close < 0 else "block"), code[pos:stop]
            else:
                stop = pos
                while stop < end and code[stop] not in "\r\n":  # CR 하나만 줄바꿈인 글도 있다
                    stop += 1
                yield "note", code[pos:stop]
            pos = stop
        elif ch in "()":
            yield ch, ch
            pos += 1
        else:
            k = pos
            while k < end and code[k] not in '";()':
                k += 1
            yield "word", code[pos:k]
            pos = k


def paren_balance(code: str):
    """(끝 깊이, 가장 낮았던 깊이, 문자열이 안 닫혔나). 끝 깊이 ≠ 0 이거나 가장 낮은 깊이 < 0 이면 불균형."""
    depth = lowest = 0
    unclosed = False
    for kind, _txt in _lisp_tokens(code):
        if kind == "(":
            depth += 1
        elif kind == ")":
            depth -= 1
            lowest = min(lowest, depth)
        elif kind in ("open_str", "open_block"):
            unclosed = True
    return depth, lowest, unclosed


def check_parens(code: str) -> None:
    """괄호가 안 맞으면 보내기 전에 막는다. 닫히지 않은 LISP를 받은 SendCommand는 입력을 더 기다리며
    돌아오지 않는다(실측) — 보낸 뒤에 알면 늦다."""
    depth, lowest, unclosed = paren_balance(code)
    if unclosed:
        if any(kind == "open_block" for kind, _t in _lisp_tokens(code)):
            raise ValueError("닫히지 않은 블록 주석(;| … |;)이 있습니다.")
        raise ValueError('닫히지 않은 문자열 리터럴(")이 있습니다.')
    if lowest < 0:
        raise ValueError("닫는 괄호가 여는 괄호보다 %d개 많습니다." % -lowest)
    if depth > 0:
        raise ValueError("닫는 괄호가 %d개 부족합니다 — 이대로 보내면 AutoCAD가 "
                         "입력 대기에 걸려 이후 명령이 막힙니다." % depth)


# 파일을 불러오는 함수 — SECURELOAD 보안 창이 떠서 AutoCAD가 멈출 수 있다(실측).
_FILE_LOADERS = ("load", "vl-load-all", "appload", "arxload", "vl-vbaload", "vl-vbarun")
_LOADER_CALL = re.compile(r"(?:\(\s*(?:(?:function|quote)\s+)?|')(%s)(?=$|[\s()])"
                          % "|".join(re.escape(f) for f in _FILE_LOADERS))


def check_banned(code: str) -> None:
    """문자열·주석 밖에서 파일 불러오기 함수를 부르거나 넘기면 막는다.
    '( load'처럼 괄호 뒤 공백, 'load·(quote load)·(function load) 같은 함수 넘기기도 같은 호출로 본다."""
    # 문자열·주석은 빈칸으로 남긴다 — 그냥 지우면 앞뒤 글자가 함수 이름에 붙어 놓치거나 엉뚱하게 붙는다.
    bare = "".join(txt if kind in ("(", ")", "word") else " " for kind, txt in _lisp_tokens(code)).lower()
    hit = _LOADER_CALL.search(bare)
    if hit:
        raise ValueError("(%s ...)는 쓸 수 없습니다 — AutoCAD 보안 설정(SECURELOAD)으로 대화창이 "
                         "떠서 멈출 수 있습니다. 불러올 파일의 코드 본문을 run_lisp에 직접 넣으세요." % hit.group(1))


def _flatten_string(lit: str) -> str:
    """문자열 토막 하나를 한 줄로: 실제 줄바꿈 → \\n, 탭 → \\t, CR은 버린다.
    줄 끝의 \\ (다음 줄로 이어 쓰기)는 \\\\ + \\n 으로 바꿔 파일이 두 줄로 갈라지지 않게 한다."""
    out, k, end = [], 0, len(lit)
    while k < end:
        ch = lit[k]
        if ch == "\\" and k + 1 < end:
            if lit[k + 1] in "\r\n":
                out.append("\\\\\\n")
                k += 3 if lit.startswith("\r\n", k + 1) else 2
            else:
                out.append(lit[k:k + 2])
                k += 2
            continue
        out.append({"\n": "\\n", "\t": "\\t", "\r": ""}.get(ch, ch))
        k += 1
    return "".join(out)


def one_line(code: str) -> str:
    """LISP 소스 → 한 줄(파일 eval이 read-line 한 번으로 읽는다). 주석은 지우고(블록 주석은 빈칸 하나),
    문자열 밖 줄바꿈·탭은 빈칸으로, 문자열 안은 이스케이프로 바꾼다."""
    parts = []
    for kind, txt in _lisp_tokens(code):
        if kind in ("str", "open_str"):
            parts.append(_flatten_string(txt))
        elif kind == "block":
            parts.append(" ")
        elif kind == "word":
            parts.append(txt.replace("\r", " ").replace("\n", " ").replace("\t", " "))
        elif kind != "note":
            parts.append(txt)
    return "".join(parts)
