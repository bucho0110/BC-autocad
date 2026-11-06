# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""새 버전 알림 — 깃허브에 올라온 버전 태그(vX.Y.Z)와 지금 버전을 비교한다. 알리기만 하고 설치는 하지 않는다.

- 하루에 한 번만 확인하고 결과를 설정 파일(UPDATE.txt)에 남긴다. 인터넷이 안 되거나 늦으면(3초) 조용히 넘어간다.
- BCHELP 창 위쪽 한 줄과 MCP guide 결과 첫 줄에 쓴다. BCHELP 창의 버튼으로 끄고 켠다(설정 '알림').
"""

import json
import re
import time
import urllib.request

from . import settings as S
from .ui import VERSION_NUM

CMD = "UPDATE"
DEFAULTS = {"알림": True, "확인시각": 0.0, "최신": ""}
TAGS_URL = "https://api.github.com/repos/bucho0110/BC-autocad/tags?per_page=100"
DAY = 24 * 3600.0
TIMEOUT = 3.0
_TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def _ver(s):
    m = _TAG.match(str(s).strip())
    return tuple(int(x) for x in m.groups()) if m else None


def enabled() -> bool:
    return bool(S.load(CMD, DEFAULTS)["알림"])


def set_enabled(on: bool) -> None:
    cfg = S.load(CMD, DEFAULTS)
    cfg["알림"] = bool(on)
    S.save(CMD, cfg)


def _fetch_latest() -> str:
    """깃허브 태그 중 가장 높은 버전(예 '0.7.0'). 읽지 못하면 ''."""
    req = urllib.request.Request(TAGS_URL, headers={"User-Agent": "BC-autocad", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        tags = json.loads(r.read().decode("utf-8"))
    vers = [v for v in (_ver(t.get("name", "")) for t in tags if isinstance(t, dict)) if v]
    return "%d.%d.%d" % max(vers) if vers else ""


def newer_version(now=None) -> str:
    """지금보다 새 버전이 있으면 그 번호, 없거나 알림을 껐거나 확인하지 못했으면 ''."""
    cfg = S.load(CMD, DEFAULTS)
    if not cfg["알림"]:
        return ""
    now = time.time() if now is None else now
    if now - float(cfg["확인시각"]) >= DAY:
        try:
            cfg["최신"] = _fetch_latest()
        except Exception:  # noqa: BLE001 — 인터넷이 안 되거나 깃허브가 답하지 않으면 알림만 건너뛴다(도구는 그대로)
            pass
        cfg["확인시각"] = now  # 실패해도 하루 동안 다시 묻지 않는다(오프라인 PC에서 매번 3초를 쓰지 않게)
        S.save(CMD, cfg)
    latest, cur = _ver(cfg["최신"]), _ver(VERSION_NUM)
    return cfg["최신"] if latest and cur and latest > cur else ""


def notice(now=None) -> str:
    """사람에게 보일 한 줄('' 이면 알릴 것 없음)."""
    v = newer_version(now)
    return "새 버전이 있습니다: BC.%s (현재 BC.%s)." % (v, VERSION_NUM) if v else ""  # 숫자 뒤 조사(이/가)를 피한다
