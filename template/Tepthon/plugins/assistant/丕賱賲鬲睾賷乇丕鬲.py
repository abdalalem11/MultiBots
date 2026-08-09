import ast
import re
import sys
import time
from asyncio.exceptions import TimeoutError as AsyncTimeOut
from os import remove
import requests
from telegraph import upload_file as upl
from telethon import Button, events
from database import JmdB

from telethon.tl.types import MessageMediaWebPage
from telethon.utils import get_peer_id
from .. import HNDLR, LOGS
from . import *

from telethon.tl import types


def text_to_url(event):
    if isinstance(event.media, MessageMediaWebPage):
        webpage = event.media.webpage
        if not isinstance(webpage, types.WebPageEmpty) and webpage.type in ["photo"]:
            return webpage.display_url
    return event.text


async def setit(event, name, value):
    try:
        JmdB.set_key(name, value)
    except BaseException as er:
        LOGS.exception(er)
        return await event.edit("**⎆ لقد حدث خطأ ما أثناء تغيير قيمة المتغير**")


_buttons = {
    "otvars": {
        "text": "⎆ من هنا يمكنك تعديل المتغيرات/الفارات الخاصة بسورس تيبثون",
        "buttons": [
            [
                Button.inline("كروب التخزين", data="taglog"),
                Button.inline("البايو/النبذة", data="bioacount"),
            ],
            [
                Button.inline("وضع التحكم", data="sudo"),
                Button.inline("رمز الاوامر", data="hhndlr"),
            ],

            [
                Button.inline("صورة الأنلاين", data="inli_pic"),
                Button.inline("رمز اوامر المتحكم", data="shndlr"),
            ],
            [Button.inline("رجـوع", data="setter")],
        ],
    },
    "apauto": {
        "text": f"⎆ من هنا يمكنك تفعيل السماح التلقائي أو تعطيله عند تفعيل هذا المتغير عندما يراسلك شخص وأنت قد فعلت نظام حماية الخاص وقتها سيمكنك السماح للشخص بالدردشة معك فقط عبر أن تراسله في الخاص بدلًا من إرسال أمـر `{HNDLR}سماح`",
        "buttons": [
            [Button.inline("تشغيل السماح التلقائي", data="apon")],
            [Button.inline("تعطيل السماح التلقائي", data="apof")],
            [Button.inline("رجـوع", data="cbs_pmcstm")],
        ],
    },
    "alvcstm": {
        "text": f"⎆ من هنا يمكنك تخصيص أمر `{HNDLR}فحص.`",
        "buttons": [
            #[Button.inline("كليشة الفحص", data="abs_alvtx")],
            [Button.inline("صورة الفحص", data="alvmed")],
            [Button.inline("حذف صورة الفحص", data="delmed")],
            [Button.inline("رجـوع", data="setter")],
        ],
    },
    "pmcstm": {
        "text": "⎆ من هنا يمكنك إعـداد وتنسيق متغيرات نظام حماية الخاص",
        "buttons": [
            [
                Button.inline("كليشة الحماية", data="pmtxt"),
                Button.inline("صورة الحماية", data="pmmed"),
            ],
            [
                Button.inline("السماح التلقائي", data="cbs_apauto"),
            ],
            [
                Button.inline("عدد التحذيرات", data="swarn"),
                Button.inline("حذف صورة الحماية", data="delpmmed"),
            ],
            [Button.inline("نوع نظام الحماية", data="cbs_pmtype")],
            [Button.inline("رجـوع", data="cbs_ppmset")],
        ],
    },
    "pmtype": {
        "text": "⎆ من هنا يمكنك إعداد نوع نظام الحماية الذي سيظهر لمن يراسلك بعد تشغيل النظام.",
        "buttons": [
            [Button.inline("صيغة الأنلاين", data="inpm_in")],
            [Button.inline("الصيغة العادية", data="inpm_no")],
            [Button.inline("رجـوع", data="cbs_pmcstm")],
        ],
    },
    "ppmset": {
        "text": "⎆ من هنا يمكنك إعداد نظام أوامر حماية الخاص :",
        "buttons": [
            [Button.inline("تشغيل حماية الخاص", data="pmon")],
            [Button.inline("تعطيل حماية الخاص", data="pmoff")],
            [Button.inline("تخصيص حماية الخاص", data="cbs_pmcstm")],
            [Button.inline("رجـوع", data="setter")],
        ],
    },
    "chatbot": {
        "text": "⎆ من هنا يمكنك إعداد تخصيص البوت المساعد الخاص بك",
        "buttons": [
            [
                Button.inline("رسالة الترحيب", data="bwel"),
                Button.inline("صورة الترحيب", data="botmew"),
            ],
            [Button.inline("كليشة معلومات البوت", data="botinfe")],
            [Button.inline("الاشتراك الإجـباري", data="pmfs")],
            [Button.inline("رجـوع", data="setter")],
        ],
    },
}

_convo = {
    "settag": {
        "var": "TAG_LOG",
        "name": "مجموعة التخزين",
        "text": f"⎆ اصنع مجموعة وأضف البوت المساعد الخاص بك بها وارفعه مشرف.\nأرسل `{HNDLR}ايدي` في المجموعة التي صنعتها وسيظهر لك ايدي المجموعة انسخه وأرسله هنا.\n\nأرسل الغاء لإلغاء العملية.",
        "back": "taglog",
    },
    "bioset": {
        "var": "MYBIO",
        "name": "نبذة الحساب",
        "text": f"⎆ من هنا يمكنك وضع او تغيير نبذة الحساب التي ستسخدم في بعض الاوامر مثل وضع هذه النبذة لأمر البايو الوقتي\n\nأرسل الغاء لإلغاء العملية.",
        "back": "bioacount",
    },
    "alvtx": {
        "var": "ALIVE_TEXT",
        "name": "كليشة الفحص",
        "text": f"**⎆ لتغيير كليشة/رسالة الفحص عندما ترسل امر** `{HNDLR}فحص` \n\nرسل الغاء لإلغاء العملية.",
        "back": "cbs_alvcstm",
    },
}


@callback(re.compile("cbs_(.*)"), owner=True)
async def _edit_to(event):
    match = event.data_match.group(1).decode("utf-8")
    data = _buttons.get(match)
    if not data:
        return
    await event.edit(data["text"], buttons=data["buttons"], link_preview=False)


@callback(re.compile("abs_(.*)"), owner=True)
async def convo_handler(event: events.CallbackQuery):
    match = event.data_match.group(1).decode("utf-8")
    if not _convo.get(match):
        return
    await event.delete()
    get_ = _convo[match]
    back = get_["back"]
    async with event.client.conversation(event.sender_id) as conv:
        await conv.send_message(get_["text"])
        response = await conv.get_response()
        themssg = response.message
        try:
            themssg = ast.literal_eval(themssg)
        except Exception:
            pass
        if themssg == "الغاء":
            return await conv.send_message(
                "**⎆ تم بنجـاح إلغاء العملية**",
                buttons=get_back_button(back),
            )
        await setit(event, get_["var"], themssg)
        await conv.send_message(
            f"**⎆ تم بنجاح تغيير {get_['name']} الى** `{themssg}`",
            buttons=get_back_button(back),
        )



@callback("hhndlr", owner=True)
async def hndlrr(event):
    await event.delete()
    pru = event.sender_id
    var = "HNDLR"
    name = "رمز الأوامر"
    async with event.client.conversation(pru) as conv:
        await conv.send_message(
            f"⎆ أرسل الرمز الذي تريد استخدامه قبل كتابة الاوامر\n❃ الرمز الحالي هو [ `{HNDLR}` ]\n\n أرسل الغاء لإلغاء العملية.",
        )
        response = conv.wait_event(events.NewMessage(chats=pru))
        response = await response
        themssg = response.message.message
        if themssg == "الغاء":
            await conv.send_message(
                "**⎆ تم بنجـاح إلغاء تنفيذ العملية**",
                buttons=get_back_button("cbs_otvars"),
            )
        elif len(themssg) > 1:
            await conv.send_message(
                "⎆ يجب عليك أرسال الرمز بشكل صحيح",
                buttons=get_back_button("cbs_otvars"),
            )
        elif themssg.startswith(("/", "#", "@")):
            await conv.send_message(
                "⎆ لا يمكن أستخدام هذه الرموز",
                buttons=get_back_button("cbs_otvars"),
            )
        else:
            await setit(event, var, themssg)
            await conv.send_message(
                f"**⎆ تم بنجاح تغيير {name} الى {themssg}**",
                buttons=get_back_button("cbs_otvars"),
            )


@callback("shndlr", owner=True)
async def hndlrr(event):
    await event.delete()
    pru = event.sender_id
    var = "SUDO_HNDLR"
    name = "رمز اوامر المتحكم"
    async with event.client.conversation(pru) as conv:
        await conv.send_message(
            f"⎆ أرسل الرمز الذي تريد استخدامه للمستخدم المتحكم\n\n أرسل الغاء لإلغاء العملية.",
        )

        response = conv.wait_event(events.NewMessage(chats=pru))
        response = await response
        themssg = response.message.message
        if themssg == "الغاء":
            await conv.send_message(
                "**⎆ تم بنجـاح إلغاء تنفيذ العملية**",
                buttons=get_back_button("cbs_otvars"),
            )
        elif len(themssg) > 1:
            await conv.send_message(
                "⎆ يجب عليك استخدام رمز بشكل صحيح",
                buttons=get_back_button("cbs_otvars"),
            )
        elif themssg.startswith(("/", "#", "@")):
            await conv.send_message(
                "⎆ لا يمكن استخدام هذه الرموز حاول بغيرها",
                buttons=get_back_button("cbs_otvars"),
            )
        else:
            await setit(event, var, themssg)
            await conv.send_message(
                f"**⎆ تم بنجاح تغيير {name} الى {themssg}**",
                buttons=get_back_button("cbs_otvars"),
            )


@callback("taglog", owner=True)
async def tagloggrr(e):
    BUTTON = [
        [Button.inline("تغيير مجموعة التخزين", data="abs_settag")],
        get_back_button("cbs_otvars"),
    ]
    await e.edit(
        "⎆ اختر من الاعدادات من الاسفل",
        buttons=BUTTON,
    )

@callback("bioacount", owner=True)
async def bioacount(e):
    BUTTON = [
        [Button.inline("تغيير نبذة الحساب", data="abs_bioset")],
        get_back_button("cbs_otvars"),
    ]
    await e.edit(
        "⎆ اختر من الاعدادات من الاسفل",
        buttons=BUTTON,
    )


@callback("sudo", owner=True)
async def pmset(event):
    BT = (
        [Button.inline("تعطيل وضع المتحكم", data="ofsudo")]
        if JmdB.get_key("SUDO")
        else [Button.inline("تشغيل وضع المتحكم", data="onsudo")]
    )

    await event.edit(
        f"⎆ وضع المتحكم يتيح للمستخدم ان يقوم باستخدام الاوامر التي في حسابك عبر حسابه اي يصبح حسابك كـ بوت له أرسل `{HNDLR}الاوامر المتحكم` للتعرف اكثر",
        buttons=[
            BT,
            [Button.inline("رجـوع", data="cbs_otvars")],
        ],
    )


@callback("onsudo", owner=True)
async def eddon(event):
    var = "SUDO"
    await setit(event, var, "True")
    await event.edit(
        f"**⎆ تم بنجاح تشغيل نظام التحكم**\n\n❃ بعد اكمالك لتغيير المتغيرات أرسل  `{HNDLR}اعادة تشغيل`",
        buttons=get_back_button("sudo"),
    )


@callback("ofsudo", owner=True)
async def eddof(event):
    var = "SUDO"
    await setit(event, var, "False")
    await event.edit(
        f"**⎆ تم بنجاح تعطيل نظام التحكم**\n\n❃ بعد اكمالك لتغيير المتغيرات أرسل  `{HNDLR}اعادة تشغيل`",
        buttons=get_back_button("sudo"),
    )




@callback("alvmed", owner=True)
async def media(event):
    await event.delete()
    pru = event.sender_id
    var = "ALIVE_PIC"
    name = "صورة الفحص"
    async with event.client.conversation(pru) as conv:
        await conv.send_message(
            "⎆ لتغيير صورة او ميديا الفحص\n❃ أرسل صورة/متحركة/فيديو لوضعها مع امر الفحص.\n\nأرسل الغاء لإلغاء العملية.",
        )
        response = await conv.get_response()
        try:
            themssg = response.message
            if themssg == "الغاء":
                return await conv.send_message(
                    "**⎆ تم بنجـاح إلغاء تنفيذ العملية**",
                    buttons=get_back_button("cbs_alvcstm"),
                )
        except BaseException as er:
            LOGS.exception(er)
        if (
            not (response.text).startswith("/")
            and response.text != ""
            and (not response.media or isinstance(response.media, MessageMediaWebPage))
        ):
            url = text_to_url(response)
        elif response.sticker:
            url = response.file.id
        else:
            media = await event.client.download_media(response, "alvpc")
            try:
                url = up_catbox(media)
            except BaseException as er:
                LOGS.exception(er)
                return await conv.send_message(
                    "**⎆ لقد حدث خطأ ما**",
                    buttons=get_back_button("cbs_alvcstm"),
                )
        await setit(event, var, url)
        await conv.send_message(
            f"**⎆ تم بنجاح وضع {name}**",
            buttons=get_back_button("cbs_alvcstm"),
        )


@callback("delmed", owner=True)
async def dell(event):
    try:
        JmdB.del_key("ALIVE_PIC")
        return await event.edit("⎆ تم بنجاح ازالة صورة الفحص", buttons=get_back_button("cbs_alabs_vcstm"))
    except BaseException as er:
        LOGS.exception(er)
        return await event.edit(
            "⎆ لقد حدث خطأ ما حاول مجددا",
            buttons=get_back_button("cbs_alabs_vcstm"),
        )


@callback("inpm_in", owner=True)
async def inl_on(event):
    var = "INLINE_PM"
    await setit(event, var, "True")
    await event.edit(
        "⎆ تم بنجاح تغيير وضع حماية الخاص الى الأنلاين",
        buttons=[[Button.inline("رجوع", data="cbs_pmtype")]],
    )


@callback("inpm_no", owner=True)
async def inl_on(event):
    var = "INLINE_PM"
    await setit(event, var, "False")
    await event.edit(
        "⎆ تم بنجاح تغيير وضع حماية الخاص الى الوضع العادي",
        buttons=[[Button.inline("رجـوع", data="cbs_pmtype")]],
    )


@callback("pmtxt", owner=True)
async def name(event):
    await event.delete()
    pru = event.sender_id
    var = "PM_TEXT"
    name = "كليشة الحماية"
    async with event.client.conversation(pru) as conv:
        await conv.send_message(
            "**⎆ لتغيير كليشة حماية الخاص\n❃ أرسل الكليشة الجديدة الآن**.\n\n❃ يمكنك استخدام هذه ال `{name}` `{fullname}` `{count}` `{mention}` `{username}` \n\nأرسل الغاء لإلغاء العملية.",
        )
        response = conv.wait_event(events.NewMessage(chats=pru))
        response = await response
        themssg = response.message.message
        if themssg == "الغاء":
            return await conv.send_message(
                "**⎆ تم بنجـاح إلغاء تنفيذ العملية**",
                buttons=get_back_button("cbs_pmcstm"),
            )
        if len(themssg) > 4090:
            return await conv.send_message(
                "**⎆ الرسالة طويلة جدا يجب ان تكون أقصر من هذه**",
                buttons=get_back_button("cbs_pmcstm"),
            )
        await setit(event, var, themssg)
        await conv.send_message(
            f"⎆ تم بنجاح تغيير {name} الى `{themssg}`\n\n❃ الآن أرسل `{HNDLR}اعادة تشغيل`",
            buttons=get_back_button("cbs_pmcstm"),
        )


@callback("swarn", owner=True)
async def name(event):
    m = range(1, 10)
    jmbt = [Button.inline(f"{x}", data=f"wrns_{x}") for x in m]
    lst = list(zip(jmbt[::3], jmbt[1::3], jmbt[2::3]))
    lst.append([Button.inline("رجـوع", data="cbs_pmcstm")])
    await event.edit(
        "⎆ أختر عدد التحذيرات التي ستظهر للمستخدم قبل ان يتم حظره.",
        buttons=lst,
    )


@callback(re.compile(b"wrns_(.*)"), owner=True)
async def set_wrns(event):
    value = int(event.data_match.group(1).decode("UTF-8"))
    if dn := JmdB.set_key("PMWARNS", value):
        await event.edit(
            f"⎆ تم تغيير عدد التحذيرات الى {value}.\n❃ المستخدمين الجدد سيتم تحذيرهم {value} مرات قبل أن بتم حظرهم",
            buttons=get_back_button("cbs_pmcstm"),
        )
    else:
        await event.edit(
            f"⎆ لقد حدث خطأ ما يرجى التأكد من الامر `{HNDLR}لوك`",
            buttons=get_back_button("cbs_pmcstm"),
        )


@callback("pmmed", owner=True)
async def media(event):
    await event.delete()
    pru = event.sender_id
    var = "PMPIC"
    name = "صورة الحماية"
    async with event.client.conversation(pru) as conv:
        await conv.send_message(
            "**⎆ تغيير صورة حماية الخاص\n❃ أرسل الصورة/الفيديو/المتحركة التي تريد وضعها مع رسالة حماية الخاص**.\n\nأرسل الغاء لإلغاء العملية.",
        )
        response = await conv.get_response()
        try:
            themssg = response.message
            if themssg == "الغاء":
                return await conv.send_message(
                    "**⎆ تم بنجـاح إلغاء تنفيذ العملية**",
                    buttons=get_back_button("cbs_pmcstm"),
                )
        except BaseException as er:
            LOGS.exception(er)
        media = await event.client.download_media(response, "pmpc")
        if (
            not (response.text).startswith("/")
            and response.text != ""
            and (not response.media or isinstance(response.media, MessageMediaWebPage))
        ):
            url = text_to_url(response)
        elif response.sticker:
            url = response.file.id
        else:
            try:
                url = up_catbox(media)
            except BaseException as er:
                LOGS.exception(er)
                return await conv.send_message(
                    "⎆ لقد حدث خطأ ما يرجى التأكد من استخدامك.",
                    buttons=get_back_button("cbs_pmcstm"),
                )
        await setit(event, var, url)
        await conv.send_message(
            f"⎆ تم بنجاح وضع {name}",
            buttons=get_back_button("cbs_pmcstm"),
        )


@callback("delpmmed", owner=True)
async def dell(event):
    try:
        JmdB.del_key("PMPIC")
        return await event.edit("⎆ تم بنجاح حذف صورة/فيديو حماية الخاص", buttons=get_back_button("cbs_pmcstm"))
    except BaseException as er:
        LOGS.exception(er)
        return await event.edit("⎆ لقد حدث خطأ ما حاول مجددا",
            buttons=[[Button.inline("الاعدادات", data="setter")]],
        )


@callback("apon", owner=True)
async def apon(event):
    var = "AUTOAPPROVE"
    await setit(event, var, "True")
    await event.edit(
        "⎆ تم بنجاح تشغيل السماح التلقائي بمجرد ان تراسل الشخص سيتم السماح له",
        buttons=[[Button.inline("رجـوع", data="cbs_apauto")]],
    )


@callback("apof", owner=True)
async def apof(event):
    try:
        JmdB.set_key("AUTOAPPROVE", "False")
        return await event.edit(
            f"⎆ تم تعطيل السماح التلقائي يجب عليك الآن إرسال `{HNDLR}سماح`  للسماح للمستخدم",
            buttons=[[Button.inline("رجـوع", data="cbs_apauto")]],
        )
    except BaseException as er:
        LOGS.exception(er)
        return await event.edit(
            "⎆ لقد حدث خطأ ما حاول مجددا",
            buttons=[[Button.inline("الاعدادات", data="setter")]],
        )




@callback("pmon", owner=True)
async def pmonn(event):
    var = "PMSETTING"
    await setit(event, var, "True")
    await event.edit(
        "⎆ تم بنجاح تشغيل نظام حماية الخاص",
        buttons=[[Button.inline("رجـوع", data="cbs_ppmset")]],
    )


@callback("pmoff", owner=True)
async def pmofff(event):
    var = "PMSETTING"
    await setit(event, var, "False")
    await event.edit(
        "⎆ تم بنجاح تعطيل نظام حماية الخاص", 
        buttons=[[Button.inline("رجـوع", data="cbs_ppmset")]],
    )


@callback("botmew", owner=True)
async def hhh(e):
    async with e.client.conversation(e.chat_id) as conv:
        await conv.send_message("⎆ الآن أرسل الصورة او الفيديو التي تريد وضعها مع رسالة الترحيب البوت المساعد")
        msg = await conv.get_response()
        if not msg.media or msg.text.startswith("/"):
            return await conv.send_message(
                "⎆ تم إلغاء العملية", buttons=get_back_button("cbs_chatbot")
            )
        JmdB.set_key("STARTMEDIA", msg.file.id)
        await conv.send_message("⎆ تم بنجاح وضع الميديا لرسالة ترحيب البوت", buttons=get_back_button("cbs_chatbot"))


@callback("botinfe", owner=True)
async def hhh(e):
    async with e.client.conversation(e.chat_id) as conv:
        await conv.send_message(
            "⎆ الآن أرسل الكليشة التي تريد وضعها عندما يضغط مستخدم البوت المساعد على زر كشف معلوماتك\n\n❃  او أرسل `False` لازالة الزر بالأصل .."
        )
        msg = await conv.get_response()
        if msg.media or msg.text.startswith("/"):
            return await conv.send_message(
                "⎆ تم إلغاء العملية", buttons=get_back_button("cbs_chatbot")
            )
        JmdB.set_key("BOT_INFO_START", msg.text)
        await conv.send_message("Done!", buttons=get_back_button("cbs_chatbot"))


@callback("pmfs", owner=True)
async def heheh(event):
    Ll = []
    err = ""
    async with event.client.conversation(event.chat_id) as conv:
        await conv.send_message(
            "⎆ الآن أرسل ايدي القناة الخاصة بك التي تريد ان تكون ضمن الاشتراك الاجباري في البوت المساعد الخاص بك\n\n❃ أرسل `تعطيل` لالغاء الاشتراك الاجباري من البوت المساعد\n❃ أرسل الغاء لإلغاء العملية.."
        )
        await conv.send_message(
            "⎆ مثال على إرسال ايدي الدردشة لاكثر من قناة أرسل الايدي على هذا الترتيب: \n\n`-1001234567890\n-1003333333`"
        )
        try:
            msg = await conv.get_response()
        except AsyncTimeOut:
            return await conv.send_message("**⎆ انتهى الوقت أبدا مجددا /start**")
        if not msg.text or msg.text.startswith("/"):
            timyork = "تم إلغاء العملية بنجاح"
            if msg.text == "تعطيل":
                JmdB.del_key("PMBOT_FSUB")
                timyork = f"تم بنجاح الغاؤ الاشتراك الاجباري من البوت المساعد الآن أرسل `{HNDLR}اعادة تشغيل`"
            return await conv.send_message(
                "تم إلغاء العملية", buttons=get_back_button("cbs_chatbot")
            )
        for chat in msg.message.split("\n"):
            if chat.startswith("-") or chat.isdigit():
                chat = int(chat)
            try:
                CHSJSHS = await event.client.get_entity(chat)
                Ll.append(get_peer_id(CHSJSHS))
            except Exception as er:
                err += f"**{chat}** : {er}\n"
        if err:
            return await conv.send_message(err)
        JmdB.set_key("PMBOT_FSUB", str(Ll))
        await conv.send_message(
            f"تم بنجاح اضافة القناة الى الاشتراك الاجباري في البوت المساعد \nالآن أرسل `{HNDLR}اعادة تشغيل`.", buttons=get_back_button("cbs_chatbot")
        )


@callback("bwel", owner=True)
async def name(event):
    await event.delete()
    pru = event.sender_id
    var = "STARTMSG"
    name = "رسالة ترحيب البوت المساعد"
    async with event.client.conversation(pru) as conv:
        await conv.send_message(
            "**⎆ تغيير رسالة ترحيب البوتالمساعد\n❃ الآن أرسل الكليشة التي تريد ان تظهر عندما يشغل احد ما البوت المساعد الخاص بك.\n❃ يمكنك استعمال هذه الاضافات في الكليشة `{me}` - لاظهار حسابك `{mention}` - لعمل منشن للمستخدم \nأرسل الغاء لإلغاء العملية.",
        )
        response = conv.wait_event(events.NewMessage(chats=pru))
        response = await response
        themssg = response.message.message
        if themssg == "الغاء":
            return await conv.send_message(
                "**⎆ تم بنجـاح إلغاء تنفيذ العملية**",
                buttons=get_back_button("cbs_chatbot"),
            )
        await setit(event, var, themssg)
        await conv.send_message(
            f"⎆ تم بنجاح تغيير {name} الى {themssg}",
            buttons=get_back_button("cbs_chatbot"),
        )



@callback("inli_pic", owner=True)
async def media(event):
    await event.delete()
    pru = event.sender_id
    var = "INLINE_PIC"
    name = "صورة/فيديو الأنلاين"
    async with event.client.conversation(pru) as conv:
        await conv.send_message(
            "**⎆ تغيير صورة/فيديو الأنلاين**\n❃ أرسل الآن فيديو/صورة/متحركة لوضعها مع أزرار الآنلاين في السورس\n\nأرسل الغاء لإلغاء العملية.",
        )
        response = await conv.get_response()
        try:
            themssg = response.message
            if themssg == "الغاء":
                return await conv.send_message(
                    "**⎆ تم بنجـاح إلغاء تنفيذ العملية**",
                    buttons=get_back_button("setter"),
                )
        except BaseException as er:
            LOGS.exception(er)
        media = await event.client.download_media(response, "inlpic")
        if (
            not (response.text).startswith("/")
            and response.text != ""
            and (not response.media or isinstance(response.media, MessageMediaWebPage))
        ):
            url = text_to_url(response)
        else:
            try:
                url = up_catbox(media)
            except BaseException as er:
                LOGS.exception(er)
                return await conv.send_message(
                    "لقد تم إلغاء العملية بسبب ما",
                    buttons=get_back_button("setter"),
                )
        await setit(event, var, url)
        await conv.send_message(
            f"⎆ تم بنجاح تغيير {name} .",
            buttons=get_back_button("setter"),
)
