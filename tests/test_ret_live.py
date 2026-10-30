# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""RET 철근 재료표 시험(실제 AutoCAD 필요) — 새 시험 도면에 철근 상세를 만들고 skill_run을 부른다.

실행: <python> -X utf8 tests\\test_ret_live.py   끝에 "FAIL: []"이면 통과.
상세 모양(실무 도면 형식): 원(반지름 4) 안 번호, 원 밑 가로선, 선 위 '직경 L=길이(mm) N=개수', 선 아래 형상 치수(a=…).
철근 번호 블록(속성 RB_NO·RB_DIA, 원 포함) + 'L=1.050'(m) 형식도 함께.
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


H = '(write-line (cdr (assoc 5 (entget (entlast)))) _fp)'


def tx(s, x, y):
    return '(entmake (list (cons 0 "TEXT") (list 10 %.3f %.3f 0.0) (cons 40 2.5) (cons 1 "%s"))) %s' % (x, y, s, H)


def detail(x, y, no_lines, dia, L, N, extra=""):
    """원 가운데 (x, y). 번호 여러 줄이면 위→아래."""
    s = '(entmake (list (cons 0 "CIRCLE") (list 10 %.3f %.3f 0.0) (cons 40 4.0))) %s' % (x, y, H)
    s += '(entmake (list (cons 0 "LINE") (list 10 %.3f %.3f 0.0) (list 11 %.3f %.3f 0.0))) %s' % (x - 4, y - 4, x + 90, y - 4, H)
    for i, t in enumerate(no_lines):
        s += tx(t, x - 2, y + 0.5 - i * 3 if len(no_lines) > 1 else y - 1.2)
    for t, dx in ((dia, 5.5), ("L=%s" % L, 41.2), ("N=%s" % N, 69.9)):
        if t:
            s += tx(t, x + dx, y - 3.8)
    if extra:
        s += tx(extra, x + 23.6, y - 9)  # 선 아래 형상 치수 — 읽지 않아야
    return s


BLOCK = ('(if (not (tblsearch "BLOCK" "CSBNUM1-JEWON")) (progn'
         ' (entmake (list (cons 0 "BLOCK") (cons 2 "CSBNUM1-JEWON") (cons 70 2) (list 10 0.0 0.0 0.0)))'
         ' (entmake (list (cons 0 "CIRCLE") (list 10 5.0 4.2 0.0) (cons 40 4.0)))'
         ' (entmake (list (cons 0 "ATTDEF") (list 10 2.0 2.5 0.0) (cons 40 3.0) (cons 1 "XX") (cons 3 "번호") (cons 2 "RB_NO") (cons 70 0)))'
         ' (entmake (list (cons 0 "ATTDEF") (list 10 11.5 1.5 0.0) (cons 40 3.0) (cons 1 "D22") (cons 3 "직경") (cons 2 "RB_DIA") (cons 70 0)))'
         ' (entmake (list (cons 0 "ENDBLK")))))')


def block_detail(x, y, no, dia, L, N):
    """블록 삽입점 (x, y), 축척 0.9 → 원 가운데 (x + 4.5, y + 3.78) 반지름 3.6."""
    # 속성 붙은 블록은 SEQEND까지 넣어야 INSERT가 생긴다 — 그 뒤의 entlast가 INSERT
    s = ('(entmake (list (cons 0 "INSERT") (cons 2 "CSBNUM1-JEWON") (list 10 %.3f %.3f 0.0) (cons 41 0.9) (cons 42 0.9) (cons 43 0.9) (cons 66 1)))'
         ' (entmake (list (cons 0 "ATTRIB") (list 10 %.3f %.3f 0.0) (cons 40 2.7) (cons 1 "%s") (cons 2 "RB_NO") (cons 70 0)))'
         ' (entmake (list (cons 0 "ATTRIB") (list 10 %.3f %.3f 0.0) (cons 40 2.7) (cons 1 "%s") (cons 2 "RB_DIA") (cons 70 0)))'
         ' (entmake (list (cons 0 "SEQEND"))) (write-line (cdr (assoc 5 (entget (entlast)))) _fp)'
         % (x, y, x + 1.8, y + 2.3, no, x + 10.4, y + 1.4, dia))
    s += '(entmake (list (cons 0 "LINE") (list 10 %.3f %.3f 0.0) (list 11 %.3f %.3f 0.0))) %s' % (x, y, x + 90, y, H)
    s += tx("L=%s" % L, x + 33, y + 0.5) + tx("N=%s" % N, x + 68, y + 0.5)
    return s


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
            # 1열(x 0): W1 H22 · W2 H22 · W4 H16 · F4 H16 · F1 H16, 2열(x 125): F3 H22 · T1 H13 · W3 H13 · W1-1(두 줄) H19
            hs = []
            for i, (no, dia, L, N, ex) in enumerate([(["W1"], "H22", "4828", "4", ""), (["W2"], "H22", "3055", "4", "a=2555"),
                                                     (["W4"], "H16", "1048", "20", ""), (["F4"], "H16", "1048", "15", "b=500"),
                                                     (["F1"], "H16", "3290", "4", "")]):
                hs += await lisp(detail(0, 100 - i * 12.5, no, dia, L, N, ex))
            for i, (no, dia, L, N) in enumerate([(["F3"], "H22", "2990", "4"), (["T1"], "H13", "550", "4"),
                                                 (["W3"], "H13", "4520", "4"), (["W1", "-1"], "H19", "2,823", "36")]):
                hs += await lisp(detail(125, 100 - i * 12.5, no, dia, L, N))
            # 도면 속 철근 표시(원 + 직경만) — 상세 아님
            hs += await lisp(detail(250, 100, ["W9"], "H22", "", ""))
            # N= 빠진 상세 — 인식 안 됨
            hs += await lisp(detail(250, 80, ["Z1"], "H22", "1000", ""))
            await lisp(BLOCK)
            # 번호 블록 + 길이 m + 1m당 개수(소수)
            hs += await lisp(block_detail(0, 30, "D1", "H13", "1.050", "20"))
            hs += await lisp(block_detail(0, 15, "H1", "H13", "0.953", "6.67"))

            r = await run("RET", handles=hs, insert_point=[400, 100], settings={"할증": 3.0, "비고": "ADD %", "강도별": True,
                                                                                 "길이단위": "자동(소수점 있으면 m)"})
            t = r["tables"][0]["rows"] if r["tables"] else []
            print(json.dumps(t, ensure_ascii=False))
            check("RET 상세 11개(도면 속 표시는 건너뜀), N 없는 Z1 하나 인식 안 됨",
                  r["details"] == 11 and [b["no"] for b in r["unrecognized"]] == ["Z1"], (r["details"], r["unrecognized"]))
            want = [["W1", "H22", "4.828", "4", "19.312", "", "", "ADD 3%"], ["W2", "H22", "3.055", "4", "12.220", "", "", ""],
                    ["F3", "H22", "2.990", "4", "11.960", "", "", ""],
                    ["소             계", "", "", "", "43.492", "3.040Kg/M", "0.132TON", "0.136TON"],
                    ["W1-1", "H19", "2.823", "36", "101.628", "", "", ""],
                    ["소             계", "", "", "", "101.628", "2.250Kg/M", "0.229TON", "0.236TON"],
                    ["W4", "H16", "1.048", "20", "20.960", "", "", ""], ["F1", "H16", "3.290", "4", "13.160", "", "", ""],
                    ["F4", "H16", "1.048", "15", "15.720", "", "", ""],
                    ["소             계", "", "", "", "49.840", "1.560Kg/M", "0.078TON", "0.080TON"],
                    # 블록 상세(원 가운데 x 4.5)는 x 0 열 바로 오른쪽 열 → 머리 글자 순 W, F, D, H, T
                    ["W3", "H13", "4.520", "4", "18.080", "", "", ""], ["D1", "H13", "1.050", "20", "21.000", "", "", ""],
                    ["H1", "H13", "0.953", "6.67", "6.357", "", "", ""], ["T1", "H13", "0.550", "4", "2.200", "", "", ""],
                    ["소             계", "", "", "", "47.637", "0.995Kg/M", "0.047TON", "0.049TON"],
                    ["총             계", "", "", "", "", "", "0.486TON", "0.501TON"]]
            for i, (g, e) in enumerate(zip(t, want)):
                if g != e:
                    check("RET 표 %d번째 줄" % (i + 1), False, (g, e))
                    break
            else:
                check("RET 표: 직경 큰 순·머리 글자 처음 나온 순(W→F→D→H→T)·번호 순, 두 줄 번호, mm·m 길이, 소수 개수, 소계·총계·할증",
                      len(t) == len(want), len(t))
            n = await lisp('(defun _n (f / x) (if (setq x (ssget "_X" f)) (sslength x) 0))'
                           '(write-line (strcat (itoa (_n (list (cons 0 "LINE") (cons 8 "CS-DIML,CS-CONC-MAJR")))) _d'
                           ' (itoa (_n (list (cons 0 "TEXT") (cons 8 "CS-DIMT")))) _d (itoa (_n (list (cons 0 "RAY"))))) _fp)')
            c = n[0].split("\t")
            # 가로선 17줄+1(머리 포함 줄 16 + 1) + 세로선, 문자 = 제목 1 + 머리 8 + 철근 줄 6칸씩 + 소계·총계
            check("RET 표 작도: 선·문자가 그려지고 인식 못 한 원에 광선 1개", int(c[0]) > 20 and int(c[1]) > 80 and c[2] == "1", c)
            r = await run("RET", handles=hs, settings={"비고": "표기 안 함", "정렬": "번호 이름순"})
            t = r["tables"][0]["rows"]
            check("RET 비고 안 함·번호 이름순: H22 줄 F3, W1, W2 / 비고 빈칸", [x[0] for x in t[:3]] == ["F3", "W1", "W2"]
                  and all(x[7] == "" for x in t), t[:4])
            # 단위 표기형(배수구조물도 견본): 같은 직경 둘째 줄부터 ", 소계 할증 칸 '0.136(3%)', 총계에 총길이
            form2 = "단위 표기형(기호·직경·길이(M)·개수·총길이(M)·단위무게(KG/M)·총무게(TON)·할증(%,TON), 같은 직경 \")"
            r = await run("RET", handles=hs, insert_point=[400, 300], settings={"양식": form2, "강도별": False,
                                                                                "정렬": "상세 순서(머리 글자 처음 나온 순)"})
            t = r["tables"][0]["rows"]
            check("RET 단위 표기형: W1 H22 / W2 \" / 소계 3.040·0.132·0.136(3%) / 총계 총길이",
                  t[0][:2] == ["W1", "H22"] and t[1][:2] == ["W2", '"'] and t[3] == ["소   계", "", "", "", "43.492", "3.040", "0.132",
                                                                                     "0.136(3%)"]
                  and t[-1][0] == "총   계" and t[-1][4] != "", (t[:4], t[-1]))
            print("시험 도면은 저장하지 않았습니다.")


asyncio.run(main())
print("FAIL:", FAIL)
