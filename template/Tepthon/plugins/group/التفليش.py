"""
❃ `{i}تفليش بالبوت`
  اذا كنت ادمن في بوت الحماية المضاف في المجموعة (لست مشرف بل وأنما عندك رتبة في بوت الحماية فقط) من خلال هذا الامر يمكنك حظر جميع الاعضاء بـ استخدام بوت الحماية

❃ `{i}ايقاف التفليش`
  لـ ايقاف عملية التفليش بالبوت 

"""
import asyncio
from telethon.errors import UserNotParticipantError
from telethon.tl.functions.channels import GetParticipantRequest
from .. import jmubot, Tepthon_cmd

spam_chats = []


@Tepthon_cmd(pattern="تفليش بالبوت$")
async def banavot(event):
    chat_id = event.chat_id
    try:
        await jmubot(GetParticipantRequest(event.chat_id, event.sender_id))
    except UserNotParticipantError:
        pass
    spam_chats.append(chat_id)
    async for usr in jmubot.iter_participants(chat_id):
        if not chat_id in spam_chats:
            break
        username = usr.username
        usrtxt = f"حظر @{username}"
        if str(username) == "None":
            idofuser = usr.id
            usrtxt = f"حظر {idofuser}"
        await jmubot.send_message(chat_id, usrtxt)
        await asyncio.sleep(0.5)
        await event.delete()
    try:
        spam_chats.remove(chat_id)
    except:
        pass


@Tepthon_cmd(pattern="ايقاف التفليش$")
async def unbanbot(event):
    if not event.chat_id in spam_chats:
        return await event.edit("**لا توجد عملية هنا لإيقافها**")
    else:
        try:
            spam_chats.remove(event.chat_id)
        except:
            pass
        return await event.edit("**- تم بنجاح إلغاء عملية التفليش**")
