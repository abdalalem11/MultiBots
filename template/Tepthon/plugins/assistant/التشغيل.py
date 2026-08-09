import contextlib, re
from datetime import datetime

from telethon import Button, events
from telethon.errors.rpcerrorlist import MessageDeleteForbiddenError
from telethon.utils import get_display_name

from Tepthon import LOGS, jmubot, HNDLR
from Tepthon.decorators import fullsudos, owner_and_sudos 
from Tepthon.config import version
from database import JmdB
from database.core.settings import KeySettings

from . import *


async def get_stored_file(event, hash):
    KeySet = KeySettings("FILE_STORE", cast=dict)
    msg_id = KeySet.get_child(hash)
    if not msg_id:
        return
    try:
        msg = await tgbot.get_messages(JmdB.get_config("LOG_CHAT"), ids=msg_id)
    except Exception as er:
        LOGS.warning(f"حدث خطأ أثناء تخزين الملف: {er}")
        return
    if not msg:
        return await tgbot.send_message(
            event.chat_id, "**⎆ تم حذف الرسالة بواسطة المالك**", reply_to=event.id
        )
    await tgbot.send_message(event.chat_id, msg.text, file=msg.media, reply_to=event.id)


def get_start_message():
    Owner_info_msg = JmdB.get_key("BOT_INFO_START")
    _custom = True
    if Owner_info_msg is None:
        _custom = False
        Owner_info_msg = f"""
**❃ مالك الحساب**: {jmubot.full_name}
**❃ ايدي المالك**: `{jmubot.uid}`

**❃ نظام التواصل**: {JmdB.get_key("PMBOT")}

**❃ سورس تيبثون: [v{version}] ، @Tepthon**
"""
    return Owner_info_msg, _custom


_start = [
    [
        Button.inline("الإعدادات ⚙️", data="setter"),
    ],
    [
        Button.inline("الحـالة ✨", data="stat"),
        Button.inline("الإذاعـة 📻", data="bcast"),
    ],
    [Button.inline("المنطقة الزمنية 🌎", data="tz")],
]


@callback("ownerinfo")
async def own(event):
    message, custom = get_start_message()
    msg = message.format(
        mention=inline_mention(event.sender), me=inline_mention(jmubot.me)
    )
    if custom:
        msg += "\n\n❃ تم صنعه بواسطة: **@Tepthon**"
    await event.edit(
        msg,
        buttons=Button.inline("اغلاق", data="closeit"),
        link_preview=False,
    )


@callback("closeit")
async def closet(lol):
    try:
        await lol.delete()
    except MessageDeleteForbiddenError:
        await lol.answer("الرسالة قديمة جدا لغلقها احذفها بنفسك", alert=True)


@tgbot_cmd(pattern="start( (.*)|$)", forwards=False, func=lambda x: not x.is_group)
async def Tepthon_handler(event):
    args = event.pattern_match.group(1).strip()
    KeySet = KeySettings("BOT_USERS", cast=list)
    if not KeySet.contains(event.sender_id) and event.sender_id not in owner_and_sudos():
        KeySet.add(event.sender_id)
        moh_Jm = JmdB.get_key("OFF_START_LOG")
        if not moh_Jm or moh_Jm != True:
            msg = f"**❃ مستخدم جديد:** {inline_mention(event.sender)} `[{event.sender_id}]`\n❃ شَغل  [البوت المساعد](@{tgbot.me.username})."
            buttons = [[Button.inline("معلومات المستخدم", "toaslJm")]]
            if event.sender.username:
                buttons[0].append(
                    Button.mention(
                        "المستخدم", await event.client.get_input_entity(event.sender_id)
                    )
                )
            await event.client.send_message(
                JmdB.get_config("LOG_CHAT"), msg, buttons=buttons
            )
    if event.sender_id not in fullsudos():
        ok = ""
        me = inline_mention(jmubot.me)
        mention = inline_mention(event.sender)
        if args and args != "set":
            await get_stored_file(event, args)
        if _starts := JmdB.get_key("STARTMSG"):
            msg = _starts
        else:
            if JmdB.get_key("PMBOT"):
                ok = "⎆ يمكنك التواصل مع صاحب البوت من هنا أرسل رسالتك وانتظـر الرد ..."
            msg = f"مرحبًـا بـك {mention} ، هذا هو البوت المساعد لـ {me}\n\n{ok}"
        await event.reply(
            msg.format(me=me, mention=mention),
            file=JmdB.get_key("STARTMEDIA"),
            buttons=(
                Button.inline("معلومات", data="ownerinfo")
                if (get_start_message()[0])
                else None
            ),
        )
    else:
        name = get_display_name(event.sender)
        if args == "set":
            await event.reply(
                "يرجى الاختيار من الإعدادات من الأسفل",
                buttons=_settings
            )
            return
        elif args == "_manager":

            with contextlib.suppress(ImportError):
                from modules.manager._help import START, get_buttons

                await event.reply(START, buttons=get_buttons())
        elif args:
            await get_stored_file(event, args)
            return

        await event.reply(
            "أهلا {}. يرجى التصفح من الخيارات مم الأسفل".format(name),
            buttons=_start,
        )


@callback("toaslJm", owner=True)
async def toasl_notif(e):
    text = f"عندما يدخل مستخدم جديد إلى البوت المساعد سيصل أشعار اليك\n\nلتعطيله أرسل : {HNDLR} OFF_START_LOG"
    await e.answer(text, alert=True)


@callback("mainmenu", owner=True, func=lambda x: not x.is_group)
async def Tepthon(event):
    await event.edit(
        "مرحبا بك {}. يرجى الاختيار من الإعدادات من الاسفل", get_display_name(event.sender),
        buttons=_start,
    )


@callback("stat", owner=True)
async def bot_stat(event):
    ok = len(JmdB.get_key("BOT_USERS") or [])
    msg = """حـالة البـوت المساعـد من تيبثـون
عدد المستخدمين:  {}""".format(
        ok,
    )
    await event.answer(msg, cache_time=0, alert=True)


@callback("bcast", owner=True)
async def bdcast_msg(event):
    KeySet = KeySettings("BOT_USERS", cast=list)
    total = KeySet.count()
    await event.edit(f"**⎆ الأذاعة إلى {total} من المستخدمين**.")
    async with event.client.conversation(event.sender_id) as conv:
        await conv.send_message(
            "**⎆ الآن أرسل الرسالة التي تريد عمل إذاعـة لها لمستخدمي بوتك.**\nأرسل `الغاء` لألغاء الأذاعة.",
        )
        response = await conv.get_response()
        if response.message == "الغاء":
            return await conv.send_message("**⎆ تم الغاء الأذاعة بنجاح**")
        success = 0
        fail = 0
        await conv.send_message(f"**⎆ ستتم الإذاعة إلى {total} من المستخدمين**")
        start = datetime.now()
        for i in KeySet.get():
            try:
                await tgbot.send_message(int(i), response)
                success += 1
            except BaseException:
                fail += 1
        end = datetime.now()
        time_taken = (end - start).seconds
        await conv.send_message(
            f"""
**⎆ تم الإذاعة في {time_taken} من الثواني.**
**⎆ عدد المستخدمين: {total}**
**⎆ تم الإذاعة إلى ** : `{success}`
**⎆ فشل الاذاعة إلى** : `{fail}`""",
        )



_settings = [
    [
        Button.inline("المتغيرات الرئيسية", data="cbs_otvars"),
        Button.inline("البوت المساعد", data="cbs_chatbot"),
    ],
    [
        Button.inline("متغيرات الفحص", data="cbs_alvcstm"),
        Button.inline("متغيرات حماية الخاص", data="cbs_ppmset"),
    ],
    [Button.inline("رجوع", data="mainmenu")],
]


@callback("setter", owner=True)
async def setting(event):
    await event.edit(
        "يرجى الاختيار من الإعدادات من الاسفل",
        buttons=_settings,
    )



@callback("tz", owner=True)
async def timezone_moh(event):
    from pytz import timezone

    await event.delete()

    pru = event.sender_id
    var = "TIMEZONE"
    name = "المنطقة الزمنية"
    async with event.client.conversation(pru) as conv:
        await conv.send_message(
            "أرسل المنطقة الزمنية الخاصة بك الآن على هذا المثال  :  القارة/عاصمة بلدك بالإنجليزية \n\nمثال من العراق أرسل `Asia/Baghdad`"
        )
        response = conv.wait_event(events.NewMessage(chats=pru))
        response = await response
        themssg = response.message.message
        if themssg == "الغاء":
            return await conv.send_message(
                "تم الإلغاء بنجاح",
                buttons=get_back_button("mainmenu"),
            )
        try:
            timezone(themssg)
            JmdB.set_key(var, themssg)
            await conv.send_message(
                f"**⎆ {name} تم تغييرها إلى {themssg}**\n",
                buttons=get_back_button("mainmenu"),
            )
        except BaseException:
            await conv.send_message(
                "**⎆ حـدث خطأ في المنطقة الزمنية حاول مجددًا بشكل صحيح**",
                buttons=get_back_button("mainmenu"),
            )
