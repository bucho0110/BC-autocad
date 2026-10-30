"""고친 결함 되풀이 확인 1(스킬 코드, 실제 AutoCAD 필요) — MCP stdio, 새 시험 도면.

실행: <python> -X utf8 tests\\test_regression_live.py   끝에 "FAIL: []"이면 통과.
"""
import asyncio
import json
import os
import sys

sys.dont_write_bytecode = True  # 패키지 폴더(동기화 폴더일 수 있음)에 __pycache__를 만들지 않는다

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
                return res.isError, (txt if res.isError else json.loads(txt))

            async def run(cmd, **a):
                return await call("skill_run", command=cmd, args=json.dumps(a, ensure_ascii=False))

            async def lisp(code):
                err, v = await call("run_lisp", code=code)
                return v if err else v["lines"]

            print("시험 도면:", (await call("new_drawing"))[1])
            # 라이브러리 올리기(아무 skill_run 한 번)
            await run("CST", stations=["0+000", "0+010"])
            out = await lisp(
                '(setq _c (bc:el-cfg "CEE" bc:cee-extra))'
                ' (write-line (bc:replace-last-num "EL=-1.50" 2.0 _c) _fp)'
                ' (write-line (bc:replace-last-num "EL.(-)1.50" 2.0 _c) _fp)'
                ' (write-line (bc:replace-last-num "EL=+1.50" -0.5 _c) _fp)'
                ' (write-line (bc:mtext-plain "{\\\\fArial|b0;\\\\H0.8x;12.50}\\\\Pm \\\\L3.0\\\\l") _fp)'
                ' (write-line (bc:rtos (bc:parse-slope "1:100" "경사기본") 2 6) _fp)'
                ' (write-line (bc:rtos (bc:parse-slope "-2%" "경사기본") 2 6) _fp)'
                ' (write-line (bc:rtos (bc:parse-slope "100" "경사기본") 2 6) _fp)')
            check("CEE 일반 음수 → 양수 부호 없음", out[0] == "EL=2.00", out[0])
            check("CEE 괄호 부호 유지", out[1] == "EL.(+)2.00", out[1])
            check("CEE + 형식 음수", out[2] == "EL=-0.50", out[2])
            check("MTEXT 서식 걷기", out[3].split() == ["12.50", "m", "3.0"], out[3])
            check("경사 1:100", out[4] == "0.010000", out[4])
            check("경사 -2%", out[5] == "-0.020000", out[5])
            check("경사 100(=1:100)", out[6] == "0.010000", out[6])
            # GEL 정점 보간: 호에는 거절
            out = await lisp('(entmake (list (cons 0 "ARC") (list 10 0.0 0.0 0.0) (cons 40 5.0) (cons 50 0.0) (cons 51 1.0)))'
                             ' (write-line (vl-princ-to-string (bc:gel-interp-ok (entlast))) _fp)')
            check("GEL 호 거절", out[0] != "T", out)
            # WCD 없는 핸들 → 오류(원점에 그리지 않음)
            err, v = await run("WCD", handle="FFFFFF")
            check("WCD 없는 핸들 거절", err and "없습니다" in v, v)
            # 원을 ZBC에 → 형식 거절
            c = (await call("create_circle", center_x=0, center_y=0, radius=3))[1]["handle"]
            err, v = await run("ZBC", handle=c, table_point=[0, 0])
            check("ZBC 원 거절", err and "LWPOLYLINE" in v, v)
            # XYB: 잠긴 레이어 섞이면 아무것도 안 바꾸고 거절
            l1 = (await call("create_line", start_x=0, start_y=0, end_x=10, end_y=0))[1]["handle"]
            l2 = (await call("create_line", start_x=0, start_y=5, end_x=10, end_y=5, layer="잠금시험"))[1]["handle"]
            await call("set_layer", name="잠금시험", locked=True)
            n0 = (await call("count_entities"))[1]
            err, v = await run("XYB", handles=[l1, l2], base_point=[0, 0], sx=2, sy=1)
            n1 = (await call("count_entities"))[1]
            check("XYB 잠긴 레이어 거절·무변경", err and "잠긴" in v and n0 == n1, (v, n0, n1))
            err, v = await run("XYB", handles=[l1], base_point=[0, 0], sx=0, sy=1)
            check("XYB 축척 0 거절", err and "0" in v, v)
            # 설정 정수 → 실수 변환(ZBC 높이 3)
            pl = (await call("create_polyline", points=json.dumps([[0, 0], [10, 0], [10, 10]]), closed=True))[1]["handle"]
            err, v = await run("ZBC", handle=pl, table_point=[20, 10], settings={"높이": 3})
            check("설정 정수 높이 허용", not err, v)
            err, v = await run("FE", base_point=[0, 0], base_el=1, points=[[1, 1]], settings={"없는키": 1})
            check("없는 설정 키 거절", err and "없는 설정 키" in v, v)
            # 핸들을 문자열 하나로 → 목록 요구
            err, v = await run("NUST", handles="2F3")
            check("handles 문자열 거절", err and "목록" in v, v)
    print("FAIL:", FAIL)


asyncio.run(main())
