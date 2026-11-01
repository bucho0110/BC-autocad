# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""QCAR 지적별 편입 면적 계산 — 용지 경계와 지적(닫힌 폴리선)이 겹친 편입 면적을 지적마다 구해 번호·목록을 만든다.

겹침은 AutoCAD 영역(REGION) 교집합으로 계산한다(호·맞닿은 변도 정확). 지적 안에 통째로 든 작은 지적은
큰 지적에서 뺀다. 지번은 문자 중심이 그 지적 안(안쪽 지적 밖)에 있는 문자, 행정구역은 지번 위치를 품은
행정구역 경계 안의 구역 문자다. 번호는 선형 좌·우 먼저(또는 측점순)로 매긴다.
classify()·compute()·draw_lisp()는 창 없이도 쓴다(MCP skill_run).
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as X
from skills.common import profile as G
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "QCAR"
ORDERS = ["선형 좌·우 먼저", "선형 측점순"]
FIELDS = [
    ("지적선레이어", "지적선 레이어 (쉼표로 여럿, 비우면 고른 닫힌 폴리선 전부)", "str", "", None),
    ("지번문자레이어", "지번 문자 레이어 (비우면 고른 문자 전부)", "str", "", None),
    ("행정구역레이어", "행정구역 경계 레이어 (비우면 구분 안 함)", "str", "", None),
    ("구역문자레이어", "행정구역 문자 레이어", "str", "", None),
    ("정렬", "번호 순서 (선형이 없으면 위→아래, 좌→우)", "choice", ORDERS[0], ORDERS),
    ("시작번호", "시작 번호", "int", 1, None),
    ("면적소수", "면적 소수 자리", "int", 2, None),
    ("최소면적", "이 면적(m²) 미만은 목록에서 제외 (0=제외 안 함)", "real", 0.0, None),
    ("축척", "축척 (1000=m 도면, 1=mm 도면)", "real", 1000.0, None),
    ("면적선레이어", "면적 산출선 레이어", "str", "편입면적선", None),
    ("면적선색", "면적 산출선 색 (ACI)", "int", 1, None),
    ("번호높이", "번호 문자 높이 (도면 단위)", "real", 2.0, None),
    ("번호레이어", "번호 문자 레이어", "str", "편입번호", None),
    ("해치", "지번을 찾은 편입 부분 해치", "bool", False, None),
    ("해치패턴", "해치 패턴", "str", "ANSI31", None),
    ("해치축척", "해치 축척", "real", 1.0, None),
    ("해치레이어", "해치 레이어", "str", "편입면적해치", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
HEAD = ["행정구역", "번호", "지번", "지목", "면적", "편입면적", "전체편입", "비고"]

# 선택 집합 _ss 덤프: 문자 TX<탭>핸들<탭>레이어<탭>가운데x<탭>y<탭>내용, 닫힌 LWPOLYLINE PG<탭>핸들<탭>레이어 + S 줄들
DUMP_LISP = (
    '(foreach _en (bc:ss-list _ss) (setq _ed (entget _en) _ty (cdr (assoc 0 _ed)))'
    ' (cond ((member _ty (list "TEXT" "MTEXT")) (setq _c (bc:obj-center _en))'
    '  (write-line (strcat "TX" _d (cdr (assoc 5 _ed)) _d (cdr (assoc 8 _ed)) _d (bc:rtos (car _c) 2 10) _d'
    '   (bc:rtos (cadr _c) 2 10) _d (vl-string-translate "\\t\\n\\r" "   " (bc:text-of _en))) _fp))'
    '  ((and (= _ty "LWPOLYLINE") (= 1 (logand 1 (cdr (assoc 70 _ed)))) (not (member _en _skip)))'
    '   (write-line (strcat "PG" _d (cdr (assoc 5 _ed)) _d (cdr (assoc 8 _ed))) _fp) (setq _al _en) %s)))' % G.ALIGN_LISP)


def _layers(s):
    return {x.strip().upper() for x in str(s).split(",") if x.strip()}


def parse_dump(rows):
    """→ (texts [{handle, layer, x, y, text}], polys [{handle, layer, elems}])."""
    texts, polys = [], []
    for r in rows:
        c = r.split("\t")
        if c[0] == "TX" and len(c) >= 6:
            texts.append({"handle": c[1], "layer": c[2], "x": float(c[3]), "y": float(c[4]), "text": c[5].strip()})
        elif c[0] == "PG":
            polys.append({"handle": c[1], "layer": c[2], "elems": []})
        elif c[0] == "S" and polys and len(c) == 6:
            polys[-1]["elems"].append(((float(c[1]), float(c[2])), (float(c[3]), float(c[4])), float(c[5])))
    for p in polys:
        p["pts"] = G.polygon(p["elems"])
        p["area"] = abs(G.area(p["elems"]))
    return texts, [p for p in polys if len(p["pts"]) >= 3]


def classify(texts, polys, cfg):
    """지적·지번·행정구역을 레이어로 가른다. 지적마다 안쪽 지적(children)·지번·행정구역을 붙인다."""
    lp, lt = _layers(cfg["지적선레이어"]), _layers(cfg["지번문자레이어"])
    la, lat = _layers(cfg["행정구역레이어"]), _layers(cfg["구역문자레이어"])
    skip = _layers(cfg["면적선레이어"])
    admin = [p for p in polys if la and p["layer"].upper() in la]
    parcels = [p for p in polys if p["layer"].upper() not in skip and p not in admin
               and (not lp or p["layer"].upper() in lp)]
    jib = [t for t in texts if (not lt or t["layer"].upper() in lt) and not (lat and t["layer"].upper() in lat)]
    names = [t for t in texts if lat and t["layer"].upper() in lat]
    for p in parcels:
        p["children"] = [q for q in parcels if q is not p and q["area"] < p["area"]
                         and all(G.inside(p["pts"], x, y) for x, y in q["pts"][::max(1, len(q["pts"]) // 12)])]
    for p in parcels:
        own = [t for t in jib if G.inside(p["pts"], t["x"], t["y"])
               and not any(G.inside(q["pts"], t["x"], t["y"]) for q in p["children"])]
        p["jibun"] = own[0]["text"] if own else ""
        p["jibun_pt"] = (own[0]["x"], own[0]["y"]) if own else None
        p["admin"] = ""
        ref = p["jibun_pt"] or G.label_point(p["pts"])
        for a in admin:
            if G.inside(a["pts"], *ref):
                nm = [t["text"] for t in names if G.inside(a["pts"], t["x"], t["y"])]
                p["admin"] = nm[0] if nm else ""
                break
    return parcels


def bool_lisp(boundary_handle, parcels) -> str:
    """경계 ∩ 지적 − 안쪽 지적 → B(경계 면적), P(지적 핸들, 지적 면적, 편입 면적) 뒤에 외곽선 L·A 줄."""
    items = " ".join('(list "%s" (list %s))' % (ls(p["handle"]), " ".join('"%s"' % ls(q["handle"]) for q in p["children"]))
                     for p in parcels)
    return (
        '(setq _ms (vla-get-ModelSpace (vla-get-ActiveDocument (vlax-get-acad-object))))'
        '(defun _qc-reg (en / r) (setq r (vl-catch-all-apply (quote vlax-invoke)'
        ' (list _ms (quote AddRegion) (list (vlax-ename->vla-object en)))))'
        ' (if (and (not (vl-catch-all-error-p r)) r) (car r)))'
        '(defun _qc-pt (p) (strcat (bc:rtos (car p) 2 10) _d (bc:rtos (cadr p) 2 10)))'
        '(defun _qc-out (rg / ex nm)'
        ' (setq ex (vl-catch-all-apply (quote vlax-invoke) (list rg (quote Explode))))'
        ' (if (not (vl-catch-all-error-p ex)) (foreach o ex (setq nm (vla-get-ObjectName o))'
        '  (cond ((= nm "AcDbLine") (write-line (strcat "L" _d (_qc-pt (vlax-get o (quote StartPoint))) _d'
        '          (_qc-pt (vlax-get o (quote EndPoint)))) _fp))'
        '        ((= nm "AcDbArc") (write-line (strcat "A" _d (_qc-pt (vlax-get o (quote StartPoint))) _d'
        '          (_qc-pt (vlax-get o (quote EndPoint))) _d (bc:rtos (* (if (< (caddr (vlax-get o (quote Normal))) 0) -1 1)'
        '          (/ (sin (/ (vla-get-TotalAngle o) 4)) (cos (/ (vla-get-TotalAngle o) 4)))) 2 14)) _fp))'
        '        ((= nm "AcDbRegion") (_qc-out o))'
        '        (T (write-line (strcat "W" _d nm) _fp)))'
        '  (vl-catch-all-apply (quote vla-Delete) (list o)))))'
        '(setq _rb (_qc-reg (handent "%s")))'
        '(if _rb (progn (write-line (strcat "B" _d (bc:rtos (vla-get-Area _rb) 2 10)) _fp)'
        ' (vla-GetBoundingBox _rb (quote _bmn) (quote _bmx))'
        ' (setq _bmn (vlax-safearray->list _bmn) _bmx (vlax-safearray->list _bmx))'
        ' (foreach _it (list %s) (setq _en (handent (car _it)) _o (vlax-ename->vla-object _en))'
        '  (vla-GetBoundingBox _o (quote _mn) (quote _mx))'
        '  (setq _mn (vlax-safearray->list _mn) _mx (vlax-safearray->list _mx))'
        '  (if (and (< (car _mn) (car _bmx)) (> (car _mx) (car _bmn)) (< (cadr _mn) (cadr _bmx)) (> (cadr _mx) (cadr _bmn)))'
        '   (progn (setq _rc (vla-Copy _rb) _rp (_qc-reg _en))'
        '    (if (and _rp (not (vl-catch-all-error-p (vl-catch-all-apply (quote vla-Boolean) (list _rc acIntersection _rp)))))'
        '     (progn'
        '      (foreach _ch (cadr _it) (if (setq _rk (_qc-reg (handent _ch)))'
        '        (progn (vl-catch-all-apply (quote vla-Boolean) (list _rc acSubtraction _rk))'
        '               (vl-catch-all-apply (quote vla-Delete) (list _rk)))))'
        '      (if (> (vla-get-Area _rc) 1e-9) (progn'
        '       (write-line (strcat "P" _d (car _it) _d (bc:rtos (vla-get-Area _o) 2 10) _d (bc:rtos (vla-get-Area _rc) 2 10)) _fp)'
        '       (_qc-out _rc)))))'
        '    (vl-catch-all-apply (quote vla-Delete) (list _rc))'
        '    (if _rp (vl-catch-all-apply (quote vla-Delete) (list _rp))))))'
        ' (vla-Delete _rb)))' % (ls(boundary_handle), items))


def _chain(segs):
    """선분·호 [(p, q, bulge)] → 닫힌 고리 목록(각각 요소 목록)."""
    segs, loops = list(segs), []
    near = lambda a, b: abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6  # noqa: E731
    while segs:
        loop = [segs.pop(0)]
        while not near(loop[-1][1], loop[0][0]):
            for i, (p, q, b) in enumerate(segs):
                if near(p, loop[-1][1]):
                    loop.append(segs.pop(i))
                    break
                if near(q, loop[-1][1]):
                    segs.pop(i)
                    loop.append((q, p, -b))
                    break
            else:
                break
        loops.append(loop)
    return loops


def parse_bool(rows):
    """bool_lisp 결과 → (경계 면적, [{handle, parcel_area, area, loops: [요소 목록]}], 경고)."""
    barea, out, warn = None, [], []
    for r in rows:
        c = r.split("\t")
        if c[0] == "B":
            barea = float(c[1])
        elif c[0] == "P":
            out.append({"handle": c[1], "parcel_area": float(c[2]), "area": float(c[3]), "segs": []})
        elif c[0] == "L" and out:
            out[-1]["segs"].append(((float(c[1]), float(c[2])), (float(c[3]), float(c[4])), 0.0))
        elif c[0] == "A" and out:
            out[-1]["segs"].append(((float(c[1]), float(c[2])), (float(c[3]), float(c[4])), float(c[5])))
        elif c[0] == "W":
            warn.append(c[1] if len(c) > 1 else "?")
    for o in out:
        loops = _chain(o.pop("segs"))
        # 안쪽 구멍(다른 고리 안에 든 고리)은 바깥 고리에 붙인다
        info = [(lp, G.polygon(lp), abs(G.area(lp))) for lp in loops]
        pieces = []
        for lp, pts, a in sorted(info, key=lambda t: -t[2]):
            host = next((pc for pc in pieces if G.inside(pc["pts"], *pts[0])), None)
            if host:
                host["holes"].append(lp)
                host["area"] -= a
            else:
                pieces.append({"loop": lp, "pts": pts, "holes": [], "area": a})
        o["pieces"] = pieces
    return barea, out, warn


def compute(parcels, barea, results, elems, cfg):
    """→ (표 행 [HEAD…], 그릴 조각 목록, 요약). 면적은 m²(축척)."""
    u2 = (1000.0 / (cfg["축척"] if cfg["축척"] > 0 else 1000.0)) ** 2
    by = {p["handle"]: p for p in parcels}
    items = []
    for r in results:
        p = by.get(r["handle"])
        if p:  # 지적 면적은 바로 안에 든 지적을 뺀 것
            kids = p["children"]
            r["parcel_area"] -= sum(k["area"] for k in kids if not any(k in d["children"] for d in kids))
        for pc in r["pieces"]:
            a = pc["area"] / u2
            if a < 1e-6 or (cfg["최소면적"] > 0 and a < cfg["최소면적"]):
                continue
            lx, ly = G.label_point(pc["pts"], [G.polygon(h) for h in pc["holes"]])
            s = side = None
            if elems:
                s, off = G.project(elems, lx, ly)
                side = "좌" if off > 0 else "우"
            items.append({"parcel": p, "piece": pc, "area": a, "total": r["parcel_area"] / u2, "label": (lx, ly),
                          "s": s, "side": side})
    # 한 지적의 여러 조각은 한 줄(합산면적)로 — 순서는 그 지적의 첫 조각 자리
    groups = {}
    for it in items:
        groups.setdefault(it["parcel"]["handle"] if it["parcel"] else id(it), []).append(it)
    if elems:
        key = (lambda g: (g[0]["side"] != "좌", min(i["s"] for i in g))) if cfg["정렬"] == ORDERS[0] else \
            (lambda g: min(i["s"] for i in g))
        order = sorted(groups.values(), key=key)
    else:
        order = C.sort_points(list(groups.values()), "위→아래 우선, 좌→우",
                              key=lambda g: (g[0]["label"][0], g[0]["label"][1], 0.0))
    dec = int(cfg["면적소수"])
    rows = [HEAD]
    total = 0.0
    for n, g in enumerate(order, int(cfg["시작번호"])):
        p = g[0]["parcel"] or {}
        a, whole = sum(i["area"] for i in g), g[0]["total"]
        for i in g:
            i["no"] = n
        jb, jm = split_jimok(p.get("jibun", ""))
        full = C.fmt(a, dec) == C.fmt(whole, dec)
        rows.append([p.get("admin", ""), n, jb, jm, C.fmt(whole, dec), C.fmt(a, dec), "○" if full else "",
                     "합산면적" if len(g) > 1 else ""])
        total += float(C.fmt(a, dec))
    b = barea / u2 if barea else 0.0
    diff = total - float(C.fmt(b, dec))
    summary = {"count": len(order), "sum": float(C.fmt(total, dec)), "boundary": float(C.fmt(b, dec)),
               "difference": float(C.fmt(diff, dec))}
    rows += [[], ["", "", "경계 전체 면적", "", "", C.fmt(b, dec)], ["", "", "편입 면적 합계", "", "", C.fmt(total, dec)],
             ["", "", "차이", "", "", C.fmt(diff, dec)]]
    return rows, items, summary


def split_jimok(s):
    """지번 문자 끝 한글 한 글자를 지목으로: '569-7도' → ('569-7', '도'). 없으면 ('569-7', '')."""
    s = s.strip()
    i = len(s)
    while i > 0 and "가" <= s[i - 1] <= "힣":
        i -= 1
    return (s[:i].strip(), s[i:]) if 0 < i < len(s) else (s, "")


def _lw(elems, lay, col):
    vs = " ".join("(list 10 %.10f %.10f) (cons 42 %.14f)" % (p[0], p[1], b) for p, _q, b in elems)
    return ('(entmake (list (quote (0 . "LWPOLYLINE")) (quote (100 . "AcDbEntity")) (cons 8 "%s") (cons 62 %d)'
            ' (quote (100 . "AcDbPolyline")) (cons 90 %d) (cons 70 1) %s))' % (lay, col, len(elems), vs))


def draw_lisp(items, cfg) -> str:
    """면적 산출선(조각 외곽·구멍), 번호, 선택 해치."""
    la, ln, lh = ls(cfg["면적선레이어"]), ls(cfg["번호레이어"]), ls(cfg["해치레이어"])
    out = ['(bc:ensure-layer "%s" %d) (bc:ensure-layer "%s" 7)' % (la, cfg["면적선색"], ln),
           '(setq _ms (vla-get-ModelSpace (vla-get-ActiveDocument (vlax-get-acad-object))))']
    if cfg["해치"]:
        out.append('(bc:ensure-layer "%s" 8)' % lh)
    for it in items:
        pc = it["piece"]
        out.append(_lw(pc["loop"], la, 256))
        if cfg["해치"] and it["parcel"] and it["parcel"]["jibun"]:
            out.append('(setq _o (vlax-ename->vla-object (entlast)) _h (vla-AddHatch _ms acHatchPatternTypePreDefined "%s" :vlax-true))'
                       ' (vlax-invoke _h (quote AppendOuterLoop) (list _o))' % ls(cfg["해치패턴"]))
            for hole in pc["holes"]:
                out.append(_lw(hole, la, 256) + ' (vlax-invoke _h (quote AppendInnerLoop) (list (vlax-ename->vla-object (entlast))))')
            out.append('(vla-put-PatternScale _h %.6f) (vla-put-Layer _h "%s") (vla-Evaluate _h)' % (cfg["해치축척"], lh))
        else:
            out += [_lw(hole, la, 256) for hole in pc["holes"]]
        out.append('(bc:text (list %.6f %.6f 0.0) "%d" %.6f "%s" "MC" 0.0)' % (it["label"][0], it["label"][1], it["no"],
                                                                             cfg["번호높이"], ln))
    return "".join(out)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "지적별 편입 면적 계산", size="580x780")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Label(self, text="엑셀에서 목록을 넣을 첫 셀을 먼저 고른 뒤 실행하세요. 경계·지적은 닫힌 폴리선이어야 합니다.",
                 bg=ui.BG, fg=ui.STATUS, font=ui.FONT, wraplength=540, justify="left").pack(fill="x", padx=10)
        tk.Button(self, text="용지 경계 → 선형(엔터=없음) → 지적·문자 선택", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        body = ('(setq _b (entsel "\\n용지 경계(닫힌 폴리선) 선택: ")) (if _b (progn'
                ' (setq _bd (car _b) _skip (list _bd)) (write-line (strcat "BD" _d (cdr (assoc 5 (entget _bd)))) _fp)'
                ' (setq _a (entsel "\\n중심 선형 선택 (없으면 엔터): "))'
                ' (if _a (progn (setq _al (car _a) _skip (cons _al _skip)) %s))'
                ' (princ "\\n지적선·지번 문자(·행정구역) 범위 선택: ")'
                ' (setq _ss (ssget (list (cons 0 "LWPOLYLINE,TEXT,MTEXT")))) (write-line "ENDAL" _fp) %s))'
                % (G.ALIGN_LISP, DUMP_LISP))
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
        if not rows or not rows[0].startswith("BD\t"):
            return
        try:
            res = run_core(lambda code: self.acad.lisp(code, 300), lambda code: self.acad.lisp_undo(code, 300), rows, cfg)
        except ValueError as e:
            self.error(str(e))
            return
        try:
            ws, r, c = X.active_cell()
            X.write_rows(ws, r, c, res["rows"])
            where = "엑셀 %s!%s행 %s열부터" % (ws.Name, r, c)
        except X.ExcelNotReady as e:
            where = "엑셀에 쓰지 못함(%s)" % e
        sm = res["summary"]
        self.status("편입 %d건, 합계 %s m², 경계 %s m², 차이 %s m² — %s"
                    % (sm["count"], sm["sum"], sm["boundary"], sm["difference"], where))


def run_core(lisp_read, lisp_write, rows, cfg, draw=True):
    """선택 덤프(BD 줄, 선형 S 줄, ENDAL, 지적·문자 덤프) → 계산·작도. 창과 MCP가 함께 쓴다."""
    bd = rows[0].split("\t")[1]
    cut = rows.index("ENDAL") if "ENDAL" in rows else len(rows)
    elems = G.parse_align(rows[1:cut])
    texts, polys = parse_dump(rows[cut + 1:])
    parcels = classify(texts, polys, cfg)
    if not parcels:
        raise ValueError("지적(닫힌 폴리선)을 찾지 못했습니다(지적선 레이어 설정 확인).")
    barea, results, warn = parse_bool(lisp_read(bool_lisp(bd, parcels)))
    if barea is None:
        raise ValueError("용지 경계로 영역을 만들 수 없습니다(닫힌 폴리선인지, 꼬인 곳이 없는지 확인).")
    table, items, summary = compute(parcels, barea, results, elems, cfg)
    if draw and items:
        lisp_write(draw_lisp(items, cfg))
    summary["warnings"] = sorted(set(warn))
    summary["no_jibun"] = sum(1 for it in items if not (it["parcel"] and it["parcel"]["jibun"]))
    return {"rows": table, "summary": summary}


def main():
    Window().mainloop()
