from telethon.tl.types import InputWebDocument

from Tepthon import tgbot
from Tepthon.decorators.asstbot import tgbot_cmd, callback, in_pattern

from .. import Button, inline_pic, inline_mention, up_catbox

AST_PLUGINS = {}

def get_back_button(name):
    return [Button.inline("رجوع", data=f"{name}")]


@in_pattern(owner=True, func=lambda x: not x.text)
async def inline_alive(o):
    TLINK = inline_pic() or "https://telegra.ph/file/78d4b06400957403fec24.jpg"
    MSG = "• ** سورس تيبثون •**"
    WEB0 = InputWebDocument(
        "https://telegra.ph/file/78d4b06400957403fec24.jpg", 0, "image/jpg", []
    )
    RES = [
        await o.builder.article(
            type="photo",
            text=MSG,
            include_media=True,
            buttons=[
                [
                    Button.url(
                        "قناة السورس", url="https://T.me/Tepthon"
                    ),
                    Button.url("مجموعة المساعدة", url="t.me/Tepthon_Support"),
                ],
            ],
            title="سورس تيبثون",
            description="Tepthon | تيبثون",
            url=TLINK,
            thumb=WEB0,
            content=InputWebDocument(TLINK, 0, "image/jpg", []),
        )
    ]
    await o.answer(
        RES,
        private=True,
        cache_time=300,
        switch_pm="👥 Tepthon",
        switch_pm_param="start",
    )
