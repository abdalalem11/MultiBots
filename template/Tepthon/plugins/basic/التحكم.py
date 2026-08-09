"""
◙ `{i}اضف متحكم` [ايدي الشخص/الرد عليه]
    لـ إضافـة متحكم لحسابك يمكنه استخدام أوامر تيبثون باستخدام حسابك 
    
◙ `{i}حذف متحكم` [ايدي الشخص/الرد عليه]
    لـحذف متحكم من استخدام سورس تيبثون الخاص بك

◙ `{i}المتحكمين`
    لـ عرض قائمة المستخدمين الذي يمكنهم التحكم بحسابك
"""

from telethon.tl.types import User
from Tepthon.decorators import get_sudos, is_sudo
from .. import jmdB, Tepthon_cmd, jmubot, inline_mention


@Tepthon_cmd(pattern="اضف متحكم( (.*)|$)", fullsudo=True)
async def add_sudo(e):
    inputs = e.pattern_match.group(1).strip()
    if e.reply_to_msg_id:
        replied_to = await e.get_reply_message()
        id_ = replied_to.sender_id
        name = await replied_to.get_sender()
    elif inputs:
        id_ = inputs
        try:
            name = await e.client.get_entity(inputs)
        except BaseException:
            name = None
    elif e.is_private:
        id_ = e.chat_id
        name = await e.get_chat()
    else:
        return await e.eor("**⎆ يجب عليك الرد على المستخدم أو وضع يوزره لإضافته في المتحكمين**", time=5)
    if name and isinstance(name, User) and (name.bot or name.verified):
        return await e.eor("**◙ لا يمكن إضافـة البوتات إلى قائمة المتحكميـن**")
    name = inline_mention(name) if name else f"`{id_}`"
    if id_ == jmubot.uid:
        mmm = "*⎆ لا يمكنك إضافـة نفسك إلى قائمة المتحكمين**"
    elif is_sudo(id_):
        mmm = f"**⎆ المستخدم: {name}\n◙ في قائمة المتحكمين أصلا**..."
    else:
        jmdB.set_key("SUDO", "True")
        key = get_sudos()
        key.append(id_)
        jmdB.set_key("SUDOS", key)
        mmm = f"**◙ المستخدم: {name}\n◙ تم بنجاح أضافته إلى قائمة المتحكمين**"
    await e.eor(mmm, time=5)


@Tepthon_cmd(pattern="حذف متحكم( (.*)|$)", fullsudo=True)
async def remov_sudo(e):
    inputs = e.pattern_match.group(1).strip()
    if e.reply_to_msg_id:
        replied_to = await e.get_reply_message()
        id_ = replied_to.sender_id
        name = await replied_to.get_sender()
    elif inputs:
        id_ = inputs
        try:
            name = await e.client.get_entity(id_)
        except BaseException:
            name = None
    elif e.is_private:
        id_ = e.chat_id
        name = await e.get_chat()
    else:
        return await e.eor("**يجب عليك الرد على المستخدم أو وضعه يوزره مع الأمر**", time=5)
    name = inline_mention(name) if name else f"`{id_}`"
    if not is_sudo(id_):
        mmm = f"**⎆ المستخدم: {name}\n◙ ليس من ضمن المتحكمين أصـلًا..**..."
    else:
        key = get_sudos()
        key.remove(id_)
        jmdB.set_key("SUDOS", key)
        mmm = f"**◙ المستخدم: {name}\n◙ تم حذفه من قائمة المتحـكمين**"
    await e.eor(mmm, time=5)


@Tepthon_cmd(pattern="المتحكمين$")
async def list_sudo(e):
    sudos = get_sudos()
    if not sudos:
        return await e.eor("**⎆ لا يوجد أي مستخدم مضاف إلى المتحكمين**", time=5)
    msg = ""
    for i in sudos:
        try:
            name = await e.client.get_entity(i)
        except BaseException:
            name = None
        if name:
            msg += f"◙ {inline_mention(name)} ( `{i}` )\n"
        else:
            msg += f"◙ `{i}` :  مستخدم غير صالح\n"
    m = jmdB.get_key("SUDO")
    if m is not True:
        m = "[غير مفعل]  | لتفعيله ادخل إلى إعدادات البوت المساعد وفعله"
    else:
        m = "[ مفعل ✅ ]"
    return await e.eor(f"**⎆ وضع التحكم : {m}\n\n◙ قائمة المتحكمين :**\n{msg}", link_preview=False)
