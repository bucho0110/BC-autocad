# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""선·문자 표 작도 공통(HAR·SEAT·DMT·ETC): 열 너비·행 높이·병합 칸으로 표를 그린다.

rows: 2차원 문자 목록. widths: 열 너비, heights: 행 높이(하나면 모두 같음), 도면 단위.
merges: [(r0, c0, r1, c1)] 병합(끝 포함) — 안쪽 선을 긋지 않고 문자는 병합 칸 가운데.
aligns: 칸 정렬 함수 (r, c, 값) → "L"|"C"|"R" (없으면 숫자는 오른쪽, 글자는 가운데).
"""

import re

from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

_NUM = re.compile(r"^[-+]?[\d,]*\.?\d+(\s*\S{0,3})?$")


def default_align(_r, _c, v):
    return "R" if _NUM.match(str(v).strip()) else "C"


def table_lisp(rows, origin, widths, heights, h, text_layer, line_layer, merges=(), aligns=None, border_layer=None,
               colors=None):
    """origin = 표 왼쪽 위. → (LISP, 너비, 높이)."""
    nr = len(rows)
    nc = max((len(r) for r in rows), default=0)
    widths = list(widths) + [widths[-1] if widths else 10 * h] * (nc - len(widths))
    if not isinstance(heights, (list, tuple)):
        heights = [heights] * nr
    heights = list(heights) + [heights[-1] if heights else 3 * h] * (nr - len(heights))
    xs, ys = [0.0], [0.0]
    for w in widths[:nc]:
        xs.append(xs[-1] + w)
    for hh in heights[:nr]:
        ys.append(ys[-1] - hh)
    ox, oy = float(origin[0]), float(origin[1])
    owner = {}
    for m in merges:
        r0, c0, r1, c1 = m
        for i in range(r0, r1 + 1):
            for j in range(c0, c1 + 1):
                owner[(i, j)] = (r0, c0)
    cell = lambda i, j: owner.get((i, j), (i, j))  # noqa: E731
    lt, ll = ls(text_layer), ls(line_layer)
    lb = ls(border_layer) if border_layer else ll
    out = ['(bc:ensure-layer "%s" 7) (bc:ensure-layer "%s" 1)' % (lt, ll)]
    if border_layer:
        out.append('(bc:ensure-layer "%s" 3)' % lb)

    def segs(n_lines, n_cells, keep):
        """줄마다 이어지는 구간 [(줄, 시작 칸, 끝 칸)]."""
        res = []
        for k in range(n_lines):
            s = None
            for j in range(n_cells + 1):
                ok = j < n_cells and keep(k, j)
                if ok and s is None:
                    s = j
                elif not ok and s is not None:
                    res.append((k, s, j))
                    s = None
        return res

    # 가로선 k(0..nr) 칸 j: 위아래 칸이 같은 병합이면 생략
    for k, a, b in segs(nr + 1, nc, lambda k, j: k in (0, nr) or cell(k - 1, j) != cell(k, j)):
        lay = lb if k in (0, nr) else ll
        out.append('(bc:line (list %.6f %.6f 0.0) (list %.6f %.6f 0.0) "%s")' % (ox + xs[a], oy + ys[k], ox + xs[b], oy + ys[k], lay))
    for k, a, b in segs(nc + 1, nr, lambda k, i: k in (0, nc) or cell(i, k - 1) != cell(i, k)):
        lay = lb if k in (0, nc) else ll
        out.append('(bc:line (list %.6f %.6f 0.0) (list %.6f %.6f 0.0) "%s")' % (ox + xs[k], oy + ys[a], ox + xs[k], oy + ys[b], lay))
    span = {}
    for m in merges:
        span[(m[0], m[1])] = m
    al = aligns or default_align
    for i, r in enumerate(rows):
        for j, v in enumerate(r):
            if v in (None, "") or cell(i, j) != (i, j):
                continue
            r0, c0, r1, c1 = span.get((i, j), (i, j, i, j))
            a = al(i, j, v)
            y = oy + (ys[r0] + ys[r1 + 1]) / 2
            x = {"L": xs[c0] + 0.5 * h, "R": xs[c1 + 1] - 0.5 * h}.get(a, (xs[c0] + xs[c1 + 1]) / 2)
            col = ""
            if colors and colors.get((i, j)):
                col = ' (setq _t (entlast)) (vla-put-Color (vlax-ename->vla-object _t) %d)' % int(colors[(i, j)])
            for k, line in enumerate(str(v).split("\n")):
                n = len(str(v).split("\n"))
                yy = y + ((n - 1) / 2.0 - k) * 1.6 * h
                out.append('(bc:text (list %.6f %.6f 0.0) "%s" %.6f "%s" "M%s" 0.0)%s'
                           % (ox + x, yy, ls(line), h, lt, {"L": "L", "R": "R"}.get(a, "C"), col))
    return "".join(out), xs[-1], -ys[-1]
