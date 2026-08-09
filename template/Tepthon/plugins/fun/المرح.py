"""
**❃ جميع هذه الأوامر تستخدم بالرد على الشخص عدا أمر كت**

❃ `{i}رفع مطي`
❃ `{i}رفع كلب`
❃ `{i}رفع حيوان`
❃ `{i}رفع زاحف`
❃ `{i}رفع مرتي`
❃ `{i}رفع زوجي`
❃ `{i}رفع تاج`
❃ `{i}رفع بكلبي`
❃ `{i}رفع بزون`
❃ `{i}رفع قرد`

❃ `{i}نسبة الحب`
❃ `{i}نسبة الانوثة`
❃ `{i}نسبة الرجولة`
❃ `{i}نسبة الغباء`
❃ `{i}نسبة المثلية`

❃ `{i}كت`
❃ `{i}اوصف`
❃ `{i}هينه`
❃ `{i}نزوج`
❃ `{i}طلاك`"""

import random

from Tepthon.helper import get_uinfo
from resources.fun import *

from .. import *


@Tepthon_cmd(pattern="رفع بكلبي(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    if custom:
        return await eor(mention, f"[{custom}](tg://user?id={user.id})")
    tag = user.first_name.replace("\u2060", "") if user.first_name else user.username
    await eor(
        mention, f"- المستخدم [{tag}](tg://user?id={user.id}) \n- تـم رفعـه بڪلبك 🖤 "
    )


@Tepthon_cmd(pattern="رفع زوجي(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    if custom:
        return await eor(mention, f"[{custom}](tg://user?id={user.id})")
    tag = user.first_name.replace("\u2060", "") if user.first_name else user.username
    await eor(
        mention,
        f"- المستخدم [{tag}](tg://user?id={user.id}) \nتـم رفعه زوجج روحوا خلفوا 🤤😂",
    )


@Tepthon_cmd(pattern="رفع مطي(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    if user.id == 1694386561:
        return await eor(mention, f"**⌔∮ أبتعد هذا صديق المطور لا**")
    if user.id == 2034443585:
        return await eor(mention, f"**⌔∮ دي هذا مطور السورس أبتعد**")
    tag = user.first_name.replace("\u2060", "") if user.first_name else user.username
    await eor(
        mention, f"- المستخدم [{tag}](tg://user?id={user.id}) \n تـم رفـعه مطي هـنا "
    )


@Tepthon_cmd(pattern="رفع مرتي(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    if user.id == 1694386561:
        return await eor(mention, f"**⌔∮ أبتعد هذا صديق المطور لا**")
    if user.id == 2034443585:
        return await eor(mention, f"**- لكك دي هذا المطور**")
    tag = user.first_name.replace("\u2060", "") if user.first_name else user.username
    await eor(
        mention,
        f"- المستخدم [{tag}](tg://user?id={user.id}) \n تـم رفعـه مـࢪتك مـشي نخـلف 😹🤤",
    )


@Tepthon_cmd(pattern="رفع كلب(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return

    if user.id == 1694386561:
        return await eor(mention, f"**⌔∮ أبتعد هذا صديق المطور لا**")
    if user.id == 2034443585:
        return await eor(mention, f"**- لكك دي هذا المطور**")
    tag = user.first_name.replace("\u2060", "") if user.first_name else user.username
    await eor(
        mention,
        f"- المستخدم [{tag}](tg://user?id={user.id}) \n تـم رفعـه جلب خليه خله ينبح 😂🐶",
    )


@Tepthon_cmd(pattern="كت(?: |$)(.*)")
async def mention(mention):
    kt = random.choice(kattwet)
    await eor(mention, f"**- {kt}**")


@Tepthon_cmd(pattern="هينه(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    if user.id == 1694386561:
        return await eor(mention, f"**⌔∮ أبتعد هذا صديق المطور لا**")
    if user.id == 2034443585:
        return await eor(mention, f"**- لكك دي هذا المطور**")
    muh = user.first_name.replace("\u2060", "") if user.first_name else user.username
    sos = random.choice(hena)
    await eor(mention, f"{sos} .")


@Tepthon_cmd(pattern="نسبة الحب(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    muh = user.first_name.replace("\u2060", "") if user.first_name else user.username
    moh = random.choice(nsba)
    await eor(
        mention, f"نـسـبتكم انـت و [{muh}](tg://user?id={user.id}) هـي {moh} 😔🖤"
    )


@Tepthon_cmd(pattern="نسبة الانوثة(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    if user.id == 1694386561:
        return await eor(mention, f"**⌔∮ أبتعد هذا صديق المطور لا**")
    if user.id == 2034443585:
        return await eor(mention, f"**- لكك دي هذا المطور زلمة وعلى راسك**")
    muh = user.first_name.replace("\u2060", "") if user.first_name else user.username
    sos = random.choice(rr7)
    await eor(
        mention, f"- نسبة الانوثة لـ [{muh}](tg://user?id={user.id}) هي {sos} 🥵🖤"
    )


@Tepthon_cmd(pattern="نسبة الغباء(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    muh = user.first_name.replace("\u2060", "") if user.first_name else user.username
    jmbot = random.choice(rr7)
    await eor(
        mention, f"نسبة الغباء لـ [{muh}](tg://user?id={user.id}) هـي {jmbot} 😂💔"
    )


@Tepthon_cmd(pattern="رفع تاج(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    if custom:
        return await eor(mention, f"[{custom}](tg://user?id={user.id})")
    tag = user.first_name.replace("\u2060", "") if user.first_name else user.username
    await eor(
        mention, f"- المستخدم [{tag}](tg://user?id={user.id}) \n تـم رفعـه تاج 👑🔥"
    )


@Tepthon_cmd(pattern="رفع قرد(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    if user.id == 1694386561:
        return await eor(mention, f"**⌔∮ أبتعد هذا صديق المطور لا**")
    if user.id == 2034443585:
        return await eor(mention, f"**- لكك دي هذا المطور**")
    tag = user.first_name.replace("\u2060", "") if user.first_name else user.username
    await eor(
        mention,
        f"- المستخدم [{tag}](tg://user?id={user.id}) \n تـم رفعـه قرد واعطائه موزة 🐒🍌",
    )


@Tepthon_cmd(pattern="اوصف(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    muh = user.first_name.replace("\u2060", "") if user.first_name else user.username
    jmbot = random.choice(Describe)
    await eor(mention, f"{jmbot}")


@Tepthon_cmd(pattern="شغله(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    muh = user.first_name.replace("\u2060", "") if user.first_name else user.username
    rezw = random.choice(jobtype)
    await eor(
        mention, f"- المستخدم [{muh}](tg://user?id={user.id}) شغله هو {rezw}"
    )


@Tepthon_cmd(pattern="نسبة الرجولة(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    if user.id == 1694386561:
        return await eor(mention, f"**⌔∮ نسبة رجولة جاسم هي 99%**")
    if user.id == 2034443585:
        return await eor(mention, f"**⌔∮ نسبة رجولة محمد مالك السورس هي 100%**")
    muh = user.first_name.replace("\u2060", "") if user.first_name else user.username
    sos = random.choice(kz)
    await eor(
        mention, f"- نسبة الرجولة لـ [{muh}](tg://user?id={user.id}) هـي {sos} 🥵🖤"
    )


@Tepthon_cmd(pattern="رفع حيوان(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    if custom:
        return await eor(mention, f"[{custom}](tg://user?id={user.id})")
    tag = user.first_name.replace("\u2060", "") if user.first_name else user.username
    await eor(
        mention, f"- المستخدم [{tag}](tg://user?id={user.id}) \n- تـم رفعـه حيوان 🐏"
    )


@Tepthon_cmd(pattern="رفع بزون(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    if custom:
        return await eor(mention, f"[{custom}](tg://user?id={user.id})")
    tag = user.first_name.replace("\u2060", "") if user.first_name else user.username
    await eor(
        mention, f"- المستخدم [{tag}](tg://user?id={user.id}) \n- تـم رفعـه بزون 🐈"
    )


@Tepthon_cmd(pattern="رفع زاحف(?: |$)(.*)")
async def permalink(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    if custom:
        return await eor(mention, f"[{custom}](tg://user?id={user.id})")
    tag = user.first_name.replace("\u2060", "") if user.first_name else user.username
    await eor(
        mention, f"- المستخدم [{tag}](tg://user?id={user.id}) \n- تـم رفعـه زاحف 🐍💞"
    )

@Tepthon_cmd(pattern="نزوج(?: |$)(.*)")
async def wiffun(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    if user.id == 2034443585:
        return await eor(mention, f"**⌔∮ عذرا هذا مطور السورس**")
    await eor(mention, f"**نزوج وماتباوع على غيري 🥺💞 ܰ**")

@Tepthon_cmd(pattern="طلاك(?: |$)(.*)")
async def mention(mention):
    user, custom = await get_uinfo(mention)
    if not user:
        return
    if user.id == 2034443585:
        return await eor(mention, f"**⌔∮ عذرا هذا مطور السورس**")
    await eor(mention, f"**طالق طالق بالعشرة 😹😭💕 ܰ**")
