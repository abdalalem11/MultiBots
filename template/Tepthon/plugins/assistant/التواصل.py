import os

from Tepthon import LOGS, tgbot, jmubot
from Tepthon.decorators.asstbot import tgbot_cmd
from telethon.errors.rpcerrorlist import UserNotParticipantError
from telethon.tl.custom import Button
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.types import Channel, Chat
from telethon.utils import get_display_name
from . import inline_mention

from database import JmdB
from database.core.settings import KeySettings

OWNER_ID = jmubot.me.id
FSUB = JmdB.get_key("PMBOT_FSUB")
CACHE = {}
blm = KeySettings("BLACKLIST_CHATS", cast=list)


def get_who(msg_id):
    val = JmdB.get_key("BOTCHAT") or {}
    return val.get(msg_id)


@tgbot_cmd(
    incoming=True,
    func=lambda e: e.is_private and not blm.contains(e.sender_id),
)
async def on_new_msg(event):
    who = event.sender_id
    if event.text.startswith("/") or who == OWNER_ID:
        return
    if FSUB:
        MSG = ""
        BTTS = []
        for chat in FSUB:
            try:
                await event.client.get_permissions(chat, event.sender_id)
            except UserNotParticipantError:
                if not MSG:
                    MSG += "**يجب عليك الانضمام إلى قناة البوت للتواصل مع مالك البوت**\n\n"
                try:
                    TAHC_ = await event.client.get_entity(chat)
                    if hasattr(TAHC_, "username") and TAHC_.username:
                        uri = f"t.me/{TAHC_.username}"
                    elif CACHE.get(chat):
                        uri = CACHE[chat]
                    else:
                        if isinstance(TAHC_, Channel):
                            FUGB = await event.client(GetFullChannelRequest(chat))
                        elif isinstance(TAHC_, Chat):
                            FUGB = await event.client(GetFullChatRequest(chat))
                        else:
                            return
                        if FUGB.full_chat.exported_invite:
                            CACHE[chat] = FUGB.full_chat.exported_invite.link
                            uri = CACHE[chat]
                    BTTS.append(Button.url(get_display_name(TAHC_), uri))
                except Exception as er:
                    LOGS.exception(
                        f"حدث خطأ أثنـاء الاشتراك الإجبـاري للبوت المساعد\n {chat} \n{er}")
        if MSG and BTTS:
            return await event.reply(MSG, buttons=BTTS)
    xx = await event.forward_to(OWNER_ID)
    if event.fwd_from:
        await xx.reply(f"**◙ توجيه من المستخدم** {inline_mention(event.sender)} [`{event.sender_id}`]")
    val = JmdB.get_key("BOTCHAT") or {}
    val[xx.id] = who
    JmdB.set_key("BOTCHAT", val)



@tgbot_cmd(
    from_users=[OWNER_ID],
    incoming=True,
    func=lambda e: e.is_private and e.is_reply,
)
async def on_out_mssg(event):
    x = event.reply_to_msg_id
    to_user = get_who(x)
    if event.text.startswith("كشف"):
        try:
            k = await tgbot.get_entity(to_user)
            photu = await event.client.download_profile_photo(k.id)
            await event.reply(
                f"◙ **الاسم :** {get_display_name(k)}\n⎆ **الأيدي :** `{k.id}`\n⎆ **رابط الحساب :** {inline_mention(k)}",
                file=photu,
            )
            if photu:
                os.remove(photu)
            return
        except BaseException as er:
            return await event.reply(f"⎆ **حدث خطأ ما : **{str(er)}")
    elif event.text.startswith("/"):
        return
    if to_user:
        await tgbot.send_message(to_user, event.message)



@tgbot_cmd(
    pattern="حظر",
    from_users=[OWNER_ID],
    func=lambda x: x.is_private,
)
async def banhammer(event):
    if not event.is_reply:
        return await event.reply("**⎆ يجب عليك الرد على المستخدم الذي تريد حظره**.")
    target = get_who(event.reply_to_msg_id)
    if blm.contains(target):
        return await event.reply("**⎆ المستخدم موجود في قائمة الحظر بالأصل**")

    blm.add(target)
    await event.reply(f"**⎆ تم بنجاح حظر المستخدم : {target}**")
    await tgbot.send_message(target, "**⎆ تم حظرك من استخدام البوت أي رسالة سترسلها لا تصل إلى مالك البوت**")


@tgbot_cmd(
    pattern="الغاء حظر",
    from_users=[OWNER_ID],
    func=lambda x: x.is_private,
)
async def unbanhammer(event):
    if not event.is_reply:
        return await event.reply("**⎆ يجب عليك الرد على المستخدم الذي تريد الغاء حظره**.")
    target = get_who(event.reply_to_msg_id)
    if not blm.contains(target):
        return await event.reply("**⎆ هذا المستخدم غير محظور اصلا**")

    blm.remove(target)
    await event.reply(f"**⎆ تم بنجاح الغاء حظر المستخدم : {target}**")
    await event.client.send_message(target, "**⎆ تم الغاء حظرك بنجاح يمكنك التواصل مع البوت الان**")

