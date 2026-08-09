"""
◙ `{i}تحميل صوتي` <(رابط يوتيوب/او أي رابط)>
   لـ تحميل الملف بشكل ملف صوتي في التليجرام، يمكنك وضع رابط أي منصة


◙ `{i}تحميل فيد` <(رابط يوتيوب/او أي رابط)>
   لـ تحميل الملف بشكل فيديو في التليجرام، يمكنك وضع رابط أي منصة


◙ `{i}صوتي` <(عنوان)>
   لـ تحميل الملف بشكل ملف صوتي في التليجرام من خلال العنوان فقط بدون رابط

"""

from .. import download_yt, get_yt_link, is_url_work, Tepthon_cmd

ytd = {
        "prefer_ffmpeg": True,
        "addmetadata": True,
        "geo-bypass": True,
        "nocheckcertificate": True,
        "postprocessors": [{"key": "FFmpegMetadata"}],
    }

@Tepthon_cmd(pattern="تحميل صوتي (.*)")
async def down_voic(event):
    jmbot = await event.eor("⎆ جار التحميل يرجى الانتظار قليلًا")
    ytd["format"] = "bestaudio"
    ytd["outtmpl"] = "%(id)s.m4a"
    ytd["postprocessors"].insert(
            0,
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "128",
            },
        )
    url = event.pattern_match.group(1)
    if not url:
        return await jmbot.eor("⎆ يجب عليك وضع رابط للتحميل الصوتي")
    try:
        await is_url_work(url)
    except BaseException:
        return await jmbot.eor("⎆ يرجى وضع الرابط بشكل صحيح")
    await download_yt(jmbot, url, ytd)

@Tepthon_cmd(pattern="تحميل فيد (.*)")
async def vidown(event):
    jmbot = await event.eor("⎆ جار التحميل يرجى الانتظار قليلًا")
    ytd["format"] = "best"
    ytd["outtmpl"] = "%(id)s.mp4"
    ytd["postprocessors"].insert(
        0, {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}
        )
    url = event.pattern_match.group(1)
    print(url)
    if not url:
        return await jmbot.eor("⎆ يجب عليك وضع رابط لتحميل الفيديـو")
    try:
        await is_url_work(url)
    except BaseException:
        return await jmbot.eor("⎆ يرجى وضع الرابط بشكل صحيح")
    await download_yt(jmbot, url, ytd)


@Tepthon_cmd(pattern="صوتي( (.*)|$)")
async def sotea(event):
    jmbot = await event.eor("⎆ جـاري التحميل يرجى الانتظار قليلًا")
    ytd["format"] = "bestaudio"
    ytd["outtmpl"] = "%(id)s.m4a"
    ytd["postprocessors"].insert(
        0,
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
            "preferredquality": "128",
        },
    )
    query = event.pattern_match.group(2) if event.pattern_match.group(1) else None
    if not query:
        return await jmbot.eor("**⎆ يجب عليك تحديد ما تريد تحميله اكتب عنوان مع الأمـر**")
    url = get_yt_link(query, ytd)
    if not url:
        return await jmbot.edit("**⎆ لم يتم العثور على الفيديو اكتب عنوان مفصل بشكل صحيح**")
    await jmbot.eor("**⎆ جاري تحميل الملف الصوتي انتظـر قليـلًا....**")
    await download_yt(jmbot, url, ytd)


