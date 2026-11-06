# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""도곽 명령 시험(실제 AutoCAD 필요) — MPTE·EMTT·DTC를 새 시험 도면과 화면 없이 만든 시험 파일로 부른다.

실행: <python> -X utf8 tests\\test_titleblock_live.py [출력폴더]
끝에 "FAIL: []"이면 통과. 출력폴더(기본 %TEMP%\\bc_tb_test)에 시험 파일·캡처를 남긴다.
도곽 셋: 축척 1, 축척 2(도면명은 MTEXT), 90도 회전. 도면번호·도면명은 영역 문자, 축척은 도곽 속성.
0.6.1: EMTT 백업·무변경·저장 형식, 화면 없이 다른 파일 읽기, 동적 블록 도곽(AutoCAD 견본), 한글 글꼴 경고, bug_report 단독.
"""
import asyncio
import glob
import json
import math
import os
import subprocess
import sys

sys.dont_write_bytecode = True
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "src")]
import background  # noqa: E402
from skills.windows import mpte  # noqa: E402
# AutoCAD에 들어 있는 동적 블록 견본(모형 공간에 매개변수를 바꾼 *U 이름 블록이 있다) — 읽기만 한다
DYN = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Autodesk", "AutoCAD 2023", "Sample", "ko-KR",
                   "Dynamic Blocks", "Annotation - Metric.dwg")
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
        if title is None:  # 도면명 문자는 따로 넣는다
            continue
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
            baks = os.path.splitext(f)[0] + ".emtt-*.bak"
            for p in [f] + glob.glob(baks):
                os.remove(p) if os.path.exists(p) else None
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
            with open(f, "rb") as fh:
                first = fh.read()
            e = await run("EMTT", registration=REG, rows=rows)
            check("EMTT 파일 3곳 바꿈", e["changed"] == 3 and not e["skipped"], e)
            check("EMTT 원본 백업(이름.emtt-날짜-시각.bak)", len(glob.glob(baks)) == 1 and e["backups"] == glob.glob(baks), e)
            with open(e["backups"][0], "rb") as fh:
                check("EMTT 백업은 고치기 전 원본", fh.read() == first, "")
            r2 = await run("MPTE", registration=REG, files=[f])
            got = {row[3]: row[4:6] for row in r2["rows"][1:]}
            check("EMTT 결과 다시 읽기", got == {"C-10": ["종단면도 {갑}", "1/200"], "C-2": ["평면도(1)", "1/600"]}, r2)

            # EMTT 바뀐 값이 없으면 파일·백업을 건드리지 않는다
            m0 = os.path.getmtime(f)
            e = await run("EMTT", registration=REG, rows=r2["rows"])
            check("EMTT 바뀐 값 없음 → 파일 그대로", e["changed"] == 0 and os.path.getmtime(f) == m0
                  and len(glob.glob(baks)) == 1, e)
            # EMTT 두 번째 고치기 → 백업이 하나 더 생기고 처음 원본 백업은 그대로
            rows = [list(x) for x in r2["rows"]]
            for row in rows[1:]:
                if row[3] == "C-2":
                    row[4] = "평면도(2)"
            e = await run("EMTT", registration=REG, rows=rows)
            got = sorted(glob.glob(baks))
            with open(got[0], "rb") as fh:
                check("EMTT 두 번 → 백업 2개, 처음 원본 유지", e["changed"] == 1 and len(got) == 2 and fh.read() == first,
                      (e, got))

            # EMTT 원래 저장 형식 유지(2013 형식 도면은 2013으로)
            f13 = os.path.join(OUT, "tb_2013.dwg")
            for p in [f13] + glob.glob(os.path.splitext(f13)[0] + ".emtt-*.bak"):
                os.remove(p) if os.path.exists(p) else None
            background.build(frames_lisp([(0, 0, 1.0, 0, "C-20", "횡단면도", False, "1/100")]), f13, preview=False,
                             save_as="2013")
            r = await run("MPTE", registration=REG, files=[f13])
            rows = [list(x) for x in r["rows"]]
            rows[1][4] = "횡단면도(1)"
            e = await run("EMTT", registration=REG, rows=rows)
            with open(f13, "rb") as fh:
                check("EMTT 2013 형식 유지", e["changed"] == 1 and fh.read(6) == b"AC1027", e)

            # 0.7.0 여러 줄: MTEXT 줄바꿈, 영역 안 TEXT 2줄, 서식 있는 MTEXT, 250자 넘는 MTEXT
            fm = os.path.join(OUT, "tb_lines.dwg")
            for p in [fm] + glob.glob(os.path.splitext(fm)[0] + ".emtt-*.bak"):
                os.remove(p) if os.path.exists(p) else None
            B = chr(92)
            long1, long2 = "가" * 120 + "나" * 180, "다" * 150 + "라" * 160
            extra = ('(entmake (list (cons 0 "TEXT") (list 10 1310.0 36.0 0.0) (cons 40 3.0) (cons 1 "상단")))'
                     '(entmake (list (cons 0 "TEXT") (list 10 4310.0 36.0 0.0) (cons 40 3.0) (cons 1 "윗줄")))'
                     '(entmake (list (cons 0 "MTEXT") (cons 100 "AcDbEntity") (cons 100 "AcDbMText")'
                     ' (list 10 3305.0 33.0 0.0) (cons 40 0.1) (cons 71 1) (cons 3 "%s") (cons 1 "%s")))'
                     % (long1[:200], long1[200:]))
            background.build(frames_lisp([
                (0, 0, 1.0, 0, "D-1", "첫줄" + B + B + "P둘째줄", True, "1/1"),
                (1000, 0, 1.0, 0, "D-2", "하단", False, "1/1"),
                (2000, 0, 1.0, 0, "D-3", "{" + B + B + "C1;빨강}제목", True, "1/1"),
                (3000, 0, 1.0, 0, "D-4", None, False, "1/1"),
                (4000, 0, 1.0, 0, "D-5", "아랫줄", False, "1/1"),
                (5000, 0, 1.0, 0, "D-6", "윗" + B + "n아래", True, "1/1")]) + extra, fm, preview=False)  # 실제 줄바꿈 글자
            r = await run("MPTE", registration=REG, files=[fm])
            got = {row[3]: row[4] for row in r["rows"][1:]}
            check("MPTE 여러 줄 읽기(MTEXT 줄바꿈·실제 줄바꿈 글자·TEXT 2줄·서식·250자 넘는 MTEXT)",
                  got == {"D-1": "첫줄\n둘째줄", "D-2": "상단\n하단", "D-3": "빨강제목", "D-4": long1, "D-5": "윗줄\n아랫줄",
                          "D-6": "윗\n아래"},
                  got)
            rows = [list(x) for x in r["rows"]]
            new = {"D-1": "첫줄\n셋째줄", "D-2": "상단2\n하단", "D-3": "바꿈", "D-4": long2, "D-5": "한 줄로",
                   "D-6": "윗\n아래"}
            for row in rows[1:]:
                row[4] = new[row[3]]
            e = await run("EMTT", registration=REG, rows=rows)
            why = {s[2] + ":" + s[3][:8] for s in e["skipped"]}
            check("EMTT 여러 줄 고치기 3곳, 서식 MTEXT·줄 수 다른 칸은 건너뜀",
                  e["changed"] == 3 and len(e["skipped"]) == 2 and any("서식" in s[3] for s in e["skipped"])
                  and any("줄 수" in s[3] for s in e["skipped"]), (e, why))
            r = await run("MPTE", registration=REG, files=[fm])
            got = {row[3]: row[4] for row in r["rows"][1:]}
            check("EMTT 여러 줄 결과 다시 읽기",
                  got == {"D-1": "첫줄\n셋째줄", "D-2": "상단2\n하단", "D-3": "빨강제목", "D-4": long2, "D-5": "윗줄\n아랫줄",
                          "D-6": "윗\n아래"},
                  got)

            # 다른 파일만 다루면 AutoCAD 화면 없이도 돈다(지금 도면을 못 얻는 상황을 흉내)
            class NoAcad:
                @property
                def doc(self):
                    raise RuntimeError("실행 중인 AutoCAD를 찾지 못했습니다(시험)")

            from skills.mcp_tools import merged_cfg
            r = mpte.run_mcp(NoAcad(), "MPTE", {"registration": REG, "files": [f13]}, 60, merged_cfg)
            check("MPTE 화면 없이(다른 파일만)", r["frames"] == 1 and r["rows"][1][3:5] == ["C-20", "횡단면도(1)"], r)
            try:
                mpte.run_mcp(NoAcad(), "MPTE", {"registration": REG}, 60, merged_cfg)
                check("MPTE 지금 도면은 화면 필요", False, "오류가 나야 함")
            except RuntimeError:
                check("MPTE 지금 도면은 화면 필요", True)

            # 동적 블록(이름 *U…) 도곽을 화면 없는 AutoCAD로 읽기
            dreg = {"blocks": {"도면 제목 - 미터법": {"items": [{"name": "제목", "kind": "box", "box": [0, 0, 1, 1]}]}}}
            r = await run("MPTE", registration=dreg, files=[DYN])
            check("MPTE 동적 블록 도곽(파일)", r["frames"] == 1, r)

            # 오류 보고서를 다른 도구보다 먼저 불러도 된다(새 파이썬에서 report만)
            pr = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", "import report; report.build('MPTE', '시험')"],
                                cwd=os.path.join(ROOT, "src"), capture_output=True, text=True, encoding="utf-8")
            check("bug_report 단독", pr.returncode == 0, pr.stderr[-300:])

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
            check("DTC 한글 글꼴 없는 스타일 경고", "한글 글꼴" in r.get("warning", ""), r.get("warning"))
            t = await call("create_text", text="한글 문자", x=0, y=-200, height=5)
            check("create_text 한글 글꼴 경고", "한글 글꼴" in t.get("warning", ""), t)
            t = await call("create_text", text="ABC", x=0, y=-220, height=5)
            check("create_text 영문은 경고 없음", "warning" not in t, t)
            await call("zoom_extents")
            cap = await call("capture_view", output_path=os.path.join(OUT, "titleblock.png"))
            check("캡처", cap.get("captured"), cap)
    print("FAIL:", FAIL)


asyncio.run(main())
