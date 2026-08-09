import contextlib
import inspect
import os
import sys
import time
from datetime import datetime
from logging import Logger

from telethon import hints, utils, TelegramClient
from telethon.errors import (
    AccessTokenExpiredError,
    AccessTokenInvalidError,
    ApiIdInvalidError,
    AuthKeyDuplicatedError,
)
from telethon.tl.types import User

from Tepthon.config import Var
from database import jmdB
from Tepthon.core.helper import fast_download
from Tepthon.core.logger import LOGS, TelethonLogger
from resources import blacklisted_users


class TepthonClient(TelegramClient):
    me: User

    def __init__(
        self,
        session,
        api_id: int = Var.API_ID,
        api_hash: str = Var.API_HASH,
        bot_token=None,
        logger: Logger = LOGS,
        log_attempt=True,
        exit_on_error=True,
        *args,
        **kwargs,
    ):
        self._cache = {}
        self._dialogs = []
        self._handle_error = exit_on_error
        self._log_at = log_attempt
        self.logger = logger
        self._thumb = {}
        kwargs["base_logger"] = TelethonLogger
        super().__init__(session, api_id=api_id, api_hash=api_hash, **kwargs)
        self.run_in_loop(self.start_client(bot_token=bot_token))
        self.dc_id = self.session.dc_id

    def __repr__(self):
        return f"<Tepthon Client :\n self: {self.full_name}\n bot: {self._bot}\n>"

    @property
    def __dict__(self):
        if self.me:
            return self.me.to_dict()

    async def start_client(self, **kwargs):
        """وظيفة لتشغيل الكلاينت""" 
        if self._log_at:
            self.logger.info("❃ جاري تسجيل الدخول...")
        try:
            await self.start(**kwargs)
        except ApiIdInvalidError:
            self.logger.critical("◙ الأيبي أيدي والأيبي هاش غير متطابقين")

            sys.exit()
        except (AuthKeyDuplicatedError, EOFError):
            if self._handle_error:
                self.logger.critical("⎆ كود السيشن أو التوكن منتهي اصنع كود جديد وأضفه إلى المتغيرات...")
                return sys.exit()
            self.logger.critical("❃ سيشن الحساب/توكن الحساب منتهي الصلاحية.")
        except (AccessTokenExpiredError, AccessTokenInvalidError):
            jmdB.del_key("BOT_TOKEN")
            self.logger.critical(
                "❃ توكن البوت منتهي أو غير صالح، اصنع بوت جديد من @Botfather وأضفه مع المتغير BOT_TOKEN في قائمة المتغيرات"
            )
            sys.exit()
        self.me = await self.get_me()
        if self.me.bot:
            me = f"@{self.me.username}"
        else:
            setattr(self.me, "phone", None)
            me = self.full_name
        if self.uid in blacklisted_users:
            self.log.error(f"({me} - {self.uid}) ~ لا يمكنك استخدام سورس تيبثون أنت محظور بسبب مخالفتك سياسة استخدام السورس @Tepthon")
            sys.exit(1)
        if self._log_at:
            self.logger.info(f"❃ تم تسجيل الدخول كـ {me}")
        self._bot = await self.is_bot()

    async def fast_uploader(self, file, **kwargs):
        """رفع الملفات بأسرع طريقة"""

        import os
        from pathlib import Path

        start_time = time.time()
        path = Path(file)
        filename = kwargs.get("filename", path.name)
        show_progress = kwargs.get("show_progress", False)
        if show_progress:
            event = kwargs["event"]
        use_cache = kwargs.get("use_cache", True)
        to_delete = kwargs.get("to_delete", False)
        message = kwargs.get("message", f"❃  جار رفع {filename} ...")
        by_bot = self._bot
        size = os.path.getsize(file)
        if size < 5 * 2**20: #اذا الملف اقل من 5 ميغا ميطلع العملية
            show_progress = False
        if use_cache and self._cache and self._cache.get("upload_cache"):
            for files in self._cache["upload_cache"]:
                if (
                    files["size"] == size
                    and files["path"] == path
                    and files["name"] == filename
                    and files["by_bot"] == by_bot
                ):
                    if to_delete:
                        with contextlib.suppress(FileNotFoundError):
                            os.remove(file)
                    return files["raw_file"], time.time() - start_time
        from .FastTelethon import upload_file
        from .helper import progress

        raw_file = None
        while not raw_file:
            with open(file, "rb") as f:
                raw_file = await upload_file(
                    client=self,
                    file=f,
                    filename=filename,
                    progress_callback=(
                        lambda completed, total: self.loop.create_task(
                            progress(completed, total, event, start_time, message)
                        )
                    )
                    if show_progress
                    else None,
                )
        cache = {
            "by_bot": by_bot,
            "size": size,
            "path": path,
            "name": filename,
            "raw_file": raw_file,
        }
        if self._cache.get("upload_cache"):
            self._cache["upload_cache"].append(cache)
        else:
            self._cache.update({"upload_cache": [cache]})
        if to_delete:
            with contextlib.suppress(FileNotFoundError):
                os.remove(file)
        return raw_file, time.time() - start_time

    async def fast_downloader(self, file, **kwargs):
        """تحميل الملفات بأسرع شكل"""
        filename = kwargs.get("filename")
        show_progress = kwargs.get("show_progress", False)
        if show_progress:
            event = kwargs["event"]
        if file.size < 10 * 2**20:
            show_progress = False
        import mimetypes

        from telethon.tl.types import DocumentAttributeFilename

        from .FastTelethon import download_file
        from .helper import progress

        start_time = time.time()
        if not filename:
            try:
                if isinstance(file.attributes[-1], DocumentAttributeFilename):
                    filename = file.attributes[-1].file_name
                assert filename != None
            except (IndexError, AssertionError):
                mimetype = file.mime_type
                filename = (
                    mimetype.split("/")[0]
                    + "-"
                    + str(datetime.now().strftime("%Y%m%d_%H%M%S"))
                    + mimetypes.guess_extension(mimetype)
                )
        message = kwargs.get("message", f"❃ جار التحميل {filename} ...")
        dirname = os.path.dirname(filename)
        if dirname and not os.path.exists(dirname):
            os.mkdir(dirname)
        raw_file = None
        while not raw_file:
            with open(filename, "wb") as f:
                raw_file = await download_file(
                    client=self,
                    location=file,
                    out=f,
                    progress_callback=(
                        lambda completed, total: self.loop.create_task(
                            progress(completed, total, event, start_time, message)
                        )
                    )
                    if show_progress
                    else None,
                )
        return raw_file, time.time() - start_time

    def run_in_loop(self, function):
        return self.loop.run_until_complete(function)

    def run(self):
        self.run_until_disconnected()

    def add_handler(self, func, *args, **kwargs):
        if func in list(map(lambda e: e[0], self.list_event_handlers())):
            return
        self.add_event_handler(func, *args, **kwargs)

    @property
    def full_name(self):
        return utils.get_display_name(self.me)

    @property
    def uid(self):
        return self.me.id

    def to_dict(self):
        return dict(inspect.getmembers(self))

    # ممكن تحذف
    async def parse_id(self, text):
        with contextlib.suppress(ValueError):
            text = int(text)
        return await self.get_peer_id(text)

    async def get_entity(
        self: "TelegramClient", entity: "hints.EntitiesLike"
    ) -> "hints.Entity":
        if isinstance(entity, str) and entity[0] != "+":
            with contextlib.suppress(ValueError):
                entity = int(entity)
        return await super().get_entity(entity)

    async def _get_custom_thumb(self, thumb: str):
        with contextlib.suppress(KeyError):
            thumb_ = self._thumb[thumb]
            if (datetime.now() - datetime.fromtimestamp(thumb_["time"])).days < 1:
                return thumb_["file"]
        _exists = os.path.exists(thumb)
        path = thumb if _exists else (await fast_download(thumb))[0]
        _thumb_ = await self.upload_file(path)
        if not _exists:
            os.remove(path)
        self._thumb[thumb] = {"file": _thumb_, "time": datetime.now().timestamp()}
        return _thumb_

    async def send_file(self, *args, **kwargs):
        custom = jmdB.get_key("CUSTOM_THUMBNAIL")
        if custom or custom is None:
            thumb = kwargs.get("thumb")
            if thumb is None:
                kwargs["thumb"] = await self._get_custom_thumb(
                    jmdB.get_key("CUSTOM_THUMBNAIL") or "resources/Tepthon.jpg"
                )
            elif thumb and isinstance(thumb, str) and thumb.startswith("http"):
                kwargs["thumb"] = await self._get_custom_thumb(thumb)
        return await super().send_file(*args, **kwargs)
