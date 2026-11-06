# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""EMTT 도곽 문자 엑셀 값으로 일괄 수정 — MPTE로 내보낸 엑셀 표에서 값을 고치면 그 값으로 도면의 도곽 문자를 바꾼다.

1) [엑셀로 내보내기]는 MPTE와 같다(경로·도곽핸들 열이 꼭 들어간다). 2) 엑셀에서 값을 고친다.
3) [엑셀 값으로 도면 고치기]: 표의 경로·도곽핸들로 도곽을 다시 찾아, 값이 달라진 항목만 바꾼다.
- 지금 도면은 바로 고치고(UNDO 한 번), 다른 파일은 화면 없는 AutoCAD로 고쳐 원래 저장 형식(2013 등) 그대로 저장한다.
  실제로 바뀐 글자가 있을 때만 파일을 바꾸고, 바꾸기 전 원본은 같은 폴더에 <이름>.emtt-날짜-시각.bak으로 남긴다
  (돌릴 때마다 새로 남겨 처음 원본이 지워지지 않는다). AutoCAD에 열려 있는 다른 도면은 덮어쓰지 않고 건너뛴다.
- 항목 자리에 문자가 하나면 그 문자를, 여럿(위→아래로 칸 안 여러 줄)이면 줄 수가 같을 때 줄마다 하나씩 바꾼다.
  칸 안 줄바꿈은 MTEXT 줄바꿈(\\P)이 되고, 250자 넘는 MTEXT는 조각으로 나눠 쓴다. 글꼴·색 같은 서식이 있는 MTEXT,
  한 줄 문자에 줄바꿈, 줄 수가 다른 여러 줄은 건너뛰고 이유를 알린다.
apply()는 창 없이도 쓴다(MCP skill_run).
"""

import os
import shutil
import tempfile
import time
import tkinter as tk

from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui
from skills.windows import mpte as M
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "EMTT"
FIELDS = [f for f in M.FIELDS if f[0] in ("공간", "정렬")] + [
    ("백업", "다른 파일을 고칠 때 원본을 <이름>.emtt-날짜-시각.bak으로 남기기", "bool", True, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


CHUNK = 200  # MTEXT 문자열 조각 길이 — 한 그룹 250자 제한보다 작게, 긴 글은 앞 조각을 3번 그룹으로


def mtext_chunks(v):
    """MTEXT에 쓸 글(이미 _mtext_safe) → 조각 목록. 역슬래시 코드(\\P·\\\\ 등)가 조각 사이에서 끊기지 않게 자른다."""
    b = chr(92)
    out = []
    while len(v) > CHUNK:
        cut = CHUNK
        while cut > 1 and (len(v[:cut]) - len(v[:cut].rstrip(b))) % 2 == 1:  # 끝이 홀수 개 역슬래시면 한 글자 덜
            cut -= 1
        out.append(v[:cut])
        v = v[cut:]
    return out + [v]


def edit_lisp(changes) -> str:
    """changes [(핸들, 새 글자 또는 MTEXT 조각 목록)] → 결과 줄 E(바꿈)·L(잠긴 레이어 등으로 못 바꿈)·N(핸들 없음)<탭>핸들.
    화면 없는 AutoCAD에서도 돌도록 entmod로 바꾼다. MTEXT는 앞 조각을 3번, 마지막 조각을 1번 그룹으로 넣는다."""
    def one(h, v):
        parts = v if isinstance(v, list) else [v]
        return '(list "%s" "%s" (list %s))' % (ls(h), ls(parts[-1]), " ".join('"%s"' % ls(p) for p in parts[:-1]))
    pairs = " ".join(one(h, v) for h, v in changes)
    return ('(foreach _p (list %s) (setq _e (handent (car _p)) _r "N")'
            ' (if _e (progn (setq _ed (entget _e))'
            '  (if (= (cdr (assoc 0 _ed)) "MTEXT")'
            '   (setq _ed (append (vl-remove-if (quote (lambda (q) (member (car q) (quote (1 3))))) _ed)'
            '    (mapcar (quote (lambda (c) (cons 3 c))) (caddr _p)) (list (cons 1 (cadr _p)))))'
            '   (setq _ed (subst (cons 1 (cadr _p)) (assoc 1 _ed) _ed)))'
            '  (if (entmod _ed) (progn (entupd _e) (setq _r "E")) (setq _r "L"))))'
            ' (write-line (strcat _r _d (car _p)) _fp))') % pairs


def _mtext_safe(v):
    """MTEXT에서 역슬래시·중괄호가 서식 코드로 읽히지 않게, 칸 안 줄바꿈은 MTEXT 줄바꿈(\\P)으로."""
    b = chr(92)
    return v.replace(b, b + b).replace("{", b + "{").replace("}", b + "}").replace("\n", b + "P")


def backup_path(path):
    """원본 백업 이름 <이름>.emtt-YYMMDD-HHMMSS.bak — 이미 있으면 -2, -3 …을 붙인다(덮어쓰지 않는다)."""
    stem = "%s.emtt-%s" % (os.path.splitext(path)[0], time.strftime("%y%m%d-%H%M%S"))
    out, i = stem + ".bak", 1
    while os.path.exists(out):
        i += 1
        out = "%s-%d.bak" % (stem, i)
    return out


def plan(rows, reg, read):
    """rows(엑셀 표) × read(gather 결과) → ({경로: [(핸들, 새 글자)]}, skipped [[경로, 도곽핸들, 항목, 이유]])."""
    if not rows:
        raise ValueError("표가 비었습니다.")
    head = [M.cell_str(v) for v in rows[0]]
    if "경로" not in head or "도곽핸들" not in head:
        raise ValueError("표 첫 줄에 '경로'와 '도곽핸들' 열이 있어야 합니다(MPTE·EMTT로 내보낸 표, 경로열 켜기).")
    ip, ih = head.index("경로"), head.index("도곽핸들")
    names = [n for n in M.item_names(reg) if n in head]
    if not names:
        raise ValueError("표 머리에 등록한 항목 이름이 없습니다: %s" % ", ".join(M.item_names(reg)))
    found = {(os.path.normcase(p), it["handle"].upper()): it for p, items in read for it in items}
    todo, skipped = {}, []
    for r in rows[1:]:
        r = list(r) + [None] * (len(head) - len(r))
        path, hd = M.cell_str(r[ip]), M.cell_str(r[ih]).upper()
        if not path or not hd:
            continue
        key = os.path.normcase(path if path == M.CURRENT else os.path.abspath(path))
        it = found.get((key, hd))
        if it is None:
            skipped.append([path, hd, "", "도곽을 찾지 못함(도면이 바뀌었으면 다시 내보내기)"])
            continue
        for n in names:
            new, old = M.cell_str(r[head.index(n)]), it["values"].get(n, "")
            if new == old:
                continue
            tg = it["targets"].get(n) or []
            why = _why_not(new, old, tg, it)
            if why:
                skipped.append([path, hd, n, why])
                continue
            if len(tg) == 1:
                todo.setdefault(path, []).append((tg[0], new))
            else:  # 여러 줄 → 줄마다 하나씩(바뀐 줄만)
                todo.setdefault(path, []).extend((h, v) for h, o, v in zip(tg, old.split("\n"), new.split("\n"))
                                                 if o != v)
    return todo, skipped


def _why_not(new, old, tg, it):
    """고치지 않을 이유(없으면 '')."""
    if not tg:
        return "자리에 문자가 없음"
    if any(h in it.get("formatted", ()) for h in tg):
        return "글꼴·색 같은 서식이 있는 MTEXT라 건너뜀(도면에서 직접 고치세요)"
    if len(tg) == 1:
        if "\n" in new and tg[0] not in it.get("mtext", ()):
            return "한 줄 문자(TEXT·속성)에는 줄을 바꿀 수 없음"
        return ""
    lines_old, lines_new = old.split("\n"), new.split("\n")
    if len(lines_old) != len(tg) or len(lines_new) != len(tg):
        return "자리에 문자가 %d개(칸 안 줄 수를 %d줄 그대로 두고 고치면 줄마다 바뀜)" % (len(tg), len(tg))
    return ""


def apply(rows, reg, cfg, live, live_edit, live_path="", open_paths=()):
    """표 값으로 도면을 고친다. live(code)는 지금 도면 읽기, live_edit(code)는 지금 도면 고치기(UNDO 묶음).
    → {changed, files, skipped}."""
    import background  # src
    head = [M.cell_str(v) for v in rows[0]] if rows else []
    if "경로" not in head:
        raise ValueError("표 첫 줄에 '경로' 열이 있어야 합니다.")
    ip = head.index("경로")
    files = []
    for r in rows[1:]:
        p = M.cell_str(r[ip]) if len(r) > ip else ""
        if p and p not in files:
            files.append(p)
    rcfg = dict(M.DEFAULTS, 공간=cfg["공간"], 정렬=cfg["정렬"])
    work = tempfile.mkdtemp(prefix="bc_emtt_")
    try:
        read = M.gather(files, reg, rcfg, live, live_path)
        # 표의 경로를 gather가 돌려준 경로로 맞춘다(지금 도면 이름표 포함)
        norm = {f: p for f, (p, _i) in zip(files, read)}
        rows = [rows[0]] + [list(r[:ip]) + [norm.get(M.cell_str(r[ip]), M.cell_str(r[ip]))] + list(r[ip + 1:])
                            for r in rows[1:] if len(r) > ip]
        todo, skipped = plan(rows, reg, read)
        live_key = os.path.normcase(live_path) if live_path else ""
        changed, done, backups = 0, [], []
        for path, ch in todo.items():
            key = os.path.normcase(path)
            is_live = path == M.CURRENT or key == live_key
            mt = {h for pth, items in read if pth == path for it in items for h in it["mtext"]}
            ch = [(h, mtext_chunks(_mtext_safe(v)) if h in mt else v) for h, v in ch]
            if is_live:
                res = live_edit(edit_lisp(ch))
            elif key in open_paths:
                skipped += [[path, "", "", "AutoCAD에 열려 있어 건너뜀(닫거나 그 도면을 활성으로 두고 다시)"]]
                continue
            else:
                tmp = os.path.join(work, "edit_%d.dwg" % len(done))
                res = background.build(edit_lisp(ch), tmp, base_drawing=path, preview=False,
                                       save_as=background.dwg_format(path))["lines"]
                if any(r.startswith("E\t") for r in res):  # 바뀐 글자가 없으면 원본을 건드리지 않는다
                    if cfg["백업"]:
                        bak = backup_path(path)
                        shutil.copy2(path, bak)
                        backups.append(bak)
                    shutil.copy2(tmp, path)
            n = sum(1 for r in res if r.startswith("E\t"))
            skipped += [[path, "", r.split("\t")[1], "고치지 못함(잠긴 레이어 등)"] for r in res if r.startswith("L\t")]
            changed += n
            done.append([path, n])
        return {"changed": changed, "files": done, "skipped": skipped, "backups": backups}
    finally:
        shutil.rmtree(work, ignore_errors=True)


class Window(M.Window):
    CMD, TITLE, FIELDS_, DEFAULTS_ = CMD, "도곽 문자 엑셀 값으로 일괄 수정", FIELDS, DEFAULTS

    def buttons(self):
        row = tk.Frame(self, bg=ui.BG)
        row.pack(fill="x", padx=10, pady=4)
        tk.Button(row, text="① 엑셀로 내보내기", command=self.export, bg="#3E5879", fg="#FFFFFF", relief="flat",
                  height=2).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(row, text="② 엑셀 값으로 도면 고치기", command=self.apply, bg="#3E5879", fg="#FFFFFF", relief="flat",
                  height=2).pack(side="left", expand=True, fill="x", padx=2)

    def export(self):
        cfg = self.form.values()
        S.save(self.CMD, cfg)
        read = self._read(dict(M.DEFAULTS, 공간=cfg["공간"], 정렬=cfg["정렬"]))
        if read is None:
            return
        try:
            ws, r0, c0 = X.active_cell()
            M.write_text_rows(ws, r0, c0, M.to_rows(read, self.reg, dict(M.DEFAULTS, 경로열=True)))
        except X.ExcelNotReady as e:
            self.error(str(e))
            return
        self.status("도곽 %d개를 내보냈습니다. 엑셀에서 값을 고친 뒤 ②를 누르세요(경로·도곽핸들 열은 그대로)." %
                    sum(len(i) for _p, i in read))

    def apply(self):
        cfg = self.form.values()
        S.save(self.CMD, cfg)
        try:
            xl = X.app()
            v = xl.ActiveSheet.UsedRange.Value
        except Exception as e:  # noqa: BLE001
            self.error("엑셀 표를 읽지 못했습니다: %s" % e)
            return
        rows = [list(r) for r in (v if isinstance(v, tuple) else ((v,),))]
        start = next((i for i, r in enumerate(rows) if "도곽핸들" in [M.cell_str(c) for c in r]), None)
        if start is None:
            self.error("지금 엑셀 시트에서 '도곽핸들' 머리 줄을 찾지 못했습니다(① 내보낸 시트를 띄워 두세요).")
            return
        try:
            # 표에 지금 도면 줄이 없으면 AutoCAD 화면이 없어도 된다
            doc = M.live_doc(lambda: self.acad.doc, M.needs_live("EMTT", {"rows": rows[start:]}, []))
            self.status("고치는 중…")
            self.update()
            res = apply(rows[start:], self.reg, cfg, (lambda code: self.acad.lisp(code, 600)) if doc else None,
                        lambda code: self.acad.lisp_undo(code, 600), (doc.FullName or "") if doc else "",
                        M.open_paths(doc))
        except Exception as e:  # noqa: BLE001 — 사람이 볼 창이므로 원문을 보인다
            self.error("%s: %s" % (type(e).__name__, e))
            return
        msg = "문자 %d개를 바꿨습니다(도면 %d개)." % (res["changed"], len(res["files"]))
        if res["skipped"]:
            msg += " 건너뜀 %d건: %s" % (len(res["skipped"]), "; ".join(
                "%s %s" % (s[2] or os.path.basename(s[0]), s[3]) for s in res["skipped"][:5]))
        self.status(msg)


def main():
    Window().mainloop()
