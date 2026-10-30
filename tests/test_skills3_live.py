"""스킬 3단계(제방·사면) 시험(실제 AutoCAD 필요) — MCP stdio로 새 시험 도면에서 skill_run.

실행: <python> -X utf8 tests\\test_skills3_live.py [출력폴더]   끝에 "FAIL: []"이면 통과.
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

            async def call(_tool, **kw):
                res = await s.call_tool(_tool, kw)
                txt = res.content[0].text if res.content else ""
                if res.isError:
                    raise RuntimeError("%s: %s" % (_tool, txt))
                return json.loads(txt)

            async def run(cmd, **a):
                return await call("skill_run", command=cmd, args=json.dumps(a, ensure_ascii=False))

            async def pl(pts):
                return (await call("create_polyline", points=json.dumps(pts)))["handle"]

            async def lens(hs):
                """핸들들의 (시작 y, 길이) — 선 개체"""
                code = ("(foreach _h (list %s) (setq _e (entget (handent _h)))"
                        " (write-line (strcat (rtos (caddr (assoc 10 _e)) 2 4) _d (rtos (distance (cdr (assoc 10 _e)) (cdr (assoc 11 _e))) 2 4)) _fp))"
                        % " ".join('"%s"' % h for h in hs))
                return [tuple(float(x) for x in ln.split("\t")) for ln in (await call("run_lisp", code=code))["lines"]]

            def hs_of(res, i=0):
                return res["results"][i].strip("()").split()

            print("시험 도면:", await call("new_drawing"))
            # DSLO 쌓기: 안쪽 y=0, 바깥쪽 y=-20, 주 10m·보조 4 → 2m마다 51개(긴 20 ×11, 짧은 10 ×40)
            top = await pl([[0, 0], [100, 0]])
            bot = await pl([[0, -20], [100, -20]])
            r = await run("DSLO", handles=[top, bot])
            L = await lens(hs_of(r))
            check("DSLO 51개", len(L) == 51, len(L))
            check("DSLO 긴 11·짧은 40", sum(1 for _y, d in L if abs(d - 20) < 1e-6) == 11 and
                  sum(1 for _y, d in L if abs(d - 10) < 1e-6) == 40, sorted({d for _y, d in L}))
            check("DSLO 쌓기는 안쪽에서 시작", all(abs(y) < 1e-6 for y, _d in L), L[:3])
            r = await run("DSLO", handles=[top, bot], settings={"종류": "깎기"})
            L = await lens(hs_of(r))
            check("DSLO 깎기는 바깥쪽에서 시작", all(abs(y + 20) < 1e-6 for y, _d in L), L[:3])
            # NSLO: 간격 2, 긴 3·짧은 1.5 번갈아
            ns = await pl([[0, 100], [20, 100]])
            r = await run("NSLO", handle=ns, side_point=[5, 90])
            L = await lens(hs_of(r))
            check("NSLO 11개 번갈아", len(L) == 11 and sum(1 for _y, d in L if abs(d - 3) < 1e-6) == 6, L)
            # DFB: 한 점 → 직선 끝선, 주 2·보조 2 → 9등분 10개(긴 4·짧은 6)
            arc = await pl([[-20, 180], [20, 180]])
            r = await run("DFB", apex=[0, 200], handle=arc)
            L = await lens(hs_of(r))
            check("DFB 10개(긴 4)", len(L) == 10 and sum(1 for _y, d in L if d > 20) == 4, L)
            # SLL: H1000·V200(세로 5배), 1:2 위로 10m → 끝 (10, 225)
            r = await run("SLL", start_point=[0, 200], slope="1:2", end_x=10, settings={"H축척": 1000, "V축척": 200})
            e = await call("get_entity", handle=r["results"][0])
            check("SLL 끝점 (10,225)", abs(e["end_point"][0] - 10) < 1e-6 and abs(e["end_point"][1] - 225) < 1e-6, e)
            # SLT: 수평 15, 수직 10 → 1:1.50
            r = await run("SLT", p1=[0, 300], p2=[15, 310])
            check("SLT 1:1.50", "1:1.50" in r["results"][0], r)
            # CSS: 지반 y=400, 점 (0,410) → 쌓기 1:1.5, 소단 5m·1m → 끝 (16,400)
            g = await pl([[-100, 400], [100, 400]])
            r = await run("CSS", ground_handle=g, point=[0, 410], side="R")
            check("CSS 쌓기·지반 만남", r["results"][0].startswith("(쌓기 T"), r)
            e = await call("get_entity", handle=r["results"][0].strip("()").split()[2])
            pts = e.get("points") or e.get("coordinates") or []
            check("CSS 끝 (16,400)", pts and abs(pts[-1][0] - 16) < 1e-6 and abs(pts[-1][1] - 400) < 1e-6, e)
            # CUT: 지반 (0,500)→(40,520) 1:2, 층높이 1m → 20단
            g2 = await pl([[0, 500], [40, 520]])
            r = await run("CUT", ground_handle=g2, p1=[0, 500], p2=[40, 520])
            check("CUT 20단", r["results"][0] == "20", r)
            g3 = await pl([[0, 600], [100, 610]])
            r = await run("CUT", ground_handle=g3, p1=[0, 600], p2=[100, 610])
            check("CUT 완만(1:10) 제외 0단", r["results"][0] == "0", r)
            await call("zoom_extents")
            cap = await call("capture_view", output_path=os.path.join(OUT, "skills3.png"))
            check("캡처", cap.get("captured"), cap)
    print("FAIL:", FAIL)


asyncio.run(main())
