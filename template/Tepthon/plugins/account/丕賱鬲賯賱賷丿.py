"""
❃ `{i}تقليد` <بالرد على الشخص/يوزره>
    لـ إعادة إرسال أي شيء سيرسله المستخدم في المحادثة وتقليده

❃ `{i}حذف_تقليد` <بالرد على الشخص/يوزره>
    لـ إعــادة الحساب إلى وضعه الطبيعي
    
❃ `{i}قائمة التقليد`
    لـ عرض قائمة المستخدمين الذي قمت بتقليدهم
"""

from telethon.utils import get_display_name
from telethon.tl import types
from telethon import events
from .. import inline_mention, JmdB, Tepthon_cmd, jmubot, LOGS


@Tepthon_cmd(pattern="تقليد( (.*)|$)")
async def echo(e):
    r = await e.get_reply_message()
    if r:
        user = r.sender_id
    else:
        try:
            user = e.text.split()[1]
            if user.startswith("@"):
                ok = await e.client.get_entity(user)
                user = ok.id
            else:
                user = int(user)
        except BaseException:
            return await e.eor("⎆ يجب عليك الرد على المستخدم أولًا.", time=5)
    if check_echo(e.chat_id, user):
        return await e.eor("⎆ أمر التقليد شغال بالأصل على هذا المستخدم.", time=5)
    add_echo(e.chat_id, user)
    ok = await e.client.get_entity(user)
    user = inline_mention(ok)
    await e.eor(f"**⎆ تم بنجاح تفعيل امر التقليد على {user}**")


@Tepthon_cmd(pattern="حذف_تقليد( (.*)|$)")
async def rmecho(e):
    r = await e.get_reply_message()
    if r:
        user = r.sender_id
    else:
        try:
            user = e.text.split()[1]
            if user.startswith("@"):
                ok = await e.client.get_entity(user)
                user = ok.id
            else:
                user = int(user)
        except BaseException:
            return await e.eor("⎆ يجب عليك الرد على المستخدم أولًا..", time=5)
    if check_echo(e.chat_id, user):
        rem_echo(e.chat_id, user)
        ok = await e.client.get_entity(user)
        user = f"[{get_display_name(ok)}](tg://user?id={ok.id})"
        return await e.eor(f"❃ تم تعطيل أمر التقليد على {user}.")
    await e.eor("⎆ أمر التقليد غير شغال على هذا المستخدم.")


@Tepthon_cmd(pattern="قائمة التقليد$")
async def lst_echo(e):
    if k := list_echo(e.chat_id):
        user = "**⎆ قائمة المستخدمين الذين تم تفعيل التقليد عليهم:**\n\n"
        for x in k:
            ok = await e.client.get_entity(int(x))
            kk = f"[{get_display_name(ok)}](tg://user?id={ok.id})"
            user += f"❃ {kk}" + "\n"
        await e.eor(user)
    else:
        await e.eor("⎆ لا يوجد أي مستخدم في هذه القائمة", time=5)

@jmubot.on(events.NewMessage(incoming=True))
async def ec_process(e):
    sender = await e.get_sender()
    if not isinstance(sender, types.User) or sender.bot:
        return
    if check_echo(e.chat_id, e.sender_id):
        try:
            await e.respond(e.message)
        except Exception as er:
            LOGS.exception(er)

def get_stuff():
    return JmdB.get_key("ECHO") or {}


def add_echo(chat, user):
    x = get_stuff()
    if k := x.get(int(chat)):
        if user not in k:
            k.append(int(user))
        x.update({int(chat): k})
    else:
        x.update({int(chat): [int(user)]})
    return JmdB.set_key("ECHO", x)


def rem_echo(chat, user):
    x = get_stuff()
    if k := x.get(int(chat)):
        if user in k:
            k.remove(int(user))
        x.update({int(chat): k})
    return JmdB.set_key("ECHO", x)


def check_echo(chat, user):
    x = get_stuff()
    if (k := x.get(int(chat))) and int(user) in k:
        return True


def list_echo(chat):
    x = get_stuff()
    return x.get(int(chat))
