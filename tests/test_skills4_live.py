"""스킬 4단계(하천 횡단) 시험(실제 AutoCAD 필요) — 가짜 횡단면 3개를 만들고 MCP skill_run.

실행: <python> -X utf8 tests\\test_skills4_live.py [출력폴더]   끝에 "FAIL: []"이면 통과.
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
SPEC = {"ground_layer": "GR", "center_layer": "CL", "center_len": 40.0, "sta_off": [0.0, -5.0], "el_off": [3.0, 6.0],
        "tol": 4.0}


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

            print("시험 도면:", await call("new_drawing"))
            # 단면 3개: 중심선 (x,0)-(x,40) CL, 지반선 V자(중심 y=5) GR, 측점 (x,-5), 지반고 문자 (x+3,6) = EL.12.50
            code = []
            for i, x in enumerate((0, 200, 400)):
                code.append('(entmake (list (cons 0 "LINE") (cons 8 "CL") (list 10 %d.0 0.0 0.0) (list 11 %d.0 40.0 0.0)))' % (x, x))
                code.append('(bc:pline (list (list %d 30) (list %d 10) (list %d 5) (list %d 10) (list %d 30)) nil "GR")'
                            % (x - 50, x - 20, x, x + 20, x + 50))
                code.append('(bc:text (list %d.0 -5.0 0.0) "0+%03d" 1.0 "TX" "MC" 0.0)' % (x, i * 20))
                code.append('(bc:text (list %d.0 6.0 0.0) "EL.12.50" 1.0 "TX" "ML" 0.0)' % (x + 3))
            await run("CST", stations=["0+000", "0+001"])  # 라이브러리 올리기
            await call("run_lisp", code="".join(code))
            n0 = (await call("count_entities"))["total"]
            r = await run("DCEM", spec=SPEC, settings={"간격": 1.0, "하단맞춤": 1.0, "여유": 1})
            n1 = (await call("count_entities"))["total"]
            check("DCEM 단면 3개 인식", r["sections_usable"] == 3 and [x["station"] for x in r["sections"]] == ["0+000", "0+020", "0+040"], r)
            check("DCEM 폴대 개체 (선 180 + 숫자 걸러 쓰기)", n1 - n0 == 6 + 174 + 6 * 10, n1 - n0)
            rows = [["측점", "HWL", "SWL"], ["0+000", 20.0, 15.0], ["0+020", 21.0, None], ["0+040.0000", 22.0, None]]
            r = await run("HWLM", spec=SPEC, rows=rows)
            check("HWLM 3단면 표기", r["marked"] == 3 and not r["not_in_excel"], r)
            # 0+000 수면선: EL 20 → y 12.5, 지반선과 만나는 X ±23.75 → 길이 47.5
            out = await call("run_lisp", code=(
                '(setq _ss (ssget "_X" (list (cons 0 "LINE"))))'
                ' (setq _i 0 _f nil) (if _ss (while (< _i (sslength _ss)) (setq _e (entget (ssname _ss _i)))'
                ' (if (and (equal (cadr (assoc 10 _e)) -23.75 1e-6) (equal (caddr (assoc 10 _e)) 12.5 1e-6)'
                ' (equal (distance (cdr (assoc 10 _e)) (cdr (assoc 11 _e))) 47.5 1e-6)) (setq _f T)) (setq _i (1+ _i))))'
                ' (write-line (if _f "Y" "N") _fp)'))
            check("HWLM 수면선 (-23.75~23.75, y=12.5)", out["lines"] == ["Y"], out)
            rows2 = [["0+020", 21.0], ["0+999", 30.0]]
            r = await run("HWLM", spec=SPEC, rows=rows2, settings={"수면선": False})
            check("HWLM 엑셀에 없는 단면 보고", r["marked"] == 1 and set(r["not_in_excel"]) == {"0+000", "0+040"}, r)
            await call("zoom_window", x1=-60, y1=-10, x2=60, y2=45)
            cap = await call("capture_view", output_path=os.path.join(OUT, "skills4.png"))
            check("캡처", cap.get("captured"), cap)
            # DDGP: 새 도면, 단면 하나. 지반 (−150,6)(−20,10)(0,5)(20,10)(150,6), 중심 y=5 ↔ EL 12.5
            # 하상 11.5(y=4), 계획고 30.5(y=23), 하폭 15, 제방폭 4, 제외지 1:2, 제내지 1:2
            # 좌: 법선(−15,4) → (−53,23) → (−57,23) → 지반과 만남(−87.1311, 7.9344)
            await call("new_drawing")
            await run("CST", stations=["0+000", "0+001"])
            await call("run_lisp", code=(
                '(entmake (list (cons 0 "LINE") (cons 8 "CL") (list 10 0.0 0.0 0.0) (list 11 0.0 40.0 0.0)))'
                ' (bc:pline (list (list -150 6) (list -20 10) (list 0 5) (list 20 10) (list 150 6)) nil "GR")'
                ' (bc:text (list 0.0 -5.0 0.0) "0+100" 1.0 "TX" "MC" 0.0)'
                ' (bc:text (list 3.0 6.0 0.0) "EL.12.50" 1.0 "TX" "ML" 0.0)'))
            rows = [["측점", "하상고", "좌계획고", "우계획고", "좌하폭", "우하폭", "제방폭", "제내지경사", "제외지경사", "HWL"],
                    ["0+100", 11.5, 30.5, 30.5, 15, 15, 4, 2, 2, 25.0]]
            r = await run("DDGP", spec=SPEC, rows=rows, settings={"레이어": "PLAN"})
            check("DDGP 1단면", r["marked"] == 1 and not r["not_in_excel"], r)
            got = await call("get_entities", layer="PLAN", entity_type="LWPOLYLINE", limit=10)
            left = None
            for e in got.get("entities", []):
                d = await call("get_entity", handle=e["handle"])
                c = d.get("coordinates") or []
                if c and c[0][0] < 0:
                    left = c
            exp = [(-15, 4), (-53, 23), (-57, 23), (-87.1311, 7.9344)]
            check("DDGP 좌 계획선 꼭짓점", left is not None and len(left) == 4 and
                  all(abs(a[0] - b[0]) < 1e-3 and abs(a[1] - b[1]) < 1e-3 for a, b in zip(left, exp)), left)
            bed = await call("get_entities", layer="PLAN", entity_type="LINE", limit=10)
            check("DDGP 하상선 −15~15", any(abs(e.get("bbox_min", [0, 0])[0] + 15) < 1e-6 and abs(e.get("bbox_max", [0, 0])[0] - 15) < 1e-6
                                          for e in bed.get("entities", [])), bed)
            await call("zoom_window", x1=-100, y1=-10, x2=100, y2=45)
            cap = await call("capture_view", output_path=os.path.join(OUT, "skills4_ddgp.png"))
            check("DDGP 캡처", cap.get("captured"), cap)
            # CSAR: 새 도면, 단면 4개(x=0,200,400,600; 각 중심선+지반선+문자 2개 = 4개체), 도곽 블록 300×200을 (1000,0)에
            # 2×2 칸, 첫 도곽 사본 (1000,−300). 칸(0,0) 가운데 (1080,−245) → 첫 단면 중심선 아래 끝 (1080,−262.5)
            await call("new_drawing")
            await run("CST", stations=["0+000", "0+001"])
            code = ['(entmake (list (cons 0 "BLOCK") (cons 2 "FR") (cons 70 0) (list 10 0.0 0.0 0.0)))',
                    '(entmake (list (cons 0 "LWPOLYLINE") (cons 100 "AcDbEntity") (cons 8 "0") (cons 100 "AcDbPolyline") (cons 90 4) (cons 70 1)'
                    ' (list 10 0.0 0.0) (list 10 300.0 0.0) (list 10 300.0 200.0) (list 10 0.0 200.0)))',
                    '(entmake (list (cons 0 "ENDBLK")))',
                    '(entmake (list (cons 0 "INSERT") (cons 2 "FR") (list 10 1000.0 0.0 0.0)))']
            for i, x in enumerate((0, 200, 400, 600)):
                code.append('(entmake (list (cons 0 "LINE") (cons 8 "CL") (list 10 %d.0 0.0 0.0) (list 11 %d.0 40.0 0.0)))' % (x, x))
                code.append('(bc:pline (list (list %d 30) (list %d 5) (list %d 30)) nil "GR")' % (x - 50, x, x + 50))
                code.append('(bc:text (list %d.0 -5.0 0.0) "0+%03d" 1.0 "TX" "MC" 0.0)' % (x, i * 20))
                code.append('(bc:text (list %d.0 6.0 0.0) "EL.12.50" 1.0 "TX" "ML" 0.0)' % (x + 3))
            await call("run_lisp", code="".join(code))
            fr = (await call("get_entities", entity_type="INSERT", limit=5))["entities"][0]["handle"]
            n0 = (await call("count_entities"))["total"]
            pick = {"centers": [[0, 0], [200, 0], [400, 0], [600, 0]], "win": [-60, -10, 60, 45], "frame_handle": fr,
                    "frame": [1000, 0, 1000, 0, 1300, 200], "area": [10, 10, 290, 190], "extra": [], "base": [1000, -300]}
            r = await run("CSAR", pick=pick, settings={"X개수": 2, "Y개수": 2, "원래순서": "왼→오른", "칸순서": "아래→위 열 우선"})
            n1 = (await call("count_entities"))["total"]
            check("CSAR 도곽 1장·단면 4개", r["frames"] == 1 and r["sections"] == 4, r)
            check("CSAR 복사 개체 17개(도곽 1 + 단면 4×4)", n1 - n0 == 17, n1 - n0)
            out = await call("run_lisp", code=(
                '(setq _ss (ssget "_X" (list (cons 0 "LINE") (cons 8 "CL"))) _i 0 _f nil)'
                ' (while (< _i (sslength _ss)) (setq _e (entget (ssname _ss _i)))'
                ' (if (and (equal (cadr (assoc 10 _e)) 1080.0 1e-6) (equal (caddr (assoc 10 _e)) -262.5 1e-6)) (setq _f T)) (setq _i (1+ _i)))'
                ' (write-line (if _f "Y" "N") _fp)'))
            check("CSAR 첫 단면 위치 (1080,−262.5)", out["lines"] == ["Y"], out)
            await call("zoom_window", x1=990, y1=-310, x2=1310, y2=-90)
            cap = await call("capture_view", output_path=os.path.join(OUT, "skills4_csar.png"))
            check("CSAR 캡처", cap.get("captured"), cap)
            # RCSE: 같은 도면의 단면 4개(0+000~0+060) + 평면 선형 (1000,1000)→(2000,1000), EL 간격 10m
            # 0+000 단면 o=−10m: 지반 y=10 → EL 17.5, 평면 (1000, 1010)(선형 왼쪽=북쪽). CSAR 사본(같은 측점)은 한 번만
            al = (await call("create_line", start_x=1000, start_y=1000, end_x=2000, end_y=1000))["handle"]
            r = await run("RCSE", handle=al, spec=SPEC, settings={"EL간격": 10.0, "소수": 1, "레이어": "RC"})
            check("RCSE 단면 4개", r["marked"] == 4, r)
            out = await call("run_lisp", code=(
                '(setq _ss (ssget "_X" (list (cons 0 "TEXT") (cons 8 "RC"))) _i 0 _f nil _n 0)'
                ' (while (< _i (sslength _ss)) (setq _e (entget (ssname _ss _i)) _n (1+ _n))'
                ' (if (and (= (cdr (assoc 1 _e)) "17.5") (equal (cadr (assoc 11 _e)) 1000.0 1e-6) (equal (caddr (assoc 11 _e)) 1010.0 1e-6)) (setq _f T))'
                ' (setq _i (1+ _i))) (write-line (strcat (if _f "Y" "N") (itoa _n)) _fp)'))
            check("RCSE 0+000 o=−10 → (1000,1010) 17.5, 문자 48개(EL 44 + 측점 4)", out["lines"] == ["Y48"], out)
            # DRRE: 직선 100 → 90° 왼쪽 원곡선(R 100) → 직선 100 선형으로 양식, 채워서 전개도
            al = (await call("run_lisp", code=(
                '(entmake (list (cons 0 "LWPOLYLINE") (cons 100 "AcDbEntity") (cons 100 "AcDbPolyline") (cons 90 4) (cons 70 0)'
                ' (list 10 0.0 3000.0) (list 10 100.0 3000.0) (cons 42 0.41421356237) (list 10 200.0 3100.0) (list 10 200.0 3200.0)))'
                ' (write-line (cdr (assoc 5 (entget (entlast)))) _fp)')))["lines"][0]
            t = await run("DRRE", mode="template", handle=al, settings={"측점간격": 50.0})
            rows = t["rows"]
            bc = [r_ for r_ in rows[1:] if r_[1] == "BC"]
            check("DRRE 양식 BC 100·R +100", bc and abs(bc[0][0] - 100) < 1e-3 and abs(bc[0][2] - 100) < 1e-3, rows)
            filled = [rows[0]] + [r_[:3] + [2.0, 3.0, 1.0, 5.0] for r_ in rows[1:]]
            n0 = (await call("count_entities"))["total"]
            r = await run("DRRE", mode="draw", rows=filled, origin=[0, 2800], settings={"호안위치": "좌"})
            n1 = (await call("count_entities"))["total"]
            curve = [sg_ for sg_ in r["segments"] if sg_["curve"]]
            check("DRRE 곡선 구간 보정(안쪽: 머리 < 중심)", curve and all(sg_["L_top"] < sg_["L"] for sg_ in curve), r["segments"])
            check("DRRE 전개도·표 그림", n1 - n0 > 30, n1 - n0)
            await call("zoom_window", x1=-20, y1=2600, x2=400, y2=2820)
            cap = await call("capture_view", output_path=os.path.join(OUT, "skills4_drre.png"))
            check("DRRE 캡처", cap.get("captured"), cap)
    print("FAIL:", FAIL)


asyncio.run(main())
