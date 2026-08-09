import re
from contextlib import suppress
from inspect import getmembers

from telethon import Button
from telethon.errors import MessageNotModifiedError
from telethon.events import NewMessage

from Tepthon.decorators.asstbot import callback, in_pattern
from Tepthon.load_plug import PLUGINS
from database import CMD_HELP, LIST, InlinePlugin, InlinePaths
from .. import HNDLR, LOGS, tgbot, jmdB, jmubot, Tepthon_cmd, inline_pic


_cache = {}


def split_list(List, index):
    new_ = []
    while List:
        new_.extend([List[:index]])
        List = List[index:]
    return new_


def get_help_buttons():
    row_1 = [
        Button.inline("• أوامر الأساسية •", data="get_basic_"),
        Button.inline("• الأوامر الشخصية •", data="get_account_"),
    ]

    row_2 = [
        Button.inline("• أوامر التسلية •", data="get_fun_"),
        Button.inline("• أوامر المجمـوعات •", data="get_group_"),
    ]

    if InlinePlugin:
        row_2.append(
            Button.inline("• أوامر الأنلاين •", data="inlone")
        )

    if all(len(row) == 1 for row in [row_1, row_2]):
        row_1.append(row_2[0])
        row_2.clear()

    Markup = [row_1]

    if len(row_2) > 1:
        Markup.append(row_2)

    settingButton = Button.url(
        "• أوامر البوت المساعد •",
        url=f"https://t.me/{tgbot.me.username}?start=set",
    )

    if len(row_2) == 1:
        row_2.append(settingButton)
    else:
        Markup.append([settingButton])

    Markup.append(
        [Button.inline("- إغـلاق -", data="close")],
    )

    if row_2 and row_2 not in Markup:
        Markup.insert(1, row_2)

    return Markup


def _sort(type, modl):
    spli = modl.split(".")

    if (
        type in spli
        and not spli[-1].startswith("_")
        and modl not in InlinePaths
    ):
        return modl.split(".")[-1]


def filter_modules(type):
    """Get names of loaded plugins"""
    return sorted(
        list(
            filter(
                lambda e: e,
                map(lambda modl: _sort(type, modl), PLUGINS),
            )
        )
    )


def _get_module(name, type):
    check = [type] if type else ["basic"]

    for path in check:
        with suppress(KeyError):
            return PLUGINS[f"plugins.{path}.{name}"]


def get_doc_from_module(name, type=""):
    if mod := _get_module(name, type):
        if not mod.__doc__:
            return get_from_funcs(mod, name)

        msg = (
            f"**⎆ أوامـر سورس النسر الاسود المتاحة في قائمـة {name}**\n\n"
        )

        msg += mod.__doc__.format(i=HNDLR)
        msg += "\n ©️ @SSSTlF"

        return msg


def get_from_funcs(mod, name):
    handlers = list(
        map(
            lambda d: d[0],
            jmubot.list_event_handlers(),
        )
    )

    funcs = list(
        filter(
            lambda d: (
                d[0].endswith(("_func", "_cmd"))
                and d[1] in handlers
                and d[1].__doc__
            ),
            getmembers(mod),
        )
    )

    if not funcs:
        return False

    msg = (
        f"**⎆ أوامـر سورس النسر التسود المتاحة في قائمـة {name}**"
    )

    for cmd in funcs:
        msg += (
            f"\n\n• "
            f"{cmd[1].__doc__.format(*list(HNDLR * len(funcs)))}"
        )

    msg += "\n ©️ @SSSTlF"

    return msg


DEF_CONFIG = {
    "plugins": {},
    "helpers": {},
    "manager": {},
}


def get_info(id):
    return DEF_CONFIG["plugins"].get(id, {})


def get_doc(module, type=""):
    msg = get_doc_from_module(module, type)

    if msg:
        return msg

    _get_info = get_info(module)

    if _get_info and (cmds := _get_info.get("cmds")):
        msg = (
            f"**⎆ أوامـر سورس النسر الاسود المتاحة في قائمـة {module}**"
        )

        for cmd in cmds:
            msg += (
                f"\n\n• `{HNDLR}{cmd}`\n"
                f" {cmds[cmd]}"
            )

    elif help := CMD_HELP.get(module):
        msg = f"اسم القائمة: {module}\n\n"
        msg += help.format(i=HNDLR)

    elif help := LIST.get(module):
        msg = f"اسم القائمة: {module}\n\n"

        for cmd in help:
            msg += f"- \n{HNDLR}{cmd}\n"

    if msg:
        msg += "\n ©️ @SSSTlF"

    return msg


@Tepthon_cmd("الاوامر($| (.*))")
async def help_cmd(event: NewMessage.Event):
    module = event.pattern_match.group(1).strip()

    if not module:
        if event.client._bot:
            return await event.reply(
                "**⎆ مالك البوت {}\n\nالقائمة الرئيسية\n\n"
                "الأوامر ~ {}**".format(
                    jmubot.full_name,
                    len(PLUGINS),
                ),
                file=inline_pic(),
                buttons=get_help_buttons(),
                link_preview=False,
            )

        result = await event.client.inline_query(
            tgbot.me.username,
            "mohd",
        )

        await result[0].click(
            event.chat_id,
            reply_to=event.id,
        )

        await event.delete()

        return

    if msg := get_doc(module):
        return await event.eor(msg)

    if not LIST.get(module):
        return await event.eor(
            f"**⎆ القائمة {module} غير موجودة أصـلًا** ."
        )

    await event.eor(
        f"**⎆ قائمة {module} لا توجد في قائمة المساعدة**"
    )


@in_pattern("mohd", owner=True)
async def inline_handler(event):
    text = (
        "** مالك البوت {}\n\nالقائمة الرئيسية\n\n"
        "الأوامر ~ {}**".format(
            jmubot.full_name,
            len(PLUGINS),
        )
    )

    if inline_pic():
        result = await event.builder.photo(
            file=inline_pic(),
            link_preview=False,
            text=text,
            buttons=get_help_buttons(),
        )
    else:
        result = await event.builder.article(
            title="**⎆ قائمـة أوامر سورس تيبثـون:**",
            text=text,
            buttons=get_help_buttons(),
        )

    await event.answer(
        [result],
        private=True,
        cache_time=300,
        gallery=True,
    )


@callback(re.compile("get_(.*)"), owner=True)
async def help_func(moh):
    key, count = (
        moh.data_match
        .group(1)
        .decode("utf-8")
        .split("_")
    )

    plugs = filter_modules(key)

    if key == "vcbot" and not plugs:
        return await moh.answer(
            "**◙ يجب عليك إضافة متغير السمـاع الصوتي**",
            alert=True,
        )

    if "|" in count:
        _, count = count.split("|")

    count = int(count) if count else 0

    _strings = {
        "basic": (
            "**⎆ مجموعة المساعدة: "
            "[اضغط هنا](t.me/SSSTlFh)**\n"
            "**❃ مالك الحساب هو: {}.\n"
            "❃ عدد القوائم الموجودة: {}**"
        ),
        "account": (
            "**⎆ مجموعة المساعدة: "
            "[اضغط هنا](t.me/Tepthon_Support)**\n"
            "**❃ مالك الحساب هو: {}.\n"
            "❃ عدد قوائم الموجودة: {}**"
        ),
        "fun": (
            "**⎆ مجموعة المساعدة: "
            "[اضغط هنا](t.me/SSSTlFh)**\n"
            "**❃ مالك الحساب هو: {}.\n"
            "❃ عدد قوائم الموجودة: {}**"
        ),
        "group": (
            "**⎆ مجموعة المساعدة: "
            "[اضغط هنا](t.me/SSSTlFh)**\n"
            "**❃ مالك الحساب هو: {}.\n"
            "❃ عدد القوائم الموجودة: {}**"
        ),
    }

    text = _strings.get(key, "").format(
        jmubot.full_name,
        len(plugs),
    )

    try:
        await moh.edit(
            text,
            buttons=page_num(count, key),
            link_preview=False,
        )
    except MessageNotModifiedError:
        return


@callback(data="open", owner=True)
async def opner(event):
    try:
        await event.edit(
            "**⎆ القائمة الرئيسية لـ أوامر سورس النسرالاسود**\n"
            "**⎆ مالك الحساب هو: {}.\n"
            "⎆ عدد القوائم الموجودة: {}**".format(
                jmubot.full_name,
                len(PLUGINS),
            ),
            buttons=get_help_buttons(),
            link_preview=False,
        )
    except MessageNotModifiedError:
        return


@callback(data="close", owner=True)
async def on_plug_in_callback_query_handler(event):
    try:
        await event.edit(
            "**⎆ تم إغلاق القائمة الرئيسية بنجاح**",
            buttons=Button.inline(
                "فتح مرة أخرى",
                data="open",
            ),
        )
    except MessageNotModifiedError:
        return


@callback(data="inlone", owner=True)
async def _(e):
    if not InlinePlugin:
        return await e.answer(
            "**⎆ لا يتوفر أوامر أنلاين حاليًّــا**",
            alert=True,
        )

    _InButtons = [
        Button.switch_inline(
            key,
            query=InlinePlugin[key],
            same_peer=True,
        )
        for key in InlinePlugin
    ]

    InButtons = split_list(_InButtons, 2)

    button = InButtons.copy()

    button.append(
        [
            Button.inline(
                "« رجوع",
                data="open",
            ),
        ],
    )

    try:
        await e.edit(
            buttons=button,
            link_preview=False,
        )
    except MessageNotModifiedError:
        return


def _get_buttons(key, index):
    rows = jmdB.get_key("HELP_ROWS") or 5
    cols = jmdB.get_key("HELP_COLUMNS") or 2
    emoji = jmdB.get_key("EMOJI_IN_HELP") or "❃"

    loaded = filter_modules(key)

    NList = []
    tl = rows * cols

    for cindex, plugs in enumerate(
        split_list(loaded, tl)
    ):
        MList = []

        for ps in split_list(plugs, rows):
            MList.extend(
                Button.inline(
                    f"{emoji} {p} {emoji}",
                    data=f"uplugin_{key}_{p}|{cindex}",
                )
                for p in ps
            )

        NList.append(
            split_list(MList, cols)
        )

    if _cache.get("help") is None:
        _cache["help"] = {}

    _cache["help"][key] = NList

    return NList


def page_num(index, key):
    fl_ = (
        _cache.get("help", {}).get(key)
        or _get_buttons(key, index)
    )

    try:
        new_ = fl_[index].copy()
    except IndexError:
        new_ = fl_[0].copy() if fl_ else []
        index = 0

    if index == 0 and len(fl_) == 1:
        new_.append(
            [
                Button.inline(
                    "« رجوع »",
                    data="open",
                )
            ]
        )
    else:
        new_.append(
            [
                Button.inline(
                    "« السابق",
                    data=f"get_{key}_{index - 1}",
                ),
                Button.inline(
                    "« رجوع »",
                    data="open",
                ),
                Button.inline(
                    "التالي »",
                    data=f"get_{key}_{index + 1}",
                ),
            ]
        )

    return new_


@callback(re.compile("uplugin_(.*)"), owner=True)
async def uptd_plugin(event):
    key, file = (
        event.data_match
        .group(1)
        .decode("utf-8")
        .split("_")
    )

    index = None

    if "|" in file:
        file, index = file.split("|")

    help_ = get_doc(file, key)

    if not help_:
        help_ = (
            f"**⎆ القائمة {file} لا تحتـوي على شرح "
            f"في قائمة المساعدة حاليًّــا**"
        )
        help_ += "\n© @Tepthon"

    buttons = []

    data = f"get_{key}_"

    if index is not None:
        data += f"|{index}"

    buttons.append(
        [
            Button.inline(
                "« رجوع",
                data=data,
            ),
        ]
    )

    try:
        await event.edit(
            help_,
            buttons=buttons,
        )
    except MessageNotModifiedError:
        return
    except Exception as er:
        LOGS.exception(er)

        help_msg = (
            f"⎆ ارسل `{HNDLR}الاوامر {file}` "
            "للحصول على شرح القائمة"
        )

        try:
            await event.edit(
                help_msg,
                buttons=buttons,
            )
        except MessageNotModifiedError:
            return
