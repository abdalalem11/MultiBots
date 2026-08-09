"""
❃ `{i}للكروبات` <رسالتك>
    لـ نشر/إذاعة الرسالة في جميع المجموعات التي لديك

❃ `{i}للخاص` <رسالتك>
    لـ نشر/إذاعة الرسالة في جميع الدردشات في الخاص التي لديك

تنبيه: يمكنك الرد على صورة أو فيديو أو متحركة كذلك لعمل إذاعة لها بالرد عليها بالأمر 

⚠️ انتبـه قد يؤدي استخدام هذا الأمر بكثرة إلى تقييد حسابك من مراسلة المستخدمين إذا قاموا بالتبليغ عنك.. 
"""

from .. import Tepthon_cmd, DEV_CHAT, DEVLIST


@Tepthon_cmd(pattern="للكروبات(?: |$)(.*)")
async def gcast(event):
    txt = event.pattern_match.group(1)
    if txt:
        msg = txt
    elif event.is_reply:
        msg = await event.get_reply_message()
    else:
        await event.eor("**⎆ يجب الرد على رسالة أو وسائط ...**")
        return
    mirz = await event.eor("⎆ يتـم الإذاعة في الخـاص ......")
    er = 0
    done = 0
    async for x in event.client.iter_dialogs():
        if x.is_group:
            chat = x.id
            try:
                if chat not in DEV_CHAT:
                    await event.client.send_message(chat, msg)
                    done += 1
            except BaseException:
                er += 1
    await mirz.edit(f"**⌔∮  تم بنجاح الإذاعة إلى ** `{done}` **من الدردشات، خطأ في الإرسال إلـى ** `{er}` **من الدردشات**")


@Tepthon_cmd(pattern="للخاص(?: |$)(.*)")
async def gucast(event):
    txt = event.pattern_match.group(1)
    if txt:
        msg = txt
    elif event.is_reply:
        msg = await event.get_reply_message()
    else:
        await event.eor("**◙ يجب الرد على الرسالة أو وسائط أو النص مع الأمر**")
        return
    mirz = await event.eor("⎆ يتم الإذاعة في الخاص انتظـر..")
    er = 0
    done = 0
    async for x in event.client.iter_dialogs():
        if x.is_user and not x.entity.bot:
            chat = x.id
            try:
                if chat not in DEVLIST:
                    await event.client.send_message(chat, msg)
                    done += 1
            except BaseException:
                er += 1
    await mirz.edit(f"**⌔∮  تم بنجاح الإذاعة إلى ** `{done}` **من الدردشات، خطأ في الإرسال إلـى ** `{er}` **من الدردشات**")
