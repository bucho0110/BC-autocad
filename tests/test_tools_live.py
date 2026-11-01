# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""cad-mcp-kr 도구 전수 시험(실제 AutoCAD 필요). 새 시험 도면을 만들어 그 안에서만 작업한다.

실행: <python> -X utf8 tests\test_tools_live.py [결과.json]
끝에 "FAIL: []"이면 통과. 시험 중 임시 폴더에 t_tools_save.dwg와 t_capture.png를 남긴다.
"""
import json
import os
import sys

sys.dont_write_bytecode = True  # 패키지 폴더(동기화 폴더일 수 있음)에 __pycache__를 만들지 않는다
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.stdout.reconfigure(encoding="utf-8")
from cad_controller import AcadControl  # noqa: E402

import tempfile
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), "cadmcp_test_result.json")
c = AcadControl()
S = c.executor.submit
R = {}
FAIL = []


class Nil(dict):
    def __getitem__(self, k):
        return Nil()
    def get(self, k, d=None):
        return Nil()
    def __eq__(self, o):
        return False
    def __hash__(self):
        return 0
    def __bool__(self):
        return False
    def __float__(self):
        return float("nan")
    def __sub__(self, o):
        return float("nan")
    def __int__(self):
        return -1


def t(name, fn, *a, expect_error=False, **kw):
    t0 = time.time()
    try:
        v = S(fn, *a, **kw)
        R[name] = {"ok": True, "s": round(time.time() - t0, 3), "v": v}
        if expect_error:
            FAIL.append(name + " (오류가 나야 함)")
    except Exception as e:
        R[name] = {"ok": False, "s": round(time.time() - t0, 3), "err": "%s: %s" % (type(e).__name__, e), "tb": traceback.format_exc()[-1500:] if not expect_error else ""}
        if not expect_error:
            FAIL.append(name)
    print(name, "=>", json.dumps(R[name], ensure_ascii=False, default=str)[:300], flush=True)
    return R[name].get("v", Nil())


def check(name, cond, info=""):
    if callable(cond):
        try:
            cond = cond()
        except Exception as e:
            cond, info = False, repr(e)
    R["CHECK " + name] = {"pass": bool(cond), "info": info}
    if not cond:
        FAIL.append("CHECK " + name)
    print("CHECK", name, "PASS" if cond else "FAIL", info, flush=True)


t("ping", c.ping)
t("health", c.health_check)
nd = t("new_drawing", c.new_drawing)
D = nd["created"]
t("info", c.get_drawing_info)

# 작도
l1 = t("create_line", c.create_line, [0, 0], [100.123456789, 0], layer="0.시험#선", color=1)
l2 = t("create_line_tc", c.create_line, [0, 10], [100, 10], true_color="12,34,56", linetype="DASHED", lineweight=35)
pl = t("create_polyline", c.create_polyline, "[[0,20],[50.5,30.25],[100,20]]", closed=False, layer="0.시험#선")
rc = t("create_rectangle", c.create_rectangle, 0, 40, 30, 60)
ci = t("create_circle", c.create_circle, [150, 30], 10)
ar = t("create_arc", c.create_arc, [150, 30], 15, 0, 90)
el = t("create_ellipse", c.create_ellipse, [200, 30], 20, 10, 30)
tx = t("create_text", c.create_text, "한글 No.1+681 ~ No.1+760 ±0.00° (10m²)", 0, 70, 2.5, 15)
mt = t("create_mtext", c.create_mtext, "첫줄\\P둘째줄 ±", 0, 80, 2.5, 50)
ha = t("create_hatch", c.create_hatch, [[110, 0], [130, 0], [130, 20]], "ANSI31", 0.5, layer="해치")
dm = t("create_dimension", c.create_dimension, [0, -10], [100, -10])
dh = t("create_dimension_h", c.create_dimension, [0, -30], [30, -23], kind="horizontal", scale=2)
dv = t("create_dimension_v", c.create_dimension, [0, -30], [30, -23], kind="vertical")
t("create_dimension_bad_kind", c.create_dimension, [0, 0], [1, 1], kind="xx", expect_error=True)
if dh and dv:
    m = S(c.run_lisp, '(foreach h (list "%s" "%s") (setq o (vlax-ename->vla-object (handent h)))'
          ' (write-line (strcat (rtos (vla-get-Measurement o) 2 4) _d (rtos (vla-get-ScaleFactor o) 2 2)) _fp))'
          % (dh["handle"], dv["handle"]))["lines"]
    check("치수 수평 30·축척 2, 수직 7", m == ["30\t2", "7\t1"], m)
hb = t("create_hatch_boundary", c.create_hatch, None, "ANSI31", 0.5, boundary_handles=[rc["handle"]] if rc else [])
if hb:
    check("기존 경계 해치(경계 새로 안 만듦)", "boundary_handle" not in hb and hb.get("boundary_handles") == [rc["handle"]], hb)
t("create_hatch_no_input", c.create_hatch, None, expect_error=True)
ld = t("create_leader", c.create_leader, [[150, 30], [165, 45], [175, 45]], "주철근 D19@200", 2.5)
if ld:
    check("지시선 MULTILEADER", ld.get("type") == "MULTILEADER", ld)
t("create_bad_radius", c.create_circle, [0, 0], 0, expect_error=True)
t("create_bad_color", c.create_line, [0, 0], [1, 1], color=300, expect_error=True)
t("create_bad_lt", c.create_line, [0, 0], [1, 1], linetype="NO_SUCH_LT", expect_error=True)

# 블록
t("create_block", c.create_block, "시험블록", 0, 0)
ib = t("insert_block", c.insert_block, "시험블록", 300, 0, 2, 2, 1, 45, layer="블록층")
t("get_blocks", c.get_blocks)
t("insert_missing_block", c.insert_block, "없는블록", 0, 0, expect_error=True)

# 레이어
t("set_layer_new", c.set_layer, "0.새층", 3, None, None, "CENTER", "", 50)
t("set_layer_tc", c.set_layer, "0.새층", -1, False, True, "", "200,100,50", -1)
lay = t("get_layers", c.get_layers)
nl = [x for x in lay if x["name"] == "0.새층"][0]
check("layer_props", nl["on"] is False and nl["locked"] is True and nl.get("true_color") == "200,100,50"
      and nl["linetype"].upper() == "CENTER" and nl["lineweight"] == 50, nl)
t("set_layer_restore", c.set_layer, "0.새층", -1, True, False)
t("set_active_layer", c.set_active_layer, "0.새층")
t("set_active_missing", c.set_active_layer, "없는층", expect_error=True)
t("set_active_back", c.set_active_layer, "0")

# 조회
g1 = t("get_entity_line", c.get_entity, l1["handle"])
check("line_coords_exact", abs(g1["end_point"][0] - 100.123456789) < 1e-9 and g1["layer"] == "0.시험#선"
      and g1["color"] == 1, g1)
g2 = t("get_entity_tc", c.get_entity, l2["handle"])
check("truecolor_lt_lw", g2.get("true_color") == "12,34,56" and g2["linetype"].upper() == "DASHED"
      and g2["lineweight"] == 35, g2)
gp = t("get_entity_poly", c.get_entity, pl["handle"])
check("poly_vertices", gp["coordinates"] == [[0, 20], [50.5, 30.25], [100, 20]] and gp["type"] == "LWPOLYLINE", gp)
gr = t("get_entity_rect", c.get_entity, rc["handle"])
check("rect_4pts", gr["vertex_count"] == 4 and gr["closed"], gr.get("vertex_count"))
gt = t("get_entity_text", c.get_entity, tx["handle"])
check("text_korean", gt["text"] == "한글 No.1+681 ~ No.1+760 ±0.00° (10m²)" and abs(gt["rotation"] - 15) < 1e-9, gt)
gb = t("get_entity_block", c.get_entity, ib["handle"])
check("block_layer_scale", gb["layer"] == "블록층" and gb["scale"][0] == 2 and abs(gb["rotation"] - 45) < 1e-9, gb)
cnt = t("count", c.count_entities)
cntl = t("count_layer", c.count_entities, "0.시험#선", "")
check("count_layer_escape", cntl["matched"] == 2, cntl)
ge = t("get_entities_all", c.get_entities, "", "", 100, 0, None)
check("get_entities_count", ge["count"] == cnt["total"] and ge["returned"] == ge["count"], (ge["count"], cnt))
gl = t("get_entities_type", c.get_entities, "", "LightWeightPolyline", 100, 0, None)
check("type_alias", gl["count"] >= 2 and all(e["type"] == "LWPOLYLINE" for e in gl["entities"]), gl["count"])
gpg = t("get_entities_page", c.get_entities, "", "", 3, 2, None)
check("paging", gpg["returned"] == 3 and gpg["truncated"] and gpg["next_offset"] == 5
      and [e["index"] for e in gpg["entities"]] == [2, 3, 4], gpg.get("next_offset"))
# 영역: 화면 밖 개체 포함 확인 — 멀리 떨어진 선을 하나 만들고 화면은 원점 근처로 줌
far = t("create_far", c.create_line, [10000, 10000], [10010, 10010])
t("zoom_window", c.zoom_window, -10, -20, 120, 90)
ga = t("get_entities_area_offscreen", c.get_entities, "", "", 100, 0, (9990, 9990, 10020, 10020))
check("area_offscreen", ga["count"] == 1 and ga["entities"][0]["handle"] == far["handle"], ga)
ga2 = t("get_entities_area_origin", c.get_entities, "", "LINE", 100, 0, (-1, -1, 101, 11))
check("area_origin", ga2["count"] == 2, [e["handle"] for e in ga2["entities"]])
sq = t("ssget_text", c.ssget_query, "TEXT", "", "*No.1*", -1, None, 100, 0, "full")
check("ssget_text_like", sq["count"] == 1 and sq["entities"][0]["handle"] == tx["handle"], sq["count"])
sh = t("ssget_handles", c.ssget_query, "", "", "", 1, None, 100, 0, "handles")
check("ssget_color_handles", sh["count"] == 1 and set(sh["entities"][0]) == {"index", "handle", "type", "layer"}, sh)
eb = t("entget_by_handles", c.entget_by_handles, [l1["handle"], "FFFFFF", tx["handle"]])
check("entget_index_pos", [e["index"] for e in eb["entities"]] == [0, 2] and eb["missing"] == 1
      and eb["entities"][1]["text"].startswith("한글"), eb)
check("entget_tc", any(e.get("true_color") == "12,34,56" for e in
                       S(c.entget_by_handles, [l2["handle"]])["entities"]), "")
ft = t("find_text", c.find_text, "No.1+681", 100, 0)
check("find_text", ft["found"] == 1 and ft["results"][0]["layer"] == "0" and ft["results"][0]["x"] == 0.0, ft)
ft2 = t("find_text_korean", c.find_text, "둘째줄", 100, 0)
check("find_mtext_korean", ft2["found"] == 1, ft2)

# 편집
t("modify", c.modify_entity, tx["handle"], "", -1, "", None, 30, "바뀐 문자 ±", 5.0, "255,0,0", 25)
gm = S(c.get_entity, tx["handle"])
check("modify_effect", gm["text"] == "바뀐 문자 ±" and abs(gm["rotation"] - 30) < 1e-9 and gm["height"] == 5
      and gm.get("true_color") == "255,0,0" and gm["lineweight"] == 25, gm)
t("modify_rotation_line", c.modify_entity, l1["handle"], rotation=10, expect_error=True)
mv = t("move", c.move_entity, ci["handle"], 5, 5, 0)
check("move_effect", S(c.get_entity, ci["handle"])["center"][:2] == [155.0, 35.0], "")
cp = t("copy", c.copy_entity, ci["handle"], 0, 30, 0)
check("copy_effect", S(c.get_entity, cp["handle"])["center"][:2] == [155.0, 65.0], cp)
t("rotate", c.rotate_entity, rc["handle"], 0, 40, 90)
t("scale", c.scale_entity, ci["handle"], 155, 35, 2)
check("scale_effect", S(c.get_entity, ci["handle"])["radius"] == 20, "")
t("mirror", c.mirror_entity, el["handle"], 230, 0, 230, 100)
t("offset", c.offset_entity, ci["handle"], 3)
al = t("array_linear", c.array_linear, l1["handle"], 3, 0, -3)
check("array_linear", len(al["new_handles"]) == 2, al)
ap = t("array_polar", c.array_polar, cp["handle"], 4, 155, 35, 360)
check("array_polar", len(ap["new_handles"]) == 3, ap)
attrs = t("block_attrs_none", c.get_block_attributes, ib["handle"])
t("block_attr_set_none", c.set_block_attribute, ib["handle"], "X", "1", expect_error=True)

# 일괄
cps = t("copy_entities", c.copy_entities, [l1["handle"], l2["handle"], "FFFFFE"], 0, 200, 0)
check("copy_entities", cps["copied"] == 2 and len(cps["errors"]) == 1, cps)
newh = [x["new_handle"] for x in cps["new_entities"]]
mvs = t("move_entities", c.move_entities, newh, 10, 0, 0)
check("move_entities", mvs["moved"] == 2 and S(c.get_entity, newh[0])["start_point"][:2] == [10.0, 200.0], mvs)
dls = t("delete_entities", c.delete_entities, newh + ["FFFFFD"])
check("delete_entities", dls["deleted"] == 2 and len(dls["errors"]) == 1, dls)
dla = t("draw_lines_atomic", c.draw_lines_atomic, pl["handle"], [[0, 100, 10, 100], [10, 100, 10, 110]])
check("draw_lines_atomic", dla["created"] == 2 and all(S(c.get_entity, h)["layer"] == "0.시험#선"
                                                        for h in dla["handles"]), dla)
t("draw_lines_atomic_badbase", c.draw_lines_atomic, "FFFFFC", [[0, 0, 1, 1]], expect_error=True)

# undo/redo — 작도 직후 조회 LISP를 끼워도 UNDO 1이 그 작도를 되돌리는가
n_before = S(c.get_drawing_info)["modelspace_count"]
nl_ = S(c.create_line, [0, -50], [10, -50])
S(c.get_entities, "", "", 5, 0, None)       # 조회 LISP를 사이에 끼움
S(c.find_text, "한글", 10, 0)
u = t("undo_after_queries", c.undo, 1)
n_after = S(c.get_drawing_info)["modelspace_count"]
check("undo_skips_queries", n_after == n_before, {"before": n_before, "after_undo": n_after, "undo": u})
r = t("redo", c.redo)
check("redo_restores", r.get("changed") is True and S(c.get_drawing_info)["modelspace_count"] == n_before + 1, r)
u3 = t("undo_batch", c.undo, 1)
t("undo_bad", c.undo, 0, expect_error=True)

# LISP
rl = t("run_lisp", c.run_lisp, '(write-line "한글±" _fp) (write-line (rtos pi 2 8) _fp)', 30)
check("run_lisp_rows", rl["lines"] == ["한글±", "3.14159265"], rl)
big = " ".join('"%X"' % i for i in range(20000))
rb = t("run_lisp_big", c.run_lisp, '(write-line (itoa (length (list %s))) _fp)' % big, 60)
check("run_lisp_big", rb["lines"] == ["20000"], rb.get("lines"))
t("run_lisp_paren", c.run_lisp, "(princ", expect_error=True)
t("run_lisp_load", c.run_lisp, '(load "x.lsp")', expect_error=True)
n0 = S(c.count_entities)["total"]
t("run_lisp_error_rollback", c.run_lisp,
  '(entmake (list (cons 0 "LINE") (cons 8 "0") (list 10 0.0 -60.0 0.0) (list 11 9.0 -60.0 0.0))) (sslength nil)',
  expect_error=True)
check("lisp_error_rollback", S(c.count_entities)["total"] == n0, "")
sc = t("send_command", c.send_command, '(entmake (list (cons 0 "POINT") (cons 8 "0") (list 10 1.0 2.0 0.0)))')
t("send_command_raw", c.send_command, "_.ZOOM _E", expect_error=True)
# 제한시간 → ESC 복구 (입력 대기 함수)
t0 = time.time()
t("run_lisp_timeout_esc", c.run_lisp, '(getpoint "MCP시험-입력대기: ")', 3, expect_error=True)
check("timeout_recovered", time.time() - t0 < 15 and S(c.health_check)["cmdactive"] == 0, round(time.time() - t0, 1))

# 뷰·캡처
t("zoom_extents", c.zoom_extents)
cv = t("capture", c.capture_view, os.path.join(os.path.dirname(OUT), "t_capture.png"))
t("capture_bad_ext", c.capture_view, os.path.join(tempfile.gettempdir(), "x.dwg"), expect_error=True)
t("regen", c.regen)

# 도면 관리
t("list_documents", c.list_documents)
t("save_untitled", c.save_drawing, "", expect_error=True)
sp = os.path.join(tempfile.gettempdir(), "t_tools_save.dwg")
if os.path.exists(sp):
    os.remove(sp)
t("save_as", c.save_drawing, sp)
t("save_inplace", c.save_drawing, "")
t("close", c.close_drawing, True)
t("open_ro", c.open_drawing, sp, True)
t("save_ro_inplace", c.save_drawing, "", expect_error=True)
t("close_ro_save", c.close_drawing, True, expect_error=True)
t("activate", c.activate_document, "t_tools_save")
t("close_nosave", c.close_drawing, False)

R["FAIL"] = FAIL
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(R, f, ensure_ascii=False, indent=1, default=str)
print("\nFAIL:", FAIL)




