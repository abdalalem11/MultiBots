from Tepthon import jmdB

BOTLOG_CHATID = jmdB.get_key("BOTLOG_CHATID")
BOTLOG = BOTLOG_CHATID

if not BOTLOG:
    BOTLOG = None
    BOTLOG_CHATID = None
