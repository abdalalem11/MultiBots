"""
أوامــر التــكرار:
❃ `{i}سبام` <عدد الرسائل> <رسالتك>
  `{i}سبام` <عدد الرسائل> <بالرد على رسالة
    لـ تكرار إرسال الرسالة في الدردشة المستخدم بها الأمر أكثر رقم هو 99

❃ `{i}مكرر` <الوقت بين الإرسال> <عدد الإرسال> <الرسالة>
    لـ تكرار إرسال الرسالة بعدد معين في الدردشة لكن بين إرسال رسالة واخرى وقت معين جرب ارسل   `. مكرر 2 5 مرحبًا`

❃ `{i}فصخ`<جملة>
   لـ تفصيخ الجملة وجعلها أمام المستخدم تكتب بشكل حرف حرف
   
❃ `{i}ايقاف مكرر`
   لـ إيقـاف امر مكرر/مؤقت في الدردشة 

   ⚠️ ملاحظة مهمة: قد يرى التليجرام أوامر السبام/التكرار مخالفة لسياسته و قد يؤدي استخدامها الى حظر أو حذف حسابك فأنت المسوؤل الوحيد عن ما سيحصل لحسابك لان في سياسة التليجرام يمنع عمل رسائل مكررة و سبام 🚨🚨🚨
"""

import asyncio

from .. import HNDLR, eod, Tepthon_cmd, JmdB

@Tepthon_cmd(pattern="فصخ ([\s\S]*)")
async def typewriter(typew):
    message = typew.pattern_match.group(1)
    sleep_time = 0.2
    typing_symbol = "|"
    old_text = ""
    typew = await typew.eor(typing_symbol)
    await asyncio.sleep(sleep_time)
    for character in message:
        old_text = old_text + "" + character
        typing_text = old_text + "" + typing_symbol
        await typew.eor(typing_text)
        await asyncio.sleep(sleep_time)
        await typew.eor(old_text)
        await asyncio.sleep(sleep_time)



@Tepthon_cmd(pattern="سبام")
async def spamnormal(e):
    message = e.text
    if e.reply_to:
        if not len(message.split()) >= 2:
            return await eod(e, "**⎆ يجب عليك استخدام الأمر بشكل صحيح**")
        spam_message = await e.get_reply_message()
    else:
        if not len(message.split()) >= 3:
            return await eod(e, "**⎆ يجب عليك وضع رسالة مع الأمر أو الرد على الرسالة بالأمر**")
        spam_message = message.split(maxsplit=2)[2]
    counter = message.split()[1]
    try:
        counter = int(counter)
        if counter >= 100:
            return await eod(e, "**⎆ لا يمكن السبام أكثر من 99 رسالة**")
    except BaseException:
        return await eod(e, "**⎆ يجب عليك استخدام الأمر بشكل صحيح**")
    await e.try_delete()
    await asyncio.wait([asyncio.create_task(e.respond(spam_message)) for i in range(counter)])


@Tepthon_cmd(pattern="(مكرر|نشر)")
async def spam_with_delay(e):
    try:
        args = e.text.split(" ", 3)
        delay = float(args[1])
        count = int(args[2])
        msg = str(args[3])
    except BaseException:
        return await e.edit("**⎆ الاستخدام :** `{HNDLR}سبام_مؤقت` <الوقت بين الإرسال> <عدد الإرسال> <الرسالة>\n\n❃ مثال: `.سبام_مؤقت 1.5 5 مرحبًا`")
    
    JmdB.set_key(f"spam_{e.chat_id}", True)
    await e.try_delete()
    
    for i in range(count):
        if not JmdB.get_key(f"spam_{e.chat_id}"):
            return
        await e.respond(msg)
        await asyncio.sleep(delay)
    JmdB.del_key(f"spam_{e.chat_id}")


@Tepthon_cmd(pattern="ايقاف (مكرر|مؤقت)")
async def stop_spam(e):
    if JmdB.get_key(f"spam_{e.chat_id}"):
        JmdB.del_key(f"spam_{e.chat_id}")
        await e.respond("**⎆ تم إيقاف التكرار الوقتي بنجاح!**")
    else:
        await e.respond("**⎆أمر المكرر ليس قيد التنفيذ حاليًّا.**")
