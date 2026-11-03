# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""MPTE 도곽 문자 엑셀로 모으기 — 도곽마다 같은 자리에 있는 문자·속성 값을 모아 엑셀 표로 낸다.

도곽은 블록(외부 참조 포함)이어야 한다. 도곽이 블록이 아니면 도곽마다 하나씩 있는 블록(회사 로고 등)을 등록한다.
- 항목 세 가지: ① 영역 문자(도곽 기준 사각 영역 안 문자) ② 도곽 속성(도곽 블록의 속성 값) ③ 영역 속성 블록
  (영역 안에 삽입점이 있는 속성 블록의 태그 값). 영역은 도곽 기준 좌표로 저장해 도곽마다 축척·회전이 달라도 맞춘다.
- 도곽 등록은 MPTE·EMTT·DTC가 같이 쓴다(설정 파일 TB_REG). 이름이 다른 도곽은 각각 등록한다.
- 지금 도면은 모형·배치 모두 읽고, 다른 도면 파일은 화면 없는 AutoCAD(src/background.py)로 열어 읽는다(원본은 그대로).
  화면 없는 AutoCAD에는 ActiveX가 없어 문자 위치는 textbox·MTEXT 폭으로 계산한다(실측).
collect()·to_rows()·gather()는 창 없이도 쓴다(MCP skill_run). EMTT·DTC가 이 모듈을 가져다 쓴다.
"""

import json
import math
import os
import re
import shutil
import tempfile
import tkinter as tk
from tkinter import filedialog, simpledialog

from skills.common import acad as A
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "MPTE"
FIELDS = [
    ("공간", "읽을 공간", "choice", "모형+배치", ["모형+배치", "모형", "배치"]),
    ("정렬", "도곽 순서", "choice", "위→아래", ["위→아래", "왼→오른", "도면 순서"]),
    ("숫자로", "숫자로 읽히는 값은 숫자로 내보내기 (EMTT로 되돌려 쓸 표는 끄기)", "bool", False, None),
    ("경로열", "경로·도곽핸들 열 넣기 (EMTT로 되돌려 쓸 때 필요)", "bool", True, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
REG_KEY = "TB_REG"
KINDS = {"box": "영역 문자", "attr": "도곽 속성", "abox": "영역 속성 블록"}
CURRENT = "(지금 도면)"


def load_reg():
    try:
        r = json.loads(S.load(REG_KEY, {"json": ""})["json"] or "{}")
    except ValueError:
        r = {}
    r.setdefault("blocks", {})
    return r


def save_reg(reg):
    S.save(REG_KEY, {"json": json.dumps(reg, ensure_ascii=False)})


def check_reg(reg):
    """MCP로 받은 등록을 확인한다. → 같은 형식의 dict."""
    if not isinstance(reg, dict) or not isinstance(reg.get("blocks"), dict) or not reg["blocks"]:
        raise ValueError("registration은 {\"blocks\": {도곽 블록 이름: {\"items\": [...]}}} 형식이어야 합니다.")
    for name, b in reg["blocks"].items():
        for it in b.get("items") or []:
            if it.get("kind") not in KINDS or not it.get("name"):
                raise ValueError("%s: 항목마다 name과 kind(box|attr|abox)가 필요합니다: %r" % (name, it))
            if it["kind"] in ("box", "abox") and len(it.get("box") or []) != 4:
                raise ValueError("%s/%s: box는 도곽 기준 [x0, y0, x1, y1]이어야 합니다." % (name, it["name"]))
            if it["kind"] in ("attr", "abox") and not it.get("tag"):
                raise ValueError("%s/%s: tag가 필요합니다." % (name, it["name"]))
    return reg


def item_names(reg):
    """등록 순서대로 항목 이름(도곽 이름이 달라도 같은 이름이면 한 열)."""
    out = []
    for b in reg["blocks"].values():
        for it in b.get("items") or []:
            if it["name"] not in out:
                out.append(it["name"])
    return out


# ---------------------------------------------------------------- 도면 읽기
# 화면 없는 AutoCAD에서도 돌도록 ActiveX 없이 쓴다(블록 실제 이름만 ActiveX가 있을 때 읽는다 — 동적 블록).
HELPERS = (
    '(defun bc:tb-name (e / r) (setq r (vl-catch-all-apply (quote (lambda () (vla-get-EffectiveName'
    ' (vlax-ename->vla-object e)))))) (if (= (type r) (quote STR)) r (cdr (assoc 2 (entget e)))))'
    '(defun bc:tb-rot (p dx dy a) (list (+ (car p) (- (* dx (cos a)) (* dy (sin a))))'
    ' (+ (cadr p) (+ (* dx (sin a)) (* dy (cos a)))) (if (caddr p) (caddr p) 0.0)))'
    '(defun bc:tb-ctr (e / ed tb p a w h c r)'
    ' (setq ed (entget e))'
    ' (if (= (cdr (assoc 0 ed)) "MTEXT")'
    '  (progn (setq p (cdr (assoc 10 ed)) a (1- (cdr (assoc 71 ed))) w (cond ((cdr (assoc 42 ed))) (0.0))'
    '   h (cond ((cdr (assoc 43 ed))) (0.0)) c (rem a 3) r (/ a 3))'
    '   (bc:tb-rot p (* w (- 0.5 (* 0.5 c))) (* h (- (* 0.5 r) 0.5))'
    '    (if (assoc 11 ed) (angle (list 0.0 0.0) (cdr (assoc 11 ed))) (cond ((cdr (assoc 50 ed))) (0.0)))))'
    '  (progn (setq tb (textbox ed) p (cdr (assoc 10 ed)))'
    '   (trans (bc:tb-rot p (/ (+ (caar tb) (caadr tb)) 2.0) (/ (+ (cadar tb) (cadadr tb)) 2.0) (cdr (assoc 50 ed))) e 0))))'
    '(defun bc:tb-str (s) (vl-string-translate "\\t\\n\\r" "   " s))')


def dump_lisp(names) -> str:
    """등록한 도곽 I<탭>핸들<탭>이름<탭>공간<탭>x<탭>y<탭>sx<탭>sy<탭>회전, 그 밖 속성 블록 B<탭>핸들<탭>공간<탭>x<탭>y,
    바로 위 블록의 속성 A<탭>태그<탭>값<탭>핸들, 문자 T(MTEXT는 M)<탭>핸들<탭>공간<탭>x<탭>y<탭>내용."""
    nm = " ".join('"%s"' % ls(n.upper()) for n in names)
    return HELPERS + (
        '(setq _nm (list %s))'
        '(foreach _e (bc:ss-list (ssget "_X" (list (cons 0 "INSERT"))))'
        ' (setq _ed (entget _e) _n (strcase (bc:tb-name _e)) _ip (trans (cdr (assoc 10 _ed)) _e 0)'
        '  _at (and (assoc 66 _ed) (= 1 (cdr (assoc 66 _ed)))) _sp (cdr (assoc 410 _ed)))'
        ' (cond ((member _n _nm) (write-line (strcat "I" _d (cdr (assoc 5 _ed)) _d _n _d _sp _d (bc:rtos (car _ip) 2 8) _d'
        '   (bc:rtos (cadr _ip) 2 8) _d (bc:rtos (cdr (assoc 41 _ed)) 2 8) _d (bc:rtos (cdr (assoc 42 _ed)) 2 8) _d'
        '   (bc:rtos (cdr (assoc 50 _ed)) 2 10)) _fp))'
        '  (_at (write-line (strcat "B" _d (cdr (assoc 5 _ed)) _d _sp _d (bc:rtos (car _ip) 2 8) _d (bc:rtos (cadr _ip) 2 8)) _fp))'
        '  (T (setq _at nil)))'
        ' (if (or _at (member _n _nm)) (progn (setq _a (entnext _e))'
        '  (while (and _a (= (cdr (assoc 0 (entget _a))) "ATTRIB"))'
        '   (write-line (strcat "A" _d (cdr (assoc 2 (entget _a))) _d (bc:tb-str (cdr (assoc 1 (entget _a)))) _d'
        '    (cdr (assoc 5 (entget _a)))) _fp) (setq _a (entnext _a))))))'
        '(foreach _e (bc:ss-list (ssget "_X" (list (cons 0 "TEXT,MTEXT"))))'
        ' (setq _p (bc:tb-ctr _e) _ed (entget _e))'
        ' (write-line (strcat (if (= (cdr (assoc 0 _ed)) "MTEXT") "M" "T") _d (cdr (assoc 5 _ed)) _d (cdr (assoc 410 _ed)) _d'
        '  (bc:rtos (car _p) 2 8) _d'
        '  (bc:rtos (cadr _p) 2 8) _d (bc:tb-str (bc:text-of _e))) _fp))') % nm


def parse(rows):
    frames, blocks, texts = [], [], []
    cur = None
    for r in rows:
        c = r.split("\t")
        if c[0] == "I" and len(c) >= 9:
            cur = {"handle": c[1], "block": c[2], "space": c[3], "x": float(c[4]), "y": float(c[5]),
                   "sx": float(c[6]), "sy": float(c[7]), "rot": float(c[8]), "att": {}}
            frames.append(cur)
        elif c[0] == "B" and len(c) >= 5:
            cur = {"handle": c[1], "space": c[2], "x": float(c[3]), "y": float(c[4]), "att": {}}
            blocks.append(cur)
        elif c[0] == "A" and cur is not None and len(c) >= 4:
            cur["att"].setdefault(c[1].upper(), (c[2].strip(), c[3]))
        elif c[0] in ("T", "M") and len(c) >= 5:
            texts.append((c[2], float(c[3]), float(c[4]), c[5].strip() if len(c) > 5 else "", c[1], c[0] == "M"))
    return frames, blocks, texts


def to_local(ins, x, y):
    dx, dy = x - ins["x"], y - ins["y"]
    c, s = math.cos(-ins["rot"]), math.sin(-ins["rot"])
    return (dx * c - dy * s) / (ins["sx"] or 1.0), (dx * s + dy * c) / (ins["sy"] or 1.0)


def _in(box, p):
    x0, y0, x1, y1 = box
    return min(x0, x1) <= p[0] <= max(x0, x1) and min(y0, y1) <= p[1] <= max(y0, y1)


def _space_ok(space, cfg):
    model = space.upper() == "MODEL"
    return cfg["공간"] == "모형+배치" or (cfg["공간"] == "모형") == model


def collect(frames, blocks, texts, reg, cfg):
    """→ [{handle, block, space, x, y, values {항목: 값}, targets {항목: [고칠 문자·속성 핸들]}, mtext {MTEXT 핸들}}]
    (cfg 정렬 순서).
    영역 안 문자가 여럿이면 위 → 아래, 왼 → 오른 순서로 띄어 잇는다."""
    regs = {k.upper(): v for k, v in reg["blocks"].items()}
    mtext = {t[4] for t in texts if t[5]}
    out = []
    for f in frames:
        if not _space_ok(f["space"], cfg) or f["block"].upper() not in regs:
            continue
        items = regs[f["block"].upper()].get("items") or []
        boxes = [it["box"] for it in items if it["kind"] in ("box", "abox")]
        reach = max([abs(v) for bx in boxes for v in bx] or [0.0]) * max(abs(f["sx"]), abs(f["sy"]), 1e-9) * 1.5
        near = lambda x, y: abs(x - f["x"]) <= reach and abs(y - f["y"]) <= reach  # noqa: E731
        loc = [(to_local(f, x, y), t, h) for sp, x, y, t, h, _m in texts if sp == f["space"] and near(x, y)]
        loc.sort(key=lambda i: (-i[0][1], i[0][0]))
        vals, tg = {}, {}
        for it in items:
            if it["kind"] == "box":
                hit = [(t, h) for p, t, h in loc if _in(it["box"], p)]
                vals[it["name"]] = " ".join(t for t, _h in hit)
                tg[it["name"]] = [h for _t, h in hit]
            elif it["kind"] == "attr":
                v, h = f["att"].get(it["tag"].upper(), ("", None))
                vals[it["name"]], tg[it["name"]] = v, [h] if h else []
            else:
                hit = [b["att"][it["tag"].upper()] for b in blocks
                       if b["space"] == f["space"] and it["tag"].upper() in b["att"] and near(b["x"], b["y"])
                       and _in(it["box"], to_local(f, b["x"], b["y"]))]
                vals[it["name"]] = " ".join(v for v, _h in hit)
                tg[it["name"]] = [h for _v, h in hit]
        out.append({"handle": f["handle"], "block": f["block"], "space": f["space"], "x": f["x"], "y": f["y"],
                    "size": reach / 1.5, "values": vals, "targets": tg,
                    "mtext": {h for hs in tg.values() for h in hs if h in mtext}})
    return sort_frames(out, cfg["정렬"])


def sort_frames(items, how):
    """모형 먼저, 배치는 이름순. 위→아래는 같은 줄(도곽 크기 절반 안)끼리 왼→오른."""
    if how == "도면 순서":
        return items
    space = lambda i: (i["space"].upper() != "MODEL", i["space"])  # noqa: E731
    if how == "왼→오른":
        return sorted(items, key=lambda i: (space(i), i["x"], -i["y"]))
    out = []
    for i in sorted(items, key=lambda i: (space(i), -i["y"])):
        if out and space(out[-1][-1]) == space(i) and abs(out[-1][0]["y"] - i["y"]) <= max(i["size"], 1e-9) * 0.5:
            out[-1].append(i)
        else:
            out.append([i])
    return [i for line in out for i in sorted(line, key=lambda i: i["x"])]


def gather(files, reg, cfg, live=None, live_path="", work=None, log=None):
    """files의 도곽을 읽는다. → [(파일 경로, 도곽 목록)]. CURRENT 또는 live_path와 같은 파일은 live(code)로
    지금 도면에서 읽고(저장 안 한 내용까지), 나머지는 화면 없는 AutoCAD로 연다(파일 하나에 몇 초)."""
    import background  # src
    names = [n for n in reg["blocks"]]
    code = dump_lisp(names)
    out = []
    own = work is None
    work = work or tempfile.mkdtemp(prefix="bc_mpte_")
    try:
        for i, f in enumerate(files):
            is_live = f == CURRENT or (live_path and os.path.normcase(os.path.abspath(f)) == os.path.normcase(live_path))
            if log:
                log("읽는 중 %d/%d: %s" % (i + 1, len(files), os.path.basename(live_path) if f == CURRENT else f))
            if is_live:
                if live is None:
                    raise ValueError("지금 도면을 읽을 수 없습니다.")
                rows = live(code)
                path = live_path or CURRENT
            else:
                if not os.path.isfile(f):
                    raise FileNotFoundError("파일이 없습니다: %s" % f)
                rows = background.build(code, os.path.join(work, "read_%d.dwg" % i), base_drawing=f,
                                        preview=False)["lines"]
                path = os.path.abspath(f)
            out.append((path, collect(*parse(rows), reg, cfg)))
        return out
    finally:
        if own:
            shutil.rmtree(work, ignore_errors=True)


_NUM = re.compile(r"^-?\d+(\.\d+)?$")


def to_rows(read, reg, cfg):
    names = item_names(reg)
    head = ["순번", "도면", "공간"] + names + (["경로", "도곽핸들"] if cfg["경로열"] else [])
    rows, n = [head], 0
    for path, items in read:
        for it in items:
            n += 1
            r = [n, os.path.basename(path), "모형" if it["space"].upper() == "MODEL" else it["space"]]
            for k in names:
                v = it["values"].get(k, "")
                r.append(X.to_float(v) if cfg["숫자로"] and _NUM.match(v) else v)
            if cfg["경로열"]:
                r += [path, it["handle"]]
            rows.append(r)
    return rows


def write_text_rows(ws, row, col, rows):
    """도면번호 '001' 같은 값이 숫자로 바뀌지 않게 칸을 문자 형식으로 두고 쓴다(숫자로 켠 값은 숫자 그대로)."""
    if not rows:
        return
    width = max(len(r) for r in rows)
    data = [list(r) + [""] * (width - len(r)) for r in rows]
    try:
        rng = ws.Range(ws.Cells(row, col), ws.Cells(row + len(data) - 1, col + width - 1))
        rng.NumberFormat = "@"
        rng.Value = data
        rng.EntireColumn.AutoFit()
    except Exception as e:
        raise X._busy(e)


def cell_str(v):
    """엑셀 칸 값 → 도면에 쓸 글자(1.0 → '1')."""
    if v is None:
        return ""
    if isinstance(v, float):
        return ("%d" % v) if v == int(v) else repr(v)
    return str(v).strip()


# ---------------------------------------------------------------- MCP
def run_mcp(ctl, doc, lib, cmd, a, timeout_s, merged_cfg):
    """skill_run MPTE·EMTT·DTC 공통 입구."""
    reg = check_reg(a["registration"]) if a.get("registration") else load_reg()
    if a.get("registration") and a.get("save_registration"):
        save_reg(reg)
    if not reg["blocks"]:
        raise ValueError("%s: 도곽 등록이 없습니다. registration을 주거나 MPTE 창에서 도곽을 먼저 등록하세요." % cmd)
    live_path = doc.FullName or ""
    live = lambda code: ctl.lisp(lib + code, doc=doc, timeout_s=timeout_s)  # noqa: E731
    files = a.get("files") or [CURRENT]
    if cmd == "EMTT":
        from skills.windows import emtt
        if not a.get("rows"):
            raise ValueError("EMTT: rows(MPTE 결과처럼 첫 줄 머리, 경로·도곽핸들 열 포함)가 필요합니다.")
        cfg = merged_cfg("EMTT", emtt.DEFAULTS, a.get("settings"))

        def live_edit(code):
            with ctl._undo_group(doc):
                return ctl.lisp(lib + code, doc=doc, timeout_s=timeout_s)
        return dict({"drawing": doc.Name}, **emtt.apply(a["rows"], reg, cfg, live, live_edit, live_path, open_paths(doc)))
    if cmd == "DTC":
        from skills.windows import dtc
        cfg = merged_cfg("DTC", dtc.DEFAULTS, a.get("settings"))
        rows = dtc.to_rows(gather(files, reg, dict(DEFAULTS, 공간=cfg["공간"], 정렬="위→아래"), live, live_path), cfg)
        res = {"drawing": doc.Name, "rows": rows}
        if a.get("insert_point"):
            with ctl._undo_group(doc):
                ctl.lisp(lib + dtc.draw_lisp(rows, a["insert_point"], cfg)[0], doc=doc, timeout_s=timeout_s)
            res["drawn"] = True
        return res
    cfg = merged_cfg(CMD, DEFAULTS, a.get("settings"))
    read = gather(files, reg, cfg, live, live_path)
    return {"drawing": doc.Name, "rows": to_rows(read, reg, cfg), "frames": sum(len(i) for _p, i in read)}


def open_paths(doc):
    """AutoCAD에 열려 있는 도면 경로(정규화) — 열린 파일은 뒤에서 덮어쓰지 않는다."""
    out = set()
    try:
        docs = doc.Application.Documents
        for i in range(docs.Count):
            p = docs.Item(i).FullName
            if p:
                out.add(os.path.normcase(os.path.abspath(p)))
    except Exception:  # noqa: BLE001 — 목록을 못 읽으면 열린 파일 보호만 빠진다(지금 도면은 따로 확인)
        pass
    return out


# ---------------------------------------------------------------- 창
PICK_BLOCK = ('(setq _s (entsel "\\n도곽(블록) 선택: ")) (if _s (progn (setq _e (car _s) _ed (entget _e))'
              ' (if (= (cdr (assoc 0 _ed)) "INSERT") (progn (setq _ip (trans (cdr (assoc 10 _ed)) _e 0))'
              ' (write-line (strcat "I" _d (cdr (assoc 5 _ed)) _d (strcase (bc:tb-name _e)) _d (cdr (assoc 410 _ed)) _d'
              ' (bc:rtos (car _ip) 2 8) _d (bc:rtos (cadr _ip) 2 8) _d (bc:rtos (cdr (assoc 41 _ed)) 2 8) _d'
              ' (bc:rtos (cdr (assoc 42 _ed)) 2 8) _d (bc:rtos (cdr (assoc 50 _ed)) 2 10)) _fp)'
              ' (setq _a (entnext _e)) (while (and _a (= (cdr (assoc 0 (entget _a))) "ATTRIB"))'
              ' (write-line (strcat "A" _d (cdr (assoc 2 (entget _a))) _d (bc:tb-str (cdr (assoc 1 (entget _a)))) _d'
              ' (cdr (assoc 5 (entget _a)))) _fp) (setq _a (entnext _a)))))))')
PICK_BOX = ('(setq _a (getpoint "\\n%s 첫 모서리: ")) (if _a (progn'
            ' (setq _b (getcorner _a "\\n반대 모서리: ")) (if _b (progn (setq _a (trans _a 1 0) _b (trans _b 1 0))'
            ' (write-line (strcat (bc:rtos (car _a) 2 10) _d (bc:rtos (cadr _a) 2 10) _d (bc:rtos (car _b) 2 10)'
            ' _d (bc:rtos (cadr _b) 2 10)) _fp)))))')


class Window(ui.BaseWindow):
    """MPTE 창. EMTT·DTC 창이 이어받아 아래 버튼만 바꾼다."""
    CMD, TITLE, FIELDS_, DEFAULTS_ = CMD, "도곽 문자 엑셀로 모으기", FIELDS, DEFAULTS

    def __init__(self):
        super().__init__(self.CMD, self.TITLE, size="640x720")
        self.acad = A.Acad()
        self.reg = load_reg()
        self.cur = None  # 등록 중인 도곽 {name, x, y, sx, sy, rot, tags}
        self.files = [CURRENT]
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", self.FIELDS_, S.load(self.CMD, self.DEFAULTS_))
        self.section(body, "도곽 등록 (MPTE·EMTT·DTC 공통)")
        self.var_reg = tk.StringVar()
        tk.Label(body, textvariable=self.var_reg, bg=ui.PANEL, fg=ui.ACCENT, font=ui.FONT, anchor="w",
                 justify="left", wraplength=600).pack(fill="x", pady=2)
        row = tk.Frame(body, bg=ui.PANEL)
        row.pack(fill="x")
        for t, fn in (("도곽 등록", self.reg_block), ("영역 문자 추가", self.add_box), ("도곽 속성 추가", self.add_attr),
                      ("영역 속성 블록 추가", self.add_abox), ("등록 지우기", self.clear)):
            tk.Button(row, text=t, command=fn, bg="#383A3E", fg="#FFFFFF", relief="flat").pack(
                side="left", expand=True, fill="x", padx=1)
        self.section(body, "읽을 도면 (다른 파일은 화면 없이 열어 읽고 원본은 그대로 둡니다)")
        self.lst = tk.Listbox(body, bg=ui.ENTRY, fg="#FFFFFF", font=ui.FONT, relief="flat", height=6)
        self.lst.pack(fill="both", expand=True, padx=4, pady=2)
        self.lst.insert("end", CURRENT)
        row = tk.Frame(body, bg=ui.PANEL)
        row.pack(fill="x")
        for t, fn in (("파일 추가", self.add_files), ("고른 것 빼기", self.remove_file), ("목록 비우기", self.clear_files)):
            tk.Button(row, text=t, command=fn, bg="#383A3E", fg="#FFFFFF", relief="flat").pack(side="left", padx=4)
        self.buttons()
        self.show()

    def buttons(self):
        tk.Button(self, text="엑셀로 내보내기 (엑셀에서 쓸 첫 칸을 먼저 고르세요)", command=self.run, bg="#3E5879",
                  fg="#FFFFFF", relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    # ---- 등록
    def show(self):
        if not self.reg["blocks"]:
            self.var_reg.set("등록 없음 — [도곽 등록]으로 도곽(블록)을 고른 뒤 항목을 추가하세요.")
            return
        lines = []
        for n, b in self.reg["blocks"].items():
            its = ", ".join("%s(%s)" % (i["name"], KINDS[i["kind"]]) for i in b.get("items") or []) or "항목 없음"
            lines.append("%s%s: %s" % ("▶ " if self.cur and self.cur["name"] == n else "", n, its))
        self.var_reg.set("\n".join(lines))

    def clear(self):
        if self.cur and self.cur["name"] in self.reg["blocks"]:
            del self.reg["blocks"][self.cur["name"]]
        else:
            self.reg["blocks"] = {}
        self.cur = None
        save_reg(self.reg)
        self.show()

    def reg_block(self):
        rows = self.in_cad(self.acad.lisp, HELPERS + PICK_BLOCK, A.PICK_TIMEOUT)
        i = [r.split("\t") for r in rows or [] if r.startswith("I\t")]
        if not i:
            return
        c = i[0]
        self.cur = {"name": c[2], "x": float(c[4]), "y": float(c[5]), "sx": float(c[6]), "sy": float(c[7]),
                    "rot": float(c[8]), "tags": [r.split("\t")[1] for r in rows if r.startswith("A\t")]}
        self.reg["blocks"].setdefault(c[2], {"items": []})
        save_reg(self.reg)
        self.show()
        self.status("도곽 %s 등록. 이 도곽 기준으로 항목을 추가하세요." % c[2])

    def _need_cur(self):
        if not self.cur:
            self.error("[도곽 등록]으로 항목을 잴 도곽을 먼저 고르세요(이미 등록한 도곽도 다시 고르면 이어서 추가합니다).")
            return False
        return True

    def _box(self, msg):
        rows = self.in_cad(self.acad.lisp, PICK_BOX % msg, A.PICK_TIMEOUT)
        if not rows:
            return None
        b = [float(v) for v in rows[0].split("\t")]
        p, q = to_local(self.cur, b[0], b[1]), to_local(self.cur, b[2], b[3])
        return [p[0], p[1], q[0], q[1]]

    def _add(self, item):
        items = self.reg["blocks"][self.cur["name"]]["items"]
        items[:] = [i for i in items if i["name"] != item["name"]] + [item]
        save_reg(self.reg)
        self.show()

    def add_box(self):
        while self._need_cur():
            box = self._box("가져올 문자 영역(끝내려면 엔터)")
            if not box:
                break
            name = simpledialog.askstring(self.CMD, "항목 이름 (예: 도면번호, 도면명, 축척):", parent=self)
            if not name:
                break
            self._add({"name": name.strip(), "kind": "box", "box": box})

    def add_attr(self):
        if not self._need_cur():
            return
        if not self.cur["tags"]:
            self.error("이 도곽에는 속성이 없습니다. [영역 문자 추가]를 쓰세요.")
            return
        got = simpledialog.askstring(self.CMD, "가져올 속성 태그(쉼표로 여러 개, 비우면 전부):\n" + ", ".join(self.cur["tags"]),
                                     parent=self)
        if got is None:
            return
        tags = [t.strip() for t in got.split(",") if t.strip()] or self.cur["tags"]
        for t in tags:
            self._add({"name": t, "kind": "attr", "tag": t})

    def add_abox(self):
        if not self._need_cur():
            return
        box = self._box("속성 블록이 있는 영역")
        if not box:
            return
        tag = simpledialog.askstring(self.CMD, "가져올 속성 태그:", parent=self)
        if not tag:
            return
        name = simpledialog.askstring(self.CMD, "항목 이름:", initialvalue=tag.strip(), parent=self)
        if name:
            self._add({"name": name.strip(), "kind": "abox", "box": box, "tag": tag.strip()})

    # ---- 파일
    def add_files(self):
        for f in filedialog.askopenfilenames(parent=self, title="읽을 도면", filetypes=[("도면", "*.dwg")]):
            if f not in self.files:
                self.files.append(f)
                self.lst.insert("end", f)

    def remove_file(self):
        for i in reversed(self.lst.curselection()):
            self.lst.delete(i)
            del self.files[i]

    def clear_files(self):
        self.files = []
        self.lst.delete(0, "end")

    def _read(self, cfg):
        if not any(b.get("items") for b in self.reg["blocks"].values()):
            self.error("도곽과 항목을 먼저 등록하세요.")
            return None
        if not self.files:
            self.error("읽을 도면을 추가하세요.")
            return None
        try:
            doc = self.acad.doc
            return gather(self.files, self.reg, cfg, lambda code: self.acad.lisp(code, 600), doc.FullName or "",
                          log=lambda m: (self.status(m), self.update()))
        except Exception as e:  # noqa: BLE001 — 사람이 볼 창이므로 원문을 보인다
            self.error("%s: %s" % (type(e).__name__, e))
            return None

    def run(self):
        cfg = self.form.values()
        S.save(self.CMD, cfg)
        read = self._read(cfg)
        if read is None:
            return
        try:
            ws, r0, c0 = X.active_cell()
            write_text_rows(ws, r0, c0, to_rows(read, self.reg, cfg))
        except X.ExcelNotReady as e:
            self.error(str(e))
            return
        self.status("도면 %d개, 도곽 %d개를 내보냈습니다." % (len(read), sum(len(i) for _p, i in read)))


def main():
    Window().mainloop()
