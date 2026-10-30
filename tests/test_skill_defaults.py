# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""설정 기본값 대조(실제 AutoCAD 필요): skills/registry.py 와 skills/lisp/*.lsp 의 기본값이 같은지. 활성 도면이 Drawing*일 때만 돈다."""
import sys
import os
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from skills.common.acad import Acad
from skills import registry
a = Acad(); a.connect()
assert a.doc.Name.startswith("Drawing")
pairs = {"FE": "(append bc:el-defaults bc:fe-extra)", "FW": "(append bc:el-defaults bc:fw-extra)",
         "FEL": "(append bc:el-defaults bc:fel-extra)", "CEE": "(append bc:el-defaults bc:cee-extra)",
         "GEL": "(append bc:el-defaults bc:gel-extra)", "SLEL": "(append bc:el-defaults bc:slel-extra)",
         "IEL": "(append bc:el-defaults bc:iel-extra)", "XY": "bc:xy-defaults", "ZBC": "bc:zbc-defaults", "WCD": "bc:wcd-defaults",
         "DCP": "bc:dcp-defaults", "DCEN": "bc:dcen-defaults", "GST": "bc:gst-defaults", "STT": "bc:stt-defaults",
         "CST": "bc:cst-defaults", "NUST": "bc:nust-defaults", "MIP": "bc:mip-defaults",
         "DSLO": "bc:dslo-defaults", "NSLO": "bc:nslo-defaults", "DFB": "bc:dfb-defaults", "SLL": "bc:sll-defaults",
         "SLT": "bc:slt-defaults", "CSS": "bc:css-defaults", "CUT": "bc:cut-defaults"}
body = "".join('(foreach _p %s (write-line (strcat "%s" _d (car _p) _d (bc:str (cdr _p))) _fp))' % (v, k) for k, v in pairs.items())
lisp = {}
for r in a.lisp(body):
    c, k, v = r.split("\t")
    lisp.setdefault(c, {})[k] = v
bad = []
for c in pairs:
    py = registry.defaults(c)
    if set(py) != set(lisp[c]):
        bad.append((c, "키 차이", set(py) ^ set(lisp[c])))
    for k, v in py.items():
        lv = lisp[c].get(k)
        pv = ("1" if v else "0") if isinstance(v, bool) else v
        if isinstance(pv, float):
            ok = abs(float(lv) - pv) < 1e-9
        else:
            ok = str(pv) == lv
        if not ok:
            bad.append((c, k, pv, lv))
print("불일치:", bad)
