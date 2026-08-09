import os
import sys
import logging

from Tepthon.config import Var
from .base import BaseDatabase

Redis = psycopg2 = Database = None
LOGS = logging.getLogger("Tepthon")


# تحميل مكتبة Redis
try:
    from redis import Redis
except ImportError:
    LOGS.info("Installing 'redis' for database.")
    os.system(
        f"{sys.executable} -m pip install -q redis hiredis"
    )
    from redis import Redis


if Redis:
    LOGS.info("Redis successfully imported.")


class RedisDB(BaseDatabase):

    def __init__(
        self,
        host,
        port=6379,
        password=None,
        logger=LOGS,
        *args,
        **kwargs,
    ):
        # إذا كان لدينا رابط Redis كامل
        if host and "://" in host:
            from urllib.parse import urlparse

            parsed = urlparse(host)

            host = parsed.hostname
            port = parsed.port or 6379

            if parsed.password:
                password = parsed.password

        # دعم host:port
        elif host and ":" in host:
            host, port = host.rsplit(":", 1)

            try:
                port = int(port)
            except ValueError:
                port = 6379

        if not host:
            logger.error(
                "Redis host غير موجود. "
                "أضف REDIS_URI أو REDISHOST في Environment Variables."
            )
            sys.exit(1)

        kwargs["host"] = host
        kwargs["port"] = port
        kwargs["password"] = password

        self.db = Redis(**kwargs)

        self.set = self.db.set
        self.get = self.db.get
        self.keys = self.db.keys
        self.delete = self.db.delete

        super().__init__()

    @property
    def name(self):
        return "REDIS"

    @property
    def usage(self):
        return sum(
            self.db.memory_usage(x) or 0
            for x in self.keys()
        )


def pyDatabase():

    if not Redis:
        LOGS.critical(
            "Redis library is not installed!"
        )
        sys.exit(1)

    # الأفضل استخدام REDIS_URI إذا كان موجودًا
    redis_uri = getattr(Var, "REDIS_URI", None)

    # وإلا نستخدم REDISHOST
    redis_host = getattr(Var, "REDISHOST", None)

    redis_password = getattr(
        Var,
        "REDIS_PASSWORD",
        None,
    )

    redis_port = getattr(
        Var,
        "REDISPORT",
        6379,
    )

    host = redis_uri or redis_host

    if not host:
        LOGS.critical(
            "No Redis configuration found!\n"
            "Please set REDIS_URI or REDISHOST."
        )
        sys.exit(1)

    try:
        return RedisDB(
            host=host,
            port=redis_port,
            password=redis_password,
            decode_responses=True,
            socket_timeout=5,
            retry_on_timeout=True,
        )

    except Exception as err:
        LOGS.exception(
            f"Redis connection failed: {err}"
        )
        sys.exit(1)
