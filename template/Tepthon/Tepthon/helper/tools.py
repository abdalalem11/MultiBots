import math
from PIL import Image
from contextlib import suppress
from . import run_async
from .. import LOGS, jmubot

from telegraph import Telegraph
from database import jmdB

def _get_value(stri):
    value = stri.strip()
    try:
        value = eval(value)
    except Exception as er:
        LOGS.debug(er)
    return value


def safe_load(file, *args, **kwargs):
    read = file.split("\n") if isinstance(file, str) else file.readlines()
    out = {}
    for line in read:
        if ":" in line:
            spli = line.split(":", maxsplit=1)
            key = spli[0].strip()
            value = _get_value(spli[1])
            out[key] = value or []
        elif "-" in line:
            spli = line.split("-", maxsplit=1)
            if value := _get_value(spli[1]):
                where = out[list(out.keys())[-1]]
                if isinstance(where, list):
                    where.append(value)
    return out



def resize_photo_sticker(photo):
    image = Image.open(photo)
    if (image.width and image.height) < 512: #اعادة تشكيل الصورة ب ابعاد 512
        size1 = image.width
        size2 = image.height
        if image.width > image.height:
            scale = 512 / size1
            size1new = 512
            size2new = size2 * scale
        else:
            scale = 512 / size2
            size1new = size1 * scale
            size2new = 512
        size1new = math.floor(size1new)
        size2new = math.floor(size2new)
        sizenew = (size1new, size2new)
        image = image.resize(sizenew)
    else:
        maxsize = (512, 512)
        image.thumbnail(maxsize)
    return image

#for telegraph

def get_client():
    _api = jmdB.get_key("_TELEGRAPH_TOKEN")
    try:
        client = Telegraph(_api, domain="graph.org")
    except TypeError:
        client = Telegraph(_api)
    if not _api:
        gd_name = jmubot.full_name
        short_name = gd_name[:30]
        profile_url = (
            f"https://t.me/{jmubot.me.username}"
            if jmubot.me.username
            else "https://t.me/Tepthon"
        )
        try:
            client.create_account(
                short_name=short_name, author_name=gd_name, author_url=profile_url
            )
        except Exception as er:
            if "SHORT_NAME_TOO_LONG" in str(er):
                client.create_account(
                    short_name="Tepthonuser",
                    author_name=gd_name,
                    author_url=profile_url,
                )
            LOGS.exception(er)
        if _token := client.get_access_token():
            jmdB.set_key("_TELEGRAPH_TOKEN", _token)
    return client


def upload_file(path):
    if path.endswith("webp"):
        with suppress(ImportError):
            from PIL import Image

            Image.open(path).save(path, "PNG")
    return f"https://graph.org{get_client().upload_file(path)[-1]['src']}"


@run_async
def make_html_telegraph(title, html=""):
    telegraph = get_client()
    page = telegraph.create_page(
        title=title,
        html_content=html,
    )
    return page["url"]

