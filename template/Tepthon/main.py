from . import *

import sys
import time

from telethon.errors import SessionRevokedError

from .core.helper import time_formatter
from .load_plug import load
from .utils import join_dev, main_process


# منع حفظ رقم الهاتف في بيانات الجلسة
jmubot.me.phone = None


# حفظ بيانات المالك
if not jmubot.me.bot:
    jmdB.set_key("OWNER_ID", jmubot.me.id)
    jmdB.set_key("NAME", jmubot.full_name)


LOGS.info("جاري تشغيل تيبثون...")


# إعداد السورس
try:
    LOGS.info("- يتم إعداد الإعدادات .......")

    jmubot.loop.run_until_complete(main_process())

    LOGS.info("تم إعداد إعدادات تيبثون ✅")

except Exception as error:
    LOGS.error(f"فشل إعداد تيبثون: {error}")
    sys.exit(1)


# تشغيل مهام البداية
jmubot.loop.create_task(join_dev())


# تحميل الإضافات
async def load_plugins():
    load(
        path=[
            "plugins/basic",
            "plugins/assistant",
            "plugins/account",
            "plugins/fun",
            "plugins/group",
        ]
    )


jmubot.run_in_loop(load_plugins())


# رسالة نجاح التشغيل
LOGS.info(
    f"⏳ تم استغراق "
    f"{time_formatter((time.time() - start_time) * 1000)} "
    f"ميللي ثانية لبدء تشغيل سورس تيبثون."
)


LOGS.info(
    """
╔══════════════════════════════════════════╗
║   ✅ تم تشغيل سورس تيبثون بنجاح          ║
║   تابع آخر التحديثات من خلال قناة @SSSTlF ║
╚══════════════════════════════════════════╝
"""
)


# تشغيل البوت المساعد
try:
    asst.run()

    LOGS.info(
        "تم بنجاح تشغيل البوت المساعد من @SSSTlF"
    )

except SessionRevokedError:
    try:
        username = asst.me.username or "Unknown"
    except Exception:
        username = "Unknown"

    LOGS.info(
        f"جلسة البوت المساعد [@{username}] فشلت، "
        "لكن سيتم تشغيل سورس الحساب فقط."
    )

    jmubot.run()
