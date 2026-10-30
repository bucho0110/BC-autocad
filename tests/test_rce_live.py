"""RCE 순번 좌표 내보내기 시험(실제 AutoCAD·엑셀 필요). 활성 도면이 Drawing*일 때만 돈다.

사람이 점을 찍는 부분(getpoint)만 정해 둔 점으로 바꾸고, 창의 실행 흐름(run)을 그대로 돌린다.
엑셀은 보이지 않는 새 엑셀을 따로 띄워 쓰고 끝나면 닫는다(켜져 있는 엑셀은 건드리지 않는다).
실행: <python> -X utf8 tests\\test_rce_live.py   끝에 "FAIL: []"이면 통과.
"""
import os
import sys

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))
import win32com.client  # noqa: E402

from skills.common import settings as S  # noqa: E402
from skills.windows import rce  # noqa: E402

FAIL = []


def check(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name, "" if cond else info)
    if not cond:
        FAIL.append(name)


PTS = [(100.0, 200.0, 0.0), (110.5, 205.25, 1.5), (-3.0, 7.125, 0.0)]
orig_lisp = rce.pick_and_mark_lisp
picks = []


def fake_lisp(label, cfg):
    """getpoint 대신 정해 둔 점(다 쓰면 nil = 엔터)"""
    s = orig_lisp(label, cfg)
    head, rest = s.split("))", 1)
    assert head.startswith("(setq _p (getpoint"), head
    p = PTS[len(picks)] if len(picks) < len(PTS) else None
    picks.append(label)
    return ("(setq _p %s)" % ("(list %r %r %r)" % p if p else "nil")) + rest


saved = S.load(rce.CMD, rce.DEFAULTS) if os.path.exists(S.path(rce.CMD)) else None
xl = win32com.client.DispatchEx("Excel.Application")
xl.Visible = False
xl.DisplayAlerts = False
wb = xl.Workbooks.Add()
ws = wb.Worksheets(1)
try:
    rce.pick_and_mark_lisp = fake_lisp
    rce.X.active_cell = lambda: (ws, 3, 2)  # B3부터
    w = rce.Window()
    errors = []
    w.error = errors.append
    w.acad.activate = lambda: None
    d = w.acad.doc
    assert d.Name.startswith("Drawing"), d.Name
    n0 = d.ModelSpace.Count
    cfg = dict(rce.DEFAULTS, **{"좌표": "수학", "소수": 2, "Z표기": True, "Z소수": 1, "순번시작": 5, "증분": 5,
                                 "자리": 2, "머리말": "P-", "원": True, "점표기": True, "Y이격": 4.0, "전체축척": 2.0})
    for k, (var, _t, _d) in w.form.vars.items():
        var.set(cfg[k])
    w.run()
    check("오류 없음", errors == [], errors)
    check("점 3개 + 엔터로 끝", picks == ["P-05", "P-10", "P-15", "P-20"], picks)
    # 값(Value): 엑셀은 숫자로 담는다. 7.125는 사사오입으로 7.13
    got = [[ws.Cells(3 + r, 2 + c).Value for c in range(4)] for r in range(4)]
    check("엑셀 B3부터 [순번, X, Y, Z] 값", got == [["P-05", 100.0, 200.0, 0.0], ["P-10", 110.5, 205.25, 1.5],
                                                 ["P-15", -3.0, 7.13, 0.0], [None, None, None, None]], got)
    # 보이는 글자(Text): 설정한 소수 자리 그대로(끝 0 유지), 뒤 줄도 열 너비가 맞아 반올림돼 보이지 않음
    shown = [[ws.Cells(3 + r, 2 + c).Text for c in range(4)] for r in range(3)]
    check("엑셀 보이는 글자 소수 자리 유지", shown == [["P-05", "100.00", "200.00", "0.0"], ["P-10", "110.50", "205.25", "1.5"],
                                                ["P-15", "-3.00", "7.13", "0.0"]], shown)
    check("상태줄", "점 3개" in w.var_status.get(), w.var_status.get())
    # 도면: 점마다 POINT·TEXT·CIRCLE 하나씩, 순번 문자는 점 + (0, 4×2) 가운데, 높이 2.5×2
    ents = [d.ModelSpace.Item(i) for i in range(n0, d.ModelSpace.Count)]
    kinds = sorted(e.ObjectName for e in ents)
    check("도면 개체 9개(점·문자·원 ×3)", kinds == ["AcDbCircle"] * 3 + ["AcDbPoint"] * 3 + ["AcDbText"] * 3, kinds)
    txt = [e for e in ents if e.ObjectName == "AcDbText"]
    t0 = [t for t in txt if t.TextString == "P-05"]
    ok = bool(t0) and abs(t0[0].TextAlignmentPoint[0] - 100.0) < 1e-6 and abs(t0[0].TextAlignmentPoint[1] - 208.0) < 1e-6 \
        and abs(t0[0].Height - 5.0) < 1e-6
    check("순번 문자 위치·높이", ok, [(t.TextString, tuple(t.TextAlignmentPoint), t.Height) for t in txt])
    c0 = [e for e in ents if e.ObjectName == "AcDbCircle" and abs(e.Center[1] - 208.0) < 1e-6]
    check("순번 원 반지름 0.9×높이", bool(c0) and abs(c0[0].Radius - 4.5) < 1e-6,
          [(tuple(e.Center), e.Radius) for e in ents if e.ObjectName == "AcDbCircle"])
    for e in ents:
        e.Delete()
    w.destroy()
finally:
    rce.pick_and_mark_lisp = orig_lisp
    if saved is None:
        if os.path.exists(S.path(rce.CMD)):
            os.remove(S.path(rce.CMD))
    else:
        S.save(rce.CMD, saved)
    wb.Close(False)
    xl.Quit()
print("FAIL:", FAIL)
