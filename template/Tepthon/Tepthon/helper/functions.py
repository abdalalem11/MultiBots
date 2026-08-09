import asyncio
import requests 
import json
import re
import os
import html
import asyncio
from functools import wraps, partial
from urllib.parse import quote, urlparse, unquote
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from telethon.utils import get_display_name 
from telethon.tl import types
from telethon.tl.types import (
    User,
    Channel,
    SendMessageUploadDocumentAction,
    DocumentAttributeAnimated,
    DocumentAttributeAudio,
    DocumentAttributeImageSize,
    DocumentAttributeSticker,
    DocumentAttributeVideo,
    Message,
)


def inline_mention(user, custom=None, html=False):
    mention_text = custom or get_display_name(user) or "حساب محذوف"
    if isinstance(user, User):
        if html:
            return f"<a href=tg://user?id={user.id}>{mention_text}</a>"
        return f"[{mention_text}](tg://user?id={user.id})"
    if isinstance(user, Channel) and user.username:
        if html:
            return f"<a href=https://t.me/{user.username}>{mention_text}</a>"
        return f"[{mention_text}](https://t.me/{user.username})"
    return mention_text


# --------------------------------------------------------------------- #

class BashError(Exception):
    pass

async def bash(cmd, run_code=0):
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    err = stderr.decode().strip() or None
    out = stdout.decode().strip()

    if not run_code and err:
        match = re.match(r"\/bin\/sh: (.*): ?(\w+): not found", err)
        if match:
            return out, f"{match[2].upper()}_NOT_FOUND"

    return out, err

# --------------------------------------------------------------------- #


def run_async(function):
    @wraps(function)
    async def wrapper(*args, **kwargs):
        return await asyncio.get_event_loop().run_in_executor(
            ThreadPoolExecutor(max_workers=multiprocessing.cpu_count() * 5),
            partial(function, *args, **kwargs),
        )
    return wrapper

def fetch_syn(url, re_json=False, evaluate=None, method="GET", *args, **kwargs):
    methods = {"POST": requests.post, "HEAD": requests.head, "GET": requests.get}
    output = methods.get(method, requests.get)(url, *args, **kwargs)

    if callable(evaluate):
        return evaluate(output)
    elif re_json:
        if "application/json" in output.headers.get("content-type", ""):
            return output.json()
        return output.text
    return output.content


async_search = fetch = run_async(fetch_syn)
 
# --------------------------------------------------------------------- #

async def is_url_work(url: str, shallow: bool = False):
    if shallow:
        parse = urlparse(url)
        return parse.netloc and parse.scheme
    try:
        await async_search(url, method="HEAD")
        return True
    except BaseException as er:
        LOGS.error(er)
    return False

# --------------------------------------------------------------------- #

async def download_file(link, name, validate=False):
    def _download(response):
        if validate and "application/json" in response.headers.get("Content-Type"):
            return None, response.json()
        with open(name, "wb") as file:
            file.write(response.content)
        return name, ""

    return await async_search(link, evaluate=_download)

# --------------------------------------------------------------------- #

def _unquote_text(text):
    return text.replace("'", unquote("%5C%27")).replace('"', unquote("%5C%22"))

async def metadata(file):
    out, _ = await bash(f'mediainfo "{_unquote_text(file)}" --Output=JSON')
    if _ and _.endswith("NOT_FOUND"):
        raise Exception(f"~ '{_}' غير مثبتة")
    data = {}
    _info = json.loads(out)["media"]["track"]
    info = _info[0]
    if info.get("Format") in ["GIF", "PNG"]:
        return {
            "height": _info[1]["Height"],
            "width": _info[1]["Width"],
            "bitrate": _info[1].get("BitRate", 320),
        }
    if info.get("AudioCount"):
        data["title"] = info.get("Title", file)
        data["performer"] = info.get("Performer") or jmdB.get_key("artist") or ""
    if info.get("VideoCount"):
        data["height"] = int(float(_info[1].get("Height", 720)))
        data["width"] = int(float(_info[1].get("Width", 1280)))
        data["bitrate"] = int(_info[1].get("BitRate", 320))
    data["duration"] = int(float(info.get("Duration", 0)))
    return data


# --------------------------------------------------------------------- #


async def set_attributes(file):
    data = await metadata(file)
    if not data:
        return None
    if "width" in data:
        return [
            DocumentAttributeVideo(
                duration=data.get("duration", 0),
                w=data.get("width", 512),
                h=data.get("height", 512),
                supports_streaming=True,
            )
        ]
    ext = "." + file.split(".")[-1]
    return [
        DocumentAttributeAudio(
            duration=data.get("duration", 0),
            title=data.get("title", file.split("/")[-1].replace(ext, "")),
            performer=data.get("performer"),
        )
    ]

# --------------------------------------------------------------------- #

def get_all_files(path, extension=None):
    filelist = []
    for root, _, files in os.walk(path):
        if extension:
            files = filter(lambda e: e.endswith(extension), files)
        filelist.extend(os.path.join(root, file) for file in files)
    return sorted(filelist)


def fetch_sync(url, re_json=False, evaluate=None, method="GET", *args, **kwargs):
    methods = {"POST": requests.post, "HEAD": requests.head, "GET": requests.get}
    output = methods.get(method, requests.get)(url, *args, **kwargs)

    if callable(evaluate):
        return evaluate(output)
    elif re_json:
        # type: ignore
        if "application/json" in output.headers.get("content-type", ""):
            return output.json()
        return output.text
    return output.content

def translate(text, target="en", source="auto", timeout=60, detect=False):
    pattern = r'(?s)class="(?:t0|result-container)">(.*?)<'
    escaped_text = quote(text.encode("utf8"))
    url = "https://translate.google.com/m?tl=%s&sl=%s&q=%s" % (
        target,
        source,
        escaped_text,
    )
    response = fetch_sync(url, timeout=timeout)
    result = response.decode("utf8")
    result = re.findall(pattern, result)
    if not result:
        return ""
    text = html.unescape(result[0])
    return (text, None) if detect else text


def mediainfo(message: Message) -> str:
    for _ in [
        "audio",
        "contact",
        "dice",
        "game",
        "geo",
        "gif",
        "invoice",
        "photo",
        "poll",
        "sticker",
        "venue",
        "video",
        "video_note",
        "voice",
        "document",
    ]:
        if getattr(message, _, None):
            if _ == "sticker":
                stickerType = {"video/webm": "video_sticker", 
                               "image/webp": "static_sticker",
                               "application/x-tgsticker": "animated_sticker"}
                return stickerType[message.document.mime_type]
            elif _ == "document":
                attributes = {
                    DocumentAttributeSticker: "sticker",
                    DocumentAttributeAnimated: "gif",
                    DocumentAttributeAudio: "audio",
                    types.DocumentAttributeCustomEmoji: "custom emoji",
                    DocumentAttributeVideo: "video",
                    DocumentAttributeImageSize: "photo",
                    }
                for __ in message.document.attributes:
                    if type(__) in attributes:
                        _i = attributes[type(__)]
                        if _i == "photo" and any(
                            isinstance(k, DocumentAttributeSticker)
                            for k in message.document.attributes
                        ):
                            _i = "sticker"
                        return f"{_i} as document"
            return _
    return ""
