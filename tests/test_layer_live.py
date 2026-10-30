# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""레이어 명령 13개와 CR 시험(실제 AutoCAD 필요) — MCP stdio로 서버를 띄워 새 시험 도면에서 skill_run을 부른다.

실행: <python> -X utf8 tests\\test_layer_live.py   끝에 "FAIL: []"이면 통과.
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


SETUP = r'''
(foreach l (list "가" "나" "다" "라")
  (entmake (list (cons 0 "LAYER") (cons 100 "AcDbSymbolTableRecord") (cons 100 "AcDbLayerTableRecord") (cons 2 l) (cons 70 0) (cons 62 7)))
  (entmake (list (cons 0 "LINE") (cons 8 l) (list 10 0.0 0.0 0.0) (list 11 10.0 0.0 0.0)))
  (write-line (strcat l _d (cdr (assoc 5 (entget (entlast))))) _fp))
(setvar "CLAYER" "0")
'''
STATE = r'''
(foreach l (list "0" "가" "나" "다" "라")
  (setq _t (tblsearch "LAYER" l))
  (write-line (strcat l _d (if (< (cdr (assoc 62 _t)) 0) "off" "on") _d (if (= 1 (logand 1 (cdr (assoc 70 _t)))) "frz" "-")
                      _d (if (= 4 (logand 4 (cdr (assoc 70 _t)))) "lck" "-")) _fp))
(write-line (strcat "CUR" _d (getvar "CLAYER")) _fp)
'''


def state(lines):
    st = {}
    for ln in lines:
        p = ln.split("\t")
        if p[0] == "CUR":
            st["cur"] = p[1]
        else:
            st[p[0]] = tuple(p[1:])
    return st


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

            async def st():
                return state((await call("run_lisp", code=STATE))["lines"])

            await call("new_drawing")
            h = dict(ln.split("\t") for ln in (await call("run_lisp", code=SETUP))["lines"])
            lst = await call("skill_list")
            check("명령 69개(레이어 13·CR·MUIN 포함)", len(lst) == 69 and {"LOL", "CR", "CCL", "MUIN"} <= {x["command"] for x in lst},
                  len(lst))

            await run("LOL", layers=["가"])
            x = await st()
            check("LOL: 가만 켜짐, 현재 레이어도 가로", x["가"][0] == "on" and x["나"][0] == "off" and x["0"][0] == "off"
                  and x["cur"] == "가", x)
            await run("LON")
            x = await st()
            check("LON: 전부 켜짐", all(x[k][0] == "on" for k in ("0", "가", "나", "다", "라")), x)
            await run("LOF", handles=[h["나"]])
            x = await st()
            check("LOF(핸들로): 나만 꺼짐", x["나"][0] == "off" and x["다"][0] == "on", x)
            await run("OLO")
            x = await st()
            check("OLO: 꺼져 있던 나만 켜지고 나머지 꺼짐", x["나"][0] == "on" and x["가"][0] == "off" and x["cur"] == "나", x)
            await run("LON")
            await call("run_lisp", code='(setvar "CLAYER" "0")')
            await run("LFR", layers=["다", "0"])
            x = await st()
            check("LFR: 다 동결, 현재 레이어 0은 제외", x["다"][1] == "frz" and x["0"][1] == "-", x)
            await run("LTH")
            x = await st()
            check("LTH: 동결 전부 해제", all(x[k][1] == "-" for k in ("0", "가", "나", "다", "라")), x)
            await run("FRE", layers=["라"])
            x = await st()
            check("FRE: 라 외 동결, 현재 레이어는 라로", x["라"][1] == "-" and x["가"][1] == "frz" and x["0"][1] == "frz"
                  and x["cur"] == "라", x)
            await run("LTH")
            await run("LLO", layers=["가"])
            x = await st()
            check("LLO: 가 잠김", x["가"][2] == "lck" and x["나"][2] == "-", x)
            await run("LUL", layers=["가"])
            x = await st()
            check("LUL: 가 잠금 풀림", x["가"][2] == "-", x)
            await run("LOE", layers=["나"])
            x = await st()
            check("LOE: 나 외 전부 잠김", x["나"][2] == "-" and x["가"][2] == "lck" and x["라"][2] == "lck", x)
            await run("ULA")
            x = await st()
            check("ULA: 잠금 전부 해제", all(x[k][2] == "-" for k in ("0", "가", "나", "다", "라")), x)
            r = await run("SCL", handle=h["다"])
            x = await st()
            check("SCL: 객체 레이어 다가 현재로", x["cur"] == "다" and r["results"] == ["다"], (x, r))
            await run("LLO", layers=["라"])
            r = await run("CCL", handles=[h["가"], h["라"]])
            lay = (await call("run_lisp", code='(foreach _h (list "%s" "%s") (write-line (cdr (assoc 8 (entget (handent _h)))) _fp))'
                              % (h["가"], h["라"])))["lines"]
            check("CCL: 가 객체는 현재(다)로, 잠긴 라는 그대로", lay == ["다", "라"] and r["results"] == ["1"], (lay, r))
            await run("ULA")
            try:
                await run("LOF", layers=["없는레이어"])
                check("없는 레이어는 오류", False)
            except RuntimeError as e:
                check("없는 레이어는 오류", "없는레이어" in str(e), str(e))

            # CR: 두 문자를 사각형 (100,100)-(200,160) 가운데(150,130)로, 서로 간격 유지
            t = (await call("run_lisp", code=
                 '(entmake (list (cons 0 "TEXT") (list 10 0.0 0.0 0.0) (cons 40 5.0) (cons 1 "ABC")))'
                 '(write-line (cdr (assoc 5 (entget (entlast)))) _fp)'
                 '(entmake (list (cons 0 "TEXT") (list 10 0.0 -10.0 0.0) (cons 40 5.0) (cons 1 "DEF")))'
                 '(write-line (cdr (assoc 5 (entget (entlast)))) _fp)'))["lines"]
            r = await run("CR", handles=t, p1=[100, 100], p2=[200, 160])
            box = (await call("run_lisp", code=
                   '(setq _a (bc:cr-box (handent "%s")) _b (bc:cr-box (handent "%s")))'
                   '(write-line (strcat (rtos (/ (+ (min (caar _a) (caar _b)) (max (caadr _a) (caadr _b))) 2.0) 2 4) _d'
                   ' (rtos (/ (+ (min (cadar _a) (cadar _b)) (max (cadadr _a) (cadadr _b))) 2.0) 2 4) _d'
                   ' (rtos (- (cadar _a) (cadar _b)) 2 4) _d (itoa (cdr (assoc 72 (entget (handent "%s")))))'
                   ' (itoa (cdr (assoc 73 (entget (handent "%s")))))) _fp)' % (t[0], t[1], t[0], t[0])))["lines"][0].split("\t")
            check("CR: 묶음 가운데가 사각형 가운데", abs(float(box[0]) - 150) < 0.01 and abs(float(box[1]) - 130) < 0.01, box)
            check("CR: 문자 사이 간격 유지(10)·가운데 정렬", abs(float(box[2]) - 10) < 0.01 and box[3] == "12", box)
            print("시험 도면은 저장하지 않았습니다.")


asyncio.run(main())
print("FAIL:", FAIL)
