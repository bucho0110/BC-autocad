# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""BC AutoCAD MCP 설치 — 이 폴더를 어느 PC에 복사해도 이것 하나로 맞춘다.

    python install\\install.py [--venv] [--claude] [--antigravity] [--codex] [--acad] [--all]

  (옵션 없음)     AutoCAD 명령 불러오기: 플러그인 폴더(%APPDATA%\\Autodesk\\ApplicationPlugins\\BC_AutoCAD.bundle)를
                  만든다 — AutoCAD가 켜질 때·도면을 열 때마다 명령(BCFE·BCXY·BCHELP…)을 불러온다.
                  같은 불러오기 파일을 %LOCALAPPDATA%\\bc-autocad\\bc_autocad.lsp에도 둔다(APPLOAD로 직접 불러올 때).
  --venv          %LOCALAPPDATA%\\bc-autocad\\venv 가상환경을 만들고 requirements를 설치
                  (이미 쓰는 파이썬이 있으면 --python 경로로 지정, 그 파이썬으로 설치 확인만)
  --claude        Claude Code에 bc-autocad로 등록(user 범위, 이미 있으면 다시 등록)
  --antigravity   안티그래비티에 bc-autocad 등록 — CLI(~/.gemini/config/mcp_config.json)와,
                  있으면 데스크톱 앱(~/.gemini/antigravity-ide/, 예전 앱 ~/.gemini/antigravity/의 mcp_config.json)
  --codex         OpenAI Codex(CLI·IDE 확장, ~/.codex/config.toml)에 bc-autocad 등록 — ChatGPT 계정으로 쓰는 경우
  --acad          AutoCAD의 신뢰 경로(TRUSTEDPATHS)에 불러오기 폴더들을 더한다.
                  예전 판이 시작하기 세트(Startup Suite)에 넣은 등록이 있으면 뺀다(플러그인 폴더와 두 번 불러오지 않게)
  --all           위 전부(--venv는 --python이 없을 때만, --claude·--codex는 그 프로그램이 있을 때만)

바꾸는 파일은 고치기 전에 %LOCALAPPDATA%\\bc-autocad\\backup\\에 사본을 남긴다.
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True  # 패키지 폴더(동기화 폴더일 수 있음)에 __pycache__를 만들지 않는다

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "bc-autocad")
BACKUP = os.path.join(DATA, "backup", datetime.datetime.now().strftime("%y%m%d_%H%M%S"))
NAME = "bc-autocad"
LOADER = os.path.join(DATA, "bc_autocad.lsp")
# AutoCAD 공식 자동 불러오기 폴더(APPAUTOLOAD). 이 사용자 계정의 AutoCAD가 켜질 때 읽는다.
BUNDLE = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Autodesk", "ApplicationPlugins",
                      "BC_AutoCAD.bundle")
BUNDLE_LSP = os.path.join(BUNDLE, "Contents", "bc_autocad.lsp")
# 고정 값(바꾸면 AutoCAD가 다른 앱으로 본다)
PRODUCT_CODE = "{6E0B2C47-9A1D-4F3B-8C55-2B7D1E4A9C10}"
UPGRADE_CODE = "{A3F1D2E8-5C47-4B9E-9D21-7C0E8B6F3A54}"


def say(*a):
    print("[install]", *a, flush=True)


def backup(path):
    if os.path.exists(path):
        os.makedirs(BACKUP, exist_ok=True)
        dst = os.path.join(BACKUP, os.path.basename(path))
        if os.path.exists(dst):  # 같은 이름(불러오기 파일 두 벌)은 폴더 이름을 앞에 붙인다
            dst = os.path.join(BACKUP, os.path.basename(os.path.dirname(path)) + "_" + os.path.basename(path))
        shutil.copy2(path, dst)
        say("백업:", dst)


def slash(p):
    return p.replace("\\", "/")


# ---------------------------------------------------------------- 파이썬
def make_venv():
    venv = os.path.join(DATA, "venv")
    py = os.path.join(venv, "Scripts", "python.exe")
    if not os.path.exists(py):
        say("가상환경 만들기:", venv)
        subprocess.check_call([sys.executable, "-m", "venv", venv])
    subprocess.check_call([py, "-m", "pip", "install", "-q", "-r", os.path.join(ROOT, "requirements.txt")])
    return py


def check_python(py):
    code = "import mcp, win32com.client, PIL; print('ok')"
    r = subprocess.run([py, "-c", code], capture_output=True, text=True)
    if r.returncode != 0:
        say("필수 패키지가 없습니다. 아래를 먼저 실행하세요:")
        say('  "%s" -m pip install -r "%s"' % (py, os.path.join(ROOT, "requirements.txt")))
        return False
    r = subprocess.run([py, "-c", "import pypdf"], capture_output=True, text=True)
    if r.returncode != 0:
        say("참고: pypdf가 없어 다중 플롯의 PDF 병합·사용자 용지 변환은 꺼집니다.")
    return True


def check_acad_version(py):
    """실행 중인 AutoCAD가 2021(R24.0) 미만이면 False. AutoCAD가 꺼져 있으면 확인하지 못하므로 True(설치는 계속).
    2020 이하는 LISP이 UTF-8 .lsp와 (open … "utf8")을 지원하지 않아 명령과 MCP가 동작하지 않는다."""
    code = "import win32com.client as w; print(w.GetActiveObject('AutoCAD.Application').Version)"
    r = subprocess.run([py, "-c", code], capture_output=True, text=True)
    ver = (r.stdout or "").strip()
    if r.returncode != 0 or not ver:
        return True
    try:
        major = int(ver.split(".")[0])
    except ValueError:
        return True
    if major < 24:
        say("[오류] AutoCAD 2021 이상이 필요합니다. 현재 실행 중인 AutoCAD는 2020 이하 버전입니다(버전 %s)." % ver)
        say("       2020 이하는 LISP의 UTF-8 지원이 없어 토목 명령과 MCP가 동작하지 않으므로 설치를 중단합니다.")
        return False
    return True


# ---------------------------------------------------------------- AutoCAD 명령 불러오기 파일
def write_loader(py):
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = py
    os.makedirs(DATA, exist_ok=True)
    text = """;;; bc_autocad.lsp — BC AutoCAD 스킬 명령 불러오기 (install.py가 이 PC에 맞춰 만든 파일)
;;; 플러그인 폴더(BC_AutoCAD.bundle)가 AutoCAD를 켤 때·도면을 열 때마다 불러온다. 급하면 APPLOAD로 직접.
(vl-load-com)
(setq *bc-root* "{root}")
(setq *bc-pyw* "{pyw}")
(setq bc:*files* (vl-directory-files (strcat *bc-root* "/skills/lisp") "*.lsp" 1))
(if (member "bc_core.lsp" bc:*files*)
  (progn
    (load (strcat *bc-root* "/skills/lisp/bc_core.lsp"))
    (foreach f (vl-sort (vl-remove "bc_core.lsp" bc:*files*) '<)
      (load (strcat *bc-root* "/skills/lisp/" f)))
    (princ "\\n[BC] AutoCAD 스킬 명령을 불러왔습니다. 목록: BCHELP"))
  (princ "\\n[BC] 스킬 폴더를 찾지 못했습니다 — install.py를 다시 실행하세요."))
(princ)
""".format(root=slash(ROOT), pyw=slash(pyw))
    for path in (LOADER, BUNDLE_LSP):
        backup(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(text)
    write_bundle_xml()
    say("AutoCAD 명령 불러오기 파일:", LOADER)
    say("AutoCAD 플러그인 폴더:", BUNDLE, "— AutoCAD를 다시 켜면 명령이 등록됩니다.")


def write_bundle_xml():
    """PackageContents.xml — AutoCAD 2021(R24.0) 이상, 도면마다(PerDocument) 켤 때 불러온다.
    2021부터 LISP이 UTF-8 .lsp(LISPSYS=1)와 (open … "utf8")을 지원한다. 2020 이하는 이 둘이 없어 대상에서 뺀다."""
    xml = """<?xml version="1.0" encoding="utf-8"?>
<ApplicationPackage SchemaVersion="1.0" AppVersion="0.3.0" ProductType="Application" Name="BC AutoCAD"
    Description="BC AutoCAD 토목 명령(BCFE·BCXY·BCMPL…, 목록 BCHELP)" Author="BC"
    ProductCode="{pc}" UpgradeCode="{uc}">
  <CompanyDetails Name="BC" />
  <RuntimeRequirements OS="Win64" Platform="AutoCAD*" SeriesMin="R24.0" />
  <Components Description="LISP">
    <RuntimeRequirements OS="Win64" Platform="AutoCAD*" SeriesMin="R24.0" />
    <ComponentEntry AppName="BCAutoCAD" Version="0.3.0" ModuleName="./Contents/bc_autocad.lsp"
        AppDescription="BC AutoCAD 스킬 명령 불러오기" LoadOnCommandInvocation="False" LoadOnAutoCADStartup="True"
        PerDocument="True" />
  </Components>
</ApplicationPackage>
""".format(pc=PRODUCT_CODE, uc=UPGRADE_CODE)
    path = os.path.join(BUNDLE, "PackageContents.xml")
    backup(path)
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(xml)


# ---------------------------------------------------------------- AutoCAD 신뢰 경로·시작하기 세트
def _norm(p):
    return p.replace("\\", "/").rstrip("/").lower()


def _active_product_key(app, key_root):
    """지금 켜진 AutoCAD 판(R24.2 등)의 제품 키. 판 키의 CurVer 값이 가리키는 것을 쓴다(여러 제품이 깔려도 하나)."""
    import winreg
    rel = "R" + ".".join(str(app.Version).split(" ")[0].split(".")[:2]).rstrip("abcdefghijklmnopqrstuvwxyz")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "%s\\%s" % (key_root, rel)) as k:
            return rel, winreg.QueryValueEx(k, "CurVer")[0]
    except OSError:
        return rel, None


def acad_setup():
    import win32com.client
    import winreg
    try:
        app = win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception:
        say("AutoCAD가 꺼져 있어 신뢰 경로는 건너뜁니다. AutoCAD를 켜고 --acad로 다시 실행하세요"
            "(안 하면 명령을 처음 불러올 때 '불러올까요' 보안 창이 뜰 수 있습니다).")
        return False
    try:
        doc = app.ActiveDocument
    except Exception:
        say("AutoCAD에 열린 도면이 없어(시작 탭) 신뢰 경로를 못 바꿉니다. 도면 하나를 열고 --acad로 다시 실행하세요.")
        return False
    want = [slash(DATA), slash(os.path.dirname(BUNDLE_LSP)), slash(os.path.join(ROOT, "skills", "lisp"))]
    cur = str(doc.GetVariable("TRUSTEDPATHS") or "")
    have = [p for p in cur.split(";") if p]
    add = [w for w in want if _norm(w) not in [_norm(h) for h in have]]
    if add:
        os.makedirs(BACKUP, exist_ok=True)
        with open(os.path.join(BACKUP, "TRUSTEDPATHS.txt"), "w", encoding="utf-8") as f:
            f.write(cur)
        say("TRUSTEDPATHS 이전 값:", repr(cur), "(백업: %s)" % os.path.join(BACKUP, "TRUSTEDPATHS.txt"))
        doc.SetVariable("TRUSTEDPATHS", ";".join(have + add))
        say("TRUSTEDPATHS 추가:", add)
    else:
        say("TRUSTEDPATHS 이미 있음")
    startup_remove_old(app)
    return True


def startup_remove_old(app):
    """예전 판이 시작하기 세트(현재 프로필의 Appload\\Startup 레지스트리)에 넣은 bc_autocad.lsp를 뺀다.
    시작하기 세트 방식은 레지스트리에 들어가 있어도 AutoCAD가 켜질 때 불러오지 않은 일이 있었다(실측 2026-10-29) —
    그래서 플러그인 폴더로 바꿨다. 둘 다 있으면 두 번 불러오므로 이 판의 등록만 지우고 다른 항목은 그대로 둔다."""
    import winreg
    key_root = r"Software\Autodesk\AutoCAD"
    prof = str(app.Preferences.Profiles.ActiveProfile)
    rel, prod = _active_product_key(app, key_root)
    dialogs = "%s\\%s\\%s\\Profiles\\%s\\Dialogs" % (key_root, rel, prod, prof) if prod else None
    try:
        if dialogs:
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, dialogs).Close()
    except OSError:
        dialogs = None
    if not dialogs:
        return
    found = dialogs + "\\Appload\\Startup"
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, found, 0, winreg.KEY_READ | winreg.KEY_WRITE)
    except OSError:
        return
    with k:
        try:
            n = int(winreg.QueryValueEx(k, "NumStartup")[0])
        except (OSError, ValueError):
            n = 0
        items = []
        for i in range(1, n + 1):
            try:
                items.append(winreg.QueryValueEx(k, "%dStartup" % i)[0])
            except OSError:
                pass
        keep = [x for x in items if os.path.normcase(x) != os.path.normcase(LOADER)]
        if len(keep) == len(items):
            return
        os.makedirs(BACKUP, exist_ok=True)
        with open(os.path.join(BACKUP, "Appload_Startup.json"), "w", encoding="utf-8") as f:
            json.dump({"key": "HKCU\\" + found, "NumStartup": n, "items": items}, f, ensure_ascii=False, indent=2)
        say("시작하기 세트 이전 목록:", items, "(백업: %s)" % os.path.join(BACKUP, "Appload_Startup.json"))
        for i in range(1, n + 1):
            try:
                winreg.DeleteValue(k, "%dStartup" % i)
            except OSError:
                pass
        for i, x in enumerate(keep, 1):
            winreg.SetValueEx(k, "%dStartup" % i, 0, winreg.REG_SZ, x)
        winreg.SetValueEx(k, "NumStartup", 0, winreg.REG_SZ, str(len(keep)))
        say("시작하기 세트에서 예전 등록을 뺐습니다:", LOADER)


# ---------------------------------------------------------------- 에이전트 등록
def server_cmd(py):
    return [py, "-X", "utf8", os.path.join(ROOT, "src", "server.py")]


def register_claude(py):
    exe = shutil.which("claude")
    if not exe:
        say("claude 명령을 찾지 못해 건너뜁니다.")
        return
    kw = dict(capture_output=True, text=True, encoding="utf-8", errors="replace")
    subprocess.run([exe, "mcp", "remove", NAME, "-s", "user"], **kw)
    r = subprocess.run([exe, "mcp", "add", NAME, "-s", "user", "--"] + server_cmd(py), **kw)
    say("Claude Code 등록:", (r.stdout or r.stderr).strip())


def antigravity_configs():
    """안티그래비티는 프로그램마다 MCP 설정 파일이 따로다.
    - CLI(agy): ~/.gemini/config/mcp_config.json (항상 등록)
    - 데스크톱 앱 Antigravity IDE: ~/.gemini/antigravity-ide/mcp_config.json (그 폴더가 있을 때)
    - 예전 데스크톱 앱 Antigravity: ~/.gemini/antigravity/mcp_config.json (그 폴더가 있을 때)"""
    g = os.path.join(os.path.expanduser("~"), ".gemini")
    out = [os.path.join(g, "config", "mcp_config.json")]
    for sub in ("antigravity-ide", "antigravity"):
        if os.path.isdir(os.path.join(g, sub)):
            out.append(os.path.join(g, sub, "mcp_config.json"))
    return out


def register_antigravity(py):
    cmd = server_cmd(py)
    for path in antigravity_configs():
        data = {"mcpServers": {}}
        if os.path.exists(path):
            backup(path)
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f) or {}
        if not isinstance(data.get("mcpServers"), dict):
            data["mcpServers"] = {}
        data["mcpServers"][NAME] = {"command": cmd[0], "args": cmd[1:]}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        say("안티그래비티 등록:", path)


def codex_home():
    return os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")


def _toml_str(s):
    # 리터럴 문자열(작은따옴표)은 백슬래시를 그대로 둔다. 경로에 작은따옴표가 있을 때만 기본 문자열로.
    if "'" not in s:
        return "'%s'" % s
    return json.dumps(s, ensure_ascii=False)


def register_codex(py):
    """OpenAI Codex(CLI·IDE 확장)의 config.toml에 [mcp_servers.bc-autocad]를 넣는다(이미 있으면 그 덩어리만 바꾼다).
    ChatGPT 앱(웹·데스크톱)은 이 PC에서 도는 MCP를 직접 붙이지 못해 Codex로 쓴다."""
    path = os.path.join(codex_home(), "config.toml")
    lines = []
    if os.path.exists(path):
        backup(path)
        with open(path, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    head = "[mcp_servers.%s]" % NAME
    out, skip = [], False
    for ln in lines:
        s = ln.strip()
        if s.startswith("["):
            skip = s == head or s.startswith("[mcp_servers.%s." % NAME)
        if not skip:
            out.append(ln)
    while out and not out[-1].strip():
        out.pop()
    cmd = server_cmd(py)
    block = [head,
             "command = %s" % _toml_str(cmd[0]),
             "args = [%s]" % ", ".join(_toml_str(x) for x in cmd[1:]),
             "startup_timeout_sec = 30",
             "tool_timeout_sec = 1800  # 다중 플롯(MPL)처럼 오래 걸리는 도구가 있다"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out + ([""] if out else []) + block) + "\n")
    say("Codex 등록:", path)


def main():
    # 파이프·리다이렉션으로 돌리면 콘솔 인코딩(CP949)이 한글 밖 글자(—, …)에서 멈춘다
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if sys.version_info < (3, 10):
        say("[중요] 파이썬 3.10 이상이 필요합니다(지금 %d.%d). python.org에서 새 버전을 설치한 뒤 다시 실행하세요."
            % sys.version_info[:2])
        return 1
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--python", help="MCP·창을 돌릴 python.exe (기본: 지금 이 파이썬)")
    ap.add_argument("--venv", action="store_true")
    ap.add_argument("--claude", action="store_true")
    ap.add_argument("--antigravity", action="store_true")
    ap.add_argument("--codex", action="store_true")
    ap.add_argument("--acad", action="store_true")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    py = a.python or sys.executable
    if a.venv or (a.all and not a.python):
        py = make_venv()
    if not check_python(py):
        return 1
    if not check_acad_version(py):
        return 1
    write_loader(py)
    if a.acad or a.all:
        acad_setup()
    if a.claude or (a.all and shutil.which("claude")):
        register_claude(py)
    if a.antigravity or (a.all and os.path.isdir(os.path.join(os.path.expanduser("~"), ".gemini"))):
        register_antigravity(py)
    if a.codex or (a.all and (shutil.which("codex") or os.path.isdir(codex_home()))):
        register_codex(py)
    say("끝. AutoCAD를 다시 켜면 명령이 등록됩니다(확인: BCHELP). 급하면 APPLOAD로 %s" % LOADER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
