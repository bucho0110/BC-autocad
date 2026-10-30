# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""TTP(Z값 점·문자)·TTE(문자를 엑셀로) 시험(실제 AutoCAD 필요) — MCP stdio로 새 시험 도면에서 skill_run을 부른다.

실행: <python> -X utf8 tests\\test_ttp_tte_live.py   끝에 "FAIL: []"이면 통과.
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


MK = '(entmake (list %s)) (write-line (cdr (assoc 5 (entget (entlast)))) _fp)'


def text(s, x, y):
    return MK % '(cons 0 "TEXT") (list 10 %s %s 0.0) (cons 40 1.0) (cons 1 "%s")' % (x, y, s)


# 새로 생긴 점·문자: 종류, x, y, z, 내용
NEW = ('(setq _e (entnext _last)) (while _e (setq _ed (entget _e))'
       ' (write-line (strcat (cdr (assoc 0 _ed)) _d (bc:rtos (cadr (assoc 10 _ed)) 2 4) _d (bc:rtos (caddr (assoc 10 _ed)) 2 4)'
       ' _d (bc:rtos (cadddr (assoc 10 _ed)) 2 4) _d (if (assoc 1 _ed) (cdr (assoc 1 _ed)) "")) _fp) (setq _e (entnext _e)))')


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

            async def created(fn):
                await lisp('(setq _last (entlast))')
                res = await fn()
                return res, [ln.split("\t") for ln in await lisp(NEW)]

            await call("new_drawing")
            # ---------------------------------------------------------------- TTP
            h = await lisp(text("EL=10.125", 0, 0) + text("높이 없음", 0, 3))
            r, new = await created(lambda: run("TTP", handles=h, settings={"기능": "문자→Z점", "문자Z": True}))
            check("TTP 문자→Z점: 점 1개, 숫자 없는 문자 건너뜀", r["points"] == 1 and r["skipped"] == 1, r)
            check("TTP 문자→Z점: (0,0,10.125)", new == [["POINT", "0.0000", "0.0000", "10.1250", ""]], new)
            z = (await lisp('(write-line (bc:rtos (cadddr (assoc 10 (entget (handent "%s")))) 2 4) _fp)' % h[0]))[0]
            check("TTP 문자 자체 Z도 10.125", z == "10.1250", z)

            p = await lisp(MK % '(cons 0 "POINT") (list 10 5.0 5.0 7.5)' + MK % '(cons 0 "POINT") (list 10 6.0 6.0 0.0)')
            r, new = await created(lambda: run("TTP", handles=p, settings={"기능": "점·블록→Z문자", "소수": 2,
                                                                          "이격Y": 1.0, "문자Z": False}))
            check("TTP 점→Z문자: Z=0 제외하고 '7.50' (5,6,0)", new == [["TEXT", "5.0000", "6.0000", "0.0000", "7.50"]], new)

            ln = await lisp(MK % '(cons 0 "LINE") (list 10 0.0 20.0 1.0) (list 11 10.0 20.0 2.25)')
            r, new = await created(lambda: run("TTP", handles=ln, settings={"기능": "선 정점→Z점·문자", "이격Y": 0.0}))
            kinds = sorted((x[0], x[4]) for x in new)
            check("TTP 선 정점: 점 2·문자 2(1.00, 2.25)", r["points"] == 2 and r["texts"] == 2
                  and kinds == [("POINT", ""), ("POINT", ""), ("TEXT", "1.00"), ("TEXT", "2.25")], (r, kinds))

            near = await lisp(text("EL=3.3", 30, 30) + MK % '(cons 0 "POINT") (list 10 30.5 30.0 0.0)'
                              + MK % '(cons 0 "POINT") (list 10 40.0 40.0 0.0)')
            r = await run("TTP", handles=near, settings={"기능": "문자 주변 점·블록 Z 올리기", "반경": 1.0})
            zs = await lisp('(foreach _h (list "%s" "%s") (write-line (bc:rtos (cadddr (assoc 10 (entget (handent _h)))) 2 4) _fp))'
                            % (near[1], near[2]))
            check("TTP Z 올리기: 가까운 점만 3.3", r["raised"] == 1 and zs == ["3.3000", "0.0000"], (r, zs))

            # ---------------------------------------------------------------- TTE
            ga = await lisp(text("A2", 100, 5) + text("A1", 100, 10))
            gb = await lisp(text("B1", 110, 10) + text("B2", 110, 5)
                            + '(entmake (list (cons 0 "TEXT") (list 10 110.0 0.0 0.0) (cons 40 1.0) (cons 1 "B3")))'
                            '(write-line (cdr (assoc 5 (entget (entlast)))) _fp)')
            r = await run("TTE", groups=[ga, gb], settings={"정렬": "Y 위→아래", "방향": "아래로", "처리": "색상 변경",
                                                           "처리색": 1})
            check("TTE 묶음=열, 위→아래", r["rows"] == [["A1", "B1"], ["A2", "B2"], ["", "B3"]], r["rows"])
            col = await lisp('(write-line (itoa (cdr (assoc 62 (entget (handent "%s"))))) _fp)' % ga[0])
            check("TTE 내보낸 문자 색 1", col == ["1"], col)
            r = await run("TTE", groups=[ga, gb], settings={"정렬": "내용 내림차순", "방향": "오른쪽으로", "처리": "변경 없음"})
            check("TTE 오른쪽으로·내용 내림차순", r["rows"] == [["A2", "A1"], ["B3", "B2", "B1"]], r["rows"])
            await call("run_lisp", code='(entmake (list (cons 0 "DIMENSION") (cons 100 "AcDbEntity") (cons 100 "AcDbDimension")'
                                        ' (list 10 12.5 -5.0 0.0) (list 11 6.25 -5.0 0.0) (cons 70 33) (cons 1 "")'
                                        ' (cons 100 "AcDbAlignedDimension") (list 13 0.0 -10.0 0.0) (list 14 12.5 -10.0 0.0)))')
            dim = (await lisp('(write-line (cdr (assoc 5 (entget (entlast)))) _fp)'))
            r = await run("TTE", handles=dim, settings={"처리": "변경 없음"})
            check("TTE 치수 값 12.5", len(r["rows"]) == 1 and float(r["rows"][0][0]) == 12.5, r["rows"])

            # ---------------------------------------------------------------- CALC
            r = await run("CALC", expression="폭 5.0 × 2 + sqrt(9)")
            check("CALC 식 직접: 13", r["result"] == 13.0, r)
            nums = await lisp(text("L=12.5", 200, 0) + text("7.5m", 200, 5) + text("메모", 200, 10))
            r = await run("CALC", handles=nums, settings={"대상": "문자", "방식": "평균", "소수": 2, "식소수": 2})
            check("CALC 문자 평균 (12.5+7.5)/2 = 10", r["result"] == 10.0 and r["expression"] == "(12.50 + 7.50) / 2", r)
            lines = await lisp(MK % '(cons 0 "LINE") (list 10 300.0 0.0 0.0) (list 11 303.0 4.0 0.0)'
                               + MK % '(cons 0 "CIRCLE") (list 10 320.0 0.0 0.0) (cons 40 1.0)')
            r = await run("CALC", handles=lines, settings={"대상": "객체 길이", "방식": "+", "소수": 4, "식소수": 4})
            check("CALC 길이 5 + 2π", abs(r["result"] - (5 + 2 * 3.14159265)) < 1e-3, r)
            r = await run("CALC", handles=lines[:1], settings={"대상": "객체 길이", "방식": "+", "축척": 1.0, "소수": 4})
            check("CALC mm 도면 축척 1 → 0.005", r["result"] == 0.005, r)
            r = await run("CALC", points=[[0, 0], [3, 4], [3, 10]], settings={"대상": "수평 거리", "방식": "+", "축척": 1000.0})
            check("CALC 수평 거리 3 + 0", r["result"] == 3.0, r)
            r = await run("CALC", points=[[0, 0], [3, 4], [3, 10]], settings={"대상": "거리", "방식": "×"})
            check("CALC 거리 5 × 6 = 30", r["result"] == 30.0, r)
            sq = await lisp(MK % '(cons 0 "LWPOLYLINE") (cons 100 "AcDbEntity") (cons 100 "AcDbPolyline") (cons 90 4) (cons 70 1)'
                            ' (list 10 400.0 0.0) (list 10 410.0 0.0) (list 10 410.0 20.0) (list 10 400.0 20.0)')
            r = await run("CALC", handles=sq, settings={"대상": "면적(객체)", "방식": "+", "소수": 1}, write_point=[400, -5],
                          replace_handle=nums[2])
            new = await lisp('(write-line (cdr (assoc 1 (entget (entlast)))) _fp)'
                             '(write-line (cdr (assoc 1 (entget (handent "%s")))) _fp)' % nums[2])
            check("CALC 면적 200, 문자 쓰기·고치기", r["result"] == 200.0 and r["replaced"] and new == ["200.0", "200.0"], (r, new))

            # ---------------------------------------------------------------- ART·CTS·INN
            def t2(s, x, y):
                return MK % '(cons 0 "TEXT") (list 10 %s %s 0.0) (cons 40 2.0) (cons 1 "%s")' % (x, y, s)

            BOX = ('(foreach _h (list %s) (setq _b (bc:cr-box (handent _h)))'
                   ' (write-line (strcat (bc:rtos (caar _b) 2 4) _d (bc:rtos (cadar _b) 2 4) _d (bc:rtos (caadr _b) 2 4) _d'
                   ' (bc:rtos (cadadr _b) 2 4)) _fp))')
            IP = ('(foreach _h (list %s) (setq _e (entget (handent _h))) (write-line (strcat (bc:rtos (cadr (assoc 10 _e)) 2 4) _d'
                  ' (bc:rtos (caddr (assoc 10 _e)) 2 4) _d (bc:rtos (cadr (assoc 11 _e)) 2 4) _d (bc:rtos (caddr (assoc 11 _e)) 2 4)'
                  ' _d (itoa (cdr (assoc 72 _e))) (itoa (cdr (assoc 73 _e)))) _fp))')
            ht = await lisp(t2("ABgy", 500, 100) + t2("CD", 510, 95) + t2("EFGH", 505, 89))
            hl = " ".join('"%s"' % h for h in ht)
            before = await lisp(BOX % hl)
            await run("ART", handles=ht, settings={"방식": "간격 조정", "정렬점": "중간 중심", "간격함께": False,
                                                   "간격방식": "수평 맨 앞·뒤 등간격"})
            mid = await lisp(BOX % hl)
            # 수평 등간격: 처음·끝 문자는 그대로, 가운데 문자만 옮겨지고 모든 문자의 보이는 크기·높이 자리는 그대로
            check("ART 정렬점만 바꾸면 보이는 자리 그대로(맨 앞·뒤)", mid[0] == before[0] and mid[1] == before[1], (before, mid))
            r = await run("ART", handles=ht, point=[600, 200], settings={"방식": "수직 정렬", "정렬점": "왼쪽", "이격": 1.0})
            ip = [x.split("\t") for x in await lisp(IP % hl)]
            check("ART 수직 정렬(왼쪽, 이격 1): 삽입점 X 601, Y 그대로", r["results"] == ["3"]
                  and [p[0] for p in ip] == ["601.0000"] * 3 and [p[4] for p in ip] == ["00"] * 3, ip)
            r = await run("ART", handles=ht, point=[600, 200], settings={"방식": "수평 정렬", "정렬점": "중간 중심",
                                                                          "간격함께": True, "간격방식": "수평 줄 간격", "간격": 10.0})
            ip = [x.split("\t") for x in await lisp(IP % hl)]
            check("ART 수평 정렬(중간 중심 Y 200) + 수평 줄 간격 10", [p[3] for p in ip] == ["200.0000"] * 3
                  and sorted(float(p[2]) for p in ip)[1] - sorted(float(p[2]) for p in ip)[0] == 10.0
                  and [p[4] for p in ip] == ["12"] * 3, ip)
            r = await run("ART", handles=ht, settings={"방식": "간격 조정", "정렬점": "왼쪽", "간격방식": "수직 줄 간격", "간격": 5.0})
            ys = sorted((float(x.split("\t")[1]) for x in await lisp(IP % hl)), reverse=True)
            check("ART 수직 줄 간격 5", ys[0] - ys[1] == 5.0 and ys[1] - ys[2] == 5.0, ys)

            sh = await lisp(t2("그림자", 700, 100))
            r = await run("CTS", handles=sh, settings={"방식": "문자 복사", "X": 0.1, "Y": -0.1, "그림자색": 8})
            c = (await lisp('(setq _e (entget (entlast))) (write-line (strcat (bc:rtos (cadr (assoc 10 _e)) 2 4) _d'
                            ' (bc:rtos (caddr (assoc 10 _e)) 2 4) _d (itoa (cdr (assoc 62 _e))) _d (cdr (assoc 1 _e))) _fp)'))[0]
            check("CTS 복사: 높이 2 × 0.1 비킴, 색 8", r["made"] == 1 and c == "700.2000\t99.8000\t8\t그림자", c)
            # 외곽선: 트루타입(맑은 고딕) 스타일 문자는 윤곽 폴리선, SHX(Standard) 문자는 건너뜀
            await lisp('(vla-SetFont (vla-Add (vla-get-TextStyles (vla-get-ActiveDocument (vlax-get-acad-object))) "시험_맑은고딕")'
                       ' "맑은 고딕" :vlax-false :vlax-false 129 34)')
            tt = await lisp(MK % '(cons 0 "TEXT") (list 10 720.0 100.0 0.0) (cons 40 2.0) (cons 1 "횡단 A") (cons 7 "시험_맑은고딕")')
            r = await run("CTS", handles=tt + sh, settings={"방식": "문자 외곽선", "두께": 10.0, "그림자색": 8})
            box = await lisp('(setq _b (bc:cr-box (handent "%s"))) (setq _n 0 _w nil _lo nil _hi nil)'
                             ' (foreach _e (bc:ss-list (ssget "_X" (list (cons 0 "LWPOLYLINE") (cons 62 8))))'
                             '  (setq _n (1+ _n) _w (cdr (assoc 43 (entget _e))))'
                             '  (foreach _p (bc:verts _e) (setq _lo (if _lo (mapcar (quote min) _lo _p) _p) _hi (if _hi (mapcar (quote max) _hi _p) _p))))'
                             ' (write-line (strcat (itoa _n) _d (bc:rtos _w 2 3) _d (bc:rtos (- (car _lo) (caar _b)) 2 3) _d'
                             '  (bc:rtos (- (cadr _lo) (cadar _b)) 2 3) _d (bc:rtos (- (car _hi) (caadr _b)) 2 3) _d'
                             '  (bc:rtos (- (cadr _hi) (cadadr _b)) 2 3)) _fp)' % tt[0])
            b = box[0].split("\t")
            check("CTS 외곽선: 1개 만들고 SHX 1개 건너뜀", r["made"] == 1 and len(r["skipped"]) == 1, r)
            # AutoCAD 외곽 상자는 잉크가 아니라 왼쪽이 펜 원점(첫 글자 왼쪽 여백 포함)이라, 윤곽은 위·아래는 상자와 같고
            # 왼쪽은 여백만큼(0 ~ 0.3) 안쪽, 오른쪽은 상자 안(0 ~ −0.1). 화면 캡처로 글자를 정확히 감싸는 것을 확인함(2026-10-30)
            check("CTS 외곽선: 폴리선 여럿·폭 0.2(높이 2의 10%)·글자 윤곽 자리", int(b[0]) >= 6 and b[1] == "0.200"
                  and 0 <= float(b[2]) <= 0.3 and abs(float(b[3])) <= 0.01 and -0.1 <= float(b[4]) <= 0
                  and abs(float(b[5])) <= 0.01, b)

            src = await lisp(t2("횡단면도 (1/6)", 800, 100) + t2("x", 800, 90) + t2("y", 800, 85))
            r = await run("INN", handles=src[1:], settings={"내용": "횡단면도 (?/6)", "시작값": "2", "증분": "1"})
            got = await lisp('(foreach _h (list "%s" "%s") (write-line (cdr (assoc 1 (entget (handent _h)))) _fp))' % (src[1], src[2]))
            check("INN 기존 문자 고치기 (2/6)·(3/6)", got == ["횡단면도 (2/6)", "횡단면도 (3/6)"], got)
            r = await run("INN", source_handle=src[0], base_point=[800, 100], points=[[800, 70], [800, 60]],
                          settings={"내용": "A-?", "시작값": "9", "자리수": 3})
            got = await lisp('(foreach _e (list (entnext (handent "%s")) (entlast))'
                             ' (write-line (strcat (cdr (assoc 1 (entget _e))) _d (bc:rtos (caddr (assoc 10 (entget _e))) 2 1)) _fp))'
                             % src[2])
            check("INN 복사: A-009(70)·A-010(60)", r["values"] == ["A-009", "A-010"] and sorted(got) == ["A-009\t70.0", "A-010\t60.0"], (r, got))
            print("시험 도면은 저장하지 않았습니다.")


asyncio.run(main())
print("FAIL:", FAIL)
