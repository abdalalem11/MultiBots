from . import *

import contextlib
import os
import sys
import time
import asyncio

from .core.helper import time_formatter  # , bash
from .load_plug import load
from telethon.errors import SessionRevokedError
from .utils import (
    join_dev,
    main_process,
)


# =========================
# Render Web Server
# =========================

async def start_render_server():
    """
    Web Server بسيط لـ Render.
    لا يغيّر طريقة عمل Tepthon،
    فقط يفتح PORT حتى لا تقوم Render بإيقاف الخدمة.
    """

    port = int(os.environ.get("PORT", "10000"))

    async def handle_client(reader, writer):
        try:
            # قراءة طلب HTTP
            await reader.read(1024)

            response_body = b"Tepthon OK"

            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/plain; charset=utf-8\r\n"
                + f"Content-Length: {len(response_body)}\r\n".encode()
                + b"Connection: close\r\n"
                b"\r\n"
                + response_body
            )

            writer.write(response)
            await writer.drain()

        except Exception:
            pass

        finally:
            writer.close()

            with contextlib.suppress(Exception):
                await writer.wait_closed()

    server = await asyncio.start_server(
        handle_client,
        host="0.0.0.0",
        port=port,
    )

    LOGS.info(
        f"Render Web Server يعمل على 0.0.0.0:{port}"
    )

    return server


# =========================
# Telegram Initialization
# =========================

jmubot.me.phone = None


if not jmubot.me.bot:
    jmdB.set_key("OWNER_ID", jmubot.me.id)
    jmdB.set_key("NAME", jmubot.full_name)


LOGS.info("جاري تثبيت النسرالاسود...")


try:
    LOGS.info("- يتم إعـداد الإعدادات .......")

    jmubot.loop.run_until_complete(
        main_process()
    )

    LOGS.info(
        "تم إعداد إعدادات النسر الاسود ✅"
    )

except Exception as meo:
    LOGS.error(f"- {meo}")
    sys.exit()


# =========================
# Developer Join Task
# =========================

jmubot.loop.create_task(
    join_dev()
)


# =========================
# Load Plugins
# =========================

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


jmubot.run_in_loop(
    load_plugins()
)


# =========================
# Startup Message
# =========================

LOGS.info(
    f"⏳ تم استغراق "
    f"{time_formatter((time.time() - start_time) * 1000)} "
    f"ميللي ثانية لبدء تشغيل سورس النسر الاسود."
)


LOGS.info(
    """
    ╔══════════════════════════════════════════╗
    ║       ✅ تم تنصيب وتشغيل سورس النسر الاسود بنجاح             ║
    ║       تابع آخر التحديثات من خلال قناة @SSSTlF            ║
    ╚══════════════════════════════════════════╝
    """
)


# =========================
# Start Render Server
# =========================

render_server = None

try:
    if os.environ.get("PORT"):
        render_server = jmubot.loop.run_until_complete(
            start_render_server()
        )

        LOGS.info(
            "✅ تم فتح Port الخاص بـ Render بنجاح"
        )

except Exception as render_error:
    LOGS.error(
        f"❌ فشل تشغيل Render Web Server: {render_error}"
    )


# =========================
# Start Assistant Bot
# =========================

try:
    asst.run()

    LOGS.info(
        "تم بنجاح تشغيل البوت المساعد من @SSSTlF"
    )

except SessionRevokedError:
    LOGS.info(
        f"جلسة البوت المساعد "
        f"[@{asst.me.username}] فشلت "
        f"لكن سيتم تشغيل سورس الحساب فقط"
    )

    jmubot.run()
