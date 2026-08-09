from telethon.utils import pack_bot_file_id

from .. import Tepthon_cmd

plugin_category = "utils"


@Tepthon_cmd(
    pattern=r"(get_id|id)(?:\s|$)([\s\S]*)",
)
async def _(event):
    """إظهار أيدي المستخدم أو المجموعة أو القناة."""

    input_str = event.pattern_match.group(2).strip()

    # إذا تم إعطاء يوزر / رابط / ID
    if input_str:
        try:
            entity = await event.client.get_entity(input_str)
        except Exception as e:
            return await event.edit(f"`{e}`")

        # مستخدم
        if hasattr(entity, "first_name"):
            return await event.edit(
                f"**User ID:** `{entity.id}`"
            )

        # مجموعة أو قناة
        if hasattr(entity, "title"):
            return await event.edit(
                f"**Chat/Channel:** `{entity.title}`\n"
                f"**ID:** `{entity.id}`"
            )

        return await event.edit(
            "**تعذر تحديد نوع الكيان.**"
        )

    # إذا كان الأمر ردًا على رسالة
    if event.reply_to_msg_id:
        replied = await event.get_reply_message()

        text = (
            f"**Current Chat ID:** `{event.chat_id}`\n"
            f"**From User ID:** `{replied.sender_id}`"
        )

        # إذا كانت الرسالة تحتوي على ميديا
        if replied.media:
            try:
                bot_api_file_id = pack_bot_file_id(replied.media)
                text += (
                    f"\n**Media File ID:** `{bot_api_file_id}`"
                )
            except Exception:
                pass

        return await event.edit(text)

    # بدون رد أو إدخال
    return await event.edit(
        f"**Current Chat ID:** `{event.chat_id}`"
    )
