import asyncio
import time
import uuid

from telethon import Button
from telethon.errors.rpcerrorlist import UserNotParticipantError
from telethon.tl import functions, types

from ..decorators import owner_and_sudos as owners

cache_mod = {}



async def admin_callback(event):
    id_ = str(uuid.uuid1()).split("-")[0]
    time.time()
    msg = await event.reply(
        "**- اضغـط على الزر أدنـاه للتحقق من أنـك مشرف**",
        buttons=Button.inline("🔒 اضغط هنا للتحقق", f"cc_{id_}"),
    )
    if not cache_mod.get("admin_callback"):
        cache_mod.update({"admin_callback": {id_: None}})
    else:
        cache_mod["admin_callback"].update({id_: None})
    while not cache_mod["admin_callback"].get(id_):
        await asyncio.sleep(1)
    key = cache_mod.get("admin_callback", {}).get(id_)
    del cache_mod["admin_callback"][id_]
    return key


async def get_linked_chat_updates(event):
    if cache_mod.get("LINKED_CHATS") and cache_mod["LINKED_CHATS"].get(event.chat_id):
        _ignore = cache_mod["LINKED_CHATS"][event.chat_id]["linked_chat"]
    else:
        channel = await event.client(
            functions.channels.GetFullChannelRequest(event.chat_id)
        )
        _ignore = channel.full_chat.linked_chat_id
        if cache_mod.get("LINKED_CHATS"):
            cache_mod["LINKED_CHATS"].update({event.chat_id: {"linked_chat": _ignore}})
        else:
            cache_mod.update(
                {"LINKED_CHATS": {event.chat_id: {"linked_chat": _ignore}}}
            )
    return _ignore


async def admin_check(event, require=None, silent: bool = False):
    if event.sender_id in owners():
        return True
    callback = None
    if (
        isinstance(event.sender, (types.Chat, types.Channel))
        and event.sender_id == event.chat_id
    ):
        if not require:
            return True
        callback = True
    if isinstance(event.sender, types.Channel):
        _ignore = await get_linked_chat_updates(event)
        if _ignore and event.sender.id == _ignore:
            return False
        callback = True
    if callback:
        if silent:
            return
        get_ = await admin_callback(event)
        if not get_:
            return
        user, perms = get_
        event._sender_id = user.id
        event._sender = user
    else:
        user = event.sender
        try:
            perms = await event.client.get_permissions(event.chat_id, user.id)
        except UserNotParticipantError:
            if not silent:
                await event.reply("**⎆ انضــم للمحادثـة أولًا**")
            return False
    if not perms.is_admin:
        if not silent:
            await event.eor("**⎆ أوبس، أنا لست مشرفًا هنـا!**", time=8)
        return
    if require and not getattr(perms, require, False):
        if not silent:
            await event.eor(f"**⌔∮ أنت لا تمتلك الصلاحيات الكافية:** `{require}`", time=8)
        return False
    return True

async def get_uinfo(e):
    user, data = None, None
    reply = await e.get_reply_message()
    data = e.pattern_match.group(1).strip()
    if reply:
        user = await reply.get_sender()
    else:
        ok = data.split(maxsplit=1)
        if len(ok) > 1:
            data = ok[1]
        try:
            user = await e.client.get_entity(await e.client.parse_id(ok[0]))
        except IndexError:
            pass
        except ValueError as er:
            await e.eor(str(er))
            return None, None
    return user, data

def ban_time(time_str):
    if not any(time_str.endswith(unit) for unit in ("s", "m", "h", "d")):
        time_str += "s"
    unit = time_str[-1]
    time_int = time_str[:-1]
    if not time_int.isdigit():
        raise Exception("**حدث خطــأ** ❌: لا يمكن تحديد المنطقة الزمنية")
    if unit == "s":
        return int(time.time() + int(time_int))
    elif unit == "m":
        return int(time.time() + int(time_int) * 60)
    elif unit == "h":
        return int(time.time() + int(time_int) * 60 * 60)
    elif unit == "d":
        return int(time.time() + int(time_int) * 24 * 60 * 60)
    return 0
