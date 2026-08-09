"""
❃  `{i}ستوري` <يوزر الشخص/الرد على الشخص>
    لـ حفظ وتنزيل اخر ستوري نشره المستخدم 
"""

import os
from contextlib import suppress
from .. import Tepthon_cmd
from telethon import TelegramClient
from telethon.tl.types import User, UserFull
from telethon.tl.functions.users import GetFullUserRequest
from telethon.events import NewMessage



@Tepthon_cmd("ستوري")
async def stories(event: NewMessage.Event):
    replied = await event.get_reply_message()
    await event.eor("**⎆ جـاري تنزيل الستـوري انتظر..**")
    try:
        username = event.text.split(maxsplit=1)[1]
    except IndexError:
        if replied and isinstance(replied.sender, User):
            username = replied.sender_id
        else:
            return await event.eor("**⎆ عليك وضع يوزر المستخدم لتنزيل الستوري الخاص به**")
    with suppress(ValueError):
        username = int(username)
    try:
        full_user: UserFull = (
            await event.client(GetFullUserRequest(id=username))
        ).full_user
    except Exception as er:
        await event.eor(f"**❃ خطأ : {er}**")
        return
    stories = full_user.stories
    if not (stories and stories.stories):
        await event.eor("**⎆ لم يتم العثور على ستوري خاص بالمستخدم**")
        return
    for story in stories.stories:
        client: TelegramClient = event.client
        file = await client.download_media(story.media)
        await event.reply(
            story.caption,
            file=file
        )
        os.remove(file)
    await event.eor("**⎆ تم بنجاح تحميل الستوري ✅**", time=5)

