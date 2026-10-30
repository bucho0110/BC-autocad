# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""QCAR 용지도 면적 산출 시험(실제 AutoCAD 필요) — 새 시험 도면에 경계·지적·지번·행정구역을 만들고 skill_run을 부른다.

실행: <python> -X utf8 tests\\test_qcar_live.py   끝에 "FAIL: []"이면 통과.
용지 경계 (0,0)-(100,20) 면적 2000.
  지적 1-1대  (-10,-10)-(40,30)            → 편입 40×20 = 800
  지적 2답    (40,-10)-(60,30), 안에 지적 3도 (45,5)-(50,10) → 2답 편입 400 − 25 = 375, 3도 25(전체편입)
  지적 4천    ㄷ자(아래 가운데 홈)           → 편입 두 조각 150 + 150 = 300(합산면적)
  지적 5전    (60,0)-(100,10), 윗변이 안으로 휜 호(볼록 0.2) → 400 − 활꼴
행정구역: x < 50 '가동', x ≥ 50 '나동'.
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


def pl(lay, pts, bulges=None):
    bulges = bulges or [0.0] * len(pts)
    vs = " ".join("(list 10 %.6f %.6f) (cons 42 %.12f)" % (x, y, b) for (x, y), b in zip(pts, bulges))
    return ('(entmake (list (cons 0 "LWPOLYLINE") (cons 100 "AcDbEntity") (cons 8 "%s") (cons 100 "AcDbPolyline")'
            ' (cons 90 %d) (cons 70 1) %s)) (write-line (cdr (assoc 5 (entget (entlast)))) _fp)' % (lay, len(pts), vs))


def tx(lay, s, x, y):
    return ('(entmake (list (cons 0 "TEXT") (cons 8 "%s") (list 10 %.3f %.3f 0.0) (list 11 %.3f %.3f 0.0) (cons 72 1) (cons 73 2)'
            ' (cons 40 1.0) (cons 1 "%s")))' % (lay, x, y, x, y, s))


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


B = 0.2
TH = 4 * math.atan(B)
R = 40 / (2 * math.sin(TH / 2))
SEG = R * R / 2 * (TH - math.sin(TH))


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
            bd = (await lisp(pl("용지경계", rect(0, 0, 100, 20))))[0]
            al = (await lisp('(entmake (list (cons 0 "LINE") (cons 8 "선형") (list 10 0.0 10.0 0.0) (list 11 100.0 10.0 0.0)))'
                             '(write-line (cdr (assoc 5 (entget (entlast)))) _fp)'))[0]
            code = (pl("지적", rect(-10, -10, 40, 30)) + pl("지적", rect(40, -10, 60, 30)) + pl("지적", rect(45, 5, 50, 10))
                    + pl("지적", [(60, 10), (75, 10), (75, 30), (85, 30), (85, 10), (100, 10), (100, 40), (60, 40)])
                    # 5전: 윗변 (100,10)→(60,10)에 볼록 −0.2(시계 방향 호 = 남쪽, 지적 안으로 휨)
                    + pl("지적", [(60, 0), (100, 0), (100, 10), (60, 10)], [0.0, 0.0, -B, 0.0])
                    + pl("행정", rect(-20, -50, 50, 50)) + pl("행정", rect(50, -50, 120, 50))
                    + tx("지번", "1-1대", 10, 25) + tx("지번", "2답", 55, 25) + tx("지번", "3도", 47.5, 7.5)
                    + tx("지번", "4천", 80, 35) + tx("지번", "5전", 80, 3)
                    + tx("행정문자", "가동", 0, -40) + tx("행정문자", "나동", 80, -40))
            await lisp(code)
            cfg = {"지적선레이어": "지적", "지번문자레이어": "지번", "행정구역레이어": "행정", "구역문자레이어": "행정문자",
                   "정렬": "선형 측점순", "면적소수": 3, "축척": 1000.0, "해치": True, "최소면적": 0.0}
            r = await run("QCAR", boundary_handle=bd, alignment_handle=al, settings=cfg)
            rows = r["rows"]
            body = {row[2]: row for row in rows[1:] if len(row) == 8 and row[2] and row[1] != ""}
            print(json.dumps(rows, ensure_ascii=False))
            check("QCAR 지적 5건", r["summary"]["count"] == 5, r["summary"])
            check("QCAR 1-1 편입 800, 지목 대, 가동", body.get("1-1", [None])[0:6] == ["가동", 1, "1-1", "대", "2000.000", "800.000"],
                  body.get("1-1"))
            check("QCAR 안쪽 지적 뺌: 2 면적 775, 편입 375", body.get("2", [""] * 8)[4:6] == ["775.000", "375.000"], body.get("2"))
            check("QCAR 안쪽 지적 3: 25 전체편입 ○", body.get("3", [""] * 8)[5] == "25.000" and body["3"][6] == "○", body.get("3"))
            check("QCAR 두 조각 4: 300 합산면적", body.get("4", [""] * 8)[5] == "300.000" and body["4"][7] == "합산면적"
                  and body["4"][0] == "나동", body.get("4"))
            want5 = "%.3f" % (400 - SEG)
            check("QCAR 호 지적 5: 400 − 활꼴 = %s" % want5, body.get("5", [""] * 8)[5] == want5, body.get("5"))
            check("QCAR 측점순 번호 1-1, 3, 2, 4, 5", [body[k][1] for k in ("1-1", "3", "2", "4", "5")] == [1, 2, 3, 4, 5],
                  {k: v[1] for k, v in body.items()})
            sm = r["summary"]
            tot = 800 + 375 + 25 + 300 + round(400 - SEG, 3)
            check("QCAR 합계·경계·차이(합계 − 경계)", sm["boundary"] == 2000.0 and abs(sm["sum"] - tot) < 1e-6
                  and abs(sm["difference"] - (tot - 2000)) < 1e-6, sm)
            cnt = ('(defun _n (f / x) (if (setq x (ssget "_X" f)) (sslength x) 0))'
                   '(write-line (strcat (itoa (_n (list (cons 8 "편입면적선")))) _d (itoa (_n (list (cons 0 "HATCH"))))'
                   ' _d (itoa (_n (list (cons 0 "REGION"))))) _fp)')
            n = await lisp(cnt)
            # 산출선: 1-1, 2(바깥)+2(구멍), 3, 4 두 조각, 5 = 7개 / 해치: 지번 있는 조각 6개 / 계산용 영역은 남지 않아야
            check("QCAR 산출선 7개·해치 6개·남은 영역 0", n == ["7\t6\t0"], n)
            a4 = await lisp('(foreach _e (bc:ss-list (ssget "_X" (list (cons 8 "편입면적선"))))'
                            ' (write-line (bc:rtos (vla-get-Area (vlax-ename->vla-object _e)) 2 3) _fp))')
            check("QCAR 산출선 면적", sorted(a4) == sorted(["800.000", "400.000", "25.000", "25.000", "150.000", "150.000", want5]), a4)
            ha = await lisp('(foreach _e (bc:ss-list (ssget "_X" (list (cons 0 "HATCH"))))'
                            ' (write-line (bc:rtos (vla-get-Area (vlax-ename->vla-object _e)) 2 3) _fp))')
            check("QCAR 해치 면적(2는 구멍 뺀 375)", sorted(ha) == sorted(["800.000", "375.000", "25.000", "150.000", "150.000", want5]), ha)
            print("시험 도면은 저장하지 않았습니다.")


asyncio.run(main())
print("FAIL:", FAIL)
