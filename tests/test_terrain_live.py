# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""지형 명령 시험(실제 AutoCAD 필요): CCON 등고선, WCZ 높이 문자, DCON 높이별 레이어, CMOB 외곽, DSEL EL 조건.

실행: <python> -X utf8 tests\\test_terrain_live.py   끝에 "FAIL: []"이면 통과.
경사면 z = 0.5x + 0.3 (x 0~10, y 0~5 격자 점)이면 등고선 1·2·3·4·5m는 x = 1.4·3.4·5.4·7.4·9.4의 세로선이다.
"""
import asyncio
import json
import math
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


GRID = ('(setq _x 0) (while (<= _x 10) (setq _y 0) (while (<= _y 5)'
        ' (entmake (list (cons 0 "POINT") (cons 8 "측점") (list 10 (float _x) (float _y) (+ 0.3 (* 0.5 _x)))))'
        ' (write-line (cdr (assoc 5 (entget (entlast)))) _fp) (setq _y (1+ _y))) (setq _x (1+ _x)))')
# 등고선: 레이어, 고도, x 최소, x 최대, 정점 수
CONS = ('(foreach _e (bc:ss-list (ssget "_X" (list (cons 0 "LWPOLYLINE") (cons 8 "등고선_*"))))'
        ' (setq _v (bc:verts _e))'
        ' (write-line (strcat (cdr (assoc 8 (entget _e))) _d (bc:rtos (cdr (assoc 38 (entget _e))) 2 3) _d'
        ' (bc:rtos (apply (quote min) (mapcar (quote car) _v)) 2 4) _d (bc:rtos (apply (quote max) (mapcar (quote car) _v)) 2 4)'
        ' _d (cdr (assoc 5 (entget _e)))) _fp))')


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
                return await call("skill_run", command=cmd, args=json.dumps(a, ensure_ascii=False))

            async def lisp(code):
                return (await call("run_lisp", code=code))["lines"]

            await call("new_drawing")
            pts = await lisp(GRID)
            r = await run("CCON", handles=pts, settings={"방식": "점에서 삼각망", "대상점": True, "주곡선간격": 1.0,
                                                        "계곡선간격": 5.0, "외측최소화": 0.0, "단순화": 0, "특정높이": ""})
            check("CCON 점 66·높이 5개·등고선 5개", r["points"] == 66 and r["levels"] == 5 and r["contours"] == 5, r)
            cons = sorted([c.split("\t") for c in await lisp(CONS)], key=lambda c: float(c[1]))
            want = [(1.0, 1.4), (2.0, 3.4), (3.0, 5.4), (4.0, 7.4), (5.0, 9.4)]
            check("CCON 등고선 위치 x = (z-0.3)/0.5, 고도 = 높이",
                  [(float(c[1]), float(c[2])) for c in cons] == want and all(c[2] == c[3] for c in cons), cons)
            check("CCON 5m는 계곡선, 나머지 주곡선",
                  [c[0] for c in cons] == ["등고선_주곡선"] * 4 + ["등고선_계곡선"], [c[0] for c in cons])
            r = await run("CCON", handles=pts, settings={"특정높이": "2.75"})
            c275 = [c for c in await lisp(CONS) if c.split("\t")[1] == "2.750"]
            check("CCON 특정 높이 2.75만 (x = 4.9)", r["contours"] == 1 and c275 and c275[0].split("\t")[2] == "4.9000", (r, c275))
            await lisp('(entdel (handent "%s"))' % c275[0].split("\t")[4])

            r = await run("WCZ", pairs=[[[0, 2.5], [10, 2.5]]], settings={"소수": 0, "레이어": "등고선_표고", "마스크": False,
                                                                       "단위만": False, "등고선레이어": "등고선_*"})
            txt = [ln.split("\t") for ln in await lisp(
                '(foreach _e (bc:ss-list (ssget "_X" (list (cons 0 "TEXT") (cons 8 "등고선_표고"))))'
                ' (write-line (strcat (cdr (assoc 1 (entget _e))) _d (bc:rtos (cdr (assoc 50 (entget _e))) 2 4) _d'
                ' (bc:rtos (cadr (assoc 11 (entget _e))) 2 4)) _fp))')]
            vals = sorted(t[0] for t in txt)
            # 등고선이 세로(아래→위 또는 위→아래)고 높은 쪽이 동쪽이면 글자 위쪽이 동쪽 → 회전 270°
            check("WCZ 높이 1~5 다섯 개, 등고선 위에", r["results"] == ["5"] and vals == ["1", "2", "3", "4", "5"]
                  and sorted(float(t[2]) for t in txt) == [1.4, 3.4, 5.4, 7.4, 9.4], (r, txt))
            check("WCZ 글자 위쪽이 높은 쪽(회전 270°)", all(abs(float(t[1]) - 3 * math.pi / 2) < 1e-3 for t in txt), txt)
            r = await run("WCZ", pairs=[[[10, 1], [0, 1]]], settings={"단위만": True, "단위": 5.0, "마스크": True})
            m = (await lisp('(setq _e (entget (entlast))) (write-line (strcat (cdr (assoc 0 _e)) _d (cdr (assoc 1 _e)) _d'
                            ' (itoa (cdr (assoc 90 _e))) _d (bc:rtos (cdr (assoc 50 _e)) 2 4)) _fp)'))[0].split("\t")
            check("WCZ 5m 단위만·마스크 MTEXT·반대 방향은 90°", r["results"] == ["1"] and m[0] == "MTEXT" and m[1] == "5"
                  and m[2] == "3" and abs(float(m[3]) - math.pi / 2) < 1e-3, (r, m))

            r = await run("DCON", settings={"간격": 5.0, "머리말": "CON-", "색단계": True, "시작색": "247,253,247"})
            lay = (await lisp('(setq _l (entget (tblobjname "LAYER" "CON-5")))'
                              '(write-line (itoa (cdr (assoc 420 _l))) _fp)'))
            check("DCON 5m 등고선 1개 → CON-5, 시작색 247,253,247", r["results"] == ["1"] and lay == [str(247 * 65536 + 253 * 256 + 247)],
                  (r, lay))

            r = await run("DSEL", handles=pts, center=[20, 20], settings={"조건": ">=", "EL": 5.0, "원": True, "반지름": 0.2,
                                                                         "레이어": "EL조건표시"})
            n = await lisp('(write-line (strcat (itoa (sslength (ssget "_X" (list (cons 0 "CIRCLE") (cons 8 "EL조건표시"))))) _d'
                           ' (itoa (sslength (ssget "_X" (list (cons 0 "LINE") (cons 8 "EL조건표시")))))) _fp)')
            check("DSEL EL >= 5 → x=10 점 6개에 원 6·연결선 6", r["results"] == ["6"] and n == ["6\t6"], (r, n))
            r = await run("DSEL", handles=pts, settings={"조건": "=", "EL": 2.8, "원": False})
            check("DSEL EL = 2.8 → x=5 점 6개", r["results"] == ["6"], r)

            lsh = await lisp('(setq _x 0) (while (< _x 20) (setq _y 0) (while (< _y 20)'
                             ' (if (or (< _x 5) (< _y 5)) (progn (entmake (list (cons 0 "POINT") (list 10 (+ 100.0 _x) (float _y) 0.0)))'
                             ' (write-line (cdr (assoc 5 (entget (entlast)))) _fp))) (setq _y (1+ _y))) (setq _x (1+ _x)))')
            r = await run("CMOB", handles=lsh, settings={"여유도": 3.0, "레이어": "지형외곽"})
            area = await lisp('(write-line (bc:rtos (vla-get-Area (vlax-ename->vla-object (entlast))) 2 3) _fp)')
            # 19×19 − 15×15 = 136에, 안쪽 모서리의 대각선 (4,6)-(6,4)(길이 2.83 < 중간 변 1 × 여유 3)가 남겨 둔 삼각형 2
            check("CMOB ㄴ자 점 → 외곽 1개, 면적 136 + 2", r["loops"] == 1 and area == ["138.000"], (r, area))
            r = await run("CMOB", handles=lsh, settings={"여유도": 10.0})
            area = await lisp('(write-line (bc:rtos (vla-get-Area (vlax-ename->vla-object (entlast))) 2 3) _fp)')
            check("CMOB 여유도 10 → 오목부를 덜 파고듦(면적 > 136)", float(area[0]) > 136, area)
            # ---------------------------------------------------------------- GRP·CFM
            # 두 번째 지형: x 200~210, y 0~5, z = 0.5(x-200) + 0.1y + 0.3 → 북쪽(진행 방향 왼쪽)이 높다
            g2 = await lisp(GRID.replace("(list 10 (float _x) (float _y) (+ 0.3 (* 0.5 _x)))",
                                         "(list 10 (+ 200.0 _x) (float _y) (+ 0.3 (* 0.5 _x) (* 0.1 _y)))"))
            r = await run("DTIN", handles=g2, settings={"레이어": "TIN2", "최대변": 0})
            tin = await lisp('(foreach _e (bc:ss-list (ssget "_X" (list (cons 8 "TIN2")))) (write-line (cdr (assoc 5 (entget _e))) _fp))')
            al = (await lisp('(entmake (list (cons 0 "LWPOLYLINE") (cons 100 "AcDbEntity") (cons 100 "AcDbPolyline") (cons 90 3) (cons 70 0)'
                             ' (list 10 201.0 1.0) (cons 42 0.0) (list 10 205.0 1.0) (cons 42 %.12f) (list 10 209.0 5.0) (cons 42 0.0)))'
                             '(write-line (cdr (assoc 5 (entget (entlast)))) _fp)' % math.tan(math.pi / 8)))[0]

            def plane(x, y):
                return 0.5 * (x - 200) + 0.1 * y + 0.3

            r = await run("GRP", handle=al, terrain_handles=tin, insert_point=[200, -40],
                          settings={"표기": "지형 교차점만", "지반고소수": 3, "역방향": False, "시작거리": "1+000"})
            sys.path.insert(0, ROOT)
            from skills.common import profile as G  # noqa: E402
            from skills.common.coords import fmt  # noqa: E402

            def C_fmt(v):
                return fmt(v, 3)
            el = [((201.0, 1.0), (205.0, 1.0), 0.0), ((205.0, 1.0), (209.0, 5.0), math.tan(math.pi / 8))]
            body = r["rows"][1:]
            bad = [row for row in body if row[2] != "" and abs(float(row[2]) - plane(*G.point_at(el, float(row[1]) - 1000)[0])) > 0.0011]
            check("GRP 길이 4 + 2π(호 계산)", abs(r["length"] - (4 + 2 * math.pi)) < 1e-4, r["length"])
            check("GRP 교차점 지반고 = 평면식(호 구간 포함)", len(body) >= 10 and not bad, bad[:3])
            check("GRP 측점은 시작거리부터·끝 지반고 5.3", body[0][0].startswith("1+0") and body[-1][2] == "5.300", (body[0], body[-1]))
            gl = await lisp('(write-line (itoa (cdr (assoc 90 (entget (car (bc:ss-list (ssget "_X" (list (cons 8 "종단_지반선"))))))))) _fp)')
            check("GRP 지반선 정점 수 = 종단 정점 수", gl == [str(r["vertices"])], (gl, r["vertices"]))
            r = await run("GRP", handle=al, terrain_handles=tin, settings={"표기": "측점 간격만", "간격": 20.0, "시작거리": "0"})
            check("GRP 간격 20 > 길이: 시점·종점 두 줄, 시점 지반고 0.90", [x[0] for x in r["rows"][1:]] == ["0+000", "0+010.283"]
                  and r["rows"][1][2] == "0.90", r["rows"])
            # 시점이 3D면 안(변 위 아님)이어도 그 면의 평면 높이로 시작한다
            al2 = (await lisp('(entmake (list (cons 0 "LINE") (list 10 201.3 1.6 0.0) (list 11 208.7 1.6 0.0)))'
                              '(write-line (cdr (assoc 5 (entget (entlast)))) _fp)'))[0]
            r = await run("GRP", handle=al2, terrain_handles=tin, settings={"표기": "측점 간격만", "간격": 100.0, "지반고소수": 3})
            check("GRP 시·종점이 3D면 안: 면 높이 %s, %s" % (round(plane(201.3, 1.6), 3), round(plane(208.7, 1.6), 3)),
                  [x[2] for x in r["rows"][1:]] == [C_fmt(plane(201.3, 1.6)), C_fmt(plane(208.7, 1.6))], r["rows"])

            st = (await lisp('(entmake (list (cons 0 "LWPOLYLINE") (cons 100 "AcDbEntity") (cons 100 "AcDbPolyline") (cons 90 2) (cons 70 0)'
                             ' (list 10 200.0 2.5) (list 10 210.0 2.5)))(write-line (cdr (assoc 5 (entget (entlast)))) _fp)'))[0]
            r = await run("CFM", handle=st, terrain_handles=tin, stations=["0+002.5", 5],
                          settings={"방식": "엑셀 측점 목록", "편측거리": 2.0, "좌우반대": False}, base_point=[300, 0])
            sc = r["sections"]
            check("CFM 측점 목록 2개, 중심 EL = 평면식", len(sc) == 2 and sc[0]["center_el"] == round(plane(202.5, 2.5), 3)
                  and sc[1]["center_el"] == round(plane(205, 2.5), 3), sc)
            g = sc[1]["ground"]
            check("CFM 편측 2m, 왼쪽(−)이 북쪽이라 높다", g[0][0] == -2.0 and g[-1][0] == 2.0 and g[0][1] > g[-1][1]
                  and abs(g[0][1] - plane(205, 4.5)) < 1e-9, g)
            ln = (await lisp('(entmake (list (cons 0 "LINE") (list 10 207.0 0.5 0.0) (list 11 207.0 4.5 0.0)))'
                             '(write-line (cdr (assoc 5 (entget (entlast)))) _fp)'))[0]
            r = await run("CFM", handle=st, terrain_handles=tin, section_handles=[ln], settings={"방식": "그려진 횡단선 선택"})
            sc = r["sections"]
            check("CFM 그려진 횡단선: 측점 0+007, 왼쪽 끝 = 북쪽 끝(-2)", len(sc) == 1 and sc[0]["station"] == "0+007"
                  and sc[0]["ground"][0][0] == -2.0 and abs(sc[0]["ground"][0][1] - plane(207, 4.5)) < 1e-9, sc)
            r = await run("CFM", handle=st, terrain_handles=tin, section_handles=[ln],
                          settings={"방식": "그려진 횡단선 선택", "좌우반대": True})
            check("CFM 좌우반대: 왼쪽이 남쪽", abs(r["sections"][0]["ground"][0][1] - plane(207, 0.5)) < 1e-9, r["sections"])
            r = await run("CFM", handle=st, terrain_handles=tin, settings={"방식": "측점 간격마다", "간격": 5.0, "편측거리": 2.0})
            check("CFM 간격 5: 0·5·10 세 단면", [x["station"] for x in r["sections"]] == ["0+000", "0+005", "0+010"], r["sections"])
            print("시험 도면은 저장하지 않았습니다.")


asyncio.run(main())
print("FAIL:", FAIL)
