# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""QCL 선 길이 바로 표기 — CL 설정 그대로 창 없이 바로 객체를 골라 길이를 쓴다(설정은 CL 창에서)."""

from skills.common import acad as A
from skills.common import settings as S
from skills.windows import cl

CMD = "QCL"
FIELDS = cl.FIELDS
DEFAULTS = cl.DEFAULTS


def main():
    a = A.Acad()
    try:
        a.activate()
        cl.pick_and_write(a, S.load(cl.CMD, cl.DEFAULTS))
    except Exception:  # noqa: BLE001 — 창이 없으니 명령줄 안내만(설정 창은 CL)
        import logging
        logging.exception("QCL")
