# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""백그라운드 작도(build_drawing_background) 시험. 화면 없는 AutoCAD(accoreconsole)만 있으면 된다 —
켜져 있는 AutoCAD 화면은 쓰지 않는다. 결과 파일은 임시 폴더에 만들고 끝에 지운다.

실행: <python> -X utf8 tests\\test_background.py   끝에 "FAIL: []"이면 통과.
"""
import os
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import background as B  # noqa: E402

FAIL = []


def check(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name, "" if cond else info)
    if not cond:
        FAIL.append(name)


def raises(fn, kind):
    try:
        fn()
    except kind as e:
        return str(e)
    except Exception as e:  # noqa: BLE001
        return "다른 오류 %s: %s" % (type(e).__name__, e)
    return None


tmp = tempfile.mkdtemp(prefix="bc_bg_test_")
try:
    print("콘솔:", B.find_console())
    a = os.path.join(tmp, "배경_1.dwg")
    code = ('(entmake (list (cons 0 "LINE") (cons 8 "시험") (list 10 0.0 0.0 0.0) (list 11 100.0 50.0 0.0)))\n'
            '(entmake (list (cons 0 "TEXT") (cons 8 "시험") (list 10 0.0 60.0 0.0) (cons 40 10.0) (cons 1 "한글 문자")))\n'
            '; 주석 줄도 된다\n'
            '(command "_.CIRCLE" (list 50.0 25.0) 5.0)\n'
            '(write-line (strcat "토목" _d (if bc:rtos "lib" "nolib")) _fp)')
    r = B.build(code, a)
    check("새 도면 작도·저장", os.path.isfile(a) and r["entities"] == 3, r)
    check("결과 줄(한글·토목 함수 불러옴)", r["lines"] == ["토목\tlib"], r["lines"])
    check("시간", r["seconds"] < 60, r["seconds"])
    # 저장한 도면을 다시 열어 한글 문자와 (command)로 그린 원을 확인, 결과는 다른 파일로
    mtime = os.path.getmtime(a)
    b = os.path.join(tmp, "배경_2.dwg")
    r2 = B.build('(write-line (cdr (assoc 1 (entget (ssname (ssget "_X" (list (cons 0 "TEXT"))) 0)))) _fp)'
                 '(write-line (itoa (sslength (ssget "_X" (list (cons 0 "CIRCLE"))))) _fp)'
                 '(entmake (list (cons 0 "POINT") (list 10 1.0 1.0 0.0)))', b, base_drawing=a, use_skills=False)
    check("기존 도면 열어 읽기(한글·원)", r2["lines"] == ["한글 문자", "1"], r2["lines"])
    check("결과는 새 파일, 원본 그대로", r2["entities"] == 4 and os.path.getmtime(a) == mtime, (r2, mtime))
    # 이미 있는 파일은 overwrite 없이 덮어쓰지 않는다
    msg = raises(lambda: B.build("(princ)", a), FileExistsError)
    check("덮어쓰기 막음", msg is not None and "overwrite" in msg, msg)
    check("원본과 같은 이름으로 저장 막음", raises(lambda: B.build("(princ)", a, base_drawing=a, overwrite=True), ValueError) is not None)
    r3 = B.build('(entmake (list (cons 0 "POINT") (list 10 0.0 0.0 0.0)))', a, overwrite=True, use_skills=False)
    check("overwrite=true면 덮어씀", r3["entities"] == 1, r3)
    # LISP 오류는 오류로 알리고 저장하지 않는다
    c = os.path.join(tmp, "오류.dwg")
    msg = raises(lambda: B.build("(car 1)", c, use_skills=False), RuntimeError)
    check("LISP 오류 보고·미저장", msg is not None and "LISP 오류" in msg and not os.path.exists(c), msg)
    check("괄호 오류는 실행 전에 막음", raises(lambda: B.build("(princ", c), ValueError) is not None)
    check("dwg가 아니면 막음", raises(lambda: B.build("(princ)", os.path.join(tmp, "x.dxf")), ValueError) is not None)
    # MCP 서버(stdio)처럼 TEMP·TMP가 없는 환경에서도 된다(콘솔이 드라이브 맨 위에 임시 파일을 만들려다 멈추던 문제)
    saved = {k: os.environ.pop(k) for k in ("TEMP", "TMP") if k in os.environ}
    try:
        d = os.path.join(tmp, "환경.dwg")
        r4 = B.build('(entmake (list (cons 0 "POINT") (list 10 0.0 0.0 0.0)))', d, use_skills=False)
        check("TEMP 없는 환경", os.path.isfile(d) and r4["entities"] == 1, r4)
    finally:
        os.environ.update(saved)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("FAIL:", FAIL)
