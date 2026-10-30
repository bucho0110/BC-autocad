# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""정밀 기하·XREF·배치 조회 시험(실제 AutoCAD 필요) — 새 도면에서 MCP 도구로.

실행: <python> -X utf8 tests\\test_geom_live.py   끝에 "FAIL: []"이면 통과.
기준값은 vlax-curve(항상 WCS)로 따로 읽어 대조한다.
"""
import asyncio
import json
import math
import os
import sys
import tempfile

sys.dont_write_bytecode = True

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAIL = []


def check(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name, "" if cond else info)
    if not cond:
        FAIL.append(name)


def near(a, b, tol=1e-7):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def bulge_mid(p, q, b):
    """bulge 호의 가운데 점."""
    c = math.dist(p[:2], q[:2])
    s = b * c / 2  # 화살 높이
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    ux, uy = (q[0] - p[0]) / c, (q[1] - p[1]) / c
    return [mx + uy * s, my - ux * s]  # 진행 방향 오른쪽이 +bulge(반시계)의 바깥


# vlax-curve로 기준값: 끝점·중간 매개변수 점·길이
CURVE_REF = ('(setq _en (handent "%s"))'
             '(foreach _a (list (vlax-curve-getStartParam _en) (vlax-curve-getEndParam _en) %s)'
             ' (setq _p (vlax-curve-getPointAtParam _en _a))'
             ' (write-line (strcat (rtos (car _p) 2 10) "," (rtos (cadr _p) 2 10) "," (rtos (caddr _p) 2 10)) _fp))'
             '(write-line (rtos (vlax-curve-getDistAtParam _en (vlax-curve-getEndParam _en)) 2 10) _fp)')


async def main():
    params = StdioServerParameters(command=sys.executable, args=["-X", "utf8", "-B", os.path.join(ROOT, "src", "server.py")])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            async def raw(_tool, **kw):
                res = await s.call_tool(_tool, kw)
                return res.isError, (res.content[0].text if res.content else "")

            async def call(_tool, **kw):
                err, txt = await raw(_tool, **kw)
                if err:
                    raise RuntimeError("%s: %s" % (_tool, txt))
                return json.loads(txt)

            async def lines(code):
                return (await call("run_lisp", code=code))["lines"]

            async def ref(h, params="0.5"):
                out = await lines(CURVE_REF % (h, params))
                pts = [[float(v) for v in ln.split(",")] for ln in out[:-1]]
                return pts, float(out[-1])

            # XREF로 붙일 작은 도면
            src = os.path.join(tempfile.gettempdir(), "bc_geom_xref_src.dwg")
            if os.path.exists(src):
                os.remove(src)
            await call("new_drawing")
            await call("create_line", start_x=0, start_y=0, end_x=5, end_y=5)
            await call("save_drawing", path=src)
            await call("close_drawing", save=False)
            print("시험 도면:", await call("new_drawing"))

            def ent(code):
                return lines(code + '(write-line (cdr (assoc 5 (entget (entlast)))) _fp)')

            # 1) LWPOLYLINE(+Z, 높이 5, 첫 구간 호)
            h1 = (await ent('(entmake (list (cons 0 "LWPOLYLINE") (cons 100 "AcDbEntity") (cons 100 "AcDbPolyline")'
                            ' (cons 90 3) (cons 70 0) (cons 38 5.0) (list 10 0.0 0.0) (cons 42 0.5)'
                            ' (list 10 10.0 0.0) (cons 42 0.0) (list 10 10.0 10.0)))'))[0]
            # 2) 같은 모양, 법선 -Z(뒤집힌 개체)
            h2 = (await ent('(entmake (list (cons 0 "LWPOLYLINE") (cons 100 "AcDbEntity") (cons 100 "AcDbPolyline")'
                            ' (cons 90 3) (cons 70 0) (cons 38 5.0) (list 10 0.0 0.0) (cons 42 0.5)'
                            ' (list 10 10.0 0.0) (cons 42 0.0) (list 10 10.0 10.0) (list 210 0.0 0.0 -1.0)))'))[0]
            g = await call("get_geometry", handles=json.dumps([h1, h2]))
            check("get_geometry 2건", g["returned"] == 2 and g["missing"] == 0, g)
            for row, h in zip(g["entities"], (h1, h2)):
                pts, ln = await ref(h, "0.5 1.0 2.0")
                vs = row["vertices"]
                check("%s 꼭짓점 = vlax-curve" % h,
                      near(vs[0][:3], pts[0]) and near(vs[1][:3], pts[3]) and near(vs[2][:3], pts[4]), (vs, pts))
                check("%s bulge 호 가운데 = vlax-curve 0.5" % h, near(bulge_mid(vs[0], vs[1], vs[0][3]), pts[2][:2]),
                      (bulge_mid(vs[0], vs[1], vs[0][3]), pts[2]))
                check("%s 길이" % h, abs(row["length"] - ln) < 1e-7, (row.get("length"), ln))
            check("뒤집힌 개체는 normal", g["entities"][1].get("normal") == [0, 0, -1] and "normal" not in g["entities"][0],
                  g["entities"])

            # 3) 호(법선 -Z), 원, 문자(-Z), 블록, MTEXT, 타원, 2D·3D 폴리선, 스플라인
            ha = (await ent('(entmake (list (cons 0 "ARC") (list 10 100.0 0.0 0.0) (cons 40 10.0) (cons 50 0.3) (cons 51 1.9)'
                            ' (list 210 0.0 0.0 -1.0)))'))[0]
            hc = (await ent('(entmake (list (cons 0 "CIRCLE") (list 10 200.0 0.0 0.0) (cons 40 3.0)))'))[0]
            ht = (await ent('(entmake (list (cons 0 "TEXT") (list 10 50.0 60.0 0.0) (cons 40 2.0) (cons 1 "가나 = ; 다")'
                            ' (cons 50 0.5) (list 210 0.0 0.0 -1.0)))'))[0]
            hm = (await ent('(entmake (list (cons 0 "MTEXT") (cons 100 "AcDbEntity") (cons 100 "AcDbMText")'
                            ' (list 10 5.0 6.0 0.0) (cons 40 1.5) (cons 41 30.0) (cons 1 "여러줄") (list 11 0.0 1.0 0.0)))'))[0]
            he = (await ent('(entmake (list (cons 0 "ELLIPSE") (cons 100 "AcDbEntity") (cons 100 "AcDbEllipse")'
                            ' (list 10 300.0 0.0 0.0) (list 11 20.0 0.0 0.0) (cons 40 0.5) (cons 41 0.0) (cons 42 3.0)))'))[0]
            hp2 = (await ent('(vla-AddPolyline (vla-get-ModelSpace (vla-get-ActiveDocument (vlax-get-acad-object)))'
                             ' (vlax-make-variant (vlax-safearray-fill (vlax-make-safearray vlax-vbDouble (cons 0 8))'
                             ' (list 400.0 0.0 0.0 410.0 0.0 0.0 410.0 10.0 0.0))))'))[0]
            hp3 = (await ent('(vla-Add3DPoly (vla-get-ModelSpace (vla-get-ActiveDocument (vlax-get-acad-object)))'
                             ' (vlax-make-variant (vlax-safearray-fill (vlax-make-safearray vlax-vbDouble (cons 0 8))'
                             ' (list 500.0 0.0 1.0 510.0 0.0 2.0 510.0 10.0 3.0))))'))[0]
            hs = (await ent('(vla-AddSpline (vla-get-ModelSpace (vla-get-ActiveDocument (vlax-get-acad-object)))'
                            ' (vlax-make-variant (vlax-safearray-fill (vlax-make-safearray vlax-vbDouble (cons 0 11))'
                            ' (list 600.0 0.0 0.0 610.0 5.0 0.0 620.0 0.0 0.0 630.0 8.0 0.0)))'
                            ' (vlax-3d-point 1.0 0.0 0.0) (vlax-3d-point 1.0 0.0 0.0))'))[0]
            await call("create_block", name="BCG_B", base_x=0, base_y=0)
            hb = (await call("insert_block", name="BCG_B", x=700, y=10, x_scale=2, y_scale=3, rotation=30))["handle"]
            hs_list = [ha, hc, ht, hm, he, hp2, hp3, hs, hb, "FFFFFF"]
            g = await call("get_geometry", handles=json.dumps(hs_list))
            by = {e["handle"]: e for e in g["entities"]}
            check("없는 핸들 missing 1", g["missing"] == 1, g)
            a = by[ha]
            pts, ln = await ref(ha, "1.1")  # 호의 매개변수는 OCS 각도 — 0.3~1.9의 가운데
            ends = sorted([a["arc_start_point"], a["arc_end_point"]])
            check("뒤집힌 호 끝점 = vlax-curve(순서 무관)", near(ends[0], sorted(pts[:2])[0]) and near(ends[1], sorted(pts[:2])[1]),
                  (a, pts))
            mid = math.radians((a["start_angle"] + ((a["end_angle"] - a["start_angle"]) % 360) / 2))
            check("뒤집힌 호 반시계 가운데 = 곡선 가운데", near([a["center"][0] + 10 * math.cos(mid), a["center"][1] + 10 * math.sin(mid)],
                                                   pts[2][:2]), (a, pts))
            check("뒤집힌 호 중심 x = -100", near(a["center"], [-100, 0, 0]), a)
            check("호 길이", abs(a["length"] - ln) < 1e-7, (a, ln))
            check("원", near(by[hc]["center"], [200, 0, 0]) and by[hc]["radius"] == 3.0, by[hc])
            t = by[ht]
            ip = await lines('(setq _p (vlax-get (vlax-ename->vla-object (handent "%s")) (quote InsertionPoint)))'
                             '(write-line (strcat (rtos (car _p) 2 10) "," (rtos (cadr _p) 2 10)) _fp)' % ht)
            check("뒤집힌 문자 삽입점 WCS = ActiveX", near(t["insertion_point"][:2], [float(v) for v in ip[0].split(",")]), (t, ip))
            check("문자 내용(=·; 포함)", t["text"] == "가나 = ; 다", t)
            check("뒤집힌 문자 회전 = 180-28.6", abs(t["rotation"] - (180 - math.degrees(0.5))) < 1e-7, t)
            check("MTEXT 회전 90", abs(by[hm]["rotation"] - 90) < 1e-7 and by[hm]["width"] == 30.0, by[hm])
            check("타원", by[he]["major_axis"] == [20, 0, 0] and by[he]["radius_ratio"] == 0.5, by[he])
            p2 = by[hp2]
            check("2D 폴리선 꼭짓점", p2["vertex_count"] == 3 and near(p2["vertices"][2], [410, 10, 0, 0]), p2)
            p3 = by[hp3]
            check("3D 폴리선 z", p3["is_3d"] and near([v[2] for v in p3["vertices"]], [1, 2, 3]), p3)
            sp = by[hs]
            pts, ln = await ref(hs)
            check("스플라인 맞춤점·제어점", len(sp["fit_points"]) == 4 and sp["vertex_count"] >= 4 and sp["degree"] == 3
                  and abs(sp["length"] - ln) < 1e-6, sp)
            b = by[hb]
            check("블록 삽입", b["block_name"] == "BCG_B" and near(b["insertion_point"], [700, 10, 0])
                  and b["x_scale"] == 2 and b["y_scale"] == 3 and abs(b["rotation"] - 30) < 1e-9, b)

            # 4) 긴 선 나눠 읽기
            hl = (await ent('(setq _i 0 _a nil) (repeat 5000 (setq _a (cons (cons 10 (list (* _i 1.0) (sin (* _i 0.01)))) _a) _i (1+ _i)))'
                            '(entmake (append (list (cons 0 "LWPOLYLINE") (cons 100 "AcDbEntity") (cons 100 "AcDbPolyline")'
                            ' (cons 90 5000) (cons 70 0)) (reverse _a)))'))[0]
            allv, st, rounds = [], 0, 0
            while True:
                g = await call("get_geometry", handles=json.dumps([hl]), vertex_start=st, max_vertices=3000)
                row = g["entities"][0]
                allv += row["vertices"]
                rounds += 1
                if not row.get("vertices_truncated"):
                    break
                st = row["next_vertex_start"]
            check("5000점 나눠 읽기(2번)", rounds == 2 and len(allv) == 5000 and near(allv[4999][:2], [4999, math.sin(49.99)]),
                  (rounds, len(allv)))
            err, txt = await raw("get_geometry", handles=json.dumps([hl]), max_vertices=5000)
            check("max_vertices 상한 거절", err, txt)

            # 5) XREF
            await lines('(vla-AttachExternalReference (vla-get-ModelSpace (vla-get-ActiveDocument (vlax-get-acad-object)))'
                        ' "%s" "BCG_X" (vlax-3d-point 1000.0 2000.0 0.0) 1.0 1.0 1.0 0.0 :vlax-false)'
                        '(write-line "" _fp)' % src.replace("\\", "/"))
            x = await call("get_xrefs")
            xr = [e for e in x["xrefs"] if e["name"] == "BCG_X"]
            check("XREF 찾음·참조 1", xr and xr[0]["resolved"] and xr[0]["ref_count"] == 1
                  and near(xr[0]["refs"][0]["insertion_point"], [1000, 2000, 0]) and xr[0]["refs"][0]["layout"] == "Model", x)

            # 6) 배치·뷰포트: Layout1 종이 공간에 뷰포트 하나, 축척 1/10
            out = await lines(
                '(setq _ob (vla-AddPViewport (vla-get-PaperSpace (vla-get-ActiveDocument (vlax-get-acad-object)))'
                ' (vlax-3d-point 100.0 80.0 0.0) 200.0 100.0))'
                '(vla-put-CustomScale _ob 0.1)'
                '(write-line (vla-get-Handle _ob) _fp)')
            hv = out[0]
            lo = await call("get_layouts")
            vp = [v for v in lo["viewports"] if v["handle"] == hv]
            paper = [l["name"] for l in lo["layouts"] if not l["model"]]
            check("배치 목록 Model + 종이 배치 2", lo["layouts"][0]["name"] == "Model" and len(paper) == 2, lo["layouts"])
            check("뷰포트 배치 이름", vp and vp[0]["layout"] == paper[0], vp)
            check("뷰포트 축척 1/10·크기", vp and abs(vp[0]["scale"] - 0.1) < 1e-9 and abs(vp[0]["scale_1_to"] - 10) < 1e-6
                  and vp[0]["width"] == 200 and abs(vp[0]["model_window"][2] - vp[0]["model_window"][0] - 2000) < 1e-6, lo)

            # 문자 겹침: 모형에 (A) 0,5000 높이 10 'OVERLAP-A'  (B) 같은 자리에서 x+30 (겹침)
            # (C) 90° 회전 문자가 A를 세로로 지남 (D) 멀리 떨어진 MTEXT (E) 꺼진 레이어의 A 복제(기본은 안 봄)
            def tx(x, y, s, rot=0.0, lay="TXO"):
                return ('(entmake (list (cons 0 "TEXT") (cons 8 "%s") (list 10 %s %s 0.0) (cons 40 10.0) (cons 1 "%s")'
                        ' (cons 50 %s)))' % (lay, x, y, s, rot))
            hs = await lines(tx(0, 5000, "OVERLAP-A") + '(setq _h (cdr (assoc 5 (entget (entlast)))))'
                             + tx(30, 5000, "OVERLAP-B") + '(setq _h (strcat _h "," (cdr (assoc 5 (entget (entlast))))))'
                             + tx(20, 4990, "ROT", "(/ pi 2)") + '(setq _h (strcat _h "," (cdr (assoc 5 (entget (entlast))))))'
                             + '(entmake (list (cons 0 "MTEXT") (cons 100 "AcDbEntity") (cons 8 "TXO") (cons 100 "AcDbMText")'
                               ' (list 10 5000.0 5000.0 0.0) (cons 40 10.0) (cons 41 100.0) (cons 71 1) (cons 1 "FAR")))'
                             + '(setq _h (strcat _h "," (cdr (assoc 5 (entget (entlast))))))'
                             + '(entmake (list (cons 0 "LAYER") (cons 100 "AcDbSymbolTableRecord") (cons 100 "AcDbLayerTableRecord")'
                               ' (cons 2 "TXOFF") (cons 70 0) (cons 62 -7)))'
                             + tx(0, 5000, "OVERLAP-A", "0.0", "TXOFF")
                             + '(write-line (strcat _h "," (cdr (assoc 5 (entget (entlast))))) _fp)')
            ha, hb, hc, hm, hoff = hs[0].split(",")
            ov = await call("find_text_overlaps", x1=-100, y1=4900, x2=6000, y2=5100)
            got = {frozenset((p["a"]["handle"], p["b"]["handle"])) for p in ov["pairs"]}
            check("겹침 A-B·A-C 잡고 MTEXT·꺼진 레이어는 안 잡음",
                  frozenset((ha, hb)) in got and frozenset((ha, hc)) in got and not any(hm in g or hoff in g for g in got)
                  and ov["checked"] == 4, ov)
            ov = await call("find_text_overlaps", x1=-100, y1=4900, x2=6000, y2=5100, include_hidden=True, min_ratio=0.99)
            same = [p for p in ov["pairs"] if p["same_text"]]
            check("꺼진 레이어 포함 시 같은 자리 같은 글자(겹침 1.0)",
                  len(same) == 1 and {same[0]["a"]["handle"], same[0]["b"]["handle"]} == {ha, hoff}, ov)
            ov = await call("find_text_overlaps", layer="TXO", x1=-100, y1=4900, x2=6000, y2=5100, min_ratio=0.99)
            check("min_ratio로 거름·레이어 필터", ov["count"] == 0 and ov["checked"] == 4, ov)

            await call("close_drawing", save=False)
            os.remove(src)


asyncio.run(main())
print("FAIL:", FAIL)
