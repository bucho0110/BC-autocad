# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""RET 철근 재료표 — 철근 상세(원 안 철근 번호 + 밑줄 위 '직경 L=길이 N=개수')를 읽어 재료표를 그린다.

인식: 원 안 문자 = 번호(두 줄이면 위→아래로 이음), 원 밑의 가로선 끝까지 선 바로 위 문자에서
  직경(구분 문자 + 숫자, 예 H22·D13), L=길이(mm), N=개수. 선 아래(a=, b= 형상 치수)는 읽지 않는다.
  원 옆에 직경만 있는 도면 속 철근 표시(L·N 없음)는 상세가 아니므로 건너뛴다.
표: 직경 큰 순, 같은 직경 안은 상세에 처음 나온 머리 글자 순(W → F → …) → 번호 순, 직경마다 소계, 끝에 총계.
  단위중량은 KS 이형봉강, 총중량은 소계 길이 × 단위중량(t, 소수 셋째), 비고에 할증(기본 ADD 3%).
compute()·table_lisp()는 창 없이도 쓴다(MCP skill_run).
"""

import math
import re
import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "RET"
# KS D 3504 이형봉강 단위중량 (kg/m)
UNIT_WEIGHT = {6: 0.249, 10: 0.560, 13: 0.995, 16: 1.560, 19: 2.250, 22: 3.040, 25: 3.980, 29: 5.040, 32: 6.230,
               35: 7.510, 38: 8.950, 41: 10.500, 51: 15.900}
NOTES = ["ADD %", "% 할증", "소계(%)", "표기 안 함"]
LEN_UNITS = ["자동(소수점 있으면 m)", "mm", "m"]
SORTS = ["상세 순서(머리 글자 처음 나온 순)", "번호 이름순"]
FIELDS = [
    ("구분문자", "철근 구분 문자 (쉼표로, 예 D,H,S,U)", "str", "D,H,S,U", None),
    ("할증", "할증 (%)", "real", 3.0, None),
    ("비고", "비고 할증 표기", "choice", NOTES[0], NOTES),
    ("강도별", "철근 강도(구분 문자)별로 표 나누기", "bool", True, None),
    ("우선", "표 우선 순서 (구분 문자 앞에서부터)", "str", "H,D,S,U", None),
    ("좌상단", "표 왼쪽 위 문자 (예: (SD 40))", "str", "", None),
    ("우상단", "표 오른쪽 위 문자 (예: (1.0M당))", "str", "", None),
    ("결합문자", "두 줄 번호 사이 문자", "str", "", None),
    ("길이단위", "상세 L= 길이 단위", "choice", LEN_UNITS[0], LEN_UNITS),
    ("정렬", "같은 직경 안 순서", "choice", SORTS[0], SORTS),
    ("원미만", "이 지름 미만 원은 검색 안 함 (0=제한 없음)", "real", 0.0, None),
    ("원초과", "이 지름 초과 원은 검색 안 함 (0=제한 없음)", "real", 0.0, None),
    ("문자높이", "표 내용 문자 높이", "real", 2.5, None),
    ("제목높이", "표 이름 문자 높이", "real", 5.0, None),
    ("칸높이", "표 한 칸 높이 (문자 높이 배수)", "real", 3.2, None),
    ("열너비", "열 너비 (문자 높이 배수, 번호·직경·길이·본수·총길이·단위중량·총중량·비고)", "str",
     "8,8,10,8,12,12,12,12", None),
    ("문자스타일", "문자 스타일 (비우면 현재 스타일)", "str", "", None),
    ("문자레이어", "문자 레이어", "str", "CS-DIMT", None),
    ("선레이어", "표 안쪽 선 레이어", "str", "CS-DIML", None),
    ("테두리레이어", "표 테두리·제목 줄 레이어", "str", "CS-CONC-MAJR", None),
    ("표간격", "강도별 표 사이 간격 (문자 높이 배수)", "real", 8.0, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
HEAD = ["번  호", "직  경", "길     이", "본  수", "총  길  이", "단위 중량", "총  중  량", "비     고"]
TITLE = "철   근    재   료   표"

# 선택 집합 _ss 덤프: 원 C<탭>핸들<탭>x<탭>y<탭>r, 문자 T<탭>핸들<탭>가운데x<탭>y<탭>내용<탭>높이<탭>스타일,
# 선·폴리선 구간 S<탭>x1<탭>y1<탭>x2<탭>y2,
# 철근 번호 블록(속성 RB_NO — 건설정보 표준 CSBNUM 블록 등) B<탭>핸들<탭>원 x<탭>y<탭>r<탭>번호<탭>직경<탭>길이
DUMP_LISP = (
    '(defun _ret-att (en tag / a r) (setq a (entnext en))'
    ' (while (and a (= (cdr (assoc 0 (entget a))) "ATTRIB"))'
    '  (if (= (strcase (cdr (assoc 2 (entget a)))) tag) (setq r (cdr (assoc 1 (entget a))))) (setq a (entnext a))) r)'
    '(defun _ret-cir (bn / e c) (setq e (cdr (assoc -2 (tblsearch "BLOCK" bn))))'
    ' (while (and e (not c)) (if (= (cdr (assoc 0 (entget e))) "CIRCLE") (setq c (list (cdr (assoc 10 (entget e))) (cdr (assoc 40 (entget e))))))'
    '  (setq e (entnext e))) c)'
    '(foreach _en (bc:ss-list _ss) (setq _ed (entget _en) _ty (cdr (assoc 0 _ed)))'
    ' (cond ((and (= _ty "INSERT") (_ret-att _en "RB_NO") (setq _bc (_ret-cir (cdr (assoc 2 _ed)))))'
    '        (setq _sx (cdr (assoc 41 _ed)) _sy (cdr (assoc 42 _ed)) _ro (cdr (assoc 50 _ed)) _ip (cdr (assoc 10 _ed))'
    '              _lx (* _sx (car (car _bc))) _ly (* _sy (cadr (car _bc)))'
    '              _c (trans (list (+ (car _ip) (- (* _lx (cos _ro)) (* _ly (sin _ro)))) (+ (cadr _ip) (+ (* _lx (sin _ro)) (* _ly (cos _ro))))'
    '                         (caddr _ip)) _en 0))'
    '        (write-line (strcat "B" _d (cdr (assoc 5 _ed)) _d (bc:rtos (car _c) 2 8) _d (bc:rtos (cadr _c) 2 8) _d'
    '         (bc:rtos (* (abs _sx) (cadr _bc)) 2 8) _d (_ret-att _en "RB_NO") _d (if (_ret-att _en "RB_DIA") (_ret-att _en "RB_DIA") "")'
    '         _d (if (_ret-att _en "RB_LEN") (_ret-att _en "RB_LEN") "")) _fp))'
    '       ((= _ty "CIRCLE") (setq _c (trans (cdr (assoc 10 _ed)) _en 0))'
    '        (write-line (strcat "C" _d (cdr (assoc 5 _ed)) _d (bc:rtos (car _c) 2 8) _d (bc:rtos (cadr _c) 2 8) _d'
    '         (bc:rtos (cdr (assoc 40 _ed)) 2 8)) _fp))'
    '       ((member _ty (list "TEXT" "MTEXT")) (setq _c (bc:obj-center _en))'
    '        (write-line (strcat "T" _d (cdr (assoc 5 _ed)) _d (bc:rtos (car _c) 2 8) _d (bc:rtos (cadr _c) 2 8) _d'
    '         (vl-string-translate "\\t\\n\\r" "   " (bc:text-of _en)) _d (bc:rtos (cdr (assoc 40 _ed)) 2 6) _d'
    '         (cdr (assoc 7 _ed))) _fp))'
    '       ((member _ty (list "LINE" "LWPOLYLINE")) (setq _v (bc:verts _en))'
    '        (while (cdr _v) (write-line (strcat "S" _d (bc:rtos (caar _v) 2 8) _d (bc:rtos (cadar _v) 2 8) _d'
    '         (bc:rtos (caadr _v) 2 8) _d (bc:rtos (cadadr _v) 2 8)) _fp) (setq _v (cdr _v))))))')


def parse_dump(rows):
    circles, texts, segs = [], [], []
    for r in rows:
        c = r.split("\t")
        if c[0] == "C" and len(c) == 5:
            circles.append({"handle": c[1], "x": float(c[2]), "y": float(c[3]), "r": float(c[4])})
        elif c[0] == "B" and len(c) >= 8:
            circles.append({"handle": c[1], "x": float(c[2]), "y": float(c[3]), "r": float(c[4]), "no": c[5].strip(),
                            "dia_text": c[6].strip(), "len_text": c[7].strip()})
        elif c[0] == "T" and len(c) >= 6:
            texts.append({"handle": c[1], "x": float(c[2]), "y": float(c[3]), "text": c[4].strip(), "h": float(c[5]),
                          "style": c[6] if len(c) > 6 else ""})
        elif c[0] == "S" and len(c) == 5:
            x1, y1, x2, y2 = map(float, c[1:])
            if abs(y2 - y1) <= 1e-6 * max(1.0, abs(x2 - x1)) and abs(x2 - x1) > 0:
                segs.append((min(x1, x2), max(x1, x2), y1))
    return circles, texts, segs


def _grades(cfg):
    return [g.strip().upper() for g in str(cfg["구분문자"]).split(",") if g.strip()]


def recognize(circles, texts, segs, cfg):
    """→ (상세 [{no, grade, dia, L(mm), N, x, y}], 인식 안 된 원 [{x, y, no, why}])."""
    dmin, dmax = float(cfg["원미만"]), float(cfg["원초과"])
    grades = _grades(cfg)
    re_d = re.compile(r"^(%s)\s*(\d+)$" % "|".join(re.escape(g) for g in grades) if grades else r"^$", re.I)
    re_l = re.compile(r"^L\s*=\s*([\d,]+(?:\.\d+)?)$", re.I)
    re_n = re.compile(r"^N\s*=\s*(\d+(?:\.\d+)?)\s*(?:EA)?$", re.I)  # 1m당 개수처럼 소수도(3.33)
    out, bad = [], []
    for c in circles:
        d = 2 * c["r"]
        if (dmin > 0 and d < dmin) or (dmax > 0 and d > dmax):
            continue
        if c.get("no"):  # 철근 번호 블록: 번호·직경은 속성
            no = c["no"]
        else:
            inner = sorted((t for t in texts if math.hypot(t["x"] - c["x"], t["y"] - c["y"]) < c["r"]),
                           key=lambda t: -t["y"])
            if not inner:
                continue
            no = str(cfg["결합문자"]).join(t["text"] for t in inner)
        # 원 밑 가로선: 원 오른쪽으로 이어지고 높이가 원 아래쪽 ~ 가운데 사이인 가장 가까운 선
        cand = [s for s in segs if s[0] <= c["x"] + c["r"] and s[1] > c["x"] + c["r"]
                and c["y"] - 1.5 * c["r"] <= s[2] <= c["y"]]
        if cand:
            line = max(cand, key=lambda s: s[2])
            ly, xend = line[2], line[1]
        else:
            ly = c["y"] - c["r"]
            nxt = [o["x"] for o in circles if o is not c and o["x"] > c["x"] and abs(o["y"] - c["y"]) < c["r"]]
            xend = (min(nxt) - c["r"]) if nxt else c["x"] + 30 * c["r"]
        row = [t for t in texts if c["x"] + c["r"] < t["x"] <= xend and ly - 0.25 * c["r"] <= t["y"] <= c["y"] + 0.5 * c["r"]]
        dia = L = N = None
        attr = [("L=" + c["len_text"]) if c.get("len_text") else "", c.get("dia_text", "")]
        for s in attr + [t["text"] for t in row]:
            s = s.replace(" ", "")
            if not s:
                continue
            m = re_d.match(s)
            if m and dia is None:
                dia = (m.group(1).upper(), int(m.group(2)))
                continue
            m = re_l.match(s)
            if m and L is None:
                L = to_mm(m.group(1), cfg["길이단위"])
                continue
            m = re_n.match(s)
            if m and N is None:
                N = m.group(1)  # 글자 그대로(표에 그대로 쓴다)
        if L is None and N is None:
            continue  # 도면 속 철근 표시(직경만) — 상세가 아님
        if dia is None or L is None or N is None:
            bad.append({"x": c["x"], "y": c["y"], "no": no,
                        "why": "직경 없음" if dia is None else "L= 없음" if L is None else "N= 없음"})
            continue
        if dia[1] not in UNIT_WEIGHT:
            bad.append({"x": c["x"], "y": c["y"], "no": no, "why": "단위중량 없는 직경 %s%d" % dia})
            continue
        out.append({"no": no, "grade": dia[0], "dia": dia[1], "L": L, "N": N, "x": c["x"], "y": c["y"]})
    return out, bad


def to_mm(s, unit):
    """L= 글자 → mm. 자동: 소수점이 있으면 m(1.050), 없으면 mm(4828·4,828 — 쉼표는 천 단위)."""
    v = float(s.replace(",", ""))
    if unit == LEN_UNITS[2] or (unit == LEN_UNITS[0] and "." in s):
        return round(v * 1000.0, 6)
    return v


def _natural(s):
    return [int(p) if p.isdigit() else p for p in re.findall(r"\d+|\D+", s)]


def order(details, how=SORTS[0]):
    """상세 배치 순(열 왼→오, 열 안 위→아래)으로 머리 글자가 처음 나온 순서 → 그 안에서 번호 순. 또는 번호 이름순."""
    if how == SORTS[1]:
        return sorted(details, key=lambda d: _natural(d["no"]))
    seq = C.sort_points(details, "좌→우 우선, 위→아래", key=lambda d: (d["x"], d["y"], 0.0))
    first = {}
    for d in seq:
        p = re.match(r"\D*", d["no"]).group(0)
        first.setdefault(p, len(first))
    return sorted(details, key=lambda d: (first[re.match(r"\D*", d["no"]).group(0)], _natural(d["no"])))


def duplicates(details):
    seen, dup = set(), []
    for d in details:
        if d["no"] in seen and d["no"] not in dup:
            dup.append(d["no"])
        seen.add(d["no"])
    return dup


def compute(details, cfg):
    """→ 표 목록 [{grade, rows: [[...8칸]], kinds: ['row'|'sub'|'total']}] (강도별이면 여럿)."""
    pct = float(cfg["할증"])
    note = cfg["비고"]
    pri = [g.strip().upper() for g in str(cfg["우선"]).split(",") if g.strip()]
    gr_of = (lambda d: d["grade"]) if cfg["강도별"] else (lambda d: "")
    grades = sorted({gr_of(d) for d in details}, key=lambda g: pri.index(g) if g in pri else len(pri))
    tables = []
    for g in grades:
        ds = order([d for d in details if gr_of(d) == g], cfg["정렬"])
        keys = sorted({(d["grade"], d["dia"]) for d in ds}, key=lambda k: (-k[1], pri.index(k[0]) if k[0] in pri else 99))
        rows, kinds, tw, tw2 = [], [], 0.0, 0.0
        for k in keys:
            grp = [d for d in ds if (d["grade"], d["dia"]) == k]
            sub = 0.0
            for d in grp:
                # 총길이는 표에 보이는 값(소수 셋째)으로 더한다 — 개수가 소수(3.33)면 곱이 길어진다
                tl = float(C.fmt(float(C.fmt(d["L"] / 1000.0, 3)) * float(d["N"]), 3))
                sub += tl
                rows.append([d["no"], "%s%d" % k, C.fmt(d["L"] / 1000.0, 3), str(d["N"]), C.fmt(tl, 3), "", "",
                             ("ADD %g%%" % pct if note == NOTES[0] else "%g%% 할증" % pct if note == NOTES[1] else "")
                             if not rows and pct > 0 else ""])  # 표 첫 줄에만(견본)
                kinds.append("row")
            w = float(C.fmt(sub * UNIT_WEIGHT[k[1]] / 1000.0, 3))
            w2 = float(C.fmt(sub * UNIT_WEIGHT[k[1]] * (1 + pct / 100.0) / 1000.0, 3))
            tw, tw2 = tw + w, tw2 + w2
            ws = C.fmt(w, 3) + "TON"
            if note == NOTES[2] and pct > 0:
                ws, extra = "%sTON(%g%%)" % (C.fmt(w2, 3), pct), ""
            else:
                extra = (C.fmt(w2, 3) + "TON") if note in NOTES[:2] and pct > 0 else ""
            rows.append(["소             계", "", "", "", C.fmt(sub, 3), "%sKg/M" % C.fmt(UNIT_WEIGHT[k[1]], 3), ws, extra])
            kinds.append("sub")
        tot = C.fmt(tw2 if note == NOTES[2] and pct > 0 else tw, 3) + "TON"
        rows.append(["총             계", "", "", "", "", "", tot,
                     (C.fmt(tw2, 3) + "TON") if note in NOTES[:2] and pct > 0 else ""])
        kinds.append("total")
        tables.append({"grade": g, "rows": rows, "kinds": kinds, "weight": float(C.fmt(tw, 3)),
                       "weight_add": float(C.fmt(tw2, 3))})
    return tables


def table_lisp(tbl, origin, cfg):
    """표 하나. origin = 표 왼쪽 위(제목 줄 위 모서리). (LISP, 표 너비)."""
    h, rh = float(cfg["문자높이"]), float(cfg["문자높이"]) * float(cfg["칸높이"])
    ws = [float(v) * h for v in str(cfg["열너비"]).split(",")][:8]
    ws += [10 * h] * (8 - len(ws))
    nc = 7 if cfg["비고"] == NOTES[3] else 8  # 비고 표기 안 함이면 비고 열 없이(견본 둘째 표)
    ws = ws[:nc]
    xs = [0.0]
    for w in ws:
        xs.append(xs[-1] + w)
    W = xs[-1]
    ox, oy = float(origin[0]), float(origin[1])
    lt, ll, lb = ls(cfg["문자레이어"]), ls(cfg["선레이어"]), ls(cfg["테두리레이어"])
    st = ('(if (tblsearch "STYLE" "%s") (setvar "TEXTSTYLE" "%s"))' % (ls(cfg["문자스타일"]), ls(cfg["문자스타일"]))
          if cfg["문자스타일"] else "")
    out = ['(setq _ts (getvar "TEXTSTYLE")) %s (bc:ensure-layer "%s" 7) (bc:ensure-layer "%s" 1) (bc:ensure-layer "%s" 3)'
           % (st, lt, ll, lb)]

    def line(x1, y1, x2, y2, lay):
        out.append('(bc:line (list %.6f %.6f 0.0) (list %.6f %.6f 0.0) "%s")' % (ox + x1, oy + y1, ox + x2, oy + y2, lay))

    def text(x, y, s, just, hh=h):
        if s != "":
            out.append('(bc:text (list %.6f %.6f 0.0) "%s" %.6f "%s" "%s" 0.0)' % (ox + x, oy + y, ls(s), hh, lt, just))

    rows, kinds = tbl["rows"], tbl["kinds"]
    n = len(rows) + 1
    text(W / 2, 6 * h, TITLE, "MC", float(cfg["제목높이"]))
    text(1.6 * h, 0.7 * h, cfg["좌상단"], "BL")
    text(W, 0.4 * h, cfg["우상단"], "BR")
    # 가로선: 맨 위·제목 아래·총계 위·맨 아래는 테두리 레이어
    for i in range(n + 1):
        y = -i * rh
        line(0, y, W, y, lb if i in (0, 1, n - 1, n) else ll)
    line(0, 0, 0, -n * rh, lb)
    line(W, 0, W, -n * rh, lb)
    for j in range(4, nc):  # 총길이부터는 끝까지
        line(xs[j], 0, xs[j], -n * rh, ll)
    # 번호~본수 사이 세로선은 소계·총계 칸에서 끊는다(제목 줄과 이어진 철근 줄 묶음마다 한 줄)
    plain = [True] + [k == "row" for k in kinds]
    i = 0
    while i < n:
        if plain[i]:
            e = i
            while e < n and plain[e]:
                e += 1
            for j in (1, 2, 3):
                line(xs[j], -i * rh, xs[j], -e * rh, ll)
            i = e
        else:
            i += 1
    for j, s in enumerate(HEAD[:nc]):
        text((xs[j] + xs[j + 1]) / 2, -0.5 * rh, s, "MC")
    for i, (r, k) in enumerate(zip(rows, kinds), 1):
        y = -(i + 0.5) * rh
        if k == "row":
            text((xs[0] + xs[1]) / 2, y, r[0], "MC")
            text((xs[1] + xs[2]) / 2, y, r[1], "MC")
            text(xs[3] - 0.4 * h, y, r[2], "MR")
            text(xs[4] - 0.4 * h, y, r[3], "MR")
            text(xs[5] - 0.4 * h, y, r[4], "MR")
            if nc == 8:
                text((xs[7] + xs[8]) / 2, y, r[7], "MC")
        else:
            text(xs[4] / 2, y, r[0], "MC")
            text(xs[5] - 0.4 * h, y, r[4], "MR")
            text((xs[5] + xs[6]) / 2, y, r[5], "MC")
            text(xs[7] - 0.4 * h, y, r[6], "MR")
            if nc == 8:
                text(xs[8] - 0.4 * h, y, r[7], "MR")
    out.append('(setvar "TEXTSTYLE" _ts)')
    return "".join(out), W


def tables_lisp(tables, origin, cfg):
    code, x = [], float(origin[0])
    for t in tables:
        c, W = table_lisp(t, (x, origin[1]), cfg)
        code.append(c)
        x += W + float(cfg["표간격"]) * float(cfg["문자높이"])
    return "".join(code)


def bad_lisp(bad):
    """인식 안 된 원 자리에 '철근-인식안됨' 레이어 광선(RAY)."""
    if not bad:
        return ""
    return '(bc:ensure-layer "철근-인식안됨" 1)' + "".join(
        '(entmake (list (quote (0 . "RAY")) (quote (100 . "AcDbEntity")) (cons 8 "철근-인식안됨") (quote (100 . "AcDbRay"))'
        ' (list 10 %.6f %.6f 0.0) (list 11 0.7071067812 0.7071067812 0.0)))' % (b["x"], b["y"]) for b in bad)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "철근 재료표 작성", size="580x820")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Label(self, text="철근 상세(원·밑줄·직경·L=·N= 문자)를 모두 고른 뒤 표 넣을 점(왼쪽 위)을 지정합니다.",
                 bg=ui.BG, fg=ui.STATUS, font=ui.FONT, wraplength=540, justify="left").pack(fill="x", padx=10)
        tk.Button(self, text="철근 상세 선택 → 재료표 그리기", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        body = ('(princ "\\n철근 상세 선택: ") (setq _ss (ssget (quote ((0 . "CIRCLE,INSERT,TEXT,MTEXT,LINE,LWPOLYLINE"))))) %s'
                ' (if _ss (progn (setq _o (getpoint "\\n재료표 넣을 점(왼쪽 위) 지정: "))'
                ' (if _o (progn (setq _o (trans _o 1 0)) (write-line (strcat "O" _d (bc:rtos (car _o) 2 10) _d'
                ' (bc:rtos (cadr _o) 2 10)) _fp)))))' % DUMP_LISP)
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
        if not rows:
            self.status("고른 객체가 없습니다.")
            return
        details, bad = recognize(*parse_dump(rows), cfg)
        if not details:
            self.error("철근 상세를 찾지 못했습니다(원 안 번호, 밑줄 위 직경·L=·N= 문자 확인).")
            return
        dup = duplicates(details)
        if dup and not messagebox_yes(self, "같은 번호가 여러 번 나옵니다: %s\n그대로 재료표를 만들까요?" % ", ".join(dup)):
            return
        org = [r.split("\t") for r in rows if r.startswith("O\t")]
        tables = compute(details, cfg)
        code = bad_lisp(bad) + (tables_lisp(tables, (float(org[0][1]), float(org[0][2])), cfg) if org else "")
        if code and self.in_cad(self.acad.lisp_undo, code, 180) is None:
            return
        msg = "철근 %d개, 표 %d개, 총중량 %s" % (len(details), len(tables),
                                         " / ".join("%s %.3fTON" % (t["grade"] or "", t["weight"]) for t in tables))
        if bad:
            msg += " — 인식 안 됨 %d곳('철근-인식안됨' 레이어 광선)" % len(bad)
        self.status(msg)


def messagebox_yes(parent, msg):
    from tkinter import messagebox
    return messagebox.askyesno(CMD, msg, parent=parent)


def main():
    Window().mainloop()
