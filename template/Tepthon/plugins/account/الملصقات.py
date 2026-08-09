"""
**الملصقــات - 𝗦𝗧𝗜𝗖𝗞𝗘𝗥𝗦**
———————×——————————
❃ `{i}ستيكر` [الرد على: صورة/ملصق/نص]
    لـ صنع حزمة ملصقات وإضافة الصورة أو النص أو الملصق الذي تم الرد عليه

❃ `{i}حزمة` <اسم الحزمة>
    لـ سرقة الحزمة التي تم الرد عليها وصنع حزمة جديدة لك منها

❃ `{i}الحزم`
    لـعرض قائمة حُزم الملصقات التي تم صنعها
"""

import glob
import io
import os
import contextlib
import random, string 
from secrets import token_hex

from telethon import errors 
from telethon.tl import functions, types
from telethon.errors.rpcerrorlist import StickersetInvalidError
from telethon.tl.functions.messages import GetStickerSetRequest as GetSticker
from telethon.tl.functions.messages import UploadMediaRequest
from telethon.tl.functions.stickers import AddStickerToSetRequest as AddSticker
from telethon.tl.functions.stickers import CreateStickerSetRequest
from telethon.tl.types import (
    DocumentAttributeSticker,
    InputPeerSelf,
    InputStickerSetEmpty,
)
from telethon.errors import StickersetInvalidError, PackShortNameInvalidError, PeerIdInvalidError
from telethon.tl.types import InputStickerSetItem as SetItem
from telethon.tl.types import InputStickerSetShortName, User, InputPeerSelf
from telethon.utils import get_display_name, get_extension, get_input_document

from Tepthon.helper.tools import resize_photo_sticker

from .. import LOGS, tgbot, fetch, jmdB, Tepthon_cmd, inline_mention, create_quotly


async def packExists(packId):
    source = await fetch(f"https://t.me/addstickers/{packId}")
    return (
        not b"""<div class="tgme_page_description">
  A <strong>Telegram</strong> user has created the <strong>Sticker&nbsp;Set</strong>.
</div>"""
        in source
    )


async def GetUniquePackName():
    packName = f"{random.choice(string.ascii_lowercase)}{token_hex(random.randint(4, 8))}_by_{tgbot.me.username}"
    return await GetUniquePackName() if await packExists(packName) else packName



def getName(sender, packType: str):
    title = f"ملصقات ~ {get_display_name(sender)}"
    if packType != "static":
        title += f" ({packType.capitalize()})"
    return title


async def AddToNewPack(packType, file, emoji, sender_id, title: str):
    sn = await GetUniquePackName()
    return await tgbot(
        CreateStickerSetRequest(
            user_id=sender_id,
            title=title,
            short_name=sn,
            stickers=[SetItem(file, emoji=emoji)],
            software="@Tepthon",
        )
    )




@Tepthon_cmd(pattern="حزمة")
async def pack_kangish(_):
    _e = await _.get_reply_message()
    local = None
    try:
        cmdtext = _.text.split(maxsplit=1)[1]
    except IndexError:
        cmdtext = None
    if cmdtext and os.path.isdir(cmdtext):
        local = True
    elif not (_e and _e.sticker and _e.file.mime_type == "image/webp"):
        return await _.eor("**◙ لا يمكن صنع حزمة من نوع الملصقات المتحركة**")
    msg = await _.eor("**⎆ جـاري صنع الحزمة يرجى الانتظار**")
    _packname = cmdtext or f"Tepthon Stickers of {_.sender_id}"
    typee = None
    if not local:
        _id = _e.media.document.attributes[1].stickerset.id
        _hash = _e.media.document.attributes[1].stickerset.access_hash
        _get_stiks = await _.client(
            functions.messages.GetStickerSetRequest(
                stickerset=types.InputStickerSetID(id=_id, access_hash=_hash), hash=0
            )
        )
        docs = _get_stiks.documents
    else:
        docs = []
        files = glob.glob(cmdtext + "/*")
        exte = files[-1]
        if exte.endswith(".tgs"):
            typee = "anim"
        elif exte.endswith(".webm"):
            typee = "vid"
        count = 0
        for file in files:
            if file.endswith((".tgs", ".webm")):
                count += 1
                upl = await tgbot.upload_file(file)
                docs.append(await tgbot(UploadMediaRequest(InputPeerSelf(), upl)))
                if count % 5 == 0:
                    await msg.edit(f"**◙ جاري رفع {count} من الملفات**")

    stiks = []
    for i in docs:
        x = get_input_document(i)
        stiks.append(
            types.InputStickerSetItem(
                document=x,
                emoji=random.choice(["♥", "🤍", "🔥"])
                if local
                else (i.attributes[1]).alt,
            )
        )
    try:
        short_name = "mohd_" + _packname.replace(" ", "_") + str(_.id)
        _r_e_s = await tgbot(
            functions.stickers.CreateStickerSetRequest(
                user_id=_.sender_id,
                title=_packname,
                short_name=f"{short_name}_by_{tgbot.me.username}",
                #animated=typee == "anim",
                #videos=typee == "vid",
                stickers=stiks,
            )
        )
    except PeerIdInvalidError:
        return await msg.eor(
            f"**◙ مرحبًـا بـك 👋 {inline_mention(_.sender)} يجب أن ترسل `/start` إلى البوت @{tgbot.me.username} وحـاول استخدام الأمر مرة أخرى**"
        )
    except BaseException as er:
        LOGS.exception(er)
        return await msg.eor(str(er))
    await msg.eor(f"**◙ تم نسخ الحزمة بنجاح**.\n**❃ رابط الحزمة:** [اضغط هنا](https://t.me/addstickers/{_r_e_s.set.short_name})")


@Tepthon_cmd(pattern="ستيكر", manager=True)
async def kang_func(event):
    sender = await event.get_sender()
    if not isinstance(sender, User):
        return
    if not event.is_reply:
        return await event.eor("**◙ يجب عليـك تحديد الرسالة/حزمة ملصقات/صورة**", time=5)
    try:
        emoji = event.text.split(maxsplit=1)[1]
    except IndexError:
        emoji = None
    reply = await event.get_reply_message()
    event = await event.eor("**◙ جاري صنع/إضافة الملصق يرجى الانتظار  .-.**")
    type_, dl = "static", None
    if reply.sticker:
        file = get_input_document(reply.sticker)
        if not emoji:
            emoji = reply.file.emoji
        name = reply.file.name
        ext = get_extension(reply.media)
        attr = list(
            filter(
                lambda prop: isinstance(prop, DocumentAttributeSticker),
                reply.document.attributes,
            )
        )
        inPack = attr and not isinstance(attr[0].stickerset, InputStickerSetEmpty)
        with contextlib.suppress(KeyError):
            type_ = {".webm": "video", ".tgs": "animated"}[ext]
        if type_ or not inPack:
            dl = await reply.download_media()
    elif reply.photo:
        dl = await reply.download_media()
        name = "sticker.webp"
        image = resize_photo_sticker(dl)
        image.save(name, "WEBP")
    elif reply.text:
        dl = await create_quotly(reply)
    else:
        return await event.eor("**◙ يجب عليك الرد على رسالة أو ملصق لأضافته لـ حزمتك**")
    if not emoji:
        emoji = "🏵"
    if dl:
        upl = await tgbot.upload_file(dl)
        file = get_input_document(await tgbot(UploadMediaRequest(InputPeerSelf(), upl)))
    get_ = jmdB.get_key("STICKERS") or {}
    title = getName(sender, type_)
    if not get_.get(event.sender_id) or not get_.get(event.sender_id, {}).get(type_):
        try:
            pack = await AddToNewPack(type_, file, emoji, sender.id, title)
        except Exception as er:
            return await event.eor(str(er))
        sn = pack.set.short_name
        if not get_.get(event.sender_id):
            get_.update({event.sender_id: {type_: [sn]}})
        else:
            get_[event.sender_id].update({type_: [sn]})
        jmdB.set_key("STICKERS", get_)
        return await event.edit(
            f"**◙ تم النسخ بنجاح ✅\n❃ الايموجي:** {emoji}\n**❃ الرابط :** [اضغط هنا](https://t.me/addstickers/{sn})\n**❃ السورس: @Tepthon**",
            link_preview=False
        )
    name = get_[event.sender_id][type_][-1]
    try:
        await tgbot(GetSticker(InputStickerSetShortName(name), hash=0))
    except StickersetInvalidError:
        get_[event.sender_id][type_].remove(name)
    try:
        await tgbot(
            AddSticker(InputStickerSetShortName(name), SetItem(file, emoji=emoji))
        )
    except (errors.StickerpackStickersTooMuchError, errors.StickersTooMuchError):
        try:
            pack = await AddToNewPack(type_, file, emoji, sender.id, title)
        except Exception as er:
            return await event.eor(str(er))
        get_[event.sender_id][type_].append(pack.set.short_name)
        jmdB.set_key("STICKERS", get_)
        return await event.edit(
            f"**◙ تم بنجاح صنع حزمة جديدة\n❃ الايموجي:** {emoji}\n**❃ الرابط :** [اضغط هنا](https://t.me/addstickers/{sn})\n**❃ سورس تيبثون - @Tepthon**",
            link_preview=False
        )
    except Exception as er:
        LOGS.exception(er)
        return await event.edit(str(er))
    await event.edit(
        f"**◙ تم بنجاح إضافة الملصق لـحزمتك**\n**❃ الرابط :** [أضغط هنا](https://t.me/addstickers/{name})\n**❃ سورس تيبثون - @Tepthon**",
        link_preview=False
    )


@Tepthon_cmd(pattern="الحزم", manager=True)
async def do_magic(mohmd):
    jasm = jmdB.get_key("STICKERS") or {}
    if not jasm.get(mohmd.sender_id):
        return await mohmd.reply("**◙ لم يتم العثور على حزمة ملصقات  :(**")
    al_ = []
    ul = jasm[mohmd.sender_id]
    for _ in ul.keys():
        al_.extend(ul[_])
    msg = "**◙ الملصقات الخاصة بـك**\n\n"
    for _ in al_:
        try:
            pack = await mohmd.client(GetSticker(InputStickerSetShortName(_), hash=0))
            msg += f"❃  [{pack.set.title}](https://t.me/addstickers/{_})\n"
        except StickersetInvalidError:
            for type_ in ["animated", "video", "static"]:
                if ul.get(type_) and _ in ul[type_]:
                    ul[type_].remove(_)
            jmdB.set_key("STICKERS", jasm)
    await mohmd.reply(msg)
