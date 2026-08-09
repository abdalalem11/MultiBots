"""
  `{i}رفع مشرف`  <بالرد على المستخــدم/وضع يوزره>
   لـ رفع مستخدم في المجموعة أو القناة بوضع معرفه مع الأمـر

  `{i}تنزيل مشرف`  <بالرد على المستخــدم/وضع يوزره>
   لـ تنزيل مستخدم من المشرفين في الدردشة ويصبح عضو عادي

  `{i}حظر`  <بالرد على المستخــدم/وضع يوزره>
   لـ حظر المستخــدم من المجموعة ومنعه من الدخول للمجموعة

  `{i}الغاء حظر`  <بالرد على المستخــدم/وضع يوزره>
   لـ الغاء حظر المستخــدم في المجموعة والسماح له بالدخول

  `{i}طرد`  <بالرد على المستخــدم/وضع يوزره>
   لـ طرد المستخــدم من المجموعة بحيث يمكنه الدخول مرة أخرى

  `{i}تثبيت`  <بالرد على الرسالة>
   لـ تثبيت رسالة في الدردشة بالرد على الرسالة التي تريد تثبيتها

  `{i}الغاء تثبيت`  <بالرد على الرسالة>
   لـ الغاء تثبيت الرسالة في الدردشة بالرد على الرسالة التي تريد الغاء تثبيتها
   لإلغاء تثبيت جميع الرسائل استخدم `{i}الغاء تثبيت الكل`

  `{i}مسح` <عدد الرسائل>
   لـ حذف الرسائل من الدردشة بالعدد، واذا قمت بالرد على مستخدم وتعيين عدد الرسائل سيحذف رسائله فقط 
   يمكنك كذلك فقط الرد على الرسالة بدون تعيين عدد وسيحذفها فقط 
"""

from telethon.errors import BadRequestError
from telethon.errors.rpcerrorlist import UserIdInvalidError
from telethon.tl.functions.channels import EditAdminRequest, GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.types import InputMessagesFilterPinned
from telethon.utils import get_display_name

from Tepthon.decorators import eod, eor
from resources import DEVLIST
from Tepthon.helper import inline_mention, get_uinfo
from Tepthon import HNDLR
from .. import LOGS, types, Tepthon_cmd



@Tepthon_cmd(
    pattern="رفع مشرف( (.*)|$)",
    admins_only=True,
    manager=True,
    require="add_admins",
    fullsudo=True,
)
async def promote(event):
    xx = await event.eor("**⎆ هممم، انتظر قليلًا...**")
    user, rank = await get_uinfo(event)
    if not rank:
        rank = "مشرف"
    FullRight = False
    if not user:
        return await xx.edit("**⎆ يجب الرد على المستـخدم لرفعه...**")
    if rank.split()[0] == "-صلاحيات":
        try:
            rank = rank.split(maxsplit=1)[1]
        except IndexError:
            rank = "مشرف"
        FullRight = True
    try:
        if FullRight:
            await event.client(
                EditAdminRequest(event.chat_id, user.id, event.chat.admin_rights, rank)
            )
        else:
            await event.client.edit_admin(
                event.chat_id,
                user.id,
                invite_users=True,
                pin_messages=True,
                manage_call=True,
                title=rank,
            )
        await eod(
            xx, "**⎆ المستخــدم: {} الآن أصبح مشرف\n❃ الدردشة: {}\n❃ اللقب: {}**".format(inline_mention(user), event.chat.title, rank)
        )
    except Exception as ex:
        return await xx.edit(f"`{ex}`")


@Tepthon_cmd(
    pattern="تنزيل مشرف( (.*)|$)",
    admins_only=True,
    manager=True,
    require="add_admins",
    fullsudo=True,
)
async def demote(unprom):
    xx = await unprom.eor("**⎆ جاري تنزيل المستخــدم من قائمة المشرفين..**")
    user, rank = await get_uinfo(unprom)
    if not rank:
        rank = " "
    if not user:
        return await xx.edit("**◙ رد على المشرف الذي تريد إزالته من المشرفين**")
    try:
        await unprom.client.edit_admin(
            unprom.chat_id,
            user.id,
            invite_users=None,
            ban_users=None,
            delete_messages=None,
            pin_messages=None,
            manage_call=None,
            title=rank,
        )
        await eod("**⎆ المستخــدم: {} تم إزالته من المشرفين\n❃ الدردشة: {}**".format(inline_mention(user), unprom.chat.title))
    except Exception as ex:
        return await xx.edit(f"`{ex}`")


@Tepthon_cmd(
    pattern="حظر( (.*)|$)",
    admins_only=True,
    manager=True,
    require="ban_users",
    fullsudo=True,
)
async def bban(mirza):
    something = await get_uinfo(mirza)
    if not something:
        return
    user, reason = something
    if not user:
        return await eod("**⎆ يجب عليك الرد على المستخــدم / أو وضع معرفه مع الأمـر | لحظر المستخــدم**")
    if user.id in DEVLIST:
        return await eod(mirza, "**⎆ عذرًا هذا مطور السورس لا يمكنني حظره**")
    try:
        await mirza.client.edit_permissions(mirza.chat_id, user.id, view_messages=False)
    except UserIdInvalidError:
        return await eod(mirza, "**⎆ لم يتم العثور على المستخــدم**")
    except BadRequestError:
        return await eod(mirza, "**⎆ يجب أن تمتلك الصلاحيات الكافية لحظر المسخدم**")
    senderme = inline_mention(await mirza.get_sender())
    userme = inline_mention(user)
    text = "**⎆ تم حظر المستخــدم : {} \n❃ بواسطة : {}\n❃ في الدردشة : {}** ".format(userme, senderme, mirza.chat.title)
    if reason:
        text += "**❃ السبب {}**".format(reason)
    await eod(mirza, text)


@Tepthon_cmd(
    pattern="الغاء حظر( (.*)|$)",
    admins_only=True,
    manager=True,
    require="ban_users",
    fullsudo=True,
)
async def uunban(jasm):
    xx = await jasm.eor("**⎆ جاري الغاء حظر المستخــدم ...**")
    if jasm.text[1:].startswith("unbanall"):
        return
    something = await get_uinfo(jasm)
    if not something:
        return
    user, reason = something
    if not user:
        return await xx.edit("**⎆ يجب الرد على المستخــدم أو وضع يوزره مع الأمر لإلغاء حظره**")
    try:
        await jasm.client.edit_permissions(jasm.chat_id, user.id, view_messages=True)
    except UserIdInvalidError:
        return await eod(jasm, "**❃ لم يتم العثور على المستخــدم بشكل صحيح  ...**")
    except BadRequestError:
        return await xx.edit("**⎆ يجب أن تمتلك الصلاحيات الكافية ألغاء حظر المسخدم**")
    sender = inline_mention(await jasm.get_sender())
    text = "**⎆ تم إلغاء حظر المستخــدم: {}\n❃ بواسطة : {}\n❃ في الدردشة : {}** ".format(inline_mention(user), sender, jasm.chat.title)
    if reason:
        text += "السبب {}".format(reason)
    await xx.edit(text)


@Tepthon_cmd(
    pattern="طرد( (.*)|$)",
    manager=True,
    require="ban_users",
    fullsudo=True,
)
async def kck(e):
    if "kickme" in e.text:
        return
    if e.is_private:
        return await e.eor("**⎆ هذا الأمر يستخدم فقط في المجموعات*", time=5)
    ml = e.text.split(" ", maxsplit=1)[0]
    xx = await e.eor("**⎆ جـار طـرد المسـتخدم من الـدردشة . . .**")
    something = await get_uinfo(e)
    if not something:
        return
    user, reason = something
    if not user:
        return await xx.edit("**⎆ لم يتم العثور على المستخــدم بشكل صحيح**")
    if user.id in DEVLIST:
        return await xx.edit("**⎆ عذرًا لا يمكنك طرد مطور السورس**")
    if getattr(user, "is_self", False):
        return await xx.edit("**⎆ هل أنت غبي؟ لا يمكنك طرد نفسك**")
    try:
        await e.client.kick_participant(e.chat_id, user.id)
    except BadRequestError as er:
        LOGS.info(er)
        return await xx.edit("**⎆ يجب أن تمتلك الصلاحيات الكافية لطرد المستخــدم**")
    except Exception as e:
        LOGS.exception(e)
        return
    sender = inline_mention(await e.get_sender())
    text = "**⎆ تم طرد المستخــدم : {}\n❃ بواسطة : {}\n❃ في الدردشة : {}**".formate(inline_mention(user), sender, e.chat.title)
    if reason:
        text +="**❃ السبب {}**".format(reason)
    await xx.edit(text)



@Tepthon_cmd(pattern="تثبيت$", manager=True, require="pin_messages", fullsudo=True)
async def pin(msg):
    if not msg.is_reply:
        return await msg.eor("**⎆ يجب عليك الرد على الرسالة التي تريد تثبيتها**")
    me = await msg.get_reply_message()
    if me.is_private:
        text = "**⎆ تم التثبيت الرسالة في الدردشة بنجاح**"
    else:
        text = f"**⎆ تم تثبيت [هذه الرسالة بنجاح]({me.message_link})**"
    try:
        await msg.client.pin_message(msg.chat_id, me.id, notify=False)
    except BadRequestError:
        return await msg.eor("**⎆ يجب أن تمتلك الصلاحيات الكافية للتثبيت**")
    except Exception as e:
        return await msg.eor(f"**❃ خطأ:**`{e}`")
    await msg.eor(text)


@Tepthon_cmd(
    pattern="الغاء تثبيت($| (.*))",
    manager=True,
    require="pin_messages",
    fullsudo=True,
)
async def unp(jasm):
    xx = await jasm.eor("**⎆ جـاري إلغاء تثبيـت الرسـالة....... ..**")
    ch = (jasm.pattern_match.group(1).strip()).strip()
    msg = None
    if jasm.is_reply:
        msg = jasm.reply_to_msg_id
    elif ch != "الكل":
        return await xx.edit("**⎆ يجب عليك الرد على الرسالة التي تريد الغاء تثبيتها\n❃ لإلغاء تثبيت جميع الرسائل استخدم** `{}الغاء تثبيت الكل`".format(HNDLR))
    try:
        await jasm.client.unpin_message(jasm.chat_id, msg)
    except BadRequestError:
        return await xx.edit("**⎆ يجب أن تمتلك الصلاحيات الكافية لإلغـاء التثبيت**")
    except Exception as e:
        return await xx.edit(f"**خطأ:**`{e}`")
    await xx.edit("**⎆ تم إلغـاء تثبيـت الرسالة ... ✅**")


@Tepthon_cmd(pattern="مسح ?(.*)")
async def purge(event):
    limit_str = event.pattern_match.group(1)
    limit = int(limit_str) if limit_str.isdigit() else None
    msg_src = await event.get_reply_message()
    if limit is None and msg_src:
        return await msg_src.delete()
    
    messages = []
    count = 0
    if event.is_reply and event.reply_to_msg_id:
        reply_message = await event.get_reply_message()
        async for message in event.client.iter_messages(
            event.chat_id, 
            from_user=reply_message.sender_id, 
            limit=limit
        ):
            if message.id == event.id:
                continue
            messages.append(message.id)
            count += 1
        await event.client.delete_messages(event.chat_id, messages)
        await event.eor(f"⎆ تم حذف {count} من رسائل المستخــدم.")
    else:
        async for message in event.client.iter_messages(event.chat_id, limit=limit + 1):
            if message.id == event.id:
                continue
            messages.append(message.id)
            count += 1
        await event.client.delete_messages(event.chat_id, messages)
        await event.eor(f"⎆ تم حذف {count} من الرسائل من الدردشة.")
