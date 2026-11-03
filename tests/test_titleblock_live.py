# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""도곽 명령 시험(실제 AutoCAD 필요) — MPTE·EMTT·DTC를 새 시험 도면과 화면 없이 만든 시험 파일로 부른다.

실행: <python> -X utf8 tests\\test_titleblock_live.py [출력폴더]
끝에 "FAIL: []"이면 통과. 출력폴더(기본 %TEMP%\\bc_tb_test)에 시험 파일·캡처를 남긴다.
도곽 셋: 축척 1, 축척 2(도면명은 MTEXT), 90도 회전. 도면번호·도면명은 영역 문자, 축척은 도곽 속성.
"""
import asyncio
import json
import math
import os
import sys

sys.dont_write_bytecode = True
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), "bc_tb_test")
os.makedirs(OUT, exist_ok=True)
FAIL = []
REG = {"blocks": {"TB_TEST": {"items": [
    {"name": "도면번호", "kind": "box", "box": [300, 10, 400, 20]},
    {"name": "도면명", "kind": "box", "box": [300, 25, 400, 40]},
    {"name": "축척", "kind": "attr", "tag": "SCALE"}]}}}


def check(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name, info if not cond else "")
    if not cond:
        FAIL.append(name)


def frames_lisp(frames):
    """frames [(x, y, 축척, 회전도, 도면번호, 도면명, 도면명 MTEXT?, 속성 축척)] → 블록 정의 + 도곽 + 문자."""
    s = ['(if (not (tblsearch "BLOCK" "TB_TEST")) (progn'
         ' (entmake (list (cons 0 "BLOCK") (cons 2 "TB_TEST") (cons 70 2) (list 10 0.0 0.0 0.0)))'
         ' (entmake (list (cons 0 "LWPOLYLINE") (cons 100 "AcDbEntity") (cons 100 "AcDbPolyline") (cons 90 4) (cons 70 1)'
         '  (list 10 0.0 0.0) (list 10 420.0 0.0) (list 10 420.0 297.0) (list 10 0.0 297.0)))'
         ' (entmake (list (cons 0 "ATTDEF") (list 10 350.0 50.0 0.0) (cons 40 3.0) (cons 1 "") (cons 3 "축척")'
         '  (cons 2 "SCALE") (cons 70 0)))'
         ' (entmake (list (cons 0 "ENDBLK")))))']
    for x, y, k, deg, no, title, mt, scale in frames:
        a = math.radians(deg)

        def w(lx, ly):
            return (x + k * (lx * math.cos(a) - ly * math.sin(a)), y + k * (lx * math.sin(a) + ly * math.cos(a)))
        ax, ay = w(350, 50)
        s.append('(entmake (list (cons 0 "INSERT") (cons 2 "TB_TEST") (cons 66 1) (list 10 %f %f 0.0) (cons 41 %f)'
                 ' (cons 42 %f) (cons 43 %f) (cons 50 %f)))' % (x, y, k, k, k, a))
        s.append('(entmake (list (cons 0 "ATTRIB") (list 10 %f %f 0.0) (cons 40 %f) (cons 1 "%s") (cons 2 "SCALE")'
                 ' (cons 70 0) (cons 50 %f))) (entmake (list (cons 0 "SEQEND")))' % (ax, ay, 3 * k, scale, a))
        nx, ny = w(310, 12)
        s.append('(entmake (list (cons 0 "TEXT") (list 10 %f %f 0.0) (cons 40 %f) (cons 1 "%s") (cons 50 %f)))'
                 % (nx, ny, 3 * k, no, a))
        tx, ty = w(305, 37) if mt else w(310, 28)
        if mt:
            s.append('(entmake (list (cons 0 "MTEXT") (cons 100 "AcDbEntity") (cons 100 "AcDbMText") (list 10 %f %f 0.0)'
                     ' (cons 40 %f) (cons 71 1) (cons 1 "%s") (list 11 %f %f 0.0)))' % (tx, ty, 3 * k, title, math.cos(a), math.sin(a)))
        else:
            s.append('(entmake (list (cons 0 "TEXT") (list 10 %f %f 0.0) (cons 40 %f) (cons 1 "%s") (cons 50 %f)))'
                     % (tx, ty, 3 * k, title, a))
    return "".join(s)


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

            async def run(cmd, timeout=300, **a):
                return await call("skill_run", command=cmd, args=json.dumps(a, ensure_ascii=False), timeout=timeout)

            lst = {c["command"]: c for c in await call("skill_list")}
            check("skill_list에 MPTE·EMTT·DTC", all(k in lst for k in ("MPTE", "EMTT", "DTC")))
            # 시험 파일(화면 없이): 도면 C-10(축척 2, MTEXT), C-2(90도)
            f = os.path.join(OUT, "tb_file.dwg")
            bak = os.path.splitext(f)[0] + ".bak"
            for p in (f, bak):
                if os.path.exists(p):
                    os.remove(p)
            await call("build_drawing_background", code=frames_lisp([
                (0, 0, 2.0, 0, "C-10", "종단면도", True, "1/200"),
                (3000, 0, 1.0, 90, "C-2", "평면도", False, "1/500")]), output_path=f, preview=False)
            d = await call("new_drawing")
            print("시험 도면:", d)
            await call("run_lisp", code=frames_lisp([(0, 0, 1.0, 0, "C-1", "위치도", False, "NONE")]))

            r = await run("MPTE", registration=REG)
            check("MPTE 지금 도면", r["frames"] == 1 and r["rows"][1][3:6] == ["C-1", "위치도", "NONE"], r)
            r = await run("MPTE", registration=REG, files=[f])
            got = {row[3]: row[4:6] for row in r["rows"][1:]}
            check("MPTE 파일(축척 2 MTEXT·90도 회전)", got == {"C-10": ["종단면도", "1/200"], "C-2": ["평면도", "1/500"]}, r)
            head = r["rows"][0]
            check("MPTE 경로·도곽핸들 열", head[-2:] == ["경로", "도곽핸들"], head)

            # EMTT: 파일의 C-2 도면명·축척, C-10 도면명(MTEXT에 중괄호) 바꾸기
            rows = [list(x) for x in r["rows"]]
            for row in rows[1:]:
                if row[3] == "C-2":
                    row[4], row[5] = "평면도(1)", "1/600"
                if row[3] == "C-10":
                    row[4] = "종단면도 {갑}"
            e = await run("EMTT", registration=REG, rows=rows)
            check("EMTT 파일 3곳 바꿈", e["changed"] == 3 and not e["skipped"], e)
            check("EMTT 원본 .bak", os.path.exists(bak))
            r2 = await run("MPTE", registration=REG, files=[f])
            got = {row[3]: row[4:6] for row in r2["rows"][1:]}
            check("EMTT 결과 다시 읽기", got == {"C-10": ["종단면도 {갑}", "1/200"], "C-2": ["평면도(1)", "1/600"]}, r2)

            # EMTT 지금 도면(UNDO 묶음) + 자리에 문자가 없는 항목은 건너뜀
            r = await run("MPTE", registration=REG)
            rows = [list(x) for x in r["rows"]]
            rows[1][4] = "위치도 및 색인도"
            e = await run("EMTT", registration=REG, rows=rows)
            check("EMTT 지금 도면", e["changed"] == 1, e)
            t = await call("find_text", keyword="위치도 및 색인도")
            check("EMTT 지금 도면 글자 확인", t.get("count", len(t.get("results", []))) >= 1, t)

            # DTC: 두 도면을 한 표로, 도면번호 자연 정렬(C-1, C-2, C-10) + 지금 도면에 그리기
            r = await run("DTC", registration=REG, files=["(지금 도면)", f], insert_point=[0, -50],
                          settings={"기타항목": "축척"})
            nos = [row[1] for row in r["rows"][1:]]
            check("DTC 자연 정렬", nos == ["C-1", "C-2", "C-10"], r)
            check("DTC 머리", r["rows"][0] == ["순번", "도면번호", "도면명", "축척"], r["rows"][0])
            check("DTC 그림", r.get("drawn"), r)
            await call("zoom_extents")
            cap = await call("capture_view", output_path=os.path.join(OUT, "titleblock.png"))
            check("캡처", cap.get("captured"), cap)
    print("FAIL:", FAIL)


asyncio.run(main())
