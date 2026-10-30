# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""skill_run 연결(종단·횡단, 수량·표, 정리, ADD·RCHK) — mcp_tools.run이 이 명령들을 여기로 넘긴다.

ctl.lisp로 덤프하고 창 모듈의 계산 함수로 결과를 만든 뒤, 그릴 것이 있으면 draw(code)로 UNDO 한 묶음에 그린다.
"""

import importlib

RUN_SPECS = {
    "DRP": "rows [[머리…], [값…]…](첫 줄 머리: 누가거리(또는 측점)·지반고·계획고·종곡선·그 밖 EL 열, x 칸은 선 끊기), "
           "insert_point [x,y](선택: 기준선 왼쪽 끝에 그리기) → table(측점·누가거리·EL…·절토고·성토고), vips(VIP 표)",
    "DCS": "profile_rows(DRP 형식, 선택 — 횡단 계획고 계산·종단 그리기용), section_rows(엑셀 형식 행, settings.횡단형식·거리높이) "
           "또는 sections [{station(거리 또는 0+000), ground [[거리(좌 −), EL]…]}], profile_point·section_point [x,y](선택: 그리기) "
           "→ sections [{station, center_el, plan_el, cut, fill}]",
    "DLS": "handle(종단 IP 폴리선), base_point [x,y](EL 아는 점), base_el, lengths [VIP별 종곡선 L…](선택, 없으면 settings.곡선길이), "
           "draw(기본 true) → vips 표 [측점, 누가거리, EL, L, 앞 경사%, 뒤 경사%, K]",
    "GSE": "handle(종단 계획선), base_point, base_el, stations [누가거리 또는 0+000…](없으면 settings.간격마다), "
           "start_x(선택: 시작 거리의 X, 없으면 계획선 왼쪽 끝) → rows [측점, 누가거리, 계획고]. settings.도면표기면 세로선·문자",
    "CFB": "sample_handles [지반선, 중심선, 측점 문자, 지반고 문자](선택, 없으면 저장된 견본 — 일괄) 또는 ground_handle + center_point [x,y] + "
           "center_el + station(하나씩) → rows(settings.양식·거리높이). settings.도면표기면 정점마다 문자",
    "EWT": "block(토적표 블록 이름) + ① station_box [x0,y0,x1,y1] + items [[이름, [x0,y0,x1,y1]]…](블록 기준 좌표) "
           "② station_tag + tags [태그…](속성 블록) → rows [측점, 누가거리, 항목…]",
    "CL": "handles(선·폴리선·호·원·타원·스플라인), draw(기본 true) → labels [{text, length}] (settings는 CL)",
    "QCL": "CL과 같음(설정은 CL 설정 파일)",
    "TLAE": "handles → count, length(m), area(㎡) (settings.축척)",
    "HAR": "handles(해치), insert_point [x,y](선택: 표 그리기) → rows(묶음별 개수·면적), total",
    "SEAT": "handles(닫힌 객체), insert_point(선택) → rows(번호·구분·면적·둘레), total. 그리면 객체에 번호",
    "DMT": "handle(닫힌 폴리선), insert_point(선택) → rows(번호·밑변·높이·면적, 합계, CAD 면적), triangles",
    "CTE": "handles(표의 선·문자) → rows, merges [[r0, c0, r1, c1]]",
    "ETC": "rows [[…]], insert_point [x,y], merges(선택), widths(선택: 도면 단위 열 너비), height(선택: 행 높이) → 그린 표 크기",
    "DDE": "handles(선택, 없으면 모형 공간 전체 대상 종류) → found(중복 수), handles(지운·옮긴 핸들, 300개까지)",
    "DOE": "handles → removed(겹친 객체 수), merged(합친 선 묶음 수)",
    "JJJ": "handles(선·호·폴리선) → polylines(만든 폴리선 수)",
    "CPL": "handles(폴리선), settings.변환('폴리선(경량)'|'2D 폴리선'|'3D 폴리선') → converted",
    "FTF": "(인자 없음) settings.방식·글꼴·큰글꼴 → styles(검사), changed(바꾼 스타일)",
    "ADD": "handles(문자·치수), settings.값·계산('+/-'|'×'|'÷') → changes [[핸들, 새 문자]]",
    "RCHK": "struct_handles(구조도 객체), detail_handles(상세도 객체) → rows [번호, 구조도 직경, 상세도 직경, 비고], problems. "
            "settings.표시면 '철근-검사' 레이어에 표시",
}
CMDS = tuple(RUN_SPECS)


def _sel(lq, hs, var="_ss"):
    return '(setq %s (ssadd)) (foreach _h (list %s) (if (handent _h) (ssadd (handent _h) %s)))' % (
        var, " ".join(lq(h) for h in hs), var)


def _all(lq, types):
    return '(setq _ss (ssget "_X" (list (cons 0 %s) (cons 410 "Model"))))' % lq(types)


def run(ctl, doc, lib, cmd, a, t1, merged_cfg, lq, draw, need):
    """명령 하나 실행 → 결과 dict."""
    mod = importlib.import_module("skills.windows.%s" % cmd.lower())
    cfg_cmd = "CL" if cmd == "QCL" else cmd
    base = importlib.import_module("skills.windows.cl") if cmd == "QCL" else mod
    cfg = merged_cfg(cfg_cmd, base.DEFAULTS, a.get("settings"))

    def L(code):
        return ctl.lisp(lib + code, doc=doc, timeout_s=t1)

    res = {"drawing": doc.Name}
    if cmd == "DRP":
        need(a, "rows")
        code, table, vt = mod.build(a["rows"], cfg, a.get("insert_point") or (0.0, 0.0))
        if a.get("insert_point"):
            draw(code)
        return dict(res, table=table, vips=vt, drawn=bool(a.get("insert_point")))
    if cmd == "DCS":
        from skills.windows import drp
        if a.get("sections"):
            secs = []
            for s in a["sections"]:
                d = mod._sta(s.get("station"), cfg)
                if d is None:
                    raise ValueError("sections의 station을 읽지 못했습니다: %r" % (s.get("station"),))
                g = sorted((float(p[0]), float(p[1])) for p in s["ground"])
                from skills.common import vprof as V
                secs.append({"dist": d, "ground": g, "center_el": V.interp(g, 0.0)})
        elif a.get("section_rows"):
            secs = mod.parse_sections(a["section_rows"], cfg)
        else:
            secs = []
        if a.get("profile_point"):
            need(a, "profile_rows")
            draw(drp.build(a["profile_rows"], cfg, a["profile_point"])[0])
        code, out = mod.sections_lisp(secs, a.get("section_point") or (0.0, 0.0), cfg, mod.plan_of(a.get("profile_rows"), cfg))
        if a.get("section_point") and secs:
            draw(code)
        return dict(res, sections=out, drawn_sections=bool(a.get("section_point") and secs),
                    drawn_profile=bool(a.get("profile_point")))
    if cmd == "DLS":
        need(a, "handle", "base_point", "base_el")
        rows = L('(setq _ip (handent %s)) %s' % (lq(a["handle"]), mod.VERTS_LISP))
        verts = [(float(c[1]), float(c[2])) for c in (r.split("\t") for r in rows) if c[0] == "V"]
        vips, x0 = mod.compute(verts, a["base_point"], float(a["base_el"]), cfg, a.get("lengths"))
        if a.get("draw", True):
            draw(mod.build_lisp(vips, x0, a["base_point"], float(a["base_el"]), cfg))
        from skills.common import vprof as V
        return dict(res, vips=V.vip_table(vips, V.start_of(cfg), cfg["측점구분"], float(cfg["체인"])))
    if cmd == "GSE":
        need(a, "handle", "base_point", "base_el")
        bb = [r.split("\t") for r in L('(setq _pl (handent %s)) %s' % (lq(a["handle"]), mod.BBOX_LISP)) if r.startswith("BB\t")]
        x0, y0, x1, y1 = (float(v) for v in bb[0][1:5])
        if a.get("start_x") is not None:
            x0 = float(a["start_x"])
        uh = 1000.0 / cfg["H축척"]
        ds = mod.dists(cfg, a.get("stations"), (x1 - x0) / uh)
        hits = L(mod.hits_lisp("(handent %s)" % lq(a["handle"]), [x0 + d * uh for d in ds], y0 - 1, y1 + 1))
        rows, marks = mod.rows_from_hits(ds, hits, a["base_point"], float(a["base_el"]), cfg)
        if cfg["도면표기"] and marks:
            draw(mod.draw_lisp(marks, cfg))
        return dict(res, rows=[["측점", "누가거리", "계획고"]] + rows, found=len(marks))
    if cmd == "CFB":
        from skills.common import xsec as XS
        from skills.common import coords as C
        if a.get("ground_handle"):
            need(a, "center_point", "center_el")
            rows = L('(foreach _p (bc:verts (handent %s)) (write-line (strcat "V" _d (bc:rtos (car _p) 2 10) _d'
                     ' (bc:rtos (cadr _p) 2 10)) _fp))' % lq(a["ground_handle"]))
            verts = [(float(c[1]), float(c[2])) for c in (r.split("\t") for r in rows) if c[0] == "V"]
            cx, cy = float(a["center_point"][0]), float(a["center_point"][1])
            uh, uv = 1000.0 / cfg["H축척"], 1000.0 / cfg["V축척"]
            to_el = lambda y: float(a["center_el"]) + (y - cy) / uv  # noqa: E731
            st = str(a.get("station") or "")
            secs = [{"station": st, "dist": C.station_to_dist(st, cfg["측점구분"], float(cfg["측점간격"])) or 0.0,
                     "points": mod.section_points(verts, cx, to_el, uh), "center_el": float(a["center_el"])}]
            marks = [(x, y, (x - cx) / uh, to_el(y)) for x, y in verts]
        else:
            if a.get("sample_handles"):
                spec = XS.spec_from_rows(L(XS.sample_body_from_handles(a["sample_handles"])))
            else:
                spec = XS.load_spec()
            if not spec:
                raise ValueError("견본 단면이 없습니다. sample_handles 또는 ground_handle·center_point·center_el을 주세요.")
            secs, marks = mod.batch(spec, L(XS.dump_body(spec)), cfg)
        if cfg["도면표기"] and marks:
            draw(mod.labels_lisp(marks, cfg))
        return dict(res, sections=len(secs), rows=mod.to_rows(secs, cfg))
    if cmd == "EWT":
        need(a, "block")
        if a.get("station_tag"):
            reg = {"block": a["block"], "mode": "attr", "station": a["station_tag"], "items": [[t, t] for t in a.get("tags", [])]}
        else:
            need(a, "station_box", "items")
            reg = {"block": a["block"], "mode": "box", "station": a["station_box"], "items": a["items"]}
        ins, texts = mod.parse(L(mod.dump_lisp(a["block"])))
        return dict(res, blocks=len(ins), rows=mod.to_rows(mod.collect(ins, texts, reg), reg, cfg))
    from skills.common import geo as G
    if cmd in ("CL", "QCL"):
        need(a, "handles")
        from skills.windows import cl
        labs = cl.labels(G.parse(L(_sel(lq, a["handles"]) + G.GEO_LISP)), cfg)
        if a.get("draw", True) and labs:
            draw(cl.lisp(labs, cfg))
        return dict(res, labels=[{"text": s, "length": round(Lm, 6)} for *_x, s, Lm in labs])
    if cmd == "TLAE":
        need(a, "handles")
        return dict(res, **mod.totals(G.parse(L(_sel(lq, a["handles"]) + G.GEO_LISP)), cfg))
    if cmd == "HAR":
        need(a, "handles")
        ents = mod.fill_missing(G.parse(L(_sel(lq, a["handles"]) + mod.dump_lisp())))
        gs = mod.group(ents, cfg)
        rows, merges, total = mod.table_rows(gs, cfg)
        if a.get("insert_point"):
            draw(mod.table_lisp(rows, merges, a["insert_point"], cfg) + (mod.number_lisp(gs, cfg) if cfg["개별번호"] else ""))
        return dict(res, rows=rows, total=total, hatches=len(ents))
    if cmd == "SEAT":
        need(a, "handles")
        from skills.windows.har import dump_lisp as hatch_dump, fill_missing
        body = (_sel(lq, a["handles"], "_all") + ' (setq _ss (ssadd) _hs (ssadd)) (foreach _e (bc:ss-list _all)'
                ' (if (= (cdr (assoc 0 (entget _e))) "HATCH") (ssadd _e _hs) (ssadd _e _ss))) %s (setq _ss _hs) %s'
                % (G.GEO_LISP, hatch_dump()))
        rows, merges, marks, total = mod.build(fill_missing(G.parse(L(body))), cfg)
        if a.get("insert_point"):
            draw(mod.draw_lisp(rows, merges, marks, a["insert_point"], cfg))
        return dict(res, rows=rows, total=total)
    if cmd == "DMT":
        need(a, "handle")
        ents = G.parse(L(_sel(lq, [a["handle"]]) + G.GEO_LISP))
        if not ents or not ents[0]["closed"]:
            raise ValueError("DMT: handle은 닫힌 폴리선이어야 합니다.")
        poly = G.polygon(ents[0]["pieces"])
        tris = mod.triangulate(poly)
        rows, total = mod.table_rows(tris, cfg, ents[0]["area"])
        if a.get("insert_point"):
            draw(mod.draw_lisp(tris, poly, a["insert_point"], cfg, rows))
        return dict(res, rows=rows, total=total, triangles=len(tris))
    if cmd == "CTE":
        need(a, "handles")
        rows, merges = mod.grid(*mod.parse(L(_sel(lq, a["handles"]) + mod.DUMP_LISP)), float(cfg["허용오차"]))
        return dict(res, rows=rows, merges=[list(m) for m in merges])
    if cmd == "ETC":
        need(a, "rows", "insert_point")
        rows = [["" if v is None else str(v) for v in r] for r in a["rows"]]
        merges = [tuple(m) for m in a.get("merges") or []]
        if a.get("widths"):
            from skills.common import cadtable as TB
            h = float(cfg["문자높이"])
            code, W, H = TB.table_lisp(rows, a["insert_point"], [float(w) for w in a["widths"]],
                                       float(a.get("height") or 2 * h), h, cfg["문자레이어"], cfg["선레이어"], merges)
        else:
            code, W, H = mod.draw_lisp(rows, a["insert_point"], dict(cfg, 크기="문자 길이에 맞춤"), merges)
        draw(code)
        return dict(res, width=round(W, 4), height=round(H, 4))
    if cmd == "DDE":
        ty = mod.types_of(cfg)
        body = _sel(lq, a["handles"]) if a.get("handles") else _all(lq, ",".join(ty))
        ents = mod.parse(L(body + mod.codes_lisp(ty) + mod.DUMP_LISP))
        hs = mod.duplicates(ents, cfg)
        if hs:
            draw(mod.apply_lisp(hs, cfg))
        return dict(res, checked=len(ents), found=len(hs), handles=hs[:300])
    if cmd == "DOE":
        need(a, "handles")
        gone, merges = mod.plan(G.parse(L(_sel(lq, a["handles"]) + G.GEO_LISP)), cfg)
        code = mod.apply_lisp(gone, merges, cfg)
        if code:
            draw(code)
        return dict(res, removed=len(gone), merged=len(merges), handles=gone[:300])
    if cmd == "JJJ":
        need(a, "handles")
        code, n = mod.build(G.parse(L(_sel(lq, a["handles"]) + G.GEO_LISP)), cfg)
        if code:
            draw(code)
        return dict(res, polylines=n)
    if cmd == "CPL":
        need(a, "handles")
        code, n = mod.convert_lisp(mod.parse(L(_sel(lq, a["handles"]) + mod.DUMP_LISP)), cfg)
        if code:
            draw(code)
        return dict(res, converted=n)
    if cmd == "FTF":
        styles = mod.parse(L(mod.DUMP_LISP))
        names = mod.targets(styles, cfg)
        if names:
            with ctl._undo_group(doc):
                err = [r.split("\t", 1)[1] for r in L(mod.fix_lisp(names, cfg)) if r.startswith("ERR\t")]
            if err:
                raise ValueError("FTF: %s" % err[0])
        return dict(res, styles=styles, changed=names)
    if cmd == "ADD":
        need(a, "handles")
        ch = mod.plan(mod.parse(L(_sel(lq, a["handles"]) + mod.DUMP_LISP)), cfg)
        if ch:
            draw(mod.apply_lisp(ch, cfg))
        return dict(res, changes=[[h, t] for h, t, _d in ch])
    if cmd == "RCHK":
        need(a, "struct_handles", "detail_handles")
        from skills.windows import ret
        sa = L(_sel(lq, a["struct_handles"]) + ret.DUMP_LISP)
        sb = L(_sel(lq, a["detail_handles"]) + ret.DUMP_LISP)
        rows, probs = mod.compare(sa, sb, cfg)
        if cfg["표시"] and probs:
            draw(mod.mark_lisp(probs))
        return dict(res, rows=[["번호", "구조도 직경", "상세도 직경", "비고"]] + rows, problems=len(probs))
    raise LookupError(cmd)
