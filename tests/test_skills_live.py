# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""스킬 시험(실제 AutoCAD 필요) — MCP stdio로 서버를 띄워 새 시험 도면에서 skill_run을 전부 부른다.

실행: <python> -X utf8 tests\\test_skills_live.py [출력폴더]
끝에 "FAIL: []"이면 통과. 출력폴더(기본 %TEMP%\\bc_skill_test)에 캡처 PNG와 PDF를 남긴다.
"""
import asyncio
import json
import os
import sys

sys.dont_write_bytecode = True  # 패키지 폴더(동기화 폴더일 수 있음)에 __pycache__를 만들지 않는다
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), "bc_skill_test")
os.makedirs(OUT, exist_ok=True)
FAIL = []


def check(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name, info if not cond else "")
    if not cond:
        FAIL.append(name)


async def main():
    params = StdioServerParameters(command=sys.executable, args=["-X", "utf8", os.path.join(ROOT, "src", "server.py")])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            check("도구 수 71", len(tools) == 71, len(tools))

            async def text(name, **kw):
                res = await s.call_tool(name, kw)
                txt = res.content[0].text if res.content else ""
                if res.isError:
                    raise RuntimeError("%s: %s" % (name, txt))
                return txt

            check("안내문 첫머리에 guide", "guide를 한 번 부른다" in (init.instructions or ""))
            g = await text("guide")
            check("guide 작도 요령", "set_text_style" in g and "create_dimension" in g and "skill_list" in g)
            ga = await text("guide", topic="전체")
            check("guide 전체", all(k in ga for k in ("[작도", "[토목", "[도면")))
            bad = await s.call_tool("guide", {"topic": "없는주제"})
            check("guide 잘못된 주제는 오류", bad.isError)

            async def call(name, **kw):
                res = await s.call_tool(name, kw)
                txt = res.content[0].text if res.content else ""
                if res.isError:
                    raise RuntimeError("%s: %s" % (name, txt))
                return json.loads(txt)

            async def run(cmd, **a):
                return await call("skill_run", command=cmd, args=json.dumps(a, ensure_ascii=False))

            lst = await call("skill_list")
            check("skill_list 17개", len(lst) >= 17, len(lst))
            d = await call("new_drawing")
            print("시험 도면:", d)

            r = await run("FE", base_point=[0, 0], base_el=100, points=[[5, 2.5], [8, -1]],
                          settings={"높이": 0.5, "소수": 3})
            check("FE 값", r["results"][0].startswith("(102.5") and r["results"][1].startswith("(99.0"), r)
            r = await run("FW", base_point=[0, 0], base_el=100, points=[[12, 1]], settings={"형식": 6})
            check("FW 형식6", r["results"][0].startswith("(101.0"), r)
            r = await run("FEL", base_point=[0, 0], base_el=100, targets=[103.5])
            check("FEL 위치", "3.5" in r["results"][0], r)
            r = await run("GEL", p1=[0, 20], el1=10, p2=[10, 20], el2=20, points=[[15, 20]])
            check("GEL 연장", r["results"][0].startswith("(25.0"), r)
            r = await run("SLEL", base_point=[0, 40], base_el=10, slope="2%", points=[[30, 80]])
            check("SLEL 2%", r["results"][0].startswith("(11.0"), r)
            r = await run("XY", points=[[1000, 2000]], settings={"높이": 1.0})
            check("XY 객체 3", r["results"][0].count(" ") == 2, r)
            r = await run("CIM", rows=[["번호", "X", "Y"], [1, 100, 200], [2, 100, 230], [3, 130, 230], [4, 130, 200]],
                          settings={"열": "번호,X,Y", "좌표": "수학", "닫기": True, "높이": 1.0})
            check("CIM 4점", r["points"] == 4, r)
            got = await call("get_entities", entity_type="LWPOLYLINE", limit=50)
            pl = [e for e in got.get("entities", []) if abs(e.get("bbox_min", [0, 0])[0] - 100) < 1e-6]
            check("CIM 폴리선 생김", len(pl) >= 1, got)
            h = pl[0]["handle"] if pl else ""
            r = await run("ZBC", handle=h, table_point=[150, 240], settings={"높이": 1.0})
            check("ZBC", len(r["results"]) == 1, r)
            r = await run("WCD", handle=h, settings={"높이": 1.0})
            check("WCD 8문자", r["results"][0].count(" ") == 7, r)
            r = await run("CEX", handles=[h], settings={"좌표": "수학", "소수": 1, "순번": True})
            check("CEX 4행", r["row_count"] == 4 and r["rows"][0][1:] == ["100.0", "200.0"], r)
            r = await run("XYB", handles=[h], base_point=[100, 200], sx=2, sy=0.5)
            check("XYB", len(r["results"]) == 1, r)
            # 삼각망: Z 있는 점
            pts = "".join('(entmake (list (cons 0 "POINT") (list 10 %f %f %f)))' % (x, y, z)
                          for x, y, z in [(300, 0, 10), (320, 0, 12), (300, 20, 14), (320, 20, 16), (310, 10, 20)])
            await call("run_lisp", code=pts)
            r = await run("DTIN", settings={"대상선": False, "대상블록": False, "최대변": 0})
            check("DTIN 4면", r["faces"] == 4, r)
            r = await run("IEL", points=[[305, 5]])
            check("IEL 값", r["results"][0] != "(nil nil)", r)
            r = await run("FPEL", start_point=[0, 300], start_el=10, rows=[["0+020", 12.0], ["0+050", 11.0]],
                          settings={"H축척": 1000, "V축척": 200})
            check("FPEL 2개", r["marked"] == 2, r)
            await call("zoom_extents")
            cap = await call("capture_view", output_path=os.path.join(OUT, "skills.png"))
            check("캡처", cap.get("captured"), cap)
            # 다중 플롯: 도곽 두 개 새 도면
            await call("new_drawing")
            await call("create_rectangle", x1=0, y1=0, x2=420, y2=297)
            await call("create_rectangle", x1=500, y1=0, x2=920, y2=297)
            r = await call("skill_run", command="MPL", args=json.dumps({"output_dir": OUT, "merge": True}), timeout=300)
            check("MPL 2장+병합", r["ok"] and len(r["pdfs"]) == 2 and os.path.exists(r.get("merged", "")), r)
    print("FAIL:", FAIL)


asyncio.run(main())
