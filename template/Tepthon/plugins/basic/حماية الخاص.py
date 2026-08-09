"""

❃ `{i}س` أو `{i}سماح`
    يستخدم بإرسـال الأمر عند المستخدم أو بكتابة الأمر مع معرف المستخدم أو بالرد عليه
    لـ السماح للمستخدم بالتواصل معك وإيقـاف نظام الحماية معه

❃ `{i}ر` أو `{i}رفض`
    يستخدم بإرسـال الأمر عند المستخدم أو بكتابة الأمر مع معرف المستخدم أو بالرد عليه
    لـ رفض للمستخدم من التواصل معك وإرجـاع نظام الحماية شغال معه

❃ `{i}بلوك`
    الاستخدام: بإرسـال الأمر عند المستخدم أو بكتابة الأمر مع معرف المستخدم أو بالرد عليه
    الشرح: لحظر المستخدم من التواصل معك على الخاص


❃ `{i}الغاء البلوك` | `{i}الغاء البلوك للكل`
    يستخدم هذا بإرسـاله عند المستخدم في الدردشة الخاصة
    لـ إلغـاء حظر المستخدم من الخاصة وإذا كتبت مع الامر للكل سيلغي حظر جميع المحظورين


❃ `{i}تشغيل الارشفة`
    لـ أرشفة المحادثات الجديدة

❃ `{i}ايقاف الارشفة`
    لـ إيقـاف أرشفة المحادثات الجديدة

❃ `{i}مسح الارشفة`
    لـ حذف جميع المحادثات المؤرشفة

❃ `{i}قائمة المسموحين`
   لعرض قائمة المستخدمين المسموح لهم بالدردشة معك

⌔∮ هذه الأوامر تعمل فقط حين تشغيل نظام حماية الخاص
"""

import asyncio
import re
from os import remove

from resources import DEVLIST
from tabulate import tabulate
from Tepthon import HNDLR
from telethon import events
from telethon.errors import MessageNotModifiedError
from telethon.tl import types
from telethon.tl.custom import Button
from telethon.tl.functions.contacts import (BlockRequest, GetBlockedRequest,
                                            UnblockRequest)
from telethon.tl.functions.messages import ReportSpamRequest
from telethon.utils import get_display_name, resolve_bot_file_id

from database.core.settings import KeySettings

from .. import (LOGS, tgbot, callback, in_pattern, inline_mention,
               jmdB, jmubot, Tepthon_cmd)

OWNER_NAME = jmubot.full_name
OWNER_ID = jmubot.me.id

COUNT_PM = {}
LASTMSG = {}
WARN_MSGS = {}
U_WARNS = {}

if isinstance(jmdB.get_key("PMPERMIT"), (int, str)):
    value = [jmdB.get_key("PMPERMIT")]
    jmdB.set_key("PMPERMIT", value)

keym = KeySettings("PMPERMIT", cast=list)
PMPIC = jmdB.get_key("PMPIC")
LOG_CHAT = jmdB.get_key("LOG_CHAT")

UND = "**⎆ يجب عليك انتظـار رد مالـك الحسـاب 🧸\n ⎆ وإن قمت بالتكرار سوف أقوم بحظرك**"
UNS = "**⌔∮  لـقد أخبرتك ألّا تُـكـرر أرسـال الرسـائل\n❃ يبـدو أنـك لا تُحـسن الـقراءة سيتم حظـرك  :)**" 
NO_REPLY = "**⎆ يجب عليك الرد على المستخدم أو في الخاص**."


UNAPPROVED_MSG = "**نظام حماية تيبثـون الخاص بـ {ON}!**\n\n{UND}\n\nلديك {warn}/{twarn} تحذيرات"
if jmdB.get_key("PM_TEXT"):
    UNAPPROVED_MSG = (
        "**نظام حماية تيبثـون الخاص بـ {ON}!**\n\n"
        + jmdB.get_key("PM_TEXT")
        + "\n\nلديك {warn}/{twarn} تحذيرات"
    )

WARNS = jmdB.get_key("PMWARNS") or 4

_not_approved = {}
_to_delete = {}

my_bot = tgbot.me.username


def update_pm(userid, message, warns_given):
    try:
        WARN_MSGS.update({userid: message})
    except KeyError:
        pass
    try:
        U_WARNS.update({userid: warns_given})
    except KeyError:
        pass


async def delete_pm_warn_msgs(chat: int):
    try:
        await _to_delete[chat].delete()
    except KeyError:
        pass


# =================================================================


if jmdB.get_key("PMSETTING"):
    if jmdB.get_key("AUTOAPPROVE"):

        @jmubot.on(
            events.NewMessage(
                outgoing=True,
                func=lambda e: e.is_private and e.out and not e.text.startswith(HNDLR),
            ),
        )
        async def autoappr(e):
            miss = await e.get_chat()
            if miss.bot or miss.is_self or miss.verified or miss.id in DEVLIST:
                return
            if keym.contains(miss.id):
                return
            keym.add(miss.id)
            await delete_pm_warn_msgs(miss.id)
            try:
                await jmubot.edit_folder(miss.id, folder=0)
            except BaseException:
                pass
            try:
                await tgbot.edit_message(
                    LOG_CHAT,
                    _not_approved[miss.id],
                    f"#السماح_تلقائيا : <b>الرسائل المرسلة.\nالمستخدم : {inline_mention(miss, html=True)}</b> [<code>{miss.id}</code>]",
                    parse_mode="html",
                )
            except KeyError:
                await tgbot.send_message(
                    LOG_CHAT,
                    f"#السماح_تلقائيا : <b>الـرسائل المرسلة.\nالمستخدمة : {inline_mention(miss, html=True)}</b> [<code>{miss.id}</code>]",
                    parse_mode="html",
                )
            except MessageNotModifiedError:
                pass

    @jmubot.on(
        events.NewMessage(
            incoming=True,
            func=lambda e: e.is_private
            and e.sender_id not in DEVLIST
            and not e.out
            #       and not e.sender.bot
            #      and not e.sender.is_self
            #       and not e.sender.verified,
        )
    )
    async def permitpm(event):
        sender = await event.get_sender()
        if (sender.bot or sender.verified or sender.is_self):
            return
        inline_pm = jmdB.get_key("INLINE_PM") or False
        user = event.sender
        if not keym.contains(user.id) and event.text != UND:
            if jmdB.get_key("MOVE_ARCHIVE"):
                try:
                    await jmubot.edit_folder(user.id, folder=1)
                except BaseException as er:
                    LOGS.info(er)
            if event.media and not jmdB.get_key("DISABLE_PMDEL"):
                await event.delete()
            name = user.first_name
            fullname = get_display_name(user)
            username = f"@{user.username}"
            mention = inline_mention(user)
            count = keym.count()
            try:
                wrn = COUNT_PM[user.id] + 1
                await tgbot.edit_message(
                    jmdB.get_key("LOG_CHAT"),
                    _not_approved[user.id],
                    f"نظام حماية الخاص من تيبثون \nالمستخدم: **{mention}** [`{user.id}`] مع **{wrn}/{WARNS}** من التحذيرات",
                    buttons=[
                        Button.inline("السماح بالدردشة ✅", data=f"approve_{user.id}"),
                        Button.inline("حظر المستخدم 🚫", data=f"block_{user.id}"),
                    ],
                )
            except KeyError:
                _not_approved[user.id] = await tgbot.send_message(
                    jmdB.get_key("LOG_CHAT"),
                    f"نظام حماية الخاص من تيبثون \nالمستخدم: **{mention}** [`{user.id}`] مع **1/{WARNS}** من التحذيرات",
                    buttons=[
                        Button.inline("السماح بالدردشة ✅", data=f"approve_{user.id}"),
                        Button.inline("حظر المستخدم 🚫", data=f"block_{user.id}"),
                    ],
                )
                wrn = 1
            except MessageNotModifiedError:
                wrn = 1
            if user.id in LASTMSG:
                prevmsg = LASTMSG[user.id]
                if event.text != prevmsg:
                    if "نظام حماية تيبثون" in event.text or "**نظام حماية تيبثون" in event.text:
                        return
                    await delete_pm_warn_msgs(user.id)
                    message_ = UNAPPROVED_MSG.format(
                        ON=OWNER_NAME,
                        warn=wrn,
                        twarn=WARNS,
                        UND=UND,
                        name=name,
                        fullname=fullname,
                        username=username,
                        count=count,
                        mention=mention,
                    )
                    update_pm(user.id, message_, wrn)
                    if inline_pm:
                        results = await jmubot.inline_query(
                            my_bot, f"ip_{user.id}"
                        )
                        try:
                            _to_delete[user.id] = await results[0].click(
                                user.id, reply_to=event.id, hide_via=True
                            )
                        except Exception as e:
                            LOGS.info(str(e))
                    elif PMPIC:
                        _to_delete[user.id] = await jmubot.send_file(
                            user.id,
                            PMPIC,
                            caption=message_,
                        )
                    else:
                        _to_delete[user.id] = await jmubot.send_message(
                            user.id, message_
                        )

                else:
                    await delete_pm_warn_msgs(user.id)
                    message_ = UNAPPROVED_MSG.format(
                        ON=OWNER_NAME,
                        warn=wrn,
                        twarn=WARNS,
                        UND=UND,
                        name=name,
                        fullname=fullname,
                        username=username,
                        count=count,
                        mention=mention,
                    )
                    update_pm(user.id, message_, wrn)
                    if inline_pm:
                        try:
                            results = await jmubot.inline_query(
                                my_bot, f"ip_{user.id}"
                            )
                            _to_delete[user.id] = await results[0].click(
                                user.id, reply_to=event.id, hide_via=True
                            )
                        except Exception as e:
                            LOGS.info(str(e))
                    elif PMPIC:
                        _to_delete[user.id] = await jmubot.send_file(
                            user.id,
                            PMPIC,
                            caption=message_,
                        )
                    else:
                        _to_delete[user.id] = await jmubot.send_message(
                            user.id, message_
                        )
                LASTMSG.update({user.id: event.text})
            else:
                await delete_pm_warn_msgs(user.id)
                message_ = UNAPPROVED_MSG.format(
                    ON=OWNER_NAME,
                    warn=wrn,
                    twarn=WARNS,
                    UND=UND,
                    name=name,
                    fullname=fullname,
                    username=username,
                    count=count,
                    mention=mention,
                )
                update_pm(user.id, message_, wrn)
                if inline_pm:
                    try:
                        results = await jmubot.inline_query(
                            my_bot, f"ip_{user.id}"
                        )
                        _to_delete[user.id] = await results[0].click(
                            user.id, reply_to=event.id, hide_via=True
                        )
                    except Exception as e:
                        LOGS.info(str(e))
                elif PMPIC:
                    _to_delete[user.id] = await jmubot.send_file(
                        user.id,
                        PMPIC,
                        caption=message_,
                    )
                else:
                    _to_delete[user.id] = await jmubot.send_message(
                        user.id, message_
                    )
            LASTMSG.update({user.id: event.text})
            if user.id not in COUNT_PM:
                COUNT_PM.update({user.id: 1})
            else:
                COUNT_PM[user.id] = COUNT_PM[user.id] + 1
            if COUNT_PM[user.id] >= WARNS:
                await delete_pm_warn_msgs(user.id)
                _to_delete[user.id] = await event.respond(UNS)
                try:
                    del COUNT_PM[user.id]
                    del LASTMSG[user.id]
                except KeyError:
                    await tgbot.send_message(
                        jmdB.get_key("LOG_CHAT"),
                        "**لم أتوقع أن تحدث هذه المشكلة ولكن هناك خطأ في نظام الحماية أرسل `.اعادة تشغيل` لحل المشكلـة 🔦**",
                    )
                    return LOGS.info("هنالك خطأ في متغير COUNT_PM")
                await jmubot(BlockRequest(user.id))
                await jmubot(ReportSpamRequest(peer=user.id))
                await tgbot.edit_message(
                    jmdB.get_key("LOG_CHAT"),
                    _not_approved[user.id],
                    f"**✦ المستخدم {mention}** [`{user.id}`]\n✦ تم حظره بسبب التكرار في الخاص.",
                )

    @Tepthon_cmd(pattern="(تشغيل|ايقاف|مسح) الارشفة$", fullsudo=True)
    async def _(e):
        x = e.pattern_match.group(1).strip()
        if x == "تشغيل":
            jmdB.set_key("MOVE_ARCHIVE", "True")
            await e.eor("**⎆ من الآن سيتم نقل المستخدم الغير مسموح له إلى الأرشيف**", time=5)
        elif x == "ايقاف":
            jmdB.set_key("MOVE_ARCHIVE", "False")
            await e.eor("**⎆ من الآن سيتم إلغاء النقل عن المستخدم الغير المسموح له إلى الأرشيف**", time=5)
        elif x == "مسح":
            try:
                await e.client.edit_folder(unpack=1)
                await e.eor("**✦ تم إلغاء أرشيـف جميع المحادثات بنجاح ✓**", time=5)
            except Exception as mm:
                await e.eor(str(mm), time=5)

    @Tepthon_cmd(pattern="(س|سماح)(?: |$)", fullsudo=True)
    async def approvepm(apprvpm):
        if apprvpm.reply_to_msg_id:
            user = (await apprvpm.get_reply_message()).sender
        elif apprvpm.is_private:
            user = await apprvpm.get_chat()
        else:
            return await apprvpm.edit(NO_REPLY)
        if user.id in DEVLIST:
            return await apprvpm.eor(
                "**⌔∮ هذا هو مطور سورس تيبثون هو بالأصل مسموح له بالدردشة  !**",
            )
        if not keym.contains(user.id):
            keym.add(user.id)
            try:
                await delete_pm_warn_msgs(user.id)
                await apprvpm.client.edit_folder(user.id, folder=0)
            except BaseException:
                pass
            await apprvpm.eor(
                f"<b>{inline_mention(user, html=True)}</b> <code>تم السماح له بالدردشة معك</code>",
                parse_mode="html",
            )
            try:
                await tgbot.edit_message(
                    jmdB.get_key("LOG_CHAT"),
                    _not_approved[user.id],
                    f"#السماح\n\n<b>{inline_mention(user, html=True)}</b> [<code>{user.id}</code>] <code>لقد تم السماح له بالدردشة معك</code>",
                    buttons=[
                        Button.inline(
                            "رفض المستخدم ❌", data=f"disapprove_{user.id}"),
                        Button.inline("حظر المستخدم 🚫", data=f"block_{user.id}"),
                    ],
                    parse_mode="html",
                )
            except KeyError:
                _not_approved[user.id] = await tgbot.send_message(
                    jmdB.get_key("LOG_CHAT"),
                    f"#السماح\n\n<b>{inline_mention(user, html=True)}</b> [<code>{user.id}</code>] <code>لقد تم السماح له بالدردشة معك</code>",
                    buttons=[
                        Button.inline(
                            "رفض المستخدم ❌", data=f"disapprove_{user.id}"),
                        Button.inline("حظر المستخدم 🚫", data=f"block_{user.id}"),
                    ],
                    parse_mode="html",
                )
            except MessageNotModifiedError:
                pass
        else:
            await apprvpm.eor("**⎆ هذا المستخدم مسموح بالدردشة معك بالأصـل 🔔**", time=5)

    @Tepthon_cmd(pattern="(ر|رفض)(?: |$)", fullsudo=True)
    async def disapprovepm(e):
        if e.reply_to_msg_id:
            user = (await e.get_reply_message()).sender
        elif e.is_private:
            user = await e.get_chat()
        else:
            return await e.edit(NO_REPLY)
        if user.id in DEVLIST:
            return await e.eor(
                "**اخرس هـذا مطـور السورس ♥️**\n لا يمكنني رفضه أبدًا",
            )
        if keym.contains(user.id):
            keym.remove(user.id)
            await e.eor(
                f"<b>{inline_mention(user, html=True)}</b> <code>تم رفضه من الدردشة معك</code>",
                parse_mode="html",
            )
            try:
                await tgbot.edit_message(
                    jmdB.get_key("LOG_CHAT"),
                    _not_approved[user.id],
                    f"#الرفض\n\n<b>{inline_mention(user, html=True)}</b> [<code>{user.id}</code>] <code>لقد تم رفضه من الدردشة معك.</code>",
                    buttons=[
                        Button.inline("السماح بالدردشة ✅", data=f"approve_{user.id}"),
                        Button.inline("حظر المستخدم 🚫", data=f"block_{user.id}"),
                    ],
                    parse_mode="html",
                )
            except KeyError:
                _not_approved[user.id] = await tgbot.send_message(
                    jmdB.get_key("LOG_CHAT"),
                    f"#الرفض\n\n<b>{inline_mention(user, html=True)}</b> [<code>{user.id}</code>] <code>لقد تم رفضه من الدردشة معك.</code>",
                    buttons=[
                        Button.inline("السماح بالدردشة ✅", data=f"approve_{user.id}"),
                        Button.inline("حظر المستخدم 🚫", data=f"block_{user.id}"),
                    ],
                    parse_mode="html",
                )
            except MessageNotModifiedError:
                pass
        else:
            await e.eor(
                f"<b>{inline_mention(user, html=True)}</b> <code>المستخدم مرفوض بالأصل</code>",
                parse_mode="html",
            )


@Tepthon_cmd(pattern="بلوك( (.*)|$)", fullsudo=True)
async def blockpm(block):
    match = block.pattern_match.group(1).strip()
    if block.reply_to_msg_id:
        user = (await block.get_reply_message()).sender_id
    elif match:
        try:
            user = await block.client.parse_id(match)
        except Exception as er:
            return await block.eor(str(er))
    elif block.is_private:
        user = block.chat_id
    else:
        return await block.eor(NO_REPLY, time=10)

    await block.client(BlockRequest(user))
    aname = await block.client.get_entity(user)
    await block.eor(f"**⌔∮ المستخدم: {inline_mention(aname)}** [`{user}`]\n**❃ تم حظره من الدردشة معك في الخاص**")
    try:
        keym.remove(user)
    except AttributeError:
        pass
    try:
        await tgbot.edit_message(
            jmdB.get_key("LOG_CHAT"),
            _not_approved[user],
            f"#بلوك\n\n**⌔∮ المستخدم: {inline_mention(aname)}** [`{user}`]\n**❃  تم حظره من الخاص بنجاح**",
            buttons=[
                Button.inline("إلغاء البلوك 🔔", data=f"unblock_{user}"),
            ],
        )
    except KeyError:
        _not_approved[user] = await tgbot.send_message(
            jmdB.get_key("LOG_CHAT"),
            f"#بلوك\n\n**⌔∮ المستخدم: {inline_mention(aname)}** [`{user}`]\n**❃ تم حظره من الخاص بنجاح**",
            buttons=[
                Button.inline("إلغاء البلوك 🔔", data=f"unblock_{user}"),
            ],
        )
    except MessageNotModifiedError:
        pass


@Tepthon_cmd(pattern="الغاء البلوك( (.*)|$)", fullsudo=True)
async def unblockpm(event):
    match = event.pattern_match.group(1).strip()
    reply = await event.get_reply_message()
    if reply:
        user = reply.sender_id
    elif match:
        if match == "للكل":
            msg = await event.eor("**⎆ جـاري إلغـاء حظر المستخدم من الخاص...**")
            u_s = await event.client(GetBlockedRequest(0, 0))
            count = len(u_s.users)
            if not count:
                return await msg.eor("**⎆ كـم أنـت حنون 😍، لا يوجد محظورين لفك الحظر عنهم**")
            for user in u_s.users:
                await asyncio.sleep(1)
                await event.client(UnblockRequest(user.id))
            # GetBlockedRequest return 20 users at most.
            if count < 20:
                return await msg.eor(f"**⌔∮ تم بنجاح الغاء حظر {count} من المستخدمين من الخاص**")
            while u_s.users:
                u_s = await event.client(GetBlockedRequest(0, 0))
                for user in u_s.users:
                    await asyncio.sleep(3)
                    await event.client(UnblockRequest(user.id))
                count += len(u_s.users)
            return await msg.eor(f"**⌔∮ تم بنجاح الغاء حظر {count} من المستخدمين من الخاص**")

        try:
            user = await event.client.parse_id(match)
        except Exception as er:
            return await event.eor(str(er))
    elif event.is_private:
        user = event.chat_id
    else:
        return await event.eor(NO_REPLY, time=10)
    try:
        await event.client(UnblockRequest(user))
        aname = await event.client.get_entity(user)
        await event.eor(f"**⌔∮ المستخدم:{inline_mention(aname)}** [`{user}`]\n**❃ تم إلغـاء حظره من الخاص بنجاح**")
    except Exception as et:
        return await event.eor(f"ERROR - {et}")
    try:
        await tgbot.edit_message(
            jmdB.get_key("LOG_CHAT"),
            _not_approved[user],
            f"#إلغاء_البلوك\n\n**⌔∮ المستخدم: {inline_mention(aname)}** [`{user}`]\n**❃ لقد تم إلغـاء حظره من الخاص بنجاح**",
            buttons=[
                Button.inline("حظر المستخدم 🚫", data=f"block_{user}"),
            ],
        )
    except KeyError:
        _not_approved[user] = await tgbot.send_message(
            jmdB.get_key("LOG_CHAT"),
            f"#إلغاء_البلوك\n\n**⌔∮ المستخدم: {inline_mention(aname)}** [`{user}`]\n**❃ لقد تم إلغـاء حظره من الخاص بنجاح**",
            buttons=[
                Button.inline("حظر المستخدم 🚫", data=f"block_{user}"),
            ],
        )
    except MessageNotModifiedError:
        pass


@Tepthon_cmd(pattern="قائمة المسموحين$", owner=True)
async def list_approved(event):
    xx = await event.eor("**⎆ جـاري جلب قائمـة المسموحين...**")
    all = keym.get()
    if not all:
        return await xx.eor("**هممممم، لا يوجد مستخدمين مسموحين لديك 💔**", time=5)
    users = []
    for i in all:
        try:
            name = get_display_name(await jmubot.get_entity(i))
        except BaseException:
            name = ""
        users.append([name.strip(), str(i)])
    with open("المسموحين.txt", "w") as list_appr:
        if tabulate:
            list_appr.write(
                tabulate(
                    users,
                    headers=[
                        "الـمعـرف",
                        "الأيـدي"],
                    showindex="always")
            )
        else:
            text = "".join(f"[{user[-1]}] - {user[0]}" for user in users)
            list_appr.write(text)
    await event.reply(
        f"**⌔∮ قائمة المستخدمين المسموح لهم بالدردشة مع [{OWNER_NAME}](tg://user?id={OWNER_ID})**",
        file="المسموحين.txt",
    )

    await xx.delete()
    remove("المسموحين.txt")


@callback(
    re.compile(
        b"approve_(.*)",
    ),
    from_users=[jmubot.uid],
)
async def apr_in(event):
    uid = int(event.data_match.group(1).decode("UTF-8"))
    if uid in DEVLIST:
        await event.edit("**هذا المطور تم السماح له بالدردشة معك فورًا!!**")
    if not keym.contains(uid):
        keym.add(uid)
        try:
            await jmubot.edit_folder(uid, folder=0)
        except BaseException:
            pass
        try:
            user = await jmubot.get_entity(uid)
        except BaseException:
            return await event.delete()
        await event.edit(
            f"#السماح\n\n<b>{inline_mention(user, html=True)}</b> [<code>{user.id}</code>] <code>تم السماح له بالدردشة معك</code>",
            buttons=[
                [
                    Button.inline("رفض المستخدم ❌", data=f"disapprove_{uid}"),
                    Button.inline("حظر المستخدم 🚫", data=f"block_{uid}"),
                ],
            ],
            parse_mode="html",
        )
        await delete_pm_warn_msgs(uid)
        await event.answer("**⎆ تم السماح للمستخدم بالدردشـة معك**", alert=True)
    else:
        await event.edit(
            "**⎆ هذا المستخدم مسموح بالدردشة له بالأصل**",
            buttons=[
                [
                    Button.inline("رفض المستخدم ❌", data=f"disapprove_{uid}"),
                    Button.inline("حظر المستخدم 🚫", data=f"block_{uid}"),
                ],
            ],
        )


@callback(
    re.compile(
        b"disapprove_(.*)",
    ),
    from_users=[jmubot.uid],
)
async def disapr_in(event):
    uid = int(event.data_match.group(1).decode("UTF-8"))
    if keym.contains(uid):
        keym.remove(uid)
        try:
            user = await jmubot.get_entity(uid)
        except BaseException:
            return await event.delete()
        await event.edit(
            f"#رفض\n\n<b>{inline_mention(user, html=True)}</b> [<code>{user.id}</code>] <code>تم رفض المستخدم من الدردشة معك</code>",
            buttons=[
                [
                    Button.inline("السماح بالدردشة ✅", data=f"approve_{uid}"),
                    Button.inline("حظر المستخدم 🚫", data=f"block_{uid}"),
                ],
            ],
            parse_mode="html",
        )
        await event.answer("**تم بنجـاح رفـض هذا المستخدم ❌**", alert=True)
    else:
        await event.edit(
            "**⌔∮ المستخدم لم يتم السماح له بالدردشة أصلًا**",
            buttons=[
                [
                    Button.inline("رفض المستخدم ❌", data=f"disapprove_{uid}"),
                    Button.inline("حظر المستخدم ✅", data=f"block_{uid}"),
                ],
            ],
        )


@callback(
    re.compile(
        b"block_(.*)",
    ),
    from_users=[jmubot.uid],
)
async def blck_in(event):
    uid = int(event.data_match.group(1).decode("UTF-8"))
    try:
        await jmubot(BlockRequest(uid))
    except BaseException:
        pass
    try:
        user = await jmubot.get_entity(uid)
    except BaseException:
        return await event.delete()
    await event.edit(
        f"#بلوك\n\n<b>{inline_mention(user, html=True)}</b> [<code>{user.id}</code>] <code>تم حظر المستخدم من الخاص</code>",
        buttons=Button.inline("إلغاء الحظر ❌", data=f"unblock_{uid}"),
        parse_mode="html",
    )
    await event.answer("⎆ تم حظر المستخدم بنجاح 🔕", alert=True)


@callback(
    re.compile(
        b"unblock_(.*)",
    ),
    from_users=[jmubot.uid],
)
async def unblck_in(event):
    uid = int(event.data_match.group(1).decode("UTF-8"))
    try:
        await jmubot(UnblockRequest(uid))
    except BaseException:
        pass
    try:
        user = await jmubot.get_entity(uid)
    except BaseException:
        return await event.delete()
    await event.edit(
        f"#إلغاء_حظر\n\n<b>{inline_mention(user, html=True)}</b> [<code>{user.id}</code>] <code>تم إلغـاء حظره من الخاص</code>",
        buttons=Button.inline("حظر المستخدم 🚫", data=f"block_{uid}"),
        parse_mode="html",
    )
    await event.answer("Unblocked.", alert=True)


@in_pattern(re.compile("ip_(.*)"), owner=True)
async def in_pm_ans(event):
    from_user = int(event.pattern_match.group(1).strip())
    try:
        warns = U_WARNS[from_user]
    except Exception as e:
        LOGS.info(e)
        warns = "?"
    try:
        msg_ = WARN_MSGS[from_user]
    except KeyError:
        msg_ = "**⌔∮ نظام حماية تيبثـون الخاص بـ {OWNER_NAME}**"
    wrns = f"{warns}/{WARNS}"
    buttons = [
        [
            Button.inline("كشف", data=f"admin_only{from_user}"),
            Button.inline(wrns, data=f"don_{wrns}"),
        ]
    ]
    include_media = True
    mime_type, res = None, None
    cont = None
    try:
        ext = PMPIC.split(".")[-1].lower()
    except (AttributeError, IndexError):
        ext = None
    if ext in ["img", "jpg", "png"]:
        type = "photo"
        mime_type = "image/jpg"
    elif ext in ["mp4", "mkv", "gif"]:
        mime_type = "video/mp4"
        type = "gif"
    else:
        try:
            res = resolve_bot_file_id(PMPIC)
        except ValueError:
            pass
        if res:
            res = [
                await event.builder.document(
                    res,
                    title="نظام حماية تيبثون الأنلاين",
                    description="~ @Tepthon",
                    text=msg_,
                    buttons=buttons,
                    link_preview=False,
                )
            ]
        else:
            type = "article"
            include_media = False
    if not res:
        if include_media:
            cont = types.InputWebDocument(PMPIC, 0, mime_type, [])
        res = [
            event.builder.article(
                title="نظام حماية تيبثون الأنلاين",
                type=type,
                text=msg_,
                description="~ @Tepthon",
                include_media=include_media,
                buttons=buttons,
                thumb=cont,
                content=cont,
            )
        ]
    await event.answer(res, switch_pm="• Tepthon •", switch_pm_param="start")


@callback(re.compile("admin_only(.*)"), from_users=[jmubot.uid])
async def _admin_tools(event):
    chat = int(event.pattern_match.group(1).strip())
    await event.edit(
        buttons=[
            [
                Button.inline("السماح بالدردشة ✅", data=f"approve_{chat}"),
                Button.inline("حظر المستخدم 🚫", data=f"block_{chat}"),
            ],
            [Button.inline("« رجوع", data=f"pmbk_{chat}")],
        ],
    )


@callback(re.compile("don_(.*)"))
async def _mejik(e):
    data = e.pattern_match.group(1).strip().decode("utf-8").split("/")
    text = "👮‍♂ عدد التحذيرات : " + data[0]
    text += "\n🤖 عدد التحذيرات الكُلي : " + data[1]
    await e.answer(text, alert=True)


@callback(re.compile("pmbk_(.*)"))
async def edt(event):
    from_user = int(event.pattern_match.group(1).strip())
    try:
        warns = U_WARNS[from_user]
    except Exception as e:
        LOGS.info(str(e))
        warns = "0"
    wrns = f"{warns}/{WARNS}"
    await event.edit(
        buttons=[
            [
                Button.inline("التحذيرات", data=f"admin_only{from_user}"),
                Button.inline(wrns, data=f"don_{wrns}"),
            ]
        ],
        )
