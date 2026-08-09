import asyncio
import logging
from datetime import datetime

from telethon.tl import functions, types

from .. import JmdB, jmubot, Tepthon_cmd
from . import BOTLOG, BOTLOG_CHATID

LOGS = logging.getLogger(__name__)


class AFK:
    def __init__(self):
        self.USERAFK_ON = {}
        self.afk_time = None
        self.last_afk_message = {}
        self.afk_star = {}
        self.afk_end = {}
        self.reason = None
        self.msg_link = False
        self.afk_type = None
        self.media_afk = None
        self.afk_on = False


AFK_ = AFK()


def get_afk_time():
    if not AFK_.afk_star:
        return "0 ثانية"

    end = datetime.now().replace(microsecond=0)
    total = end - AFK_.afk_star
    seconds = int(total.total_seconds())

    d = seconds // (24 * 3600)
    seconds %= 24 * 3600

    h = seconds // 3600
    seconds %= 3600

    m = seconds // 60
    s = seconds % 60

    if d > 0:
        return f"{d} يوم {h} ساعة {m} دقيقة {s} ثانية"
    elif h > 0:
        return f"{h} ساعة {m} دقيقة {s} ثانية"
    elif m > 0:
        return f"{m} دقيقة {s} ثانية"

    return f"{s} ثانية"


# =========================
# إلغاء السليب عند إرسال رسالة
# =========================

@Tepthon_cmd(
    pattern="",
    outgoing=True,
    edited=False,
)
async def set_not_afk(event):
    if not AFK_.afk_on:
        return

    endtime = get_afk_time()
    current_message = event.message.message or ""

    # تجاهل رسائل تشغيل السليب نفسها
    if "سليب" in current_message or "#afk" in current_message:
        return

    if not AFK_.USERAFK_ON:
        return

    try:
        shite = await event.client.send_message(
            event.chat_id,
            f"**الان اعمل بشكل طبيعي\n"
            f"لقد كان امر السليب مفعل منذ {endtime}**",
        )

        AFK_.USERAFK_ON = {}
        AFK_.afk_time = None
        AFK_.afk_on = False
        AFK_.afk_type = None
        AFK_.reason = None
        AFK_.media_afk = None
        AFK_.msg_link = False

        await asyncio.sleep(5)

        try:
            await shite.delete()
        except Exception:
            pass

        if BOTLOG:
            await event.client.send_message(
                BOTLOG_CHATID,
                f"⌔∮ انتهاء امر السليب\n"
                f"⌔∮ تم تعطيله والرجوع للوضع الطبيعي\n"
                f"كان مفعلًا لمدة {endtime}",
            )

    except Exception as e:
        LOGS.error(f"خطأ في إلغاء السليب: {e}")


# =========================
# الرد على الأشخاص أثناء السليب
# =========================

@Tepthon_cmd(
    pattern="",
    incoming=True,
    func=lambda e: bool(e.mentioned or e.is_private),
    edited=False,
)
async def on_afk(event):
    if not AFK_.afk_on or not AFK_.USERAFK_ON:
        return

    sender = await event.get_sender()

    if not sender:
        return

    if getattr(sender, "bot", False):
        return

    current_message_text = (event.message.message or "").lower()

    if "مؤقت" in current_message_text or "#afk" in current_message_text:
        return False

    endtime = get_afk_time()

    msg = None

    # =========================
    # سليب ميديا
    # =========================

    if AFK_.afk_type == "media":
        if AFK_.reason:
            message_to_reply = (
                f"⪼ انا الان في حالة عدم الاتصال منذ\n"
                f"{endtime}\n"
                f"السبب : {AFK_.reason}"
            )
        else:
            message_to_reply = (
                f"⪼ انا الان في حالة عدم الاتصال منذ\n"
                f"{endtime}"
            )

        if event.chat_id:
            try:
                if AFK_.media_afk and AFK_.media_afk.media:
                    msg = await event.reply(
                        message_to_reply,
                        file=AFK_.media_afk.media,
                    )
                else:
                    msg = await event.reply(message_to_reply)
            except Exception as e:
                LOGS.error(f"خطأ في إرسال ميديا AFK: {e}")
                msg = await event.reply(message_to_reply)

    # =========================
    # سليب نصي
    # =========================

    elif AFK_.afk_type == "text":
        if AFK_.reason:
            message_to_reply = (
                f"⪼ انا الان في حالة عدم الاتصال منذ\n\n"
                f"{endtime}\n"
                f"السبب : {AFK_.reason}"
            )
        else:
            message_to_reply = (
                f"⪼ انا الان في حالة عدم الاتصال منذ\n\n"
                f"{endtime}"
            )

        if event.chat_id:
            msg = await event.reply(message_to_reply)

    # =========================
    # حذف الرد السابق في نفس المحادثة
    # =========================

    if msg is not None:
        try:
            if event.chat_id in AFK_.last_afk_message:
                old_msg = AFK_.last_afk_message[event.chat_id]

                if old_msg:
                    await old_msg.delete()

            AFK_.last_afk_message[event.chat_id] = msg

        except Exception as e:
            LOGS.info(f"تعذر حذف رسالة AFK القديمة: {e}")

    # الخاص لا يدخل إلى سجل المجموعات
    if event.is_private:
        return

    # =========================
    # سجل الرسالة في مجموعة اللوج
    # =========================

    try:
        hmm = await event.get_chat()

        if not hasattr(Config, "PM_LOGGER_GROUP_ID"):
            return

        if not Config.PM_LOGGER_GROUP_ID:
            return

        if Config.PM_LOGGER_GROUP_ID == -100:
            return

        full = None

        try:
            full = await event.client.get_entity(event.message.from_id)
        except Exception as e:
            LOGS.info(str(e))

        try:
            messaget = media_type(event)
        except Exception:
            messaget = None

        resalt = (
            f"<b>المجموعة :</b> "
            f"<code>{getattr(hmm, 'title', 'غير معروف')}</code>"
        )

        if full is not None:
            try:
                resalt += (
                    f"\n<b>المرسل :</b> "
                    f"{_format.htmlmentionuser(full.first_name, full.id)}"
                )
            except Exception:
                resalt += (
                    f"\n<b>المرسل :</b> "
                    f"<code>{full.id}</code>"
                )

        if messaget:
            resalt += (
                f"\n<b>نوع الرسالة :</b> "
                f"<code>{messaget}</code>"
            )
        else:
            resalt += (
                f"\n<b>الرسالة :</b> "
                f"{event.message.message or ''}"
            )

        # استخراج رقم المجموعة بشكل صحيح للرابط
        chat_id = str(event.chat_id)

        if chat_id.startswith("-100"):
            chat_id = chat_id[4:]

        resalt += (
            f"\n<b>رابط الرسالة :</b> "
            f"<a href='https://t.me/c/{chat_id}/{event.message.id}'>"
            f"الرابط</a>"
        )

        await event.client.send_message(
            Config.PM_LOGGER_GROUP_ID,
            resalt,
            parse_mode="html",
            link_preview=False,
        )

    except Exception as e:
        LOGS.error(f"خطأ في سجل AFK: {e}")


# =========================
# تشغيل السليب النصي
# الأمر: سليب
# =========================

@Tepthon_cmd(
    pattern="سليب(?:\\s|$)([\\s\\S]*)"
)
async def _(event):
    AFK_.USERAFK_ON = {}
   
