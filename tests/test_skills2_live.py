# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""스킬 2단계(선형·측점) 시험(실제 AutoCAD 필요) — MCP stdio로 새 시험 도면에서 skill_run.

실행: <python> -X utf8 tests\\test_skills2_live.py [출력폴더]   끝에 "FAIL: []"이면 통과.
"""
import asyncio
import json
import os
import sys
import tempfile

sys.dont_write_bytecode = True  # 패키지 폴더(동기화 폴더일 수 있음)에 __pycache__를 만들지 않는다

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), "bc_skill_test")
os.makedirs(OUT, exist_ok=True)
FAIL = []


def check(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name, "" if cond else info)
    if not cond:
        FAIL.append(name)


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

            async def pl(pts):
                return (await call("create_polyline", points=json.dumps(pts)))["handle"]

            print("시험 도면:", await call("new_drawing"))
            # 좌안·우안 제방선(폭 40) — 가운데가 y=20 이어야 한다
            left = await pl([[0, 0], [100, 0], [200, 30], [300, 30]])
            right = await pl([[0, 40], [100, 40], [200, 70], [300, 70]])
            r = await run("DCP", handles=[left, right])
            check("DCP 중심선", len(r["results"]) == 1, r)
            cl = r["results"][0]
            info = await call("get_entity", handle=cl)
            check("DCP 시점 y≈20", abs(info.get("bbox_min", [0, 99])[1] - 20) < 0.5, info)
            # 중심선 위 표본 점마다 양쪽 선까지 거리 차이(꺾이는 곳 톱니가 없어야 한다)
            dev = await call("run_lisp", code=(
                '(setq _c (handent "%s") _a (handent "%s") _b (handent "%s") _L (vlax-curve-getDistAtParam _c (vlax-curve-getEndParam _c)) _i 1 _mx 0.0)'
                ' (repeat 199 (setq _p (vlax-curve-getPointAtDist _c (* _L (/ _i 200.0)))'
                ' _mx (max _mx (abs (- (distance _p (vlax-curve-getClosestPointTo _a _p)) (distance _p (vlax-curve-getClosestPointTo _b _p)))))'
                ' _i (1+ _i))) (write-line (rtos _mx 2 6) _fp)' % (cl, left, right)))
            mx = float(dev["lines"][0])
            check("DCP 양쪽 거리 차 < 0.05 (폭 40)", mx < 0.05, mx)

            # 측점: 직선 1000m 선형, 축척 1000 (1m = 1)
            al = await pl([[0, 200], [1000, 200]])
            r = await run("GST", handle=al, points=[[250.5, 230]], settings={"소수": 1, "머리말": "No.", "도면표기": False})
            check("GST 0+250.5", "No.0+250.5" in r["results"][0], r)
            r = await run("GST", handle=al, reverse=True, points=[[250, 230]], settings={"소수": 0, "도면표기": False})
            check("GST 반대방향 0+750", "0+750" in r["results"][0], r)
            r = await run("GST", handle=al, points=[[500, 230]],
                          settings={"측점구분": "Number", "측점간격": 20.0, "머리말": "No.", "도면표기": False})
            check("GST Number No.25+0", "No.25+0" in r["results"][0], r)
            r = await run("STT", handle=al, points=[[100, 210], [180, 210]], sides="A",
                          settings={"방식": "두점", "표기명칭": "호안"})
            check("STT 두점 양쪽+명칭(16개)", len(r["results"]) == 1 and r["results"][0].count(" ") == 15, r)
            # 구간(평면도 지구명 견본): 긴 구간은 양 끝 안쪽에 두 줄씩, 짧은 구간은 가운데 한 곳
            r = await run("STT", handle=al, stations=["0+100", "1+000"], sides="L", name="시험지구",
                          settings={"방식": "구간", "높이": 5.0, "구간거리": 6.0})
            hs = r["results"][0].strip("()").split()
            ents = (await call("entget_by_handles", handles=json.dumps(hs)))["entities"] if hs else []
            txt = [e.get("text") for e in ents]
            check("STT 구간 4개·문구", len(hs) == 4 and txt[0] == "시험지구 L=900m" and txt[1] == "(No.0+100 ~ No.1+000)", txt)
            ys = [e.get("insertion_point", e.get("position", [0, 0]))[1] for e in ents]
            check("STT 구간 좌측(y>200)", all(y > 200 for y in ys), ys)
            r = await run("STT", handle=al, stations=[100, 120], sides="R", name="짧은",
                          settings={"방식": "구간", "높이": 5.0, "구간소수": 1, "구간구분": "~"})
            hs = r["results"][0].strip("()").split()
            ents = (await call("entget_by_handles", handles=json.dumps(hs)))["entities"] if hs else []
            txt = [e.get("text") for e in ents]
            check("STT 짧은 구간 1곳·구분자·소수", len(hs) == 2 and txt == ["짧은 L=20.0m", "(No.0+100~No.0+120)"], txt)
            r = await run("CST", stations=["No.1+250", "1+400.5"])
            check("CST 150.5", r["results"][0].startswith("150.5"), r)
            r = await run("DSTA", handle=al, settings={"간격": 20.0, "문자표기간격": 100.0, "원간격": 100.0, "머리말": ""})
            check("DSTA 51곳", r["marked"] == 51 and r["stations"][5] == "0+100" and r["stations"][-1].startswith("1+000"), r)
            r = await run("DSTA", handle=al, stations=["0+125.5", 333.3], settings={"교차소수": 1})
            check("DSTA 목록 2곳", r["marked"] == 2 and r["stations"] == ["0+125.5", "0+333.3"], r)
            # 이격 거리: 기준선 y=200 위아래에 y=230(좌, +30), y=150(우, -50)
            up = await pl([[0, 230], [1000, 230]])
            dn = await pl([[0, 150], [1000, 150]])
            r = await run("DIBC", handle=al, others=[up, dn], settings={"간격": 250.0})
            t = r["table"]
            check("DIBC 표", t[1][2] == "30.000" and t[1][3] == "-50.000" and t[1][4] == "80.000" and len(t) == 6, t[:3])
            # 보간: 기본 선형 = al, 실시 선형 = y=210 평행선(0~500). 값 = 거리×0.01 + 10
            det = await pl([[0, 210], [500, 210]])
            rows = [["0+000", 10.0], ["0+500", 15.0], ["1+000", 20.0]]
            r = await run("HWLI", base_handle=al, detail_handle=det, rows=rows, settings={"간격": 100.0})
            t = r["table"]
            check("HWLI 0+300 → 13.000", any(row[0] == "0+300" and row[3] == "13.000" for row in t), t)
            # 원곡선: 직선-호-직선
            arcpl = await call("run_lisp", code='(setq _e (entmake (list (cons 0 "LWPOLYLINE") (cons 100 "AcDbEntity") (cons 100 "AcDbPolyline") (cons 90 4) (cons 70 0) (list 10 0.0 500.0) (list 10 100.0 500.0) (cons 42 0.41421356) (list 10 200.0 600.0) (list 10 200.0 700.0)))) (write-line (cdr (assoc 5 (entget (entlast)))) _fp)')
            h = arcpl["lines"][0] if "lines" in arcpl else (arcpl.get("output") or [""])[0]
            r = await run("MIP", handle=h, settings={"높이": 2.0})
            check("MIP IP 표기", len(r["results"]) == 1 and r["results"][0].count(" ") >= 5, r)
            r = await run("DCEN", two_lines=[up, dn])
            check("DCEN 두 선", len(r["results"]) == 1, r)
            txt = (await call("create_text", text="No.12+5", x=0, y=800, height=2))["handle"]
            r = await run("NUST", handles=[txt], settings={"측점구분": "Number", "측점간격": 20.0, "숫자소수": 1})
            check("NUST No.12+5 → 245.0", "245.0" in r["results"][0], r)
            await call("zoom_extents")
            cap = await call("capture_view", output_path=os.path.join(OUT, "skills2.png"))
            check("캡처", cap.get("captured"), cap)
    print("FAIL:", FAIL)


asyncio.run(main())
