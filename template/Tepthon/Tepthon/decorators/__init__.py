from contextlib import suppress
from database import JmdB
from .manager import eod, eor


StatsHolder = {}

def should_allow_sudos():
    return JmdB.get_key("SUDO")


def get_sudos() -> list:
    return JmdB.get_key("SUDOS") or []


def is_sudo(userid):
    return userid in get_sudos()


def owner_and_sudos(only_full=False):
    if only_full:
        return [JmdB.get_config("OWNER_ID"), *fullsudos()]
    return [JmdB.get_config("OWNER_ID"), *get_sudos()]


def _parse(key):
    with suppress(TypeError):
        return int(key)
    return key


def fullsudos():
    fullsudos = []
    if sudos := JmdB.get_key("FULLSUDO"):
        fullsudos.extend(str(sudos).split())
    owner = JmdB.get_config("OWNER_ID")
    if owner and owner not in fullsudos:
        fullsudos.append(owner)
    return list(map(_parse, filter(lambda id: id, fullsudos)))
