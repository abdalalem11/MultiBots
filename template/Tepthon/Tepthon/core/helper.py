import re
import requests
import math
import time
from urllib.parse import unquote

from telethon.helpers import _maybe_await
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import SendMessageUploadDocumentAction


def time_with_fixed_format(years, months, weeks, days, hours, minutes, seconds):
    tmp = (
        ((f"{years} years ") if years else "")
        + ((f"{months} months ") if months else "")
        + ((f"{weeks} weeks ") if weeks else "")
        + ((f"{days} days ") if days else "")
        + ((f"{hours}:") if hours else "00:")
        + ((f"{minutes}:") if minutes else "00:")
        + ((f"{seconds}") if seconds else "00")
    )
    _ = re.search(r"(\d+:\d+:\d+)", tmp)[0]
    _tmp = ":".join(
        str(k).zfill(2) for k in re.search(r"(\d+:\d+:\d+)", tmp)[0].split(":")
    )
    return re.sub(_, _tmp, tmp)



def time_formatter(milliseconds, fixed_format=False):
    minutes, seconds = divmod(int(milliseconds / 1000), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    weeks, days = divmod(days, 7)
    months, weeks = divmod(weeks, 4)
    years, months = divmod(months, 13)  #13 شهر لأن 13*4*7 يساوي 364 يوم

    if fixed_format:
        return time_with_fixed_format(
            years, months, weeks, days, hours, minutes, seconds
        )
    tmp = (
        (f"{str(weeks)}w:" if weeks else "")
        + (f"{str(days)}d:" if days else "")
        + (f"{str(hours)}h:" if hours else "")
        + (f"{str(minutes)}m:" if minutes else "")
        + (f"{str(seconds)}s" if seconds else "")
    )
    if not tmp:
        return "0s"
    return tmp[:-1] if tmp.endswith(":") else tmp


def humanbytes(size: int) -> str:
    size = int(size)
    if not size:
        return "0B"
    unit = ""
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z", "Y"]:
        if size < 1024:
            break
        size /= 1024
    if isinstance(size, int):
        size = f"{size}{unit}B"
    elif isinstance(size, float):
        size = f"{size:.2f}{unit}B"
    return size


No_Flood = {}

async def progress(current, total, event, start, type_of_ps, file_name=None, to_chat=None):
    now = time.time()
    chat_id = event.chat_id
    event_id = event.id

    last_update = No_Flood.get(chat_id, {}).get(event_id)
    if last_update and (now - last_update) < 1.1:
        return
    No_Flood.setdefault(chat_id, {})[event_id] = now

    diff = now - start
    if round(diff % 10.00) == 0 or current == total:
        percentage = (current * 100) / total
        speed = current / diff if diff > 0 else 0
        time_to_completion = round((total - current) / speed * 1000) if speed > 0 else 0

        progress_str = "`[{0}{1}] {2}%`\n\n".format(
            "".join("●" for _ in range(math.floor(percentage / 5))),
            "".join(" " for _ in range(20 - math.floor(percentage / 5))),
            round(percentage, 2),
        )

        tmp = (
            progress_str
            + "`{0} من {1}`\n\n`✦ السرعة: {2}/s`\n\n`✦ الوقت المتبقي: {3}`\n\n".format(
                humanbytes(current),
                humanbytes(total),
                humanbytes(speed),
                time_formatter(time_to_completion),
            )
        )

        if type_of_ps.startswith("Upload"):
            await event.client(
                SetTypingRequest(
                    to_chat or event.chat_id, SendMessageUploadDocumentAction(round(percentage))
                )
            )

        if file_name:
            await event.edit(
                f"`✦ {type_of_ps}`\n\n**❃ اسم الملف: {file_name}**\n\n{tmp}"
            )
        else:
            await event.edit(f"`✦ {type_of_ps}`\n\n{tmp}")


async def fast_download(download_url, filename=None, progress_callback=None):
    session = requests.Session()
    response = session.get(download_url, timeout=None, stream=True)
    if not filename:
        filename = unquote(download_url.rpartition("/")[-1])
    total_size = int(response.headers.get("content-length", 0)) or None
    downloaded_size = 0
    start_time = time.time()
    with open(filename, "wb") as f:
        for chunk in response.iter_content(2**20):
            if chunk:
                f.write(chunk)
                downloaded_size += len(chunk)
            if progress_callback and total_size:
                await _maybe_await(progress_callback(downloaded_size, total_size))
    return filename, time.time() - start_time
    
    

