# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""BC 이름(BCFE…)과 짧은 이름(FE…) 켜고 끄기 시험(실제 AutoCAD 필요). 활성 도면이 Drawing*일 때만 돈다.

기본은 BC 이름만, 짧은 이름은 설정 파일(shortnames.txt)에 적힌 명령만. 시험 동안 설정 파일을 바꾸고 끝에 되돌린다.
실행: <python> -X utf8 tests\\test_alias_live.py   끝에 "FAIL: []"이면 통과.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from skills.common.acad import Acad  # noqa: E402
from skills.common import settings as S  # noqa: E402
from skills import registry  # noqa: E402

FAIL = []


def check(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name, "" if cond else info)
    if not cond:
        FAIL.append(name)


a = Acad()
a.connect()
assert a.doc.Name.startswith("Drawing"), a.doc.Name
saved = S.load_short() if os.path.exists(S.short_path()) else None
names = list(registry.COMMANDS)
lits = " ".join('"%s"' % n for n in names)
STATE = ('(write-line (strcat (if c:FE (if (eq c:FE bc:sw-FE) "FE=짧은" "FE=남") "FE=없음") _d'
         ' (if (eq c:BCFE nil) "BCFE없음" "BCFE있음") _d (if c:XY "XY=있음" "XY=없음") _d'
         ' (if c:MPLOT "MPLOT=있음" "MPLOT=없음") _d (vl-princ-to-string bc:*short*)) _fp)')
try:
    # 1) 기본: 설정 없음 → BC 이름 40개 모두, 짧은 이름 없음
    S.save_short([])
    a.lisp('(setq bc:libver nil)', 30)
    rows = a.lisp('(foreach _n (list %s) (write-line (strcat _n _d (if (eval (read (strcat "c:BC" _n))) "1" "0")'
                  ' _d (if (eval (read (strcat "c:" _n))) "1" "0")) _fp))' % lits, 60)
    have = dict((r.split("\t")[0], r.split("\t")[1:]) for r in rows)
    check("기본: BC 이름 %d개 모두 있음" % len(names), all(have.get(n, ["0"])[0] == "1" for n in names),
          [n for n in names if have.get(n, ["0"])[0] != "1"])
    check("기본: 짧은 이름은 하나도 없음", all(have.get(n, ["", "1"])[1] == "0" for n in names),
          [n for n in names if have.get(n, ["", "1"])[1] != "0"])
    check("기본: MPLOT도 없음", a.lisp(STATE, 30) == ["FE=없음\tBCFE있음\tXY=없음\tMPLOT=없음\tnil"], a.lisp(STATE, 30))
    # 2) 설정 파일에 FE·MPL → 다시 불러오면 FE·MPLOT 켜짐, XY는 꺼짐
    S.save_short(["FE", "MPL"])
    a.lisp('(setq bc:libver nil)', 30)
    rows = a.lisp(STATE, 60)
    check("설정한 것만 켬(FE·MPL→MPLOT)", rows == ['FE=짧은\tBCFE있음\tXY=없음\tMPLOT=있음\t(FE MPL)'], rows)
    # 3) 짧은 이름 감싸개는 [BC] 표시 뒤 우리 함수를 부른다(창 명령 MPL을 가짜 함수로 바꿔 확인)
    rows = a.lisp('(setq _bcm bc:fn-MPLOT) (defun bc:fn-MPLOT () "우리 MPL") (write-line (vl-princ-to-string (c:MPLOT)) _fp)'
                  ' (setq bc:fn-MPLOT _bcm)', 30)
    check("짧은 이름 MPLOT → 우리 함수", rows == ["우리 MPL"], rows)
    # 4) BCOFF → 설정 비우고 이 도면에서 즉시 꺼짐
    rows = a.lisp('(c:BCOFF) (write-line "" _fp)', 30)
    rows = a.lisp(STATE, 30)
    check("BCOFF: 즉시 모두 꺼짐", rows == ["FE=없음\tBCFE있음\tXY=없음\tMPLOT=없음\tnil"], rows)
    check("BCOFF: 설정 파일 비움", S.load_short() == [], S.load_short())
    # 5) 먼저 있던 다른 리습 c:CST: 짧은 이름이 꺼져 있으면 그대로 두고, 켜면 우리 것, 끄면 다시 남의 것
    a.lisp('(defun c:CST () "남의 CST") (setq bc:libver nil)', 30)
    rows = a.lisp('(write-line (strcat (vl-princ-to-string (c:CST)) _d (if c:BCCST "BCCST있음" "없음")) _fp)', 60)
    check("먼저 있던 리습 CST는 그대로·우리는 BCCST", rows == ["남의 CST\tBCCST있음"], rows)
    rows = a.lisp('(foreach _p (bc:short-conflicts (list "CST" "FE")) (write-line (strcat (car _p) _d (caddr _p)) _fp))', 30)
    check("겹침 검사: CST는 다른 리습", rows == ["CST\t다른 리습"], rows)
    S.save_short(["CST"])
    rows = a.lisp('(bc:short-apply) (write-line (if (eq c:CST bc:sw-CST) "우리" "남") _fp)', 30)
    check("CST 켜면 우리 것", rows == ["우리"], rows)
    S.save_short([])
    rows = a.lisp('(bc:short-apply) (write-line (vl-princ-to-string (c:CST)) _fp)', 30)
    check("CST 끄면 남의 것이 돌아옴", rows == ["남의 CST"], rows)
    # 6) 남이 먼저 쓴 BC 이름은 건드리지 않는다
    a.lisp('(defun c:BCXY () "남의 것") (setq bc:*aliases* (vl-remove "BCXY" bc:*aliases*)) (setq bc:libver nil)', 30)
    rows = a.lisp('(write-line (vl-princ-to-string (c:BCXY)) _fp)', 60)
    check("남이 먼저 쓴 BCXY는 그대로", rows == ["남의 것"], rows)
    # 7) 단축키 파일 읽기: 다른 유틸리티식 줄(FE, *UTIL_FE)과 BOM·주석·빈 줄
    pgp = os.path.join(os.environ["TEMP"], "bc_test_acad.pgp")
    with open(pgp, "w", encoding="utf-8-sig") as f:
        f.write("; 주석, 쉼표 있음\n\nC,         *CIRCLE\n  FE, *UTIL_FE\nXY,*UTIL_XY\n")
    rows = a.lisp('(write-line (vl-princ-to-string (reverse (bc:pgp-names "%s"))) _fp)' % pgp.replace("\\", "/"), 30)
    check("단축키 파일 이름 읽기", rows == ["(C FE XY)"], rows)
    os.remove(pgp)
finally:
    if saved is None:
        if os.path.exists(S.short_path()):
            os.remove(S.short_path())
    else:
        S.save_short(saved)
    a.lisp('(setq c:CST nil c:BCXY nil bc:libver nil)', 30)
    a.lisp('(write-line "" _fp)', 60)
rows = a.lisp('(write-line (if (and (or (null c:CST) (eq c:CST bc:sw-CST)) c:BCXY c:BCCST) "복구" "남음") _fp)', 30)
check("시험 뒤 원상태", rows == ["복구"], rows)
print("FAIL:", FAIL)
