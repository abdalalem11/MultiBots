import hashlib
from telethon.tl import types
from telethon.tl.custom import InlineBuilder


async def article(
    self: "InlineBuilder",
    title,
    description=None,
    *,
    url=None,
    thumb=None,
    content=None,
    id=None,
    text=None,
    parse_mode=(),
    link_preview=True,
    geo=None,
    period=60,
    contact=None,
    game=False,
    buttons=None,
    type="article",
    include_media: bool = False
):
    result = types.InputBotInlineResult(
        id=id or "",
        type=type,
        send_message=await self._message(
            text=text,
            parse_mode=parse_mode,
            link_preview=link_preview,
            geo=geo,
            period=period,
            contact=contact,
            game=game,
            buttons=buttons,
            media=include_media
        ),
        title=title,
        description=description,
        url=url,
        thumb=thumb,
        content=content,
    )
    if id is None:
        result.id = hashlib.sha256(bytes(result)).hexdigest()

    return result

setattr(InlineBuilder, "article", article)
