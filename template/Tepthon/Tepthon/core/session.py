import base64
import ipaddress
import struct
import sys
from telethon.sessions.string import _STRUCT_PREFORMAT, CURRENT_VERSION, StringSession
from logging import getLogger

LOGS = getLogger("Tepthon")
_PYRO_FORM = {351: ">B?256sI?", 356: ">B?256sQ?", 362: ">BI?256sQ?"}

# https://github.com/pyrogram/pyrogram/blob/master/docs/source/faq/what-are-the-ip-addresses-of-telegram-data-centers.rst


def _pyrogram_session(session):
    DC_IPV4 = {
        1: "149.154.175.53",
        2: "149.154.167.51",
        3: "149.154.175.100",
        4: "149.154.167.91",
        5: "91.108.56.130",
    }
    data_ = struct.unpack(
        _PYRO_FORM[len(session)],
        base64.urlsafe_b64decode(session + "=" * (-len(session) % 4)),
    )
    auth_id = 2 if len(session) in {351, 356} else 3
    dc_id, auth_key = data_[0], data_[auth_id]
    return StringSession(
        CURRENT_VERSION
        + base64.urlsafe_b64encode(
            struct.pack(
                _STRUCT_PREFORMAT.format(4),
                dc_id,
                ipaddress.ip_address(DC_IPV4[dc_id]).packed,
                443,
                auth_key,
            )
        ).decode("ascii")
    )


def both_session(session, logger=LOGS, _exit=True):
    if session:
        if session.startswith(CURRENT_VERSION):
            if len(session.strip()) != 353:
                logger.exception("✖️ خطأ: كود السيشن غير صحيح، يرجى التأكد من إدخاله بالشكل الصحيح.")
                sys.exit()
            return StringSession(session)

        elif len(session) in _PYRO_FORM:
            return _pyrogram_session(session)
        else:
            logger.exception("✖️ خطأ: كود السيشن غير صحيح، يرجى التأكد من إدخاله بالشكل الصحيح.")
            if _exit:
                sys.exit()
    logger.exception("⚠️ لم يتم العثور على كود سيشن. إلغاء العملية.")
    if _exit:
        exit()
