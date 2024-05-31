from aiogram import types

from api import api
from response_composer import ResponseComposer
from utils.logger import logger


def click(method):
    async def clicked(*args, **kw):
        msg = kw.get("msg")
        user = kw.get("user") or await api.get_user(telegram_id=msg.from_user.id)
        kw["user"] = user
        if user["is_baned"]:
            return await ResponseComposer.you_are_baned(user)
        logger.debug(f'User id={user["id"]}, tg={user["telegram_id"]} used {method.__name__}')
        if "msg" in kw:
            del kw["msg"]
        return await method(*args, **kw)

    return clicked
