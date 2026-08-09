"""

❃ `{i}اسم وقتي`
   لـ بدأ وضع الساعة مع اسمك حسابك

❃ `{i}انهاء اسم وقتي`
   لـ تعطيل ظهور الساعة مع الاسم الخاص بك

❃ `{i}بايو وقتي`
   لـ بدأ وضع الساعة مع النبذة/البايو الخاص بك

❃ `{i}انهاء اسم وقتي`
   لـ تعطيل ظهور الوقت مع النبذة الخاصة بك
"""

import asyncio
import random
import time

from telethon.tl.functions.account import UpdateProfileRequest

from .. import JmdB, jmubot, Tepthon_cmd

USERBIO = JmdB.get_key("MYBIO") or "اللهم صلِّ على سيدنا وعلى آله وصحبه أجمعين"
NAME = JmdB.get_key("NAME")


@Tepthon_cmd(pattern="اسم وقتي$")
async def autoname(event):
    if JmdB.get_key("AUTONAME"):
        return await event.eor("**⎆ تم تفعيـل الاسم الوقتـي مسبقًا .. 🔔**")
    JmdB.set_key("AUTONAME", "True")
    await event.eor("**⎆ تم تشغيل الاسم الوقتـي بنجاح .. ✅**", time=6)
    while JmdB.get_key("AUTONAME"):
        HM = time.strftime("%I:%M")
        name = f"{HM}"
        await event.client(UpdateProfileRequest(first_name=name))
        await asyncio.sleep(60)


@Tepthon_cmd(pattern="بايو وقتي$")
async def autobio(event):
    if JmdB.get_key("AUTOBIO"):
        return await event.eor("**⎆ تم تشغيل البايو الوقتـي مسبقّا**")
    JmdB.set_key("AUTOBIO", "True")
    await event.eor("**⎆ تم تشغيـل الاسم الوقتي بنجـاح .. ✅**", time=6)
    BIOS = [
        "الحمد لله رب العالمين",
        "اللهم صلِّ وسلم وبارك على سيدنا محمد وعلى آله وصحبه أجمعين ♥️"
        "أستغفر الله العلي العظيم "
    ]
    while JmdB.get_key("AUTOBIO"):
        BIOMSG = JmdB.get_key("MYBIO") or random.choice(BIOS)
        HM = time.strftime("%I:%M")
        name = f"{BIOMSG} | {HM}"
        await event.client(
            UpdateProfileRequest(
                about=name,
            )
        )
        await asyncio.sleep(60)



@Tepthon_cmd(pattern=r"انهاء ([\s\S]*)")
async def _(event):
    input_str = event.pattern_match.group(1)
    if (
        input_str == "اسم وقتي"
        or input_str == "اسم الوقتي"
        or input_str == "الاسم الوقتي"
        or input_str == "الاسم وقتي"
    ):
        if JmdB.get_key("AUTONAME"):
            JmdB.del_key("AUTONAME")
            await event.client(UpdateProfileRequest(first_name=NAME))
            return await event.eor("**⎆ تم إيقـاف الاسم الوقتـي**")
        return await event.eor("**هممممم، الاسم الوقتي غير مفعـل لديك أصلًا**")
    if input_str == "بايو وقتي" or input_str == "البايو الوقتي":
        if JmdB.get_key("AUTOBIO"):
            JmdB.del_key("AUTOBIO")
            await event.client(UpdateProfileRequest(about=USERBIO))
            return await event.eor("**⎆ تم إيقاف البايو الوقتـي**")
        return await event.eor("**⎆ البايو الوقتـي غير مفعل لديك أصلًا**")
