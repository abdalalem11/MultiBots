"""
❃ `{i}ازالة متحركات` <عدد>
   لـ حذف المتحركات المحفوظة في حسابك ويمكنك حذف جميع المتحركات إذا وضعت كلمة الكل في مكان العدد
"""

from telethon import functions, types
from .. import Tepthon_cmd

@Tepthon_cmd(pattern="ازالة متحركات ?(.*)")
async def clear_gif(event):
    number = event.pattern_match.group(1).strip()
    result = await event.client(functions.messages.GetSavedGifsRequest(hash=0))
    total_gifs = len(result.gifs)

    if number.lower() == "الكل":
        gifcount = total_gifs
    elif number.isdigit():
        gifcount = min(int(number), total_gifs)
    else:
        return event.eor("**⎆ يجب عليك تحديد العدد الذي تريد حذفه**")

    if gifcount == 0:
        return await event.eor("❃ لا توجد متحركات محفوظة لحذفها.")


    await event.eor(f"**❃ جاري حذف {gifcount} من المتحركات...**")

    count = 0
    for gif in result.gifs[:gifcount]:
        gifid = types.InputDocument(id=gif.id, access_hash=gif.access_hash, file_reference=gif.file_reference)
        await event.client(functions.messages.SaveGifRequest(id=gifid, unsave=True))
        count += 1

    await event.eor(f"**⎆ تم بنجاح حذف {count} من المتحركات.**")
