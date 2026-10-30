# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""정밀 기하 일괄 조회·XREF 조회·배치/뷰포트 조회(읽기 전용).

LISP로 한 번에 읽어 탭 구분 줄로 받는다. 좌표는 모두 WCS [x, y, z]로 바꿔 돌려준다
(LWPOLYLINE·원·호·문자·블록의 정의점은 개체 OCS라 법선이 -Z인 '뒤집힌' 개체는 x가 반대로 저장된다).
"""

import math
from typing import List

try:
    from . import validators as V
except ImportError:
    import validators as V

# 개체 한 건에 싣는 꼭짓점 수 상한(한 페이지 256KB 안에 들도록). 더 긴 선은 vertex_start로 나눠 읽는다.
MAX_VERTICES = 3000

# 본문 앞에 붙는 함수들. _d(탭)·_fp(결과 파일)는 bc:job의 지역 변수를 그대로 쓴다(동적 범위).
#   bcg:put  한 칸(탭 + 키=값)을 줄바꿈 없이 바로 파일에 쓴다 — 긴 꼭짓점 목록을 strcat으로 모으지 않는다.
#   bcg:flat 법선이 +Z면 1, -Z면 -1, 비스듬하면 0.
#   bcg:verts 꼭짓점 목록 ((점 4번째값) ...) 중 st부터 mx개만 쓴다. 4번째 값은 볼록(bulge)이나 가중치.
_GEOM_DEFUN = (
    "(defun bcg:n (v) (rtos v 2 10))"
    "(defun bcg:p (p) (strcat (bcg:n (car p)) \",\" (bcg:n (cadr p)) \",\" (bcg:n (if (cddr p) (caddr p) 0.0))))"
    "(defun bcg:put (k v) (princ (strcat _d k \"=\" v) _fp))"
    "(defun bcg:deg (a) (bcg:n (* a (/ 180.0 pi))))"
    "(defun bcg:ang (a / t2) (setq t2 (* 2.0 pi)) (rem (+ (rem a t2) t2) t2))"
    "(defun bcg:rot (a fl) (if (= fl -1) (bcg:ang (- pi a)) a))"
    "(defun bcg:flat (n)"
    " (if (and (equal (car n) 0.0 1e-10) (equal (cadr n) 0.0 1e-10)) (if (< (caddr n) 0) -1 1) 0))"
    "(defun bcg:nrm (e) (if (assoc 210 e) (cdr (assoc 210 e)) (list 0.0 0.0 1.0)))"
    "(defun bcg:g (k e d) (if (assoc k e) (cdr (assoc k e)) d))"
    "(defun bcg:len (en / r)"
    " (setq r (vl-catch-all-apply (function (lambda () (vlax-curve-getDistAtParam en (vlax-curve-getEndParam en)))) nil))"
    " (if (and r (not (vl-catch-all-error-p r)) (numberp r)) (bcg:put \"len\" (bcg:n r))))"
    "(defun bcg:verts (vs st mx / k first)"
    " (bcg:put \"n\" (itoa (length vs))) (bcg:put \"vs\" (itoa st))"
    " (princ (strcat _d \"v=\") _fp) (setq k 0 first T)"
    " (foreach v vs"
    "  (if (and (>= k st) (< k (+ st mx)))"
    "   (progn (princ (strcat (if first \"\" \";\") (bcg:p (car v)) \",\" (bcg:n (cadr v))) _fp) (setq first nil)))"
    "  (setq k (1+ k))))"
    "(defun bcg:nums (k lst / first)"
    " (princ (strcat _d k \"=\") _fp) (setq first T)"
    " (foreach x lst (princ (strcat (if first \"\" \";\") (bcg:n x)) _fp) (setq first nil)))"
    "(defun bcg:pts (k lst mx / first c)"
    " (princ (strcat _d k \"=\") _fp) (setq first T c 0)"
    " (foreach p lst (if (< c mx) (progn (princ (strcat (if first \"\" \";\") (bcg:p p)) _fp) (setq first nil c (1+ c))))))"
    "(defun bcg:row (i e en st mx / ty fl el vs v ve vf hp a0 a1 c r ob nm)"
    " (setq ty (cdr (assoc 0 e)) fl (bcg:flat (bcg:nrm e)))"
    " (princ (strcat (itoa i) _d (cdr (assoc 5 e)) _d ty _d (cdr (assoc 8 e))) _fp)"
    " (if (/= fl 1) (bcg:put \"nz\" (bcg:p (bcg:nrm e))))"
    " (cond"
    "  ((= ty \"LINE\") (bcg:put \"p1\" (bcg:p (cdr (assoc 10 e)))) (bcg:put \"p2\" (bcg:p (cdr (assoc 11 e)))))"
    "  ((= ty \"POINT\") (bcg:put \"p\" (bcg:p (cdr (assoc 10 e)))))"
    "  ((= ty \"LWPOLYLINE\")"
    "   (setq el (bcg:g 38 e 0.0) vs nil)"
    "   (foreach g e"
    "    (cond ((= (car g) 10) (setq vs (cons (list (trans (list (cadr g) (caddr g) el) en 0) 0.0) vs)))"
    "          ((and (= (car g) 42) vs) (setq vs (cons (list (car (car vs)) (if (= fl -1) (- (cdr g)) (cdr g))) (cdr vs))))))"
    "   (bcg:put \"cl\" (itoa (logand (bcg:g 70 e 0) 1)))"
    "   (bcg:verts (reverse vs) st mx))"
    "  ((= ty \"POLYLINE\")"
    "   (setq vf (bcg:g 70 e 0) hp (cdr (assoc 10 e)) vs nil v (entnext en))"
    "   (bcg:put \"cl\" (itoa (logand vf 1))) (bcg:put \"3d\" (if (/= 0 (logand vf 8)) \"1\" \"0\"))"
    "   (if (/= 0 (logand vf 80)) (bcg:put \"mesh\" \"1\")"
    "    (progn"
    "     (while (and v (= (cdr (assoc 0 (setq ve (entget v)))) \"VERTEX\"))"
    "      (if (= 0 (logand (bcg:g 70 ve 0) 16))"
    "       (setq vs (cons (list (if (/= 0 (logand vf 8)) (cdr (assoc 10 ve))"
    "                              (trans (list (cadr (assoc 10 ve)) (caddr (assoc 10 ve)) (caddr hp)) en 0))"
    "                            (if (= fl -1) (- (bcg:g 42 ve 0.0)) (bcg:g 42 ve 0.0))) vs)))"
    "      (setq v (entnext v)))"
    "     (bcg:verts (reverse vs) st mx))))"
    "  ((member ty (quote (\"ARC\" \"CIRCLE\")))"
    "   (setq c (trans (cdr (assoc 10 e)) en 0) r (cdr (assoc 40 e)))"
    "   (bcg:put \"c\" (bcg:p c)) (bcg:put \"r\" (bcg:n r))"
    "   (if (= ty \"ARC\")"
    "    (progn (setq a0 (cdr (assoc 50 e)) a1 (cdr (assoc 51 e)))"
    "     (cond ((= fl 1) (setq a0 (bcg:ang a0) a1 (bcg:ang a1)))"
    "           ((= fl -1) (setq r a0 a0 (bcg:ang (- pi a1)) a1 (bcg:ang (- pi r)) r (cdr (assoc 40 e)))))"
    "     (bcg:put \"a0\" (bcg:deg a0)) (bcg:put \"a1\" (bcg:deg a1))"
    "     (if (/= fl 0) (progn (bcg:put \"sp\" (bcg:p (polar c a0 r))) (bcg:put \"ep\" (bcg:p (polar c a1 r))))))))"
    "  ((= ty \"ELLIPSE\")"
    "   (bcg:put \"c\" (bcg:p (cdr (assoc 10 e)))) (bcg:put \"maj\" (bcg:p (cdr (assoc 11 e))))"
    "   (bcg:put \"ratio\" (bcg:n (cdr (assoc 40 e)))) (bcg:put \"t0\" (bcg:n (cdr (assoc 41 e)))) (bcg:put \"t1\" (bcg:n (cdr (assoc 42 e))))"
    "   (bcg:put \"nz\" (bcg:p (bcg:nrm e))))"
    "  ((= ty \"SPLINE\")"
    "   (setq vs nil c nil r nil ob nil)"
    "   (foreach g e (cond ((= (car g) 10) (setq vs (cons (list (cdr g) 1.0) vs)))"
    "                      ((= (car g) 41) (setq ob (cons (cdr g) ob)))"
    "                      ((= (car g) 40) (setq r (cons (cdr g) r)))"
    "                      ((= (car g) 11) (setq c (cons (cdr g) c)))))"
    "   (bcg:put \"deg\" (itoa (bcg:g 71 e 3))) (bcg:put \"sf\" (itoa (bcg:g 70 e 0)))"
    "   (if (and ob (= (length ob) (length vs))) (setq vs (mapcar (function (lambda (p w) (list (car p) w))) vs ob)))"
    "   (bcg:verts (reverse vs) st mx) (bcg:nums \"k\" (reverse r)) (bcg:pts \"f\" (reverse c) mx))"
    "  ((member ty (quote (\"TEXT\" \"ATTDEF\")))"
    "   (bcg:put \"ip\" (bcg:p (trans (cdr (assoc 10 e)) en 0)))"
    "   (if (or (/= 0 (bcg:g 72 e 0)) (/= 0 (bcg:g (if (= ty \"TEXT\") 73 74) e 0)))"
    "    (bcg:put \"ap\" (bcg:p (trans (cdr (assoc 11 e)) en 0))))"
    "   (bcg:put \"h\" (bcg:n (cdr (assoc 40 e)))) (bcg:put \"rot\" (bcg:deg (bcg:rot (bcg:g 50 e 0.0) fl)))"
    "   (bcg:put \"wf\" (bcg:n (bcg:g 41 e 1.0))) (bcg:put \"hj\" (itoa (bcg:g 72 e 0)))"
    "   (bcg:put \"vj\" (itoa (bcg:g (if (= ty \"TEXT\") 73 74) e 0))) (bcg:put \"st\" (bcg:g 7 e \"\"))"
    "   (if (= ty \"ATTDEF\") (bcg:put \"tag\" (bcg:g 2 e \"\"))))"
    "  ((= ty \"MTEXT\")"
    "   (bcg:put \"ip\" (bcg:p (cdr (assoc 10 e)))) (bcg:put \"h\" (bcg:n (cdr (assoc 40 e))))"
    "   (bcg:put \"w\" (bcg:n (bcg:g 41 e 0.0))) (bcg:put \"att\" (itoa (bcg:g 71 e 1))) (bcg:put \"st\" (bcg:g 7 e \"\"))"
    "   (bcg:put \"rot\" (bcg:deg (if (assoc 11 e) (angle (list 0.0 0.0) (cdr (assoc 11 e))) (bcg:g 50 e 0.0)))))"
    "  ((= ty \"INSERT\")"
    "   (setq ob (vlax-ename->vla-object en)"
    "    nm (vl-catch-all-apply (function vla-get-EffectiveName) (list ob)))"
    "   (bcg:put \"nm\" (cdr (assoc 2 e)))"
    "   (if (and nm (not (vl-catch-all-error-p nm)) (/= nm (cdr (assoc 2 e)))) (bcg:put \"en\" nm))"
    "   (bcg:put \"ip\" (bcg:p (trans (cdr (assoc 10 e)) en 0)))"
    "   (bcg:put \"sx\" (bcg:n (bcg:g 41 e 1.0))) (bcg:put \"sy\" (bcg:n (bcg:g 42 e 1.0))) (bcg:put \"sz\" (bcg:n (bcg:g 43 e 1.0)))"
    "   (bcg:put \"rot\" (bcg:deg (bcg:rot (bcg:g 50 e 0.0) fl))) (bcg:put \"atr\" (itoa (bcg:g 66 e 0))))"
    "  ((= ty \"HATCH\")"
    "   (setq r (vl-catch-all-apply (function vla-get-Area) (list (vlax-ename->vla-object en))))"
    "   (bcg:put \"pat\" (bcg:g 2 e \"\")) (bcg:put \"loops\" (itoa (bcg:g 91 e 0)))"
    "   (if (and (numberp r) (not (vl-catch-all-error-p r))) (bcg:put \"area\" (bcg:n r))))"
    "  ((= ty \"DIMENSION\")"
    "   (bcg:put \"meas\" (bcg:n (bcg:g 42 e 0.0))) (bcg:put \"p10\" (bcg:p (cdr (assoc 10 e))))"
    "   (if (assoc 13 e) (bcg:put \"p13\" (bcg:p (cdr (assoc 13 e)))))"
    "   (if (assoc 14 e) (bcg:put \"p14\" (bcg:p (cdr (assoc 14 e)))))"
    "   (bcg:put \"dt\" (bcg:g 1 e \"\"))))"
    " (if (member ty (quote (\"LINE\" \"LWPOLYLINE\" \"POLYLINE\" \"ARC\" \"CIRCLE\" \"ELLIPSE\" \"SPLINE\"))) (bcg:len en))"
    " (if (member ty (quote (\"TEXT\" \"MTEXT\" \"ATTDEF\"))) (bcg:put \"t\" (bcq:text e)))"
    " (write-line \"\" _fp))"
)

_PT = lambda s: [float(x) for x in s.split(",")]  # noqa: E731
# 줄의 키 → (돌려줄 이름, 변환)
_KEYS = {
    "p1": ("start_point", _PT), "p2": ("end_point", _PT), "p": ("point", _PT),
    "c": ("center", _PT), "r": ("radius", float), "a0": ("start_angle", float), "a1": ("end_angle", float),
    "sp": ("arc_start_point", _PT), "ep": ("arc_end_point", _PT),
    "maj": ("major_axis", _PT), "ratio": ("radius_ratio", float), "t0": ("start_param", float),
    "t1": ("end_param", float), "nz": ("normal", _PT),
    "cl": ("closed", lambda s: s == "1"), "3d": ("is_3d", lambda s: s == "1"), "mesh": ("mesh", lambda s: s == "1"),
    "n": ("vertex_count", int), "vs": ("vertex_start", int),
    "deg": ("degree", int), "sf": ("spline_flags", int),
    "k": ("knots", lambda s: [float(x) for x in s.split(";")] if s else []),
    "f": ("fit_points", lambda s: [_PT(p) for p in s.split(";")] if s else []),
    "ip": ("insertion_point", _PT), "ap": ("alignment_point", _PT), "h": ("height", float),
    "rot": ("rotation", float), "wf": ("width_factor", float), "hj": ("h_justify", int),
    "vj": ("v_justify", int), "st": ("style", str), "tag": ("tag", str), "w": ("width", float),
    "att": ("attachment", int), "nm": ("block_name", str), "en": ("effective_name", str),
    "sx": ("x_scale", float), "sy": ("y_scale", float), "sz": ("z_scale", float), "atr": ("has_attributes", lambda s: s == "1"),
    "pat": ("pattern", str), "loops": ("loop_count", int), "area": ("area", float),
    "meas": ("measurement", float), "p10": ("dim_line_point", _PT), "p13": ("ext_point1", _PT),
    "p14": ("ext_point2", _PT), "dt": ("text_override", str), "len": ("length", float),
}


def parse_geom_line(line: str) -> dict:
    cells = line.split("\t")
    row = {"index": int(cells[0]), "handle": cells[1], "type": cells[2], "layer": cells[3]}
    rest = cells[4:]
    for j, cell in enumerate(rest):
        k, _, v = cell.partition("=")
        if k == "t":  # 문자 내용은 맨 끝 칸 — 안에 탭이 있어도 나머지를 붙인다
            row["text"] = "\t".join([v] + rest[j + 1:])
            break
        if k == "v":
            pts = [[float(x) for x in p.split(",")] for p in v.split(";")] if v else []
            if row["type"] == "SPLINE":
                row["control_points"] = [p[:3] for p in pts]
                if any(p[3] != 1.0 for p in pts):
                    row["weights"] = [p[3] for p in pts]
            else:
                # [x, y, z, bulge] — bulge는 그 꼭짓점에서 다음 꼭짓점까지 호의 tan(사잇각/4), +는 반시계
                row["vertices"] = pts
            continue
        name, conv = _KEYS.get(k, (k, str))
        row[name] = conv(v)
    if "vertex_count" in row:
        got = len(row.get("vertices", row.get("control_points", [])))
        end = row["vertex_start"] + got
        if end < row["vertex_count"]:
            row["vertices_truncated"] = True
            row["next_vertex_start"] = end
    return row


def geometry_body(handles: List[str], vertex_start: int, max_vertices: int) -> str:
    lits = " ".join('"%s"' % V.lisp_str(h) for h in handles)
    return (_GEOM_DEFUN +
            "(setq _i 0)"
            "(foreach _h (list " + lits + ")"
            " (if (and (setq _en (handent _h)) (setq _e (entget _en)) (assoc 8 _e))"
            "  (bcg:row _i _e _en %d %d))"
            " (setq _i (1+ _i)))" % (vertex_start, max_vertices))


# ---------------------------------------------------------------- XREF

# XR<탭>이름<탭>플래그<탭>경로 / RF<탭>이름<탭>핸들<탭>배치<탭>레이어<탭>x,y,z<탭>sx<탭>sy<탭>sz<탭>회전(도)
XREF_BODY = (
    "(setq _t (tblnext \"BLOCK\" T) _m nil)"
    "(while _t"
    " (if (/= 0 (logand (cdr (assoc 70 _t)) 4))"
    "  (progn (setq _m (cons (cdr (assoc 2 _t)) _m))"
    "   (write-line (strcat \"XR\" _d (cdr (assoc 2 _t)) _d (itoa (cdr (assoc 70 _t))) _d"
    "    (if (assoc 1 _t) (cdr (assoc 1 _t)) \"\")) _fp)))"
    " (setq _t (tblnext \"BLOCK\")))"
    "(if (and _m (setq _ss (ssget \"_X\" (list (cons 0 \"INSERT\")))))"
    " (progn (setq _n (sslength _ss) _k 0)"
    "  (while (< _k _n)"
    "   (setq _en (ssname _ss _k) _e (entget _en) _k (1+ _k))"
    "   (if (member (cdr (assoc 2 _e)) _m)"
    "    (write-line (strcat \"RF\" _d (cdr (assoc 2 _e)) _d (cdr (assoc 5 _e)) _d"
    "     (if (assoc 410 _e) (cdr (assoc 410 _e)) (if (= 1 (cdr (assoc 67 _e))) \"*Paper\" \"Model\")) _d"
    "     (cdr (assoc 8 _e)) _d (bcg:p (trans (cdr (assoc 10 _e)) _en 0)) _d"
    "     (bcg:n (bcg:g 41 _e 1.0)) _d (bcg:n (bcg:g 42 _e 1.0)) _d (bcg:n (bcg:g 43 _e 1.0)) _d"
    "     (bcg:deg (bcg:g 50 _e 0.0))) _fp)))))"
)


def parse_xrefs(lines: List[str], max_refs: int) -> dict:
    xrefs, order = {}, []
    for ln in lines:
        c = ln.split("\t")
        if c[0] == "XR" and len(c) >= 4:
            f = int(c[2])
            xrefs[c[1]] = {"name": c[1], "path": c[3], "overlay": bool(f & 8), "nested": bool(f & 16),
                           "resolved": bool(f & 32), "flags": f, "ref_count": 0, "refs": []}
            order.append(c[1])
    for ln in lines:
        c = ln.split("\t")
        if c[0] == "RF" and len(c) >= 10 and c[1] in xrefs:
            x = xrefs[c[1]]
            x["ref_count"] += 1
            if len(x["refs"]) < max_refs:
                x["refs"].append({"handle": c[2], "layout": c[3], "layer": c[4], "insertion_point": _PT(c[5]),
                                  "scale": [float(c[6]), float(c[7]), float(c[8])], "rotation": float(c[9])})
    out = [xrefs[n] for n in order]
    for x in out:
        if x["ref_count"] > len(x["refs"]):
            x["refs_truncated"] = True
    return {"count": len(out), "xrefs": out}


# ---------------------------------------------------------------- 배치·뷰포트

# VP<탭>핸들<탭>배치<탭>레이어<탭>중심<탭>폭<탭>높이<탭>뷰중심(DCS)<탭>목표<탭>방향<탭>뷰높이<탭>비틀림(도)<탭>90플래그<탭>68상태<탭>자르기핸들
# FZ<탭>뷰포트핸들<탭>동결 레이어 이름
VIEWPORT_BODY = (
    "(setq _ss (ssget \"_X\" (list (cons 0 \"VIEWPORT\"))) _m 0)"
    "(if _ss (progn (setq _n (sslength _ss) _k 0)"
    " (while (< _k _n)"
    "  (setq _en (ssname _ss _k) _e (entget _en) _k (1+ _k))"
    "  (if (/= 1 (bcg:g 69 _e 0))"  # 69=1은 배치 자체(종이 전체)의 뷰포트
    "   (progn (setq _m (1+ _m))"
    "    (write-line (strcat \"VP\" _d (cdr (assoc 5 _e)) _d (bcg:g 410 _e \"\") _d (cdr (assoc 8 _e)) _d"
    "     (bcg:p (cdr (assoc 10 _e))) _d (bcg:n (cdr (assoc 40 _e))) _d (bcg:n (cdr (assoc 41 _e))) _d"
    "     (bcg:p (cdr (assoc 12 _e))) _d (bcg:p (bcg:g 17 _e (list 0.0 0.0 0.0))) _d"
    "     (bcg:p (bcg:g 16 _e (list 0.0 0.0 1.0))) _d (bcg:n (cdr (assoc 45 _e))) _d"
    "     (bcg:deg (bcg:g 51 _e 0.0)) _d (itoa (bcg:g 90 _e 0)) _d (itoa (bcg:g 68 _e 0)) _d"
    "     (if (assoc 340 _e) (cdr (assoc 5 (entget (cdr (assoc 340 _e))))) \"\")) _fp)"
    "    (foreach _t _e"
    "     (if (and (= (car _t) 341) (setq _c (entget (cdr _t))))"
    "      (write-line (strcat \"FZ\" _d (cdr (assoc 5 _e)) _d (cdr (assoc 2 _c))) _fp))))))))"
    "(write-line (strcat \"TOTAL\" _d (itoa _m)) _fp)"
)


def parse_viewports(lines: List[str], max_frozen: int) -> list:
    vps, by = [], {}
    for ln in lines:
        c = ln.split("\t")
        if c[0] == "VP" and len(c) >= 15:
            w, h, vh = float(c[5]), float(c[6]), float(c[10])
            vc, tg, dr = _PT(c[7]), _PT(c[8]), _PT(c[9])
            twist = float(c[11])
            vp = {"handle": c[1], "layout": c[2], "layer": c[3], "center": _PT(c[4])[:2], "width": w, "height": h,
                  "view_height": vh, "twist": twist, "locked": bool(int(c[12]) & 16384), "on": int(c[13]) != 0,
                  "frozen_layer_count": 0, "frozen_layers": []}
            if c[14]:
                vp["clip_handle"] = c[14]
            if vh > 0:
                vp["scale"] = h / vh  # 종이 길이 / 모형 길이
                vp["scale_1_to"] = vh / h if h > 0 else None
            plan = abs(dr[0]) < 1e-12 and abs(dr[1]) < 1e-12 and dr[2] > 0
            vp["plan_view"] = plan
            if plan and abs(twist) < 1e-9 and h > 0:
                # 평면 보기·비틀림 없음이면 DCS 원점 = 목표점이라 모형 중심 = 목표 + 뷰중심
                cx, cy = tg[0] + vc[0], tg[1] + vc[1]
                mw = vh * w / h
                vp["model_center"] = [cx, cy]
                vp["model_window"] = [cx - mw / 2, cy - vh / 2, cx + mw / 2, cy + vh / 2]
            else:
                vp["view_center_dcs"] = vc[:2]
                vp["view_target"] = tg
                vp["view_direction"] = dr
            by[c[1]] = vp
            vps.append(vp)
    for ln in lines:
        c = ln.split("\t")
        if c[0] == "FZ" and len(c) >= 3 and c[1] in by:
            vp = by[c[1]]
            vp["frozen_layer_count"] += 1
            if len(vp["frozen_layers"]) < max_frozen:
                vp["frozen_layers"].append(c[2])
    return vps


def layout_info(doc) -> list:
    """배치 탭 목록(COM). 플롯 설정은 이름만 읽는다(바꾸지 않는다)."""
    units = {0: "inch", 1: "mm", 2: "pixel"}
    out = []
    los = doc.Layouts
    for i in range(los.Count):
        lo = los.Item(i)
        row = {"name": lo.Name, "tab_order": int(lo.TabOrder), "model": bool(lo.ModelType)}
        for key, attr in (("plotter", "ConfigName"), ("media", "CanonicalMediaName"), ("plot_style", "StyleSheet")):
            try:
                row[key] = getattr(lo, attr)
            except Exception:
                pass
        try:
            w, h = lo.GetPaperSize()
            row["paper_size"] = [w, h]
            row["paper_units"] = units.get(int(lo.PaperUnits), str(lo.PaperUnits))
        except Exception:
            pass
        try:
            row["plot_rotation_deg"] = int(lo.PlotRotation) * 90
        except Exception:
            pass
        out.append(row)
    out.sort(key=lambda r: r["tab_order"])
    return out


# ---------------------------------------------------------------- 문자 겹침 검수

# TB<탭>핸들<탭>배치<탭>레이어<탭>종류<탭>문자(앞 60자)<탭>x,y;x,y;x,y;x,y (WCS 네 모서리)
# TEXT는 textbox(개체 좌표, 정렬·폭 비율 반영)를 회전·OCS→WCS로, MTEXT는 실제 폭·높이(42·43)와 붙임점(71)·방향(11)으로.
# 블록 안 문자·속성은 보지 않는다. 꺼진·동결 레이어는 include_hidden이 아니면 뺀다.
_TB_DEFUN = (
    "(defun bcg:xy (p) (strcat (bcg:n (car p)) \",\" (bcg:n (cadr p))))"
    "(defun bcg:tb (en e / ty b o a q u v xa ya nz w h at col row vt pts)"
    " (setq ty (cdr (assoc 0 e)))"
    " (cond"
    "  ((= ty \"TEXT\")"
    "   (if (setq b (textbox e))"
    "    (progn (setq o (cdr (assoc 10 e)) a (bcg:g 50 e 0.0))"
    "     (foreach q (list (list (car (car b)) (cadr (car b))) (list (car (cadr b)) (cadr (car b)))"
    "                      (list (car (cadr b)) (cadr (cadr b))) (list (car (car b)) (cadr (cadr b))))"
    "      (setq u (car q) v (cadr q)"
    "            pts (cons (trans (list (+ (car o) (- (* u (cos a)) (* v (sin a)))) (+ (cadr o) (* u (sin a)) (* v (cos a)))"
    "                                   (if (caddr o) (caddr o) 0.0)) en 0) pts))))))"
    "  ((= ty \"MTEXT\")"
    "   (setq o (cdr (assoc 10 e)) nz (bcg:nrm e) w (bcg:g 42 e 0.0) h (bcg:g 43 e 0.0) at (bcg:g 71 e 1)"
    "         xa (if (assoc 11 e) (cdr (assoc 11 e)) (list (cos (bcg:g 50 e 0.0)) (sin (bcg:g 50 e 0.0)) 0.0)))"
    "   (setq a (distance '(0 0) (list (car xa) (cadr xa))))"
    "   (if (and (> a 1e-12) (> w 0.0) (> h 0.0))"
    "    (progn (setq xa (list (/ (car xa) a) (/ (cadr xa) a)) ya (list (- (* (caddr nz) (cadr xa))) (* (caddr nz) (car xa)))"
    "                 col (rem (1- at) 3) row (/ (1- at) 3) u (* -0.5 w col) vt (* 0.5 h row))"
    "     (foreach q (list (list u vt) (list (+ u w) vt) (list (+ u w) (- vt h)) (list u (- vt h)))"
    "      (setq pts (cons (list (+ (car o) (* (car q) (car xa)) (* (cadr q) (car ya)))"
    "                            (+ (cadr o) (* (car q) (cadr xa)) (* (cadr q) (cadr ya)))) pts)))))))"
    " (if pts"
    "  (write-line (strcat \"TB\" _d (cdr (assoc 5 e)) _d"
    "   (if (assoc 410 e) (cdr (assoc 410 e)) (if (= 1 (bcg:g 67 e 0)) \"*Paper\" \"Model\")) _d"
    "   (cdr (assoc 8 e)) _d ty _d (vl-string-translate \"\\t\\n\\r\" \"   \" (substr (bcg:g 1 e \"\") 1 60)) _d"
    "   (bcg:xy (nth 3 pts)) \";\" (bcg:xy (nth 2 pts)) \";\" (bcg:xy (nth 1 pts)) \";\" (bcg:xy (nth 0 pts))) _fp)))"
)


def text_boxes_body(layer: str, include_hidden: bool) -> str:
    flt = "(list (cons 0 \"TEXT,MTEXT\")%s)" % ((" (cons 8 \"%s\")" % V.lisp_str(layer)) if layer else "")
    hide = "" if include_hidden else (
        " (setq _t (tblsearch \"LAYER\" (cdr (assoc 8 _e))))"
        " (if (and _t (or (/= 0 (logand (cdr (assoc 70 _t)) 1)) (< (cdr (assoc 62 _t)) 0))) (setq _e nil))")
    return (_GEOM_DEFUN + _TB_DEFUN +
            "(if (setq _ss (ssget \"_X\" " + flt + "))"
            " (progn (setq _n (sslength _ss) _k 0)"
            "  (while (< _k _n)"
            "   (setq _en (ssname _ss _k) _e (entget _en) _k (1+ _k))" + hide +
            "   (if _e (bcg:tb _en _e)))))")


def parse_text_boxes(lines: List[str]) -> list:
    out = []
    for ln in lines:
        c = ln.split("\t")
        if c[0] == "TB" and len(c) >= 7:
            pts = [tuple(float(v) for v in p.split(",")) for p in c[6].split(";")]
            if len(pts) == 4:
                out.append({"handle": c[1], "layout": c[2], "layer": c[3], "type": c[4], "text": c[5], "box": pts})
    return out


def _area(poly) -> float:
    # 신발끈 공식, 반시계면 양수
    return 0.5 * sum(poly[i - 1][0] * poly[i][1] - poly[i][0] * poly[i - 1][1] for i in range(len(poly)))


def _ccw(poly):
    return poly if _area(poly) >= 0 else poly[::-1]


def _clip(subject, clip):
    """볼록 다각형 교집합(서덜랜드-호지먼). 둘 다 반시계."""
    out = list(subject)
    for i in range(len(clip)):
        if not out:
            break
        a, b = clip[i - 1], clip[i]
        inp, out = out, []

        def side(p):
            return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])

        for j in range(len(inp)):
            p, q = inp[j - 1], inp[j]
            sp, sq = side(p), side(q)
            if sq >= 0:
                if sp < 0:
                    k = sp / (sp - sq)
                    out.append((p[0] + k * (q[0] - p[0]), p[1] + k * (q[1] - p[1])))
                out.append(q)
            elif sp >= 0:
                k = sp / (sp - sq)
                out.append((p[0] + k * (q[0] - p[0]), p[1] + k * (q[1] - p[1])))
    return out


def find_overlaps(boxes: list, window=None, min_ratio: float = 0.0) -> tuple:
    """같은 배치 안에서 문자 상자가 겹치는 짝. ratio = 겹친 넓이 / 작은 상자 넓이. 반환 (검사한 문자 수, 짝 목록)."""
    items = []
    for b in boxes:
        poly = _ccw(b["box"])
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        bb = (min(xs), min(ys), max(xs), max(ys))
        if window and (bb[2] < window[0] or bb[0] > window[2] or bb[3] < window[1] or bb[1] > window[3]):
            continue
        ar = _area(poly)
        if ar > 0:
            items.append((b, poly, bb, ar))
    if not items:
        return 0, []
    # 격자: 칸 크기 = 상자 크기 중앙값의 2배
    sizes = sorted(max(it[2][2] - it[2][0], it[2][3] - it[2][1]) for it in items)
    cell = max(sizes[len(sizes) // 2] * 2.0, 1e-9)
    grid = {}
    for i, it in enumerate(items):
        bb = it[2]
        for gx in range(int(math.floor(bb[0] / cell)), int(math.floor(bb[2] / cell)) + 1):
            for gy in range(int(math.floor(bb[1] / cell)), int(math.floor(bb[3] / cell)) + 1):
                grid.setdefault((it[0]["layout"], gx, gy), []).append(i)
    seen, pairs = set(), []
    for ids in grid.values():
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                i, j = ids[x], ids[y]
                if (i, j) in seen:
                    continue
                seen.add((i, j))
                a, b = items[i], items[j]
                if a[2][2] < b[2][0] or b[2][2] < a[2][0] or a[2][3] < b[2][1] or b[2][3] < a[2][1]:
                    continue
                inter = _clip(a[1], b[1])
                ov = _area(inter) if len(inter) >= 3 else 0.0
                if ov <= 1e-12:
                    continue
                ratio = ov / min(a[3], b[3])
                if ratio < min_ratio:
                    continue
                cx = sum(p[0] for p in inter) / len(inter)
                cy = sum(p[1] for p in inter) / len(inter)
                pairs.append({"a": {k: a[0][k] for k in ("handle", "layer", "type", "text")},
                              "b": {k: b[0][k] for k in ("handle", "layer", "type", "text")},
                              "layout": a[0]["layout"], "overlap_ratio": round(ratio, 4), "overlap_area": ov,
                              "at": [cx, cy], "same_text": a[0]["text"] == b[0]["text"]})
    pairs.sort(key=lambda p: -p["overlap_ratio"])
    return len(items), pairs
