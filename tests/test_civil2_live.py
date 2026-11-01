# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""종단·횡단·수량·표·정리 명령 시험(실제 AutoCAD 필요) — 새 시험 도면에 객체를 만들고 skill_run을 부른다.

DRP·DCS·DLS·GSE·CFB·EWT · CL·QCL·TLAE·HAR·SEAT·DMT·CTE·ETC · DDE·DOE·JJJ·CPL·FTF · ADD·RCHK
실행: <python> -X utf8 tests\\test_civil2_live.py   끝에 "FAIL: []"이면 통과.
"""
import asyncio
import json
import os
import sys

sys.dont_write_bytecode = True
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAIL = []


def check(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name, info if not cond else "")
    if not cond:
        FAIL.append(name)


H = '(write-line (cdr (assoc 5 (entget (entlast)))) _fp)'


def line(x1, y1, x2, y2, lay="0"):
    return '(entmake (list (cons 0 "LINE") (cons 8 "%s") (list 10 %g %g 0.0) (list 11 %g %g 0.0))) %s' % (lay, x1, y1, x2, y2, H)


def pline(pts, closed=False, lay="0", bulges=None):
    bs = bulges or [0.0] * len(pts)
    body = " ".join("(cons 10 (list %g %g)) (cons 42 %g)" % (x, y, b) for (x, y), b in zip(pts, bs))
    return ('(entmake (list (cons 0 "LWPOLYLINE") (cons 100 "AcDbEntity") (cons 8 "%s") (cons 100 "AcDbPolyline")'
            ' (cons 90 %d) (cons 70 %d) %s)) %s' % (lay, len(pts), 1 if closed else 0, body, H))


def text(s, x, y, h=2.5, lay="0"):
    return '(entmake (list (cons 0 "TEXT") (cons 8 "%s") (list 10 %g %g 0.0) (cons 40 %g) (cons 1 "%s"))) %s' % (lay, x, y, h, s, H)


def circle(x, y, r):
    return '(entmake (list (cons 0 "CIRCLE") (list 10 %g %g 0.0) (cons 40 %g))) %s' % (x, y, r, H)


async def main():
    params = StdioServerParameters(command=sys.executable, args=["-X", "utf8", os.path.join(ROOT, "src", "server.py")])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            async def call(name, **kw):
                res = await s.call_tool(name, kw)
                txt = res.content[0].text if res.content else ""
                if res.isError:
                    raise RuntimeError("%s: %s" % (name, txt))
                return json.loads(txt)

            async def run(cmd, **a):
                try:
                    return await call("skill_run", command=cmd, args=json.dumps(a, ensure_ascii=False))
                except RuntimeError as e:
                    check("%s 실행" % cmd, False, str(e)[:600])
                    return {}

            async def lisp(code):
                return (await call("run_lisp", code=code))["lines"]

            async def count(flt):
                n = await lisp('(setq _x (ssget "_X" %s)) (write-line (itoa (if _x (sslength _x) 0)) _fp)' % flt)
                return int(n[0])

            await call("new_drawing")
            # ---------------------------------------------------------------- DRP
            prof = [["누가거리", "지반고", "계획고", "종곡선", "제방고"], [0, 99.5, 100, None, 101], [20, 100.2, None, None, 101.2],
                    [40, 101, None, None, "x"], [60, 100.5, None, None, 101.6], [100, 102.5, 102, 40, 102], [140, 100.4, None, None, 101],
                    [200, 98.7, 99, None, 100]]
            r = await run("DRP", rows=prof, insert_point=[0, 0], settings={"간격": 20.0, "V축척": 200.0})
            t = r.get("table") or [[]]
            check("DRP 표 머리(지반고·제방고·계획고·절성고)", t[0] == ["측점", "누가거리", "지반고", "제방고", "계획고", "절토고", "성토고"], t[0])
            row100 = next((x for x in t if x[1] == "100.000"), None)
            check("DRP 100m 계획고 101.75(종곡선 L=40, K=8)·절토 0.75", row100 and row100[4] == "101.75" and row100[5] == "0.75", row100)
            check("DRP VIP 표 K=8", (r.get("vips") or [[]] * 2)[1][-1] == "8.000", r.get("vips"))
            check("DRP 계획선·지반선 그림", await count('(list (cons 0 "LWPOLYLINE") (cons 8 "종단_계획선"))') >= 1
                  and await count('(list (cons 0 "LWPOLYLINE") (cons 8 "종단_지반선"))') >= 1)
            # ---------------------------------------------------------------- DCS
            secrows = [[0, -10, 99], [None, 0, 99.5], [None, 10, 99.8], [20, -5, 100], [None, 0, 100.2], [None, 5, 100.1]]
            r = await run("DCS", profile_rows=prof, section_rows=secrows, section_point=[0, -300])
            sec = r.get("sections") or []
            check("DCS 횡단 2개·계획고 100.4(20m)·성토 0.2", len(sec) == 2 and sec[1]["plan_el"] == 100.4 and sec[1]["fill"] == 0.2, sec)
            r = await run("DCS", sections=[{"station": "0+040", "ground": [[-3, 99], [0, 98], [4, 99.5]]}],
                          settings={"횡단형식": "좌우 구분"})
            check("DCS sections 인자(계획 없이) 중심 지반고 98", (r.get("sections") or [{}])[0].get("center_el") == 98.0, r)
            # ---------------------------------------------------------------- DLS (V=1000: 1m = 도면 1)
            ip = (await lisp(pline([(400, 0), (500, 10), (600, -5)])))[0]
            r = await run("DLS", handle=ip, base_point=[400, 0], base_el=100, lengths=[60], settings={"V축척": 1000.0})
            v = r.get("vips") or [[]] * 3
            check("DLS VIP EL 110·L 60·K 2.4 (경사 +10% → −15%)", v[1][2] == "110.000" and v[1][3] == "60.000" and v[1][6] == "2.400", v)
            # ---------------------------------------------------------------- GSE
            pl = (await lisp(pline([(700, 0), (800, 10)])))[0]
            r = await run("GSE", handle=pl, base_point=[700, 0], base_el=100, stations=[50, "0+100"], settings={"V축척": 1000.0})
            rows = r.get("rows") or []
            check("GSE 50m 105.000, 100m 110.000", rows[1:] == [["0+050", "50.000", "105.000"], ["0+100", "100.000", "110.000"]], rows)
            # ---------------------------------------------------------------- CFB
            g = (await lisp(pline([(890, -2), (896, -1.5), (900, -1), (906, 0.2)])))[0]
            r = await run("CFB", ground_handle=g, center_point=[900, 0], center_el=100, station="0+020",
                          settings={"양식": "중심 기준 1열", "거리높이": "절대거리/절대EL"})
            check("CFB 중심 기준 1열", (r.get("rows") or [])[:4] == [["0+020", "-10.000", "98.000"], ["", "-4.000", "98.500"],
                                                                 ["", "0.000", "99.000"], ["", "6.000", "100.200"]], r.get("rows"))
            # ---------------------------------------------------------------- EWT
            await lisp('(entmake (list (cons 0 "BLOCK") (cons 2 "TJTEST") (cons 70 0) (list 10 0.0 0.0 0.0)))'
                       ' (entmake (list (cons 0 "LWPOLYLINE") (cons 100 "AcDbEntity") (cons 100 "AcDbPolyline") (cons 90 4) (cons 70 1)'
                       ' (cons 10 (list 0 0)) (cons 10 (list 40 0)) (cons 10 (list 40 10)) (cons 10 (list 0 10))))'
                       ' (entmake (list (cons 0 "ENDBLK")))')
            for k, (x, y, sc) in enumerate([(1000, 0, 1.0), (1000, 50, 2.0)]):
                await lisp('(entmake (list (cons 0 "INSERT") (cons 2 "TJTEST") (list 10 %g %g 0.0) (cons 41 %g) (cons 42 %g) (cons 43 1.0)))'
                           % (x, y, sc, sc))
                await lisp(text(("0+020", "0+000")[k], x + 2 * sc, y + 6 * sc, 2 * sc) + text(("12.5", "8.25")[k], x + 22 * sc, y + 6 * sc, 2 * sc))
            r = await run("EWT", block="TJTEST", station_box=[0, 5, 20, 10], items=[["깎기", [20, 5, 40, 10]]])
            check("EWT 블록 축척 달라도 측점 순 [0+000 8.25, 0+020 12.5]", (r.get("rows") or [])[1:] ==
                  [["0+000", "0.000", 8.25], ["0+020", "20.000", 12.5]], r.get("rows"))
            # ---------------------------------------------------------------- CL·QCL·TLAE
            l1 = (await lisp(line(0, 500, 25, 500)))[0]
            sq = (await lisp(pline([(40, 500), (50, 500), (50, 510), (40, 510)], True)))[0]
            r = await run("CL", handles=[l1])
            check("CL 'L=25.00m'", [x["text"] for x in r.get("labels", [])] == ["L=25.00m"], r)
            r = await run("QCL", handles=[sq], settings={"구간마다": True, "머리말": "", "꼬리말": ""})
            check("QCL 구간마다 4개 10.00", [x["text"] for x in r.get("labels", [])] == ["10.00"] * 4, r)
            r = await run("TLAE", handles=[l1, sq])
            check("TLAE 길이 65·면적 100", r.get("length") == 65.0 and r.get("area") == 100.0, r)
            # ---------------------------------------------------------------- HAR·SEAT
            hs = []
            for k, (x, lay) in enumerate([(100, "면A"), (130, "면A"), (160, "면B")]):
                await lisp('(bc:ensure-layer "%s" 7)' % lay)
                await lisp(pline([(x, 500), (x + 20, 500), (x + 20, 510), (x, 510)], True, lay))
                hs += await lisp('(setq _ms (vla-get-ModelSpace (vla-get-ActiveDocument (vlax-get-acad-object))))'
                                 ' (setq _pl (vlax-ename->vla-object (entlast)) _h (vla-AddHatch _ms 1 "ANSI31" :vlax-true))'
                                 ' (setq _ar (vlax-make-safearray vlax-vbObject (quote (0 . 0)))) (vlax-safearray-put-element _ar 0 _pl)'
                                 ' (vla-AppendOuterLoop _h _ar) (vla-Evaluate _h) (vla-put-Layer _h "%s")'
                                 ' (write-line (vla-get-Handle _h) _fp)' % lay)
            r = await run("HAR", handles=hs, insert_point=[100, 480], settings={"무늬별": False})
            check("HAR 레이어별 면A 400·면B 200·합계 600", (r.get("rows") or [])[1:] ==
                  [["면A", "2", "400.00"], ["면B", "1", "200.00"], ["합계", "3", "600.00"]], r.get("rows"))
            sqs = [(await lisp(pline([(x, 540), (x + 10, 540), (x + 10, 545 + k * 5), (x, 545 + k * 5)], True, "면A")))[0]
                   for k, x in enumerate((100, 120))]
            r = await run("SEAT", handles=sqs, insert_point=[100, 600], settings={"순서": "선택 순"})
            check("SEAT 50·100·합계 150", [x[-1] for x in (r.get("rows") or [])[1:]] == ["50.00", "100.00", "150.00"], r.get("rows"))
            # ---------------------------------------------------------------- DMT
            pg = (await lisp(pline([(300, 500), (310, 500), (310, 505), (305, 508), (300, 505)], True)))[0]
            r = await run("DMT", handle=pg, insert_point=[320, 520])
            rows = r.get("rows") or []
            check("DMT 삼각형 3개·CAD 면적 65.00", r.get("triangles") == 3 and rows[-1][-1] == "65.00", rows)
            # ---------------------------------------------------------------- CTE·ETC
            await lisp('(bc:ensure-layer "표시험" 7)')
            await run("ETC", rows=[["구분", "", "수량"], ["A", "1", "10.5"], ["B", "2", "3"]], insert_point=[0, 700],
                      merges=[[0, 0, 0, 1]], widths=[10, 10, 15], height=6, settings={"문자레이어": "표시험", "선레이어": "표시험"})
            hs = await lisp('(foreach _e (bc:ss-list (ssget "_X" (list (cons 8 "표시험")))) (write-line (cdr (assoc 5 (entget _e))) _fp))')
            r = await run("CTE", handles=hs)
            check("ETC → CTE 되읽기(병합 칸 포함)", r.get("rows") == [["구분", "", "수량"], ["A", "1", "10.5"], ["B", "2", "3"]]
                  and r.get("merges") == [[0, 0, 0, 1]], r)
            # ---------------------------------------------------------------- DDE·DOE·JJJ·CPL
            d1 = (await lisp(line(0, 800, 10, 800)))[0]
            d2 = (await lisp(line(10, 800, 0, 800)))[0]
            d3 = (await lisp(line(0, 801, 10, 801)))[0]
            r = await run("DDE", handles=[d1, d2, d3])
            check("DDE 방향 반대 같은 선 1개 지움", r.get("found") == 1 and r.get("handles") == [d2], r)
            o1 = (await lisp(line(0, 820, 100, 820)))[0]
            o2 = (await lisp(line(10, 820, 20, 820)))[0]
            m1 = (await lisp(line(200, 820, 210, 820)))[0]
            m2 = (await lisp(line(205, 820, 220, 820)))[0]
            r = await run("DOE", handles=[o1, o2, m1, m2], settings={"결합": True})
            n = await lisp('(write-line (if (entget (handent "%s")) "y" "n") _fp) (setq _e (entget (handent "%s")))'
                           ' (write-line (strcat (rtos (cadr (assoc 10 _e)) 2 3) "," (rtos (cadr (assoc 11 _e)) 2 3)) _fp)' % (o2, m1))
            check("DOE 겹친 짧은 선 삭제·일직선 선 결합 200~220", r.get("removed") == 1 and r.get("merged") == 1
                  and n[0] == "n" and n[1] == "200,220", (r, n))
            j1 = (await lisp(line(0, 850, 10, 850)))[0]
            j2 = (await lisp(pline([(20, 860), (10, 850)])))[0]
            j3 = (await lisp(line(20, 860, 30, 860)))[0]
            r = await run("JJJ", handles=[j1, j2, j3])
            n = await count('(list (cons 0 "LWPOLYLINE") (cons 90 4))')
            check("JJJ 3개 → 폴리선 1개(정점 4)", r.get("polylines") == 1 and n >= 1, (r, n))
            c1 = (await lisp(pline([(0, 900), (10, 900), (10, 910)], False, "0", [0.0, 0.5, 0.0])))[0]
            r = await run("CPL", handles=[c1], settings={"변환": "3D 폴리선"})
            n = await count('(list (cons 0 "POLYLINE") (cons 100 "AcDb3dPolyline"))')
            check("CPL 경량 → 3D 폴리선", r.get("converted") == 1 and n == 1, (r, n))
            # ---------------------------------------------------------------- FTF
            await lisp('(entmake (list (cons 0 "STYLE") (cons 100 "AcDbSymbolTableRecord") (cons 100 "AcDbTextStyleTableRecord")'
                       ' (cons 2 "없는글꼴시험") (cons 70 0) (cons 40 0.0) (cons 41 1.0) (cons 50 0.0) (cons 71 0) (cons 42 2.5)'
                       ' (cons 3 "nofont_bc_xyz.shx") (cons 4 "")))')
            r = await run("FTF")
            check("FTF 없는 글꼴 스타일만 바꿈", "없는글꼴시험" in (r.get("changed") or []) and "Standard" not in (r.get("changed") or []),
                  r.get("changed"))
            # ---------------------------------------------------------------- ADD
            a1 = (await lisp(text("EL=12.50", 0, 950)))[0]
            a2 = (await lisp(text("STA. 1+250", 0, 945)))[0]
            r = await run("ADD", handles=[a1], settings={"값": "0.6"})
            r2 = await run("ADD", handles=[a2], settings={"값": "100", "측점": True})
            check("ADD EL=13.10, 측점 1+350", r.get("changes") == [[a1, "EL=13.10"]] and r2.get("changes") == [[a2, "STA. 1+350"]],
                  (r, r2))
            # ---------------------------------------------------------------- RCHK
            st = []
            for no, x in (("W1", 0), ("W2", 30)):
                st += await lisp(circle(x, 1000, 4) + text(no, x - 2, 999) + text("H22@250", x + 6, 999))
            dt = []
            dt += await lisp(circle(100, 1000, 4) + line(96, 996, 190, 996) + text("W1", 98, 999) + text("H19", 106, 996.2)
                             + text("L=2500", 141, 996.2) + text("N=4", 170, 996.2))
            dt += await lisp(circle(100, 980, 4) + line(96, 976, 190, 976) + text("F1", 98, 979) + text("H13", 106, 976.2)
                             + text("L=1000", 141, 976.2) + text("N=2", 170, 976.2))
            r = await run("RCHK", struct_handles=st, detail_handles=dt)
            check("RCHK W1 직경 다름·W2 상세도 누락·F1 상세도만", (r.get("rows") or [])[1:] ==
                  [["F1", "", "H13", "상세도만 있음"], ["W1", "H22", "H19", "직경 다름"], ["W2", "H22", "", "상세도 누락"]], r.get("rows"))
            # ---------------------------------------------------------------- bug_report(오류 보고서)
            r = await call("bug_report", problem="시험 보고", command="CL", error_text="실패 D:/과업/지구명/도면이름.dwg")
            check("bug_report: 버전·AutoCAD·명령 설정, 폴더·도면 이름 가림", "BC.0.5.3" in r["text"] and "신뢰 경로 등록" in r["text"]
                  and "지구명" not in r["text"] and "도면이름" not in r["text"] and os.path.exists(r["path"]), r["text"][:800])
            print("시험 도면은 저장하지 않았습니다.")


asyncio.run(main())
print("FAIL:", FAIL)
