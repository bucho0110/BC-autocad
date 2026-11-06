# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""모형·배치 공간 시험(실제 AutoCAD 필요) — 조회·작도의 layout, undo 판단, find_text 줌, 해치·선분 원자 작도의 공간,
run_lisp 입력 대기 함수 거절, 지시선 한글 글꼴 경고. 새 시험 도면에서만 한다.

실행: <python> -X utf8 tests\\test_layout_live.py   끝에 "FAIL: []"이면 통과.
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

            async def fails(name, **kw):
                try:
                    await call(name, **kw)
                    return ""
                except RuntimeError as e:
                    return str(e)

            print("시험 도면:", await call("new_drawing"))
            lay = [x["name"] for x in (await call("get_layouts"))["layouts"] if x["name"] != "Model"][0]
            ln = await call("create_line", start_x=0, start_y=0, end_x=100, end_y=0)
            ci = await call("create_circle", center_x=50, center_y=50, radius=10, layout=lay)
            check("배치에 작도 → layout 표시", ci.get("layout") == lay and "layout" not in ln, (ci, ln))
            await call("create_text", text="배치문자ABC", x=20, y=20, height=3, layout=lay)

            m = await call("get_entities")
            p = await call("get_entities", layout=lay)
            a = await call("get_entities", layout="*")
            check("기본 조회는 모형만", m["count"] == 1 and m["entities"][0]["handle"] == ln["handle"], m)
            nv = lambda es: [e for e in es if e["type"] != "VIEWPORT"]  # noqa: E731 — 배치를 연 적이 있으면 뷰포트가 있다
            check("배치 이름으로 조회", len(nv(p["entities"])) == 2 and all(e.get("layout") == lay for e in p["entities"]), p)
            check("전체 조회 + 배치 개체에만 layout", len(nv(a["entities"])) == 3
                  and sum(1 for e in nv(a["entities"]) if "layout" in e) == 2
                  and all("layout" not in e for e in a["entities"] if e["handle"] == ln["handle"]), a)
            c = await call("count_entities", layout=lay)
            cv = await call("count_entities", layout=lay, entity_type="VIEWPORT")
            check("count_entities 배치", c["total"] - cv["matched"] == 2, (c, cv))
            h = await call("ssget_query", fields="handles", layout="*")
            check("ssget_query handles 전체", len(nv(h["entities"])) == 3
                  and sum(1 for e in nv(h["entities"]) if "layout" in e) == 2, h)
            err = await fails("get_entities", layout="없는배치")
            check("없는 배치 이름은 알림", "배치가 없습니다" in err, err)

            ft = await call("find_text", keyword="배치문자", layout=lay, zoom=True)
            check("find_text 배치 + 다른 탭이면 줌 건너뜀", ft["found"] == 1 and ft["results"][0].get("layout") == lay
                  and "skipped" in ft.get("zoom", {}), ft)
            ft0 = await call("find_text", keyword="배치문자")
            check("find_text 기본은 모형만", ft0["found"] == 0, ft0)

            # 배치의 닫힌 폴리선으로 해치(경계가 있는 공간에 만든다)
            pl = await call("create_polyline", points=[[0, 0], [10, 0], [10, 10], [0, 10]], closed=True, layout=lay)
            ht = await call("create_hatch", boundary_handles=[pl["handle"]])
            hl = await call("entget_by_handles", handles=[ht["handle"]])
            check("배치 경계로 해치", hl["entities"][0].get("layout") == lay, hl)

            # 선분 원자 작도: 기준 개체가 배치에 있으면 같은 배치에
            dl = await call("draw_lines_atomic", base_handle=pl["handle"], segments=[[0, 20, 10, 20]])
            de = await call("entget_by_handles", handles=dl["handles"])
            check("draw_lines_atomic 배치 기준 → 같은 배치", de["entities"][0].get("layout") == lay, de)

            # undo: 배치에서 한 작업도 '바뀜'으로 판단
            await call("create_circle", center_x=80, center_y=80, radius=5, layout=lay)
            u = await call("undo")
            check("배치 작업 undo → changed", u.get("changed") is True, u)

            # run_lisp: 입력 대기 함수는 보내기 전에 거절
            err = await fails("run_lisp", code='(getpoint "x")')
            check("run_lisp getpoint 거절", "쓸 수 없습니다" in err, err)
            ok = await call("run_lisp", code='(write-line (getvar "CLAYER") _fp)')
            check("run_lisp getvar 통과", ok["count"] == 1, ok)

            ld = await call("create_leader", points=[[0, -20], [10, -10], [20, -10]], text="한글 지시선")
            check("create_leader 한글 글꼴 경고", "한글 글꼴" in ld.get("warning", ""), ld)
    print("FAIL:", FAIL)


asyncio.run(main())
