# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""명령별 설정 파일. LISP 명령과 파이썬 창이 같은 파일을 읽고 쓴다.

형식: %LOCALAPPDATA%/bc-autocad/settings/<명령>.txt, UTF-8, 한 줄에 `키=값`.
LISP 쪽은 skills/lisp/bc_core.lsp의 bc:cfg-load가 같은 파일을 읽는다.
"""

import os

from .paths import SETTINGS


def path(cmd: str) -> str:
    return os.path.join(SETTINGS, cmd.upper() + ".txt")


def load(cmd: str, defaults: dict) -> dict:
    """기본값 위에 저장된 값을 얹는다. 형식은 기본값의 형식을 따른다."""
    out = dict(defaults)
    p = path(cmd)
    if not os.path.exists(p):
        return out
    with open(p, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k not in defaults:
                out[k] = v
                continue
            d = defaults[k]
            try:
                if isinstance(d, bool):
                    out[k] = v.strip() in ("1", "T", "true", "True")
                elif isinstance(d, int):
                    out[k] = int(float(v))
                elif isinstance(d, float):
                    out[k] = float(v)
                else:
                    out[k] = v
            except ValueError:
                pass
    return out


def short_path() -> str:
    """BC 없는 짧은 이름(FE…)을 켠 명령 목록. 한 줄에 하나. LISP는 bc_zz_alias.lsp의 bc:short-read가 읽는다."""
    return os.path.join(SETTINGS, "shortnames.txt")


def load_short() -> list:
    p = short_path()
    if not os.path.exists(p):
        return []
    with open(p, "r", encoding="utf-8-sig") as f:
        return [s for s in (ln.strip().upper() for ln in f) if s]


def save_short(names) -> str:
    p = short_path()
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        for n in names:
            f.write(n + "\n")
    return p


def save(cmd: str, values: dict) -> str:
    p = path(cmd)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        for k, v in values.items():
            if isinstance(v, bool):
                v = "1" if v else "0"
            f.write("%s=%s\n" % (k, str(v).replace("\n", " ")))
    return p
