# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""MUIN(여러 도면 원래 좌표로 불러오기) 시험(실제 AutoCAD 필요) — MCP stdio로 서버를 띄워 새 시험 도면에서 부른다.

불러올 DWG·DXF는 화면 없는 AutoCAD로 임시 폴더에 만든다. 기준점(INSBASE)이 0이 아니고 단위(INSUNITS)가 달라도
원래 좌표 그대로 들어오는지 본다.
실행: <python> -X utf8 tests\\test_muin_live.py   끝에 "FAIL: []"이면 통과.
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import background as B  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

FAIL = []


def check(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name, info if not cond else "")
    if not cond:
        FAIL.append(name)


tmp = tempfile.mkdtemp(prefix="bc_muin_test_")
slash = lambda p: p.replace(chr(92), "/")
dwg = os.path.join(tmp, "선도면.dwg")
dxf = os.path.join(tmp, "원도면.dxf")
B.build('(entmake (list (cons 0 "LINE") (cons 8 "가선") (list 10 1000.0 2000.0 0.0) (list 11 1100.0 2000.0 0.0)))'
        '(setvar "INSBASE" (list 500.0 500.0 0.0)) (setvar "INSUNITS" 6)', dwg, use_skills=False, preview=False)
B.build('(entmake (list (cons 0 "CIRCLE") (cons 8 "나원") (list 10 3000.0 4000.0 0.0) (cons 40 25.0)))'
        '(entmake (list (cons 0 "TEXT") (cons 8 "나원") (list 10 3000.0 4100.0 0.0) (cons 40 10.0) (cons 1 "한글")))'
        '(setvar "INSBASE" (list 100.0 100.0 0.0)) (setvar "INSUNITS" 6) (command "_.DXFOUT" "%s" "")' % slash(dxf),
        os.path.join(tmp, "dxf_src.dwg"), use_skills=False, preview=False)

READ = r'''
(foreach _s (list (ssget "_X" (list (cons 0 "LINE") (cons 8 "가선"))) (ssget "_X" (list (cons 0 "CIRCLE") (cons 8 "나원")))
                  (ssget "_X" (list (cons 0 "TEXT") (cons 8 "나원"))))
  (if _s (setq _e (entget (ssname _s 0))))
  (write-line (if _s (strcat (cdr (assoc 0 _e)) _d (rtos (cadr (assoc 10 _e)) 2 4) _d (rtos (caddr (assoc 10 _e)) 2 4)
                             _d (if (assoc 40 _e) (rtos (cdr (assoc 40 _e)) 2 4) "-") _d (if (assoc 1 _e) (cdr (assoc 1 _e)) "-")) "없음") _fp))
(setq _b (tblnext "BLOCK" T) _k 0)
(while _b (if (wcmatch (strcase (cdr (assoc 2 _b))) "BC_MUIN_*") (setq _k (1+ _k))) (setq _b (tblnext "BLOCK")))
(write-line (strcat "TMPBLK" _d (itoa _k) _d "INSUNITS" _d (itoa (getvar "INSUNITS"))) _fp)
'''


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

            await call("new_drawing")
            await call("run_lisp", code='(setvar "INSUNITS" 4)')  # 지금 도면은 mm, 불러올 도면은 m — 자동 축척이 끼면 안 됨
            r = await run("MUIN", files=[dwg, dxf])
            check("MUIN: 파일 2개, 객체 3개", len(r["files"]) == 2 and r["entities"] == 3, r)
            got = (await call("run_lisp", code=READ))["lines"]
            check("DWG 선: 원래 좌표(1000,2000)", got[0].startswith("LINE\t1000\t2000"), got)
            check("DXF 원: 원래 좌표(3000,4000)·반지름 25", got[1] == "CIRCLE\t3000\t4000\t25\t-", got)
            check("DXF 한글 문자 그대로", got[2].endswith("\t한글") and "\t3000\t4100\t" in got[2], got)
            check("임시 블록 정의 남지 않음·단위 설정 복원", got[3] == "TMPBLK\t0\tINSUNITS\t4", got)
            r = await call("undo")
            got = (await call("run_lisp", code=READ))["lines"]
            check("UNDO 한 번에 모두 취소", got[:3] == ["없음", "없음", "없음"], (r, got))
            # 폭파하지 않으면 파일 이름 블록으로, 삽입점은 원래 기준점
            r = await run("MUIN", files=[dwg], explode=False)
            b = (await call("run_lisp", code='(setq _s (ssget "_X" (list (cons 0 "INSERT"))) _e (entget (ssname _s 0)))'
                                              '(write-line (strcat (cdr (assoc 2 _e)) _d (rtos (cadr (assoc 10 _e)) 2 4) _d'
                                              ' (rtos (caddr (assoc 10 _e)) 2 4)) _fp)'))["lines"]
            check("폭파 안 함: '선도면' 블록, 삽입점 = 원래 기준점(500,500)", b == ["선도면\t500\t500"], (r, b))
            try:
                await run("MUIN", files=[os.path.join(tmp, "없음.dwg")])
                check("없는 파일은 오류", False)
            except RuntimeError as e:
                check("없는 파일은 오류", "없습니다" in str(e), str(e))
            print("시험 도면은 저장하지 않았습니다.")


try:
    asyncio.run(main())
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("FAIL:", FAIL)
