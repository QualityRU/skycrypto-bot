import asyncio
import os

import redis
import requests
from aiogram import Bot
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import Dispatcher

from utils.logger import logger

if os.environ.get("TEST"):
    host = os.environ.get("API_HOST")
    if host:
        API_HOST = host
    else:
        API_HOST = "http://api:5555"
else:
    API_HOST = "http://api:5555"

API_KEY = os.environ["API_KEY"]

settings = requests.get(API_HOST + "/settings", headers={"Token": API_KEY}).json()

SYMBOL = settings["symbol"]

redis_postfix = os.environ.get('REDIS_POSTFIX', SYMBOL)
redis_host = os.environ.get("REDIS_HOST") + redis_postfix

loop = asyncio.get_event_loop()
redis_general_host = os.environ.get("REDIS_GENERAL_HOST", "redis_general")

redis_general = redis.Redis(host=redis_general_host)

storage = RedisStorage2(db=5, host=redis_host)
token = os.environ.get("BOT_TOKEN")
controller_token = os.environ.get("CONTROLLER_TOKEN")
internal_controller_token = os.environ.get("INTERNAL_CONTROLLER_TOKEN")
if token is None:
    exit(1)

bot = Bot(token=token, parse_mode="html", loop=loop)
dp = Dispatcher(bot, storage=storage)

controller_bot = Bot(token=controller_token, parse_mode="html", loop=loop)
internal_controller_bot = Bot(token=internal_controller_token, parse_mode="html", loop=loop)

logger.warning(settings)
SYMBOL_NAME = settings["coin_name"]
CONTROL_CHAT_ID = settings["control_chat"]
MESSAGES_CHAT_ID = settings["messages_chat"]
PROFIT_CHAT_ID = settings["profits_chat"]
EARNINGS_CHAT_ID = settings["earnings_chat"]
DEAL_CONTROL_CHAT_ID = settings["deal_control_chat"]

DECIMALS = {"btc": 8, "eth": 18, "usdt": 6}[SYMBOL.lower()]


SUPPORT = "@SKY_CRYPTO_SUPPORT"
SUPPORT_ID = 507422683

PROMOCODE_TYPES = ["crypto", "fiat"]
MIN_PROMOCODE_AMOUNT_CRYPTO = {"eth": 0.001, "btc": 0.0001, "usdt": 1}
MIN_PROMOCODE_AMOUNT_FIAT = {"rub": 100, "usd": 1, "kzt": 500, "uah": 30, "byn": 3, "uzs": 10000, "azn": 1, "tjs": 100}
# KEY = os.environ['KEY_V2']

BUYER_COMMISSION = 0.01
SELLER_COMMISSION = 0.005
BUYER_REFERRAL_COMMISSION_FROM_COMMISSION = 0.4


CURRENCIES = ("rub", "inr", "usd", "uah")
LOTS_ON_PAGE = 10
STATES = "proposed", "confirmed", "paid", "closed", "deleted"

FILES_PATH = os.path.abspath("files")

IS_TEST = os.environ.get("TEST", False)
