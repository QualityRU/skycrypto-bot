import datetime
import math
import random
import string
import time
from collections import defaultdict
from decimal import Decimal

from aiogram import Dispatcher, types
from aiogram.dispatcher import DEFAULT_RATE_LIMIT
from aiogram.dispatcher.handler import CancelHandler, current_handler
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.utils.exceptions import Throttled
from dateutil.parser import parse
from dateutil.tz import UTC

from api import api
from settings import bot, redis_general

MESSAGES_WHILE_BANED = defaultdict(int)


def rate_limit(limit: int, key=None):
    def decorator(func):
        setattr(func, "throttling_rate_limit", limit)
        if key:
            setattr(func, "throttling_key", key)
        return func

    return decorator


async def save_message(message, bot=True):
    await api.message(message_id=message.message_id, telegram_id=message.chat.id, text=message.text, bot=bot)


class MessageMiddleware(BaseMiddleware):
    def __init__(self, limit=DEFAULT_RATE_LIMIT, key_prefix="antiflood_"):
        self.rate_limit = limit
        self.prefix = key_prefix
        super(MessageMiddleware, self).__init__()

    async def check_spam(self, message: types.Message):

        is_baned_key = f"is_baned_{message.from_user.id}"
        is_banned: str = redis_general.get(is_baned_key)

        if is_banned:
            # from data_handler import send_message
            # text = '🚫 Вы были забанены за спам. Если вы считаете, что это произошло по ошибке, пожалуйста, обратитесь в поддержку @SKY_CRYPTO_SUPPORT'
            # bot.loop.create_task(send_message(text, message.from_user.id))
            return True

    async def on_process_message(self, message: types.Message, _):
        if await self.check_spam(message):
            raise CancelHandler()

        handler = current_handler.get()
        dispatcher = Dispatcher.get_current()
        if handler:
            limit = getattr(handler, "throttling_rate_limit", self.rate_limit)
            key = getattr(handler, "throttling_key", f"{self.prefix}_{handler.__name__}")
        else:
            limit = self.rate_limit
            key = f"{self.prefix}_message"

        try:
            await dispatcher.throttle(key, rate=limit)
            MESSAGES_WHILE_BANED[message.from_user.id] = 0
        except Throttled as t:
            await self.message_throttled(message, t)
            current_cnt = MESSAGES_WHILE_BANED[message.from_user.id]
            MESSAGES_WHILE_BANED[message.from_user.id] = current_cnt + 1
            if current_cnt > 50:
                text = f"Более 50 сообщений заблокировано ботом от юзера {message.from_user.id} со времени последнего успешного ответа. Вероятно, спам атака"
                from data_handler import send_message

                for tg_id in (138510832, 173724189, 1144473266):
                    bot.loop.create_task(send_message(text, tg_id))
                MESSAGES_WHILE_BANED[message.from_user.id] = 0
            raise CancelHandler()

        # loop.create_task(save_message(message, bot=False))

    async def message_throttled(self, message: types.Message, throttled: Throttled):
        pass


def timeit(method):
    async def timed(*args, **kw):
        ts = time.time()
        result = await method(*args, **kw)
        te = time.time()
        logger.info(f"{method.__name__} {round((te - ts) * 1000, 2)} ms")
        return result

    return timed


def get_new_pk():
    return ch.get_new_pk()


def get_nickname():
    final_nick = "".join(random.choices(string.digits, k=3))
    final_nick += "".join(random.choices(string.ascii_letters, k=2))
    return final_nick


def get_random_str(len_=7):
    final_str = "".join(random.choices(string.ascii_letters, k=len_))
    return final_str


def get_time_in_3_seconds():
    return datetime.datetime.now() + datetime.timedelta(seconds=3)


def get_correct_value(num):
    if Decimal(str(num)) == 0:
        return Decimal("0")
    if "." in str(num):
        num = str(num).rstrip("0")
        if num[-1] == ".":
            num = num[:-1]
    return round(Decimal(num), 8)


async def get_brokers(user_currency):
    return await api.get_brokers(user_currency)


async def save_error(message, telegram_id):
    return
    # asyncio.create_task(api.error(telegram_id=telegram_id, text=message))


def truncate(number, digits) -> float:
    if isinstance(number, Decimal):
        number = float(number)
    stepper = 10.0**digits
    return math.floor(stepper * number) / stepper


def localize_datetime(dt: datetime.datetime):
    return dt.replace(tzinfo=UTC)


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(tz=UTC)


def parse_utc_datetime(dt: str) -> datetime.datetime:
    return localize_datetime(parse(dt))


def get_commission_exponent(number: float):
    return -Decimal(str(number)).as_tuple().exponent
