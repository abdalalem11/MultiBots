"""
❃  `{i}كتم` <وضع ايديه/ بالرد عليه>
    لـ كتم المستخدم في المحادثة وحذف رسائله التي سيرسلها.

❃  `{i}الغاء كتم` <وضع ايديه/ بالرد عليه>
    لـ الغاء كتم المستخدم وعدم حذف رسائله والسماح له بالارسال

"""
from telethon import events
from telethon.utils import get_display_name

from .. import tgbot, JmdB, jmubot, Tepthon_cmd


@jmubot.on(events.NewMessage(incoming=True))
async def watcher(event):
    if is_muted(event.chat_id, event.sender_id):
        await event.delete()
    if event.via_bot and is_muted(event.chat_id, event.via_bot_id):
        await event.delete()


@Tepthon_cmd(pattern="كتم( (.*)|$)")
async def start_mute(event):
    moh = await event.eor("⎆ جاري كتم المستخدم انتظر ثوانٍ ...")
    if input_ := event.pattern_match.group(1).strip():
        try:
            userid = await event.client.parse_id(input_)
        except Exception as x:
            return await moh.edit(str(x))
    elif event.reply_to_msg_id:
        reply = await event.get_reply_message()
        userid = reply.sender_id
        if reply.out or userid in [jmubot.me.id, tgbot.me.id]:
            return await moh.eor("⎆ لا يمكنـك كتم نفسك أو كتم البوت المسـاعد الخاص بك")
    elif event.is_private:
        userid = event.chat_id
    else:
        return await moh.eor("**⎆ يجب عليك الرد على المستخدم أو وضع أيديـه مع الأمر**", time=5)
    chat = await event.get_chat()
    if "admin_rights" in vars(chat) and vars(chat)["admin_rights"] is not None:
        if not chat.admin_rights.delete_messages:
            return await moh.eor("**⎆ أنت لا تمتلك الصلاحيات الكافية لكتم المستخدم هنا**", time=5)
    elif "creator" not in vars(chat) and not event.is_private:
        return await moh.eor("**⎆ أنت لا تمتلك الصلاحيات الكافية لكتم المستخدم هنا**", time=5)
    if is_muted(event.chat_id, userid):
        return await moh.eor("**⎆ هذا المستخدم مكتوم في هذه الدردشة أصلا**", time=5)
    mute(event.chat_id, userid)
    await moh.eor("**⎆ تم بنجاح كتم المستـخدم في الدردشـة**", time=3)


@Tepthon_cmd(pattern="الغاء كتم( (.*)|$)")
async def end_mute(event):
    moh = await event.eor("⎆ جـاري إلغاء كتم المستخدم انتظر ثوانٍ")
    if input_ := event.pattern_match.group(1).strip():
        try:
            userid = await event.client.parse_id(input_)
        except Exception as x:
            return await moh.edit(str(x))
    elif event.reply_to_msg_id:
        userid = (await event.get_reply_message()).sender_id
    elif event.is_private:
        userid = event.chat_id
    else:
        return await moh.eor("**⎆ يجب عليك الرد على المستخدم أو وضع ايديه مع الأمر**", time=5)
    if not is_muted(event.chat_id, userid):
        return await moh.eor("**⎆ هذا المستخدم غير مكتوم في هذه الدردشة أصلًا**", time=3)
    unmute(event.chat_id, userid)
    await moh.eor("**⎆ تم بنجاح الغاء كتم المستخدم في الدردشة**", time=3)


def get_muted():
    return JmdB.get_key("MUTE") or {}


def mute(chat, id):
    ok = get_muted()
    if ok.get(chat):
        if id not in ok[chat]:
            ok[chat].append(id)
    else:
        ok.update({chat: [id]})
    return JmdB.set_key("MUTE", ok)


def unmute(chat, id):
    ok = get_muted()
    if ok.get(chat) and id in ok[chat]:
        ok[chat].remove(id)
    return JmdB.set_key("MUTE", ok)


def is_muted(chat, id):
    ok = get_muted()
    return bool(ok.get(chat) and id in ok[chat])
