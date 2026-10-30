# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""결함 고침 시험(실제 AutoCAD 필요) — 새 도면에서 MCP 도구로.

실행: <python> -X utf8 tests\test_fixes_live.py   끝에 "FAIL: []"이면 통과.
"""
import asyncio
import json
import math
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
    params = StdioServerParameters(command=sys.executable, args=["-X", "utf8", "-B", os.path.join(ROOT, "src", "server.py")])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            async def raw(_tool, **kw):
                res = await s.call_tool(_tool, kw)
                return res.isError, (res.content[0].text if res.content else "")

            async def call(_tool, **kw):
                err, txt = await raw(_tool, **kw)
                if err:
                    raise RuntimeError("%s: %s" % (_tool, txt))
                return json.loads(txt)

            print("시험 도면:", await call("new_drawing"))
            # run_lisp 끝 줄 주석·CR 줄바꿈 주석
            out = await call("run_lisp", code='(write-line "ok" _fp) ; 끝 주석')
            check("run_lisp 끝 줄 주석", out["lines"] == ["ok"], out)
            out = await call("run_lisp", code='; 주석\r(write-line "ok2" _fp)')
            check("run_lisp CR 줄바꿈 주석", out["lines"] == ["ok2"], out)
            err, txt = await raw("run_lisp", code='(write-line "x" _fp) ;| 안 닫힘')
            check("닫히지 않은 블록 주석은 보내기 전에 막음", err and "블록 주석" in txt, txt)
            err, txt = await raw("run_lisp", code='(apply (quote load) (list "a.lsp"))')
            check("(quote load) 막음", err and "load" in txt, txt)
            # 빈 핸들 목록
            for tool in ("delete_entities", "move_entities", "copy_entities"):
                err, txt = await raw(tool, handles="[]")
                check("%s 빈 목록은 0건" % tool, not err and '":0' in txt.replace(" ", ""), txt)
            # 비도형 핸들(블록 표 등)이 섞여도 나머지는 돌려준다
            ln = await call("create_line", start_x=0, start_y=0, end_x=10, end_y=0)
            r = await call("entget_by_handles", handles=json.dumps(["1", ln["handle"]]))
            check("비도형 핸들 건너뜀", r["returned"] == 1 and r["entities"][0]["handle"] == ln["handle"], r)
            # find_text 특수 문자는 글자 그대로
            await call("create_text", text="D16@200", x=0, y=10, height=1)
            await call("create_text", text="1,234", x=0, y=20, height=1)
            await call("create_text", text="1", x=0, y=30, height=1)
            r = await call("find_text", keyword="D16@200")
            check("find_text D16@200", r["found"] == 1, r)
            r = await call("find_text", keyword="1,234")
            check("find_text 1,234 (쉼표는 OR가 아님)", r["found"] == 1, r)
            # area 글자 "0,0,0,0"은 원점 한 점 영역(전체가 아님)
            await call("create_circle", center_x=500, center_y=500, radius=1)
            r = await call("ssget_query", area="0,0,0,0", fields="handles")
            check("ssget_query area 0,0,0,0은 원점만", r["count"] == 1, r)
            # 배치 탭이 켜져 있어도 선 일괄 작도는 기준 개체(모형 공간) 옆에
            await call("run_lisp", code='(setvar "TILEMODE" 0) (write-line "" _fp)')
            r = await call("draw_lines_atomic", base_handle=ln["handle"], segments=[[0, -5, 10, -5]])
            out = await call("run_lisp", code='(setq _e (entget (handent "%s"))) (write-line (itoa (if (assoc 67 _e) (cdr (assoc 67 _e)) 0)) _fp) (setvar "TILEMODE" 1)' % r["handles"][0])
            check("배치 탭에서도 모형 공간에 작도", out["lines"] == ["0"], out)
            # DIBC: 대상 선이 그 측점 옆에 없으면 멀리서 만나도 비운다(ㄱ자 선형, 대상 선은 둘째 다리 옆 y=900)
            await call("skill_run", command="CST", args=json.dumps({"stations": ["0+000", "0+001"]}))  # 라이브러리 올리기
            out = await call("run_lisp", code=(
                '(setq _a (bc:pline (list (list 0 0) (list 1000 0) (list 1000 1000)) nil "AL"))'
                '(setq _b (bc:pline (list (list 100 900) (list 1500 900)) nil "OT"))'
                '(setq _c (bc:pline (list (list 0 30) (list 900 30)) nil "OT"))'
                '(write-line (strcat (cdr (assoc 5 (entget _a))) "," (cdr (assoc 5 (entget _b))) "," (cdr (assoc 5 (entget _c)))) _fp)'))
            ha, hb, hc = out["lines"][0].split(",")
            ha_dibc, hb_dibc = ha, hc
            r = await call("skill_run", command="DIBC", args=json.dumps({"handle": ha, "others": [hb, hc], "settings": {"간격": 200.0}}))
            row = [x for x in r["table"] if x[0].endswith("+200")][0]
            check("DIBC 옆에 없는 선은 비움·합계도 비움", row[2] == "" and row[3] == "30.000" and row[4] == "", row)


            # DCP: 한쪽이 짧으면 마주 보는 구간만(0~400, y=50) — 예전에는 짧은 선 끝을 돌아 휘다가 (1400,50)으로 튀었다
            out = await call("run_lisp", code=(
                '(setq _a (bc:pline (list (list 0 0) (list 400 0)) nil "DA"))'
                '(setq _b (bc:pline (list (list 0 100) (list 2400 100)) nil "DB"))'
                '(write-line (strcat (cdr (assoc 5 (entget _a))) "," (cdr (assoc 5 (entget _b)))) _fp)'))
            ha, hb = out["lines"][0].split(",")
            await call("skill_run", command="DCP", args=json.dumps({"handles": [ha, hb], "settings": {"레이어": "DC"}}))
            out = await call("run_lisp", code=(
                '(setq _v (bc:verts (ssname (ssget "_X" (list (cons 8 "DC"))) 0)))'
                '(foreach _p _v (write-line (strcat (rtos (car _p) 2 6) "," (rtos (cadr _p) 2 6)) _fp))'))
            pts = [tuple(map(float, x.split(","))) for x in out["lines"]]
            check("DCP 한쪽 짧으면 마주 보는 구간만", len(pts) >= 2 and all(abs(y - 50) < 1e-6 for _x, y in pts)
                  and abs(min(x for x, _y in pts)) < 1e-6 and abs(max(x for x, _y in pts) - 400) < 1e-6, pts)
            # DCP 끝연장: 같은 두 선에서 긴 선 끝(2400)까지 y=50으로 늘인다
            await call("skill_run", command="DCP", args=json.dumps({"handles": [ha, hb], "settings": {"레이어": "DCX", "끝연장": True}}))
            out = await call("run_lisp", code=(
                '(setq _v (bc:verts (ssname (ssget "_X" (list (cons 8 "DCX"))) 0)))'
                '(foreach _p _v (write-line (strcat (rtos (car _p) 2 6) "," (rtos (cadr _p) 2 6)) _fp))'))
            pts = [tuple(map(float, x.split(","))) for x in out["lines"]]
            check("DCP 끝연장은 긴 선 끝까지", len(pts) >= 2 and all(abs(y - 50) < 1e-6 for _x, y in pts)
                  and abs(min(x for x, _y in pts)) < 1e-6 and abs(max(x for x, _y in pts) - 2400) < 1e-6, pts)
            # DCP: U자 만곡(바깥 제방이 목 너머로 더 이어짐)과 나팔형 합류부 — 길이 비율로 짝지으면 못 그리거나 꼬였다
            async def dcp_case(pa, pb, lay):
                out = await call("run_lisp", code=(
                    '(setq _a (bc:pline (list %s) nil "%sA") _b (bc:pline (list %s) nil "%sB"))'
                    % (" ".join("(list %s %s)" % p for p in pa), lay, " ".join("(list %s %s)" % p for p in pb), lay) +
                    '(write-line (strcat (cdr (assoc 5 (entget _a))) "," (cdr (assoc 5 (entget _b)))) _fp)'))
                h1, h2 = out["lines"][0].split(",")
                await call("skill_run", command="DCP", args=json.dumps({"handles": [h1, h2], "settings": {"레이어": lay}}))
                out = await call("run_lisp", code=(
                    '(setq _ss (ssget "_X" (list (cons 8 "%s"))))' % lay +
                    '(if _ss (progn (setq _n (vlax-ename->vla-object (ssname _ss 0)) _A (vlax-ename->vla-object (handent "%s"))'
                    ' _B (vlax-ename->vla-object (handent "%s")) _L (vlax-curve-getDistAtParam _n (vlax-curve-getEndParam _n)) _i 0 _mx 0.0)' % (h1, h2) +
                    ' (while (<= _i 400) (setq _p (vlax-curve-getPointAtDist _n (* _L (/ _i 400.0))) _mx (max _mx (abs (bc:eq-gap _A _B _p))) _i (1+ _i)))'
                    ' (write-line (strcat (rtos _L 2 3) "," (rtos _mx 2 6)) _fp)) (write-line "없음" _fp))'))
                return out["lines"][0]
            r = await dcp_case([(0, 0), (300, 0), (300, 200), (0, 200)], [(0, -80), (380, -80), (380, 280), (-60, 280), (-60, 60)], "UB")
            ok = r != "없음" and float(r.split(",")[0]) > 600 and float(r.split(",")[1]) < 0.002
            check("DCP U자 만곡에서도 그림(길이>600, 거리차<2mm)", ok, r)
            r = await dcp_case([(0, 0), (1000, 0)], [(150, 250), (0, 100), (1000, 100)], "FL")
            ok = r != "없음" and float(r.split(",")[1]) < 0.002
            check("DCP 나팔형 합류부(거리차<2mm)", ok, r)

            # skill_list: 전체는 가볍게, command를 주면 settings까지
            allc = await call("skill_list")
            one = await call("skill_list", command="DSTA")
            check("skill_list 전체 91개(설정 빼고)·한 명령은 설정 포함", len(allc) == 91 and "settings" not in allc[0]
                  and any(x["key"] == "간격" for x in one["settings"]), (len(allc), list(one)))
            # DCP 결과가 nil이면 이유를 담은 오류(닫힌 선)
            out = await call("run_lisp", code=(
                '(setq _a (bc:pline (list (list 0 0) (list 10 0) (list 10 10)) T "NC") _b (bc:pline (list (list 0 20) (list 10 20)) nil "NC"))'
                '(write-line (strcat (cdr (assoc 5 (entget _a))) "," (cdr (assoc 5 (entget _b)))) _fp)'))
            h1, h2 = out["lines"][0].split(",")
            err, txt = await raw("skill_run", command="DCP", args=json.dumps({"handles": [h1, h2]}))
            check("DCP 실패는 이유를 담은 오류", err and "닫힌 선" in txt, txt)
            out = await call("run_lisp", code=(
                '(setq _a (bc:pline (list (list 0 0) (list 100 100)) nil "NX") _b (bc:pline (list (list 0 100) (list 100 0)) nil "NX"))'
                '(write-line (strcat (cdr (assoc 5 (entget _a))) "," (cdr (assoc 5 (entget _b)))) _fp)'))
            h1, h2 = out["lines"][0].split(",")
            err, txt = await raw("skill_run", command="DCP", args=json.dumps({"handles": [h1, h2]}))
            check("DCP 교차하는 두 선은 거절", err and "만나거나" in txt, txt)

            # CSS의 ground_handle에 문자를 넘기면 허공에 그리기 전에 거절
            tx = await call("create_text", text="지반 아님", x=0, y=-50, height=1)
            err, txt = await raw("skill_run", command="CSS", args=json.dumps({"ground_handle": tx["handle"], "point": [0, 10], "side": "R"}))
            check("CSS ground_handle 종류 검사", err and "ground_handle" in txt, txt)

            # DCP: 고도가 다른 두 선도 평면 거리로(a 고도 50)
            out = await call("run_lisp", code=(
                '(setq _a (bc:pline (list (list 0 0) (list 50 20) (list 100 0)) nil "EA"))'
                '(entmod (subst (cons 38 50.0) (assoc 38 (entget _a)) (entget _a)))'
                '(setq _b (bc:pline (list (list 0 40) (list 100 40)) nil "EB"))'
                '(write-line (strcat (cdr (assoc 5 (entget _a))) "," (cdr (assoc 5 (entget _b)))) _fp)'))
            ha, hb = out["lines"][0].split(",")
            await call("skill_run", command="DCP", args=json.dumps({"handles": [ha, hb], "settings": {"레이어": "EC"}}))
            out = await call("run_lisp", code=(
                '(setq _n (vlax-ename->vla-object (ssname (ssget "_X" (list (cons 8 "EC"))) 0))'
                ' _A (vlax-ename->vla-object (handent "%s")) _B (vlax-ename->vla-object (handent "%s"))'
                ' _L (vlax-curve-getDistAtParam _n (vlax-curve-getEndParam _n)) _i 0 _mx 0.0)'
                '(while (<= _i 200) (setq _p (vlax-curve-getPointAtDist _n (* _L (/ _i 200.0))) _mx (max _mx (abs (bc:eq-gap _A _B _p))) _i (1+ _i)))'
                '(write-line (rtos _mx 2 6) _fp)' % (ha, hb)))
            check("DCP 고도 다른 두 선 평면 거리차 < 2mm", float(out["lines"][0]) < 0.002, out)

            # 현재 레이어가 잠겨 있어도 DIBC 임시 선이 남지 않는다
            n0 = (await call("count_entities"))["total"]
            await call("run_lisp", code='(bc:ensure-layer "LK" 7) (setvar "CLAYER" "LK") (command "_.-LAYER" "_LO" "LK" "") (write-line "" _fp)')
            r = await call("skill_run", command="DIBC", args=json.dumps({"handle": ha_dibc, "others": [hb_dibc], "settings": {"간격": 500.0}}))
            n1 = (await call("count_entities"))["total"]
            await call("run_lisp", code='(command "_.-LAYER" "_U" "LK" "") (setvar "CLAYER" "0") (write-line "" _fp)')
            check("현재 레이어 잠김에도 DIBC 임시 선 안 남음", n1 == n0 and len(r["table"]) > 1, (n0, n1))
            # 폴리선 대상이면 임시 개체를 아예 만들지 않는다(핸들 번호가 그대로)
            probe = '(setq _e (entmakex (list (cons 0 "POINT") (list 10 0.0 0.0 0.0)))) (write-line (cdr (assoc 5 (entget _e))) _fp) (entdel _e)'
            h0 = (await call("run_lisp", code=probe))["lines"][0]
            await call("skill_run", command="DIBC", args=json.dumps({"handle": ha_dibc, "others": [hb_dibc], "settings": {"간격": 100.0}}))
            h1 = (await call("run_lisp", code=probe))["lines"][0]
            # 새 개체 핸들은 하나씩 늘어난다 — 사이에 임시 개체를 만들었다면 그만큼 더 건너뛴다
            check("DIBC가 도면에 아무것도 만들지 않음(핸들 +1)", int(h1, 16) == int(h0, 16) + 1, (h0, h1))
            # 사선은 중심바로 잡지 않는다
            out = await call("run_lisp", code=(
                '(setq _s (bc:pline (list (list 0 0) (list 5 2.4)) nil "CB") _v (bc:pline (list (list 9 0) (list 9 2.4)) nil "CB"))'
                '(write-line (vl-prin1-to-string (list (bc:vbar _s) (if (bc:vbar _v) T nil))) _fp)'))
            check("bc:vbar 사선 거름·세로선 통과", out["lines"] == ["(nil T)"], out)
            # 긴 MTEXT(앞부분이 3번 그룹)도 NUST가 통째로 바꾼다
            long_tail = "가" * 300
            out = await call("run_lisp", code=(
                '(entmake (list (cons 0 "MTEXT") (cons 100 "AcDbEntity") (cons 100 "AcDbMText") (list 10 0.0 50.0 0.0) (cons 40 1.0)'
                ' (cons 3 "%s") (cons 1 "No.12+5")))' % long_tail[:250] +
                '(write-line (cdr (assoc 5 (entget (entlast)))) _fp)'))
            hm = out["lines"][0]
            await call("skill_run", command="NUST", args=json.dumps({"handles": [hm], "settings": {"변환": "측점→숫자", "측점구분": "Number"}}))
            out = await call("run_lisp", code='(write-line (bc:text-of (handent "%s")) _fp)' % hm)
            # 앞부분(3번 그룹)이 남으면 "가…"가 붙어 나온다
            check("NUST 긴 MTEXT 앞부분(3번 그룹)까지 바꿈", len(out["lines"]) == 1 and "가" not in out["lines"][0], out)

            # ---- 4차 검토(26번)
            async def pl(pts, elev=None):
                code = '(setq _e (bc:pline (list %s) nil "DCPT"))' % " ".join("(list %s %s)" % tuple(p) for p in pts)
                if elev is not None:
                    code += '(entmod (subst (cons 38 %s) (assoc 38 (entget _e)) (entget _e)))' % float(elev)
                return (await call("run_lisp", code=code + '(write-line (cdr (assoc 5 (entget _e))) _fp)'))["lines"][0]

            async def dcp(h1, h2):
                return await raw("skill_run", command="DCP", args=json.dumps({"handles": [h1, h2]}))
            # U자가 짧은 선을 감싸면 중심이 양쪽에 생김 → 거절(지그재그를 그리지 않음)
            u = await pl([(1100, 10), (990, 10), (990, -10), (1100, -10)])
            inner = await pl([(1000, 0), (1100, 0)])
            err, txt = await dcp(u, inner)
            check("DCP 감싸는 선 거절", err and "감쌈" in txt, txt)
            # 끝점 하나를 함께 쓰는 V자 두 선은 그린다(가운데 y≈0)
            v1 = await pl([(2000, 0), (2100, 10)])
            v2 = await pl([(2000, 0), (2100, -10)])
            err, txt = await dcp(v1, v2)
            ok = not err
            if ok:
                hc = json.loads(txt)["results"][0]
                g = await call("get_geometry", handles=json.dumps([hc]))
                ys = [p[1] for p in g["entities"][0]["vertices"]]
                ok = max(abs(y) for y in ys) < 1e-6 and g["entities"][0]["length"] > 90
            check("DCP 끝점만 맞닿은 V자는 그림", ok, txt)
            # 일부 겹치는 두 직선 → 거절
            o1 = await pl([(3000, 0), (3100, 0)])
            o2 = await pl([(3050, 0), (3150, 0)])
            err, txt = await dcp(o1, o2)
            check("DCP 겹치는 두 선 거절", err, txt)
            # 고도가 다른 두 선이 평면에서 X자 → 거절
            x1 = await pl([(4000, 0), (4100, 10)], 0)
            x2 = await pl([(4000, 10), (4100, 0)], 50)
            err, txt = await dcp(x1, x2)
            check("DCP 고도 달라도 평면 교차 거절", err, txt)
            # 고도가 변하는 3D 폴리선 → 거절
            p3 = (await call("run_lisp", code=(
                '(setq _ob (vla-Add3DPoly (vla-get-ModelSpace (vla-get-ActiveDocument (vlax-get-acad-object)))'
                ' (vlax-make-variant (vlax-safearray-fill (vlax-make-safearray vlax-vbDouble (cons 0 5))'
                ' (list 5000.0 0.0 0.0 5100.0 0.0 9.0)))))'
                '(write-line (vla-get-Handle _ob) _fp)')))["lines"][0]
            q3 = await pl([(5000, 20), (5100, 20)])
            err, txt = await dcp(p3, q3)
            check("DCP 3D 선 거절", err and "3D" in txt, txt)
            # FE에 호 핸들 → 종류 거절
            arc = await call("create_arc", center_x=0, center_y=-500, radius=5, start_angle=0, end_angle=90)
            err, txt = await raw("skill_run", command="FE", args=json.dumps({"base_point": [0, 0], "base_el": 10, "handle": arc["handle"]}))
            check("FE 호 핸들 거절", err and "FE의 handle" in txt, txt)
            # 견본 핸들 자리별 종류(측점 문자 자리에 선)
            ln2 = await call("create_line", start_x=0, start_y=-600, end_x=0, end_y=-590)
            err, txt = await raw("skill_run", command="DCEM", args=json.dumps(
                {"sample_handles": [ln2["handle"], ln2["handle"], ln2["handle"], ln2["handle"]], "dry_run": True}))
            check("sample_handles 자리별 종류 검사", err and "sample_handles" in txt, txt)
            # STT 측점 글자: 읽을 수 있으면 그리고, 못 읽으면 알림
            al = await pl([(0, -800), (200, -800)])
            err, txt = await raw("skill_run", command="STT", args=json.dumps({"handle": al, "stations": ["0+050", 120]}))
            check("STT 측점 글자 받음", not err and "nil" not in json.loads(txt)["results"][0], txt)
            err, txt = await raw("skill_run", command="STT", args=json.dumps({"handle": al, "stations": ["엉터리"]}))
            check("STT 못 읽는 측점 알림", err and "엉터리" in txt, txt)
            # DIBC 꺾임점(10도) 측점에서도 안쪽·바깥쪽 50 떨어진 선 거리를 낸다(예전: 안쪽이 빈칸)
            out = await call("run_lisp", code=(
                '(setq _a (bc:pline (list (list 0 -3000) (list 1000 -3000) (list 1984.8078 -2826.3518)) nil "AL"))'
                '(setq _ob (vlax-ename->vla-object _a))'
                '(setq _b (vlax-invoke _ob (quote Offset) 50.0) _c (vlax-invoke _ob (quote Offset) -50.0))'
                '(write-line (strcat (cdr (assoc 5 (entget _a))) "," (vla-get-Handle (car _b)) "," (vla-get-Handle (car _c))) _fp)'))
            ha, hb, hc = out["lines"][0].split(",")
            r = await call("skill_run", command="DIBC", args=json.dumps({"handle": ha, "others": [hb, hc], "settings": {"간격": 1000.0}}))
            row = [x for x in r["table"] if x[0].endswith("1+000")]
            # 바깥쪽 오프셋은 모서리가 뾰족하게 연장돼 꺾임점 수직선에서 50/cos10° = 50.771
            vals = sorted(abs(float(v)) for v in row[0][2:4]) if row and "" not in row[0][2:4] else []
            check("DIBC 꺾임점 측점 양쪽 거리(빈칸 없음)", len(vals) == 2 and abs(vals[0] - 50) < 1e-3
                  and abs(vals[1] - 50 / math.cos(math.radians(10))) < 2e-3, r["table"])

            # bc:rtos 0 값: DIMZIN 앞뒤 0 지우기(12)에서도 "0.00"
            out = await call("run_lisp", code=(
                '(setq _a (getvar "DIMZIN")) (setvar "DIMZIN" 12) (write-line (bc:rtos 0.0 2 2) _fp)'
                '(write-line (bc:rtos -0.5 2 2) _fp) (setvar "DIMZIN" _a)'))
            check("bc:rtos 0·음수 DIMZIN 12", out["lines"] == ["0.00", "-0.50"], out)

            # health_check는 대화창 없으면 빠르게 정상
            r = await call("health_check")
            check("health_check 정상", r.get("responsive") is True and r.get("dialog_open") is False, r)


asyncio.run(main())
print("FAIL:", FAIL)
