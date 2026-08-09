"""
❃ `{i}تفعيل حماية الحساب`
    بعد تفعيل الامر اي شخص سيحاول التسجيل/الدخول الى حسابك التليجرام الخاص بك مباشرة سيقوم سورس تيبثون بطرده من الحساب

❃ `{i}تعطيل حماية الحساب`
    لإيقاف الأمر أعلاه ويقوم بالسماح للدخول إلى حسابك

ملاحظة: بعد تفعيل الامر سيقوم بطرد الجلسات الجديدة فقط 

"""

import asyncio
from telethon.tl.functions.account import GetAuthorizationsRequest
from telethon import functions, events
from .. import Tepthon_cmd, JmdB, jmubot


session_hashes = []

@Tepthon_cmd(pattern="تفعيل حماية الحساب$")
async def save_on(e):
    if not JmdB.get_key("WORK"):
        global session_hashes
        chat_id = JmdB.get_config("LOG_CHAT")
        sessions = await e.client(GetAuthorizationsRequest())
        session_hashes = [str(session.hash) for session in sessions.authorizations]
        #message = "جلساتك المحفوظة:\n" + "\n".join(session_hashes)
        #await jmubot.send_message(chat_id, message)
        JmdB.set_key("WORK", True)
        await work_run()
        await e.eor("**⎆ تم بنجاح تفعيل حماية الحساب من تسجيل الدخول**")
    else:
        await e.eor("**⎆ نظام منع تسجيل الدخول إلى الحساب شغال بالأصل**")
        
       
@Tepthon_cmd(pattern="تعطيل حماية الحساب$")
async def save_of(e):
    if not JmdB.get_key("WORK"):
        await e.eor("**⎆ نظام منع تسجيل الدخول إلى الحساب غير شغال بالأصل**")
    else:
        JmdB.del_key("WORK")
        await e.eor("**⎆ تم تعطيل نظام منع تسجيل الدخول إلى الحساب**")


async def work_run():
    chat_id = JmdB.get_key("LOG_CHAT")
    while JmdB.get_key("WORK"):
        sessions = await jmubot(GetAuthorizationsRequest())
        all_hashes = [str(session.hash) for session in sessions.authorizations]

        for session in all_hashes:
            if session not in session_hashes:
                message = "**⚠️ نظام حماية الحساب اكتشف دخول جلسة جديدة تم طردها بنجاح**\n"# + session
                await jmubot.send_message(chat_id, message)
                await jmubot(functions.account.ResetAuthorizationRequest(hash=int(session)))
        await asyncio.sleep(10)
