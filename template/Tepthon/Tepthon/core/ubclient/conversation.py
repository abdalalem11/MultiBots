from telethon.tl.custom import Message, Button
from telethon.tl import types
from telethon.tl.types import (
    InputKeyboardButtonUserProfile,
    KeyboardButtonSimpleWebView,
)



def message_link(self: "Message"):
    if self.chat.username:
        return f"https://t.me/{self.chat.username}/{self.id}"
    return f"https://t.me/c/{self.chat.id}/{self.id}"

setattr(Message, "message_link", property(message_link))



def mention(text, user):
    return InputKeyboardButtonUserProfile(text, user)


def web(text, url):
    return KeyboardButtonSimpleWebView(text, url)

is_button_inline = Button._is_inline

def is_inline(button):
    if isinstance(button, (
        types.InputKeyboardButtonUserProfile,
        types.KeyboardButtonSimpleWebView
    )):
        return True
    return is_button_inline(button)

setattr(Button, "mention", mention)
setattr(Button, "web", web)
setattr(Button, "_is_inline", is_inline)
