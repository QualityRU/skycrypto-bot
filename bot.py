import base64
import os
import re
import time
import traceback
from datetime import datetime, timedelta
from io import BytesIO

import requests
from aiogram import exceptions, types
from aiogram.types.message import ContentType
from aiogram.utils import executor
from aiogram.utils.exceptions import MessageNotModified
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from constants import *
from data_handler import dh, send_message
from settings import Dispatcher, bot, dp, loop
from translations import get_trans_list, sm
from utils.helpers import MessageMiddleware, rate_limit, save_error


@dp.message_handler(commands=["id"])
@rate_limit(1)
async def get_id(message: types.Message):
    await message.reply(text=message.chat.id)


@dp.message_handler(commands=["start"], state="*")
@rate_limit(30)
async def start(message: types.Message, state):
    await state.reset_state(with_data=True)

    print(f"start: {message.from_user.id}")

    (text, k), data = await dh.start(msg=message)
    await state.set_state(CONFIRM_POLICY)
    file = BytesIO(requests.get("https://sky-site.s3.eu-west-2.amazonaws.com/agreement.pdf").content)
    file.name = "agreement.pdf"
    await bot.send_document(chat_id=message.chat.id, document=file)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("yes"), state=CONFIRM_START_WITHDRAW)
@rate_limit(1)
async def confirm_start_withdraw(message: types.Message, state):
    data = await state.get_data()
    address = data["address"]
    amount = data["amount"]
    token = data["token"]
    await state.reset_state(with_data=True)
    text, k = await dh.confirm_start_tx(msg=message, amount=amount, address=address, token=token)
    await message.reply(text, reply_markup=k, reply=False)


@dp.message_handler(lambda msg: msg.text in get_trans_list("no"), state=CONFIRM_START_WITHDRAW)
@rate_limit(1)
async def action_declined(message: types.Message, state):
    await state.reset_state(with_data=True)
    text, k = await dh.action_declined(msg=message)
    await message.reply(text, reply_markup=k, reply=False)


@dp.message_handler(lambda msg: msg.text.startswith(sm("confirm_policy")), state=CONFIRM_POLICY)
async def confirm_policy(message: types.Message, state):
    text, k = await dh.confirm_policy(msg=message, username=message.from_user.username)
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text.startswith(sm("wallet")))
@rate_limit(3)
async def wallet(message: types.Message):
    print(f"wallet: {message.from_user.id}")
    text, k = await dh.wallet(msg=message)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "wallet")
@rate_limit(1)
async def wallet_inline(message: types.CallbackQuery):
    text, k = await dh.wallet(msg=message)
    await message.message.edit_text(text, reply_markup=k)


@dp.message_handler(lambda msg: msg.text.startswith(sm("exchange")))
@rate_limit(3)
async def exchange(message: types.Message):
    print(f"exchange: {message.from_user.id}")
    text, k = await dh.exchange(msg=message)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "exchange")
@rate_limit(1)
async def exchange_inline(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.exchange(msg=message)
    if text == message.message.text:
        await bot.edit_message_reply_markup(
            message_id=message.message.message_id, chat_id=message.message.chat.id, reply_markup=k
        )
    else:
        await message.message.edit_text(text, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "active_deals")
@rate_limit(1)
async def active_deals(message: types.CallbackQuery):
    await message.answer()
    _, k = await dh.active_deals(msg=message)
    await bot.edit_message_reply_markup(
        message_id=message.message.message_id, chat_id=message.message.chat.id, reply_markup=k
    )


@dp.callback_query_handler(lambda msg: re.match(r"^deal [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def deal(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.deal(msg=message, deal_id=message.data.split()[1])
    await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: re.match(r"^/d[a-zA-Z0-9]+$", msg.text))
@rate_limit(1)
async def deal(message: types.Message):
    text, k = await dh.deal(msg=message, deal_id=message.text[2:])
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "deposit")
@rate_limit(1)
async def deposit(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.deposit(msg=message)
    await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "deposit_rub")
@rate_limit(1)
async def deposit_rub(message: types.CallbackQuery):
    await message.answer()
    qr = await dh.deposit_rub(msg=message)
    if qr:
        target_file = base64.b64decode(qr.split(',')[1])
        await bot.send_photo(chat_id=message.message.chat.id, photo=target_file)


@dp.callback_query_handler(lambda msg: msg.data == "withdraw")
@rate_limit(3)
async def withdraw(message: types.CallbackQuery, state):
    await message.answer()
    (text, k), status = await dh.withdraw(msg=message)
    if status:
        await state.set_state(CHOOSE_ADDRESS_WITHDRAW)
    await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=CHOOSE_ADDRESS_WITHDRAW)
@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=CHOOSE_AMOUNT_WITHDRAW)
@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=CONFIRMATION_WITHDRAW)
@dp.message_handler(lambda msg: msg.text in get_trans_list("no"), state=CONFIRMATION_WITHDRAW)
@rate_limit(1)
async def cancel_withdraw(message: types.Message, state):
    await state.reset_state(with_data=True)
    text, k = await dh.cancel_withdraw(msg=message)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(state=CHOOSE_ADDRESS_WITHDRAW)
@rate_limit(1)
async def handle_address(message: types.Message, state):
    (text, k), address = await dh.handle_address(msg=message, address=message.text)
    if address:
        await state.set_state(CHOOSE_AMOUNT_WITHDRAW)
        await state.set_data({"address": address})
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(state=CHOOSE_AMOUNT_WITHDRAW)
@rate_limit(1)
async def handle_amount(message: types.Message, state):
    data = await state.get_data()
    (text, k), success = await dh.handle_amount(msg=message, address=data["address"], text=message.text)
    if success:
        await state.set_state(CONFIRMATION_WITHDRAW)
        await state.set_data({"amount": message.text, **data})
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("yes"), state=CONFIRMATION_WITHDRAW)
@rate_limit(1)
async def confirm_withdraw(message: types.Message, state):
    data = await state.get_data()
    (text, k), success = await dh.handle_withdrawal(msg=message, address=data["address"], text=data["amount"])
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "promocodes")
@rate_limit(1)
async def promocodes(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.promocodes(msg=message)
    message = await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "reports")
@rate_limit(1)
async def reports(message: types.CallbackQuery):
    await message.answer()
    files = await dh.reports(msg=message)
    for file in files:
        await bot.send_document(document=file, chat_id=message.from_user.id)


@dp.message_handler(lambda msg: msg.text.startswith(sm("about")))
@rate_limit(3)
async def about(message: types.Message):
    print(f"about: {message.from_user.id}")
    text, k = await dh.about(msg=message)
    await message.reply(text, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "get_code")
@rate_limit(1)
async def get_code(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.get_code(msg=message)
    message = await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data.startswith("handle_lots"))
@rate_limit(1)
async def handle_lots(message: types.CallbackQuery):
    await message.answer()
    if message.data.split()[-1] == "0":
        return
    text, k = await dh.handle_lots(msg=message, data=message.data)
    try:
        if text == message.message.text:
            await bot.edit_message_reply_markup(
                chat_id=message.from_user.id, message_id=message.message.message_id, reply_markup=k
            )
        else:
            await message.message.edit_text(text, reply_markup=k)
    except:
        pass


@dp.callback_query_handler(lambda msg: msg.data == "change_trading_activity_status")
@rate_limit(1)
async def change_trading_activity_status(message: types.CallbackQuery):
    await message.answer()
    _, k = await dh.change_trading_activity_status(msg=message)
    try:
        await bot.edit_message_reply_markup(
            chat_id=message.from_user.id, message_id=message.message.message_id, reply_markup=k
        )
    except:
        pass


@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=NEW_LOT_TYPE)
@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=NEW_LOT_RATE)
@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=NEW_LOT_LIMITS)
@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=NEW_LOT_BROKER)
@rate_limit(1)
async def cancel_create_lot(message: types.Message, state):
    await state.reset_state(with_data=True)
    text, k = await dh.cancel_create_lot(msg=message)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda x: x.data == "create_lot")
@rate_limit(1)
async def create_lot(message: types.CallbackQuery, state):
    await message.answer()
    await state.set_state(NEW_LOT_TYPE)
    text, k = await dh.choose_type(msg=message)
    message = await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(content_types=types.ContentType.TEXT, state=NEW_LOT_TYPE)
@rate_limit(1)
async def new_lot_type(message: types.Message, state):
    (text, k), t = await dh.handle_type(msg=message, text=message.text)
    if t is not None:
        await state.set_state(NEW_LOT_BROKER)
        await state.set_data({"new_lot_type": t})

    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda x: x.text, state=NEW_LOT_BROKER)
@rate_limit(1)
async def new_lot_broker(message: types.Message, state):
    (text, k), broker = await dh.handle_broker(msg=message, text=message.text)
    if broker is not None:
        await state.set_state(NEW_LOT_RATE)
        data = await state.get_data()
        data["new_lot_broker"] = broker
        await state.set_data(data)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda x: x.text, state=NEW_LOT_RATE)
@rate_limit(1)
async def new_lot_rate(message: types.Message, state):
    (text, k), (new_lot_rate_, coefficient) = await dh.handle_rate(msg=message, text=message.text)
    if new_lot_rate_ is not None:
        await state.set_state(NEW_LOT_LIMITS)
        data = await state.get_data()
        data["new_lot_rate"] = str(new_lot_rate_)
        data["coefficient"] = str(coefficient) if coefficient else None
        await state.set_data(data)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda x: x.text, state=NEW_LOT_LIMITS)
@rate_limit(1)
async def new_lot_limits(message: types.Message, state):
    data = await state.get_data()
    (text, k), status = await dh.handle_creating_lot(msg=message, text=message.text, data=data)
    if status is True:
        await state.reset_state(with_data=True)

    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: re.match("^(buy|sell) [0-9]+$", msg.data))
@rate_limit(1)
async def market(message: types.CallbackQuery):
    await message.answer()
    t, page = message.data.split()
    if page == "0":
        return
    text, k = await dh.market(msg=message, page=int(page), t=t)
    if text != message.message.text:
        try:
            await message.message.edit_text(text, reply_markup=k)
        except MessageNotModified:
            pass


@dp.callback_query_handler(lambda msg: msg.data.startswith("lots buy "))
@rate_limit(1)
async def lots_buy_from_broker(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.menu_lots_buy_from_broker(msg=message, data=message.data)
    try:
        if text == message.message.text:
            await bot.edit_message_reply_markup(
                chat_id=message.from_user.id, message_id=message.message.message_id, reply_markup=k
            )
        else:
            await message.message.edit_text(text, reply_markup=k)
    except:
        pass


@dp.callback_query_handler(lambda msg: msg.data.startswith("lots sell "))
@rate_limit(1)
async def lots_sell_from_broker(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.menu_lots_sell_from_broker(msg=message, data=message.data)
    try:
        if text == message.message.text:
            await bot.edit_message_reply_markup(
                chat_id=message.from_user.id, message_id=message.message.message_id, reply_markup=k
            )
        else:
            await message.message.edit_text(text, reply_markup=k)
    except:
        pass


@dp.callback_query_handler(lambda msg: msg.data == "lots empty")
@rate_limit(1)
async def lots_empty(message: types.CallbackQuery):
    await message.answer()


@dp.message_handler(lambda msg: re.match(r"^/l[a-zA-Z0-9]+$", msg.text))
@rate_limit(1)
async def lot(message: types.Message):
    text, k = await dh.lot(msg=message, identificator=message.text[2:])
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: re.match("^lot [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def lot_inline(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.lot(msg=message, identificator=message.data.split()[1])
    await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: re.match("^begin_deal [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def begin_deal(message: types.CallbackQuery, state):
    await message.answer()
    (text, k), lot_id = await dh.begin_deal(msg=message, lot_id=message.data.split()[1])
    if lot_id is not None:
        await state.set_state(ENTER_SUM_DEAL)
        await state.set_data({"lot_id": lot_id, "pressed_at": int(time.time())})
    await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=ENTER_SUM_DEAL)
@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=ENTER_REQ_DEAL)
@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=CONFIRMATION_DEAL)
@dp.message_handler(lambda msg: msg.text in get_trans_list("no"), state=CONFIRMATION_DEAL)
@rate_limit(1)
async def cancel_create_deal(message: types.Message, state):
    await state.reset_state(with_data=True)
    text, k = await dh.cancel_create_deal(msg=message)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(state=ENTER_SUM_DEAL)
@rate_limit(1)
async def enter_sum_deal(message: types.Message, state):
    data = await state.get_data()
    (text, k), deal_sum, value_units, including_requisite_step = await dh.handle_sum_deal(
        msg=message, text=message.text, lot_id=data["lot_id"]
    )
    if deal_sum is not None:
        if including_requisite_step:
            await state.set_state(ENTER_REQ_DEAL)
        else:
            await state.set_state(CONFIRMATION_DEAL)
        data["value_currency"] = str(deal_sum)
        data["value_units"] = str(value_units)
        await state.set_data(data)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(state=ENTER_REQ_DEAL)
@rate_limit(1)
async def enter_req_deal(message: types.Message, state):
    data = await state.get_data()

    (text, k), req = await dh.handle_requisites(
        msg=message,
        text=message.text,
        lot_id=data["lot_id"],
        value_units=data["value_units"],
        value_currency=data["value_currency"],
    )
    if req is not None:
        await state.set_state(CONFIRMATION_DEAL)
        data["req"] = req
        await state.set_data(data)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(state=CONFIRMATION_DEAL)
@rate_limit(1)
async def confirmation_deal(message: types.Message, state):
    data = await state.get_data()
    (text, k), success = await dh.handle_create_deal(msg=message, data=data)
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


############### CANCELING DEAL ############


@dp.callback_query_handler(lambda msg: re.match("^cancel_deal [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def cancel_deal(message: types.CallbackQuery, state):
    await message.answer()
    (text, k), deal_id = await dh.cancel_deal(msg=message, deal_id=message.data.split()[1])
    if deal_id:
        await state.set_state(CONFIRMATION_DECLINE_DEAL)
        await state.set_data({"deal_id": deal_id})
    message = await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("yes"), state=CONFIRMATION_DECLINE_DEAL)
@rate_limit(1)
async def cancel_deal_confirmed(message: types.Message, state):
    data = await state.get_data()
    text, k = await dh.cancel_deal_confirmed(msg=message, deal_id=data["deal_id"])
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("no"), state=CONFIRMATION_DECLINE_DEAL)
@rate_limit(1)
async def decline_cancel_deal(message: types.Message, state):
    text, k = await dh.decline_cancel_deal(msg=message)
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


###########################################


@dp.callback_query_handler(lambda msg: re.match("^accept_deal [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def accept_deal(message: types.CallbackQuery, state):
    await message.answer()
    (text, k), include_req_step, deal_id = await dh.accept_deal(msg=message, deal_id=message.data.split()[1])
    if include_req_step:
        await state.set_state(ENTER_REQ_DEAL_WHILE_ACCEPTING)
        await state.set_data({"deal_id": deal_id})
    else:
        await state.reset_state(with_data=True)
    message = await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=ENTER_REQ_DEAL_WHILE_ACCEPTING)
@rate_limit(1)
async def cancel_enter_req(message: types.Message, state):
    await state.reset_state(with_data=True)
    text, k = await dh.cancel_enter_req(msg=message)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(state=ENTER_REQ_DEAL_WHILE_ACCEPTING)
@rate_limit(1)
async def enter_req_accepting(message: types.Message, state):
    data = await state.get_data()
    text, k = await dh.enter_req_accepting(msg=message, req=message.text)
    await state.set_data({'req': message.text, **data})
    await state.set_state(ENTER_REQ_DEAL_WHILE_ACCEPTING_CONFIRM)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("yes"), state=ENTER_REQ_DEAL_WHILE_ACCEPTING_CONFIRM)
@rate_limit(1)
async def enter_req_accepting_confirmed(message: types.Message, state):
    data = await state.get_data()
    text, k = await dh.enter_req_accepting_confirmed(msg=message, req=data['req'], deal_id=data["deal_id"])
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("no"), state=ENTER_REQ_DEAL_WHILE_ACCEPTING_CONFIRM)
@rate_limit(1)
async def enter_req_accepting_declined(message: types.Message, state):
    text, k = await dh.cancel_enter_req(msg=message)
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


#############################################


@dp.callback_query_handler(lambda msg: re.match("^confirm_sent_fiat [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def confirm_sent_fiat(message: types.CallbackQuery, state):
    await message.answer()
    (text, k), deal_id = await dh.confirm_sent_fiat(msg=message, deal_id=message.data.split()[1])
    if deal_id:
        await state.set_state(CONFIRMATION_FIAT_SENDING)
        await state.set_data({"deal_id": deal_id})
    message = await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("no"), state=CONFIRMATION_FIAT_SENDING)
@rate_limit(1)
async def unconfirm_sent_fiat(message: types.Message, state):
    text, k = await dh.unconfirm_sent_fiat(msg=message)
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("yes"), state=CONFIRMATION_FIAT_SENDING)
@rate_limit(1)
async def confirm_sent_fiat(message: types.Message, state):
    data = await state.get_data()
    text, k = await dh.confirm_sent_fiat_finaly(msg=message, deal_id=data["deal_id"])
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


#############################################


@dp.callback_query_handler(lambda msg: re.match("^send_crypto_wo_agreement [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def send_crypto_wo_agreement(message: types.CallbackQuery, state):
    await message.answer()
    (text, k), deal_id = await dh.send_crypto_wo_agreement(msg=message, deal_id=message.data.split()[1])
    if deal_id:
        await state.set_state(CRYPTO_SENDING_NO_CONFIRMATION)
        await state.set_data({"deal_id": deal_id})
    message = await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("no"), state=CRYPTO_SENDING_NO_CONFIRMATION)
@rate_limit(1)
async def unconfirm_send_crypto_wo_agreement(message: types.Message, state):
    text, k = await dh.unconfirm_send_crypto(msg=message)
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("yes"), state=CRYPTO_SENDING_NO_CONFIRMATION)
@rate_limit(1)
async def confirm_send_crypto_wo_agreement(message: types.Message, state):
    data = await state.get_data()
    text, k = await dh.confirm_send_crypto_wo_agreement(msg=message, deal_id=data["deal_id"])
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


#############################################


@dp.callback_query_handler(lambda msg: re.match("^run_payment [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def run_payment(message: types.CallbackQuery, state):
    await message.answer()
    (text, k), deal_id = await dh.run_payment(msg=message, deal_id=message.data.split()[1])
    if deal_id:
        await state.set_state(CRYPTO_SENDING_FD_DECLINED_DEAL)
        await state.set_data({"deal_id": deal_id})
    message = await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("no"), state=CRYPTO_SENDING_FD_DECLINED_DEAL)
@rate_limit(1)
async def unconfirm_run_payment(message: types.Message, state):
    text, k = await dh.unconfirm_send_crypto(msg=message)
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("yes"), state=CRYPTO_SENDING_FD_DECLINED_DEAL)
@rate_limit(1)
async def confirm_run_payment(message: types.Message, state):
    data = await state.get_data()
    await state.reset_state(with_data=True)
    text, k = await dh.confirm_run_payment(msg=message, deal_id=data["deal_id"])
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


#############################################



@dp.callback_query_handler(lambda msg: re.match("^run_payment_with_req [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def run_payment(message: types.CallbackQuery, state):
    await message.answer()
    (text, k), deal_id = await dh.run_payment_with_req(msg=message, deal_id=message.data.split()[1])
    if deal_id:
        await state.set_state(CRYPTO_SENDING_FD_DECLINED_DEAL_WITH_REQ)
        await state.set_data({"deal_id": deal_id})
    await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(state=CRYPTO_SENDING_FD_DECLINED_DEAL_WITH_REQ)
@rate_limit(1)
async def sending_no_agreement_with_req(message: types.Message, state):
    req = message.text
    data = await state.get_data()
    (text, k), deal_id = await dh.run_payment(msg=message, deal_id=data['deal_id'])
    await state.set_state(CRYPTO_SENDING_FD_DECLINED_DEAL_WITH_REQ_CONFIRMATION)
    await state.set_data({'req': req, **data})
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


# yes
@dp.message_handler(lambda msg: msg.text in get_trans_list("yes"), state=CRYPTO_SENDING_FD_DECLINED_DEAL_WITH_REQ_CONFIRMATION)
@rate_limit(1)
async def confirm_run_payment_with_req(message: types.Message, state):
    data = await state.get_data()
    text, k = await dh.confirm_run_payment_with_req(msg=message, req=data['req'], deal_id=data['deal_id'])
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


# no
@dp.message_handler(lambda msg: msg.text in get_trans_list("no"), state=CRYPTO_SENDING_FD_DECLINED_DEAL_WITH_REQ_CONFIRMATION)
@rate_limit(1)
async def unconfirm_run_payment_with_req(message: types.Message, state):
    text, k = await dh.unconfirm_send_crypto(msg=message)
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)




#############################################


@dp.callback_query_handler(lambda msg: re.match("^send_crypto [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def send_crypto(message: types.CallbackQuery, state):
    await message.answer()
    (text, k), deal_id = await dh.send_crypto(msg=message, deal_id=message.data.split()[1])
    if deal_id:
        await state.set_state(CONFIRMATION_CRYPTO_SENDING)
        await state.set_data({"deal_id": deal_id})
    message = await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("no"), state=CONFIRMATION_CRYPTO_SENDING)
@rate_limit(1)
async def unconfirm_send_crypto(message: types.Message, state):
    text, k = await dh.unconfirm_send_crypto(msg=message)
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("yes"), state=CONFIRMATION_CRYPTO_SENDING)
@rate_limit(1)
async def confirm_send_crypto(message: types.Message, state):
    data = await state.get_data()
    text, k = await dh.confirm_send_crypto(msg=message, deal_id=data["deal_id"])
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


###############################  DISPUTES  ######################################


@dp.callback_query_handler(lambda msg: re.match("^open_dispute [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def open_dispute(message: types.CallbackQuery):
    await message.answer()
    deal_id = message.data.split()[1]
    text, k = await dh.open_dispute(msg=message, deal_id=deal_id)
    await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: re.match(r"^decline_dispute [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def decline_dispute(message: types.CallbackQuery, state):
    await message.answer()
    (text, k), deal_id = await dh.decline_dispute(msg=message, deal_id=message.data.split()[1])
    if deal_id is not None:
        await state.set_state(DECLINE_DISPUTE)
        await state.set_data({"deal_id": deal_id})
    await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("no"), state=DECLINE_DISPUTE)
@rate_limit(1)
async def cancel_decline_dispute(message: types.Message, state):
    text, k = await dh.cancel_decline_dispute(msg=message)
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("yes"), state=DECLINE_DISPUTE)
@rate_limit(1)
async def handle_decline_dispute(message: types.Message, state):
    data = await state.get_data()
    text, k = await dh.handle_decline_dispute(msg=message, deal_id=data["deal_id"])
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: re.match("^(like|dislike) [0-9]+ [a-zA-Z0-9]+$", msg.data))
@rate_limit(2)
async def rate_user(message: types.CallbackQuery):
    await message.answer()
    try:
        await bot.edit_message_reply_markup(
            chat_id=message.from_user.id, message_id=message.message.message_id, reply_markup=None
        )
    except exceptions.MessageNotModified:
        pass
    method, user_id, deal_id = message.data.split()
    res = await dh.rate_user(msg=message, user_id=int(user_id), method=method, deal_id=deal_id)
    if res:
        text, k = res
        message = await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text.startswith(sm("about")))
@rate_limit(1)
async def about(message: types.Message):
    text, k = await dh.about(msg=message)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "about")
@rate_limit(1)
async def about_inline(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.about(msg=message)
    await message.message.edit_text(text, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "communication")
@rate_limit(1)
async def communication(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.communication(msg=message)
    await message.message.edit_text(text, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "friends")
@rate_limit(1)
async def friends(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.friends(msg=message)
    await message.message.edit_text(text, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "affiliate")
@rate_limit(1)
async def affiliate(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.affiliate(msg=message)
    await message.message.edit_text(text, reply_markup=k)


@dp.message_handler(lambda msg: msg.text.startswith(sm("settings")))
@rate_limit(3)
async def settings(message: types.Message):
    print(f"settings: {message.from_user.id}")
    text, k = await dh.settings(msg=message)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "settings")
@rate_limit(1)
async def settings_inline(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.settings(msg=message)
    await message.message.edit_text(text, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "lang_settings")
@rate_limit(1)
async def lang_settings(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.lang_settings(msg=message)
    await message.message.edit_text(text, reply_markup=k)


@dp.callback_query_handler(lambda msg: re.match(r"^lang_[a-z]{2}$", msg.data))
@rate_limit(1)
async def update_lang(message: types.CallbackQuery):
    await message.answer()
    new_lang = message.data.split('_')[1]
    text, k = await dh.update_lang_settings(msg=message, new_lang=new_lang)
    await message.message.edit_text(text, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "rate_settings")
@rate_limit(1)
async def rate_settings(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.rate_settings(msg=message)
    await message.message.edit_text(text, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "currency_settings")
@rate_limit(1)
async def currency_settings(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.currency_settings(msg=message)
    await message.message.edit_text(text, reply_markup=k)


@dp.callback_query_handler(lambda msg: re.match(r"^choose_currency [a-z]{3}$", msg.data))
@rate_limit(1)
async def choose_currency(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.choose_currency(msg=message, data=message.data)
    await message.message.edit_text(text, reply_markup=k)


######################################################################################


@dp.callback_query_handler(lambda msg: msg.data == "promocodes")
@rate_limit(1)
async def promocodes(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.promocodes(msg=message)
    await message.message.edit_text(text, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "create_promocode")
@rate_limit(1)
async def create_promocode_(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.create_promocode_(msg=message)
    await message.message.edit_text(text, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "activate_promocode")
@rate_limit(1)
async def activate_promocode(message: types.CallbackQuery, state):
    await message.answer()
    text, k = await dh.activate_promocode(msg=message)
    await state.set_state(ACTIVATE_PROMOCODE)
    message = await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=ACTIVATE_PROMOCODE)
@rate_limit(1)
async def cancel_activate_promocode(message: types.Message, state):
    await state.reset_state(with_data=True)
    text, k = await dh.cancel_activate_promocode(msg=message)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(state=ACTIVATE_PROMOCODE)
@rate_limit(1)
async def check_promocode(message: types.Message, state):
    await state.reset_state(with_data=True)
    text, k = await dh.check_promocode(msg=message, text=message.text)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: re.match(r"^create_promocode [a-z]+$", msg.data))
@rate_limit(1)
async def create_promocode(message: types.CallbackQuery, state):
    await message.answer()
    (text, k), type_ = await dh.create_promocode(msg=message, data=message.data)
    if type_ is not None:
        await state.set_data({"type": type_})
        await state.set_state(PROMOCODES_COUNT)
    message = await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=PROMOCODES_COUNT)
@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=PROMOCODES_AMOUNT)
@rate_limit(1)
async def cancel_create_promocode(message: types.Message, state):
    await state.reset_state(with_data=True)
    text, k = await dh.cancel_create_promocode(msg=message)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(state=PROMOCODES_COUNT)
@rate_limit(1)
async def handle_count(message: types.Message, state):
    data = await state.get_data()
    (text, k), count = await dh.handle_count(msg=message, text=message.text, promocode_type=data["type"])
    if count is not None:
        data["count"] = count
        await state.set_data(data)
        await state.set_state(PROMOCODES_AMOUNT)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(state=PROMOCODES_AMOUNT)
@rate_limit(1)
async def handle_amount(message: types.Message, state):
    data = await state.get_data()
    (text, k), success = await dh.handle_amount_promocode(
        msg=message, text=message.text, type_=data["type"], count=data["count"]
    )
    if success:
        await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: msg.data == "active_promocodes")
@rate_limit(1)
async def active_promocodes(message: types.CallbackQuery):
    await message.answer()
    await dh.active_promocodes(msg=message)


@dp.callback_query_handler(lambda msg: re.match(r"^delete_promocode [0-9]+$", msg.data))
@rate_limit(1)
async def delete_promocode(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.delete_promocode(msg=message, data=message.data)
    message = await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


########################################################################################


@dp.message_handler(lambda msg: msg.text.startswith("/u"))
@rate_limit(1)
async def user(message: types.Message):
    text, k = await dh.user(msg=message, nickname=message.text[2:])
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: re.match(r"^write_message [0-9]+$", msg.data))
@rate_limit(1)
async def write_message(message: types.CallbackQuery, state):
    await message.answer()
    (text, k), receiver_id = await dh.write_message(msg=message, data=message.data)
    await state.set_state(WRITE_MESSAGE)
    await state.set_data({"receiver_id": receiver_id})
    await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=WRITE_MESSAGE)
@rate_limit(1)
async def cancel_write_message(message: types.Message, state):
    await state.reset_state(with_data=True)
    text, k = await dh.cancel_write_message(msg=message)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(content_types=ContentType.TEXT, state=WRITE_MESSAGE)
@rate_limit(1)
async def send_text_message(message: types.Message, state):
    data = await state.get_data()
    text, k = await dh.send_usermessage(msg=message, text=message.text, receiver_id=data["receiver_id"])
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(content_types=ContentType.PHOTO, state=WRITE_MESSAGE)
@rate_limit(1)
async def send_photo(message: types.Message, state):
    data = await state.get_data()
    text, k = await dh.send_photo(msg=message, photo=message.photo, receiver_id=data["receiver_id"])
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(content_types=ContentType.DOCUMENT, state=WRITE_MESSAGE)
@rate_limit(1)
async def send_pdf(message: types.Message, state):
    data = await state.get_data()
    text, k = await dh.send_photo(msg=message, photo=message.document, receiver_id=data["receiver_id"])
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


##################################  SELF LOT  ##########################################


@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=CHANGE_LIMITS)
@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=CHANGE_CONDITIONS)
@dp.message_handler(lambda msg: msg.text.startswith(sm("cancel")), state=CHANGE_RATE)
@rate_limit(1)
async def cancel_change_lot(message: types.Message, state):
    await state.reset_state(with_data=True)
    text, k = await dh.cancel_change_lot(msg=message)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: re.match(r"^change_limits [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def change_limits(message: types.CallbackQuery, state):
    await message.answer()
    (text, k), lot_id = await dh.change_limits(msg=message, data=message.data)
    await state.set_state(CHANGE_LIMITS)
    await state.set_data({"lot_id": lot_id})
    message = await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(state=CHANGE_LIMITS)
@rate_limit(1)
async def edit_limits(message: types.Message, state):
    data = await state.get_data()
    text, k = await dh.edit_limits(msg=message, lot_id=data["lot_id"], text=message.text)
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: re.match(r"^change_rate [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def change_rate(message: types.CallbackQuery, state):
    await message.answer()
    (text, k), lot_id = await dh.change_rate(msg=message, data=message.data)
    await state.set_state(CHANGE_RATE)
    await state.set_data({"lot_id": lot_id})
    await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(state=CHANGE_RATE)
@rate_limit(1)
async def edit_rate(message: types.Message, state):
    data = await state.get_data()
    text, k = await dh.edit_rate(msg=message, lot_id=data["lot_id"], text=message.text)
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: re.match(r"^change_conditions [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def change_conditions(message: types.CallbackQuery, state):
    await message.answer()
    (text, k), lot_id = await dh.change_conditions(msg=message, data=message.data)
    await state.set_state(CHANGE_CONDITIONS)
    await state.set_data({"lot_id": lot_id})
    await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(state=CHANGE_CONDITIONS)
@rate_limit(1)
async def edit_conditions(message: types.Message, state):
    data = await state.get_data()
    text, k = await dh.edit_conditions(msg=message, lot_id=data["lot_id"], text=message.text)
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


############## DELETE LOT #######################


@dp.callback_query_handler(lambda msg: re.match(r"^delete_lot [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def delete_lot_confirmation(message: types.CallbackQuery, state):
    await message.answer()
    text, k = await dh.delete_lot_confirmation(msg=message, lot_id=message.data.split()[1])
    msg = await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)
    await state.set_data({"lot_id": message.data.split()[1]})
    await state.set_state(CONFIRMATION_DELETE_LOT)


@dp.message_handler(lambda msg: msg.text in get_trans_list("no"), state=CONFIRMATION_DELETE_LOT)
@rate_limit(1)
async def cancel_delete_lot(message: types.Message, state):
    await state.reset_state(with_data=True)
    text, k = await dh.cancel_delete_lot(msg=message)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text in get_trans_list("yes"), state=CONFIRMATION_DELETE_LOT)
@rate_limit(1)
async def delete_lot(message: types.Message, state):
    data = await state.get_data()
    text, k = await dh.delete_lot(msg=message, lot_id=data["lot_id"])
    await state.reset_state(with_data=True)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler(lambda msg: re.match(r"^change_lot_status [a-zA-Z0-9]+$", msg.data))
@rate_limit(1)
async def change_lot_status(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.change_lot_status(msg=message, data=message.data)
    await bot.edit_message_reply_markup(
        message_id=message.message.message_id, chat_id=message.message.chat.id, reply_markup=k
    )


@dp.callback_query_handler(lambda msg: re.match(r"^show .*$", msg.data))
@rate_limit(1)
async def show_text(message: types.CallbackQuery):
    await message.answer()
    await send_message(text=message.data.split()[1], chat_id=message.message.chat.id)


@dp.callback_query_handler(lambda msg: re.match(r"^decline_token$", msg.data))
@rate_limit(1)
async def decline_token(message: types.CallbackQuery):
    await message.answer()
    await bot.edit_message_reply_markup(
        message_id=message.message.message_id, chat_id=message.message.chat.id, reply_markup=None
    )
    text, k = await dh.action_declined(msg=message)
    await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


####################################


@dp.callback_query_handler(lambda msg: re.match(r"^(confirm|decline)_resolving [0-9]+$", msg.data))
@rate_limit(1)
async def confirm_resolving(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.confirm_resolving(msg=message, data=message.data)
    await message.message.edit_text(text, reply_markup=None)


@dp.callback_query_handler(lambda msg: re.match(r"^(confirm|decline)_transaction [0-9]+$", msg.data))
@rate_limit(1)
async def confirm_transaction(message: types.CallbackQuery):
    await message.answer()
    text, k = await dh.confirm_transaction(msg=message, data=message.data)
    await bot.edit_message_reply_markup(
        chat_id=message.message.chat.id, message_id=message.message.message_id, reply_markup=None
    )
    await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.message_handler(commands=["get_api_key"])
@rate_limit(1)
async def get_api_key(message: types.Message):
    text = await dh.get_api_key(msg=message)
    await send_message(text=text, chat_id=message.chat.id)


########################################################################################


@dp.callback_query_handler(lambda msg: re.match(r"^cancel_deal [0-9a-zA-Z]+ (buyer|seller)$", msg.data))
@rate_limit(1)
async def admin_cancel_deal(message: types.CallbackQuery):
    await message.answer()
    deal_id, winner = message.data.split()[1:]
    text, k = await dh.admin_cancel_deal(msg=message, winner=winner, deal_id=deal_id)
    await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)
    await bot.edit_message_reply_markup(
        chat_id=message.message.chat.id, message_id=message.message.message_id, reply_markup=None
    )


@dp.message_handler(commands=["menu"])
@rate_limit(1)
async def menu(message: types.Message):
    text, k = await dh.menu(msg=message)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler(lambda msg: msg.text.startswith("/get_tx"))
@rate_limit(1)
async def get_tx(message: types.Message):
    text = await dh.get_tx(msg=message, tx_hash=message.text.split()[1])
    await send_message(text=text, chat_id=message.chat.id)


@dp.callback_query_handler(lambda msg: msg.data == "users_report")
@rate_limit(1)
async def users_report(message: types.CallbackQuery):
    await message.answer()
    text = await dh.get_each_month(msg=message, prefix="ru")
    await bot.send_message(chat_id=message.from_user.id, text=text)


@dp.callback_query_handler(lambda msg: msg.data == "lots_report")
@rate_limit(1)
async def lots_report(message: types.CallbackQuery):
    await message.answer()
    text = await dh.get_each_month(msg=message, prefix="rl")
    await bot.send_message(chat_id=message.from_user.id, text=text)


@dp.callback_query_handler(lambda msg: msg.data == "exchange_report")
@rate_limit(1)
async def exchange_report(message: types.CallbackQuery):
    await message.answer()
    text = await dh.get_each_month(msg=message, prefix="re")
    await bot.send_message(chat_id=message.from_user.id, text=text)


@dp.callback_query_handler(lambda msg: msg.data == "promocodes_report")
@rate_limit(10)
async def promocodes_report(message: types.CallbackQuery):
    await message.answer()
    text = await dh.get_each_month(msg=message, prefix="rp")
    await bot.send_message(chat_id=message.from_user.id, text=text)


@dp.callback_query_handler(lambda msg: msg.data == "deals_report")
@rate_limit(1)
async def deals_report(message: types.CallbackQuery):
    await message.answer()
    text = await dh.get_each_month(msg=message, prefix="rd")
    await bot.send_message(chat_id=message.from_user.id, text=text)


@dp.callback_query_handler(lambda msg: msg.data == "transactions_report")
@rate_limit(1)
async def transactions_report(message: types.CallbackQuery):
    await message.answer()
    text = await dh.get_each_month(msg=message, prefix="rt")
    await bot.send_message(chat_id=message.from_user.id, text=text)


@dp.callback_query_handler(lambda msg: msg.data == "financial_report")
@rate_limit(1)
async def financial_report(message: types.CallbackQuery):
    await message.answer()
    text = await dh.get_each_month(msg=message, prefix="rf")
    await bot.send_message(chat_id=message.from_user.id, text=text)


@dp.callback_query_handler(lambda msg: msg.data == "merchant_report")
@rate_limit(1)
async def merchants_report(message: types.CallbackQuery):
    await message.answer()
    text = await dh.get_each_month(msg=message, prefix="rm")
    await bot.send_message(chat_id=message.from_user.id, text=text)


@dp.message_handler(lambda msg: re.match(r"^/r([dpleutfcm])_[0-9]+_[0-9]+$", msg.text))
@rate_limit(1)
async def report(message: types.Message):
    cmd, year, month = message.text.split("_")
    cmd = cmd[2:]
    if cmd == "d":
        meth = dh.report_deals
    elif cmd == "p":
        meth = dh.report_promocodes
    elif cmd == "l":
        meth = dh.report_lots
    elif cmd == "e":
        meth = dh.report_exchange
    elif cmd == "u":
        meth = dh.report_users
    elif cmd == "t":
        meth = dh.report_transactions
    elif cmd == "f":
        meth = dh.report_financial
    elif cmd == "m":
        meth = dh.report_merchants
    else:
        return
    doc = await meth(msg=message, year=int(year), month=int(month))
    await bot.send_document(chat_id=message.from_user.id, document=doc)


@dp.message_handler(
    lambda msg: re.match(r"^/p [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", msg.text)
)
@rate_limit(1)
async def get_payment_for_support(message: types.Message):
    payment_id = message.text.split()[1]
    text = await dh.get_payment_for_support(msg=message, payment_id=payment_id)
    await send_message(text=text, chat_id=message.chat.id)


@dp.message_handler(
    lambda msg: re.match(r"^/p2 [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", msg.text)
)
@rate_limit(1)
async def get_payment_for_support(message: types.Message):
    payment_id = message.text.split()[1]
    text = await dh.get_payment_v2_for_support(msg=message, payment_id=payment_id)
    await send_message(text=text, chat_id=message.chat.id)


@dp.message_handler(
    lambda msg: re.match(r"^/s [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", msg.text)
)
@rate_limit(1)
async def get_sale_for_support(message: types.Message):
    sale_id = message.text.split()[1]
    text = await dh.get_sale_for_support(msg=message, sale_id=sale_id)
    await send_message(text=text, chat_id=message.chat.id)


@dp.message_handler(
    lambda msg: re.match(r"^/s2 [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", msg.text)
)
@rate_limit(1)
async def get_sale_v2_for_support(message: types.Message):
    sale_v2_id = message.text.split()[1]
    text = await dh.get_sale_v2_for_support(msg=message, sale_v2_id=sale_v2_id)
    await send_message(text=text, chat_id=message.chat.id)


@dp.message_handler(
    lambda msg: re.match(r"^/cp [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", msg.text)
)
@rate_limit(1)
async def get_cpayment_for_support(message: types.Message):
    cpayment_id = message.text.split()[1]
    text = await dh.get_cpayment_for_support(msg=message, cpayment_id=cpayment_id)
    await send_message(text=text, chat_id=message.chat.id)


@dp.message_handler(
    lambda msg: re.match(r"^/w2 [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", msg.text)
)
@rate_limit(1)
async def get_withdrawal_for_support(message: types.Message):
    withdrawal_id = message.text.split()[1]
    text = await dh.get_withdrawal_for_support(msg=message, withdrawal_id=withdrawal_id)
    await send_message(text=text, chat_id=message.chat.id)


@dp.message_handler(lambda msg: re.match(r"^/rcontr_[0-9]+_[0-9]+_[0-9]+$", msg.text))
@rate_limit(1)
async def report_control(message: types.Message):
    _, year, month, day = message.text.split("_")
    doc = await dh.report_control(msg=message, year=int(year), month=int(month), day=int(day))
    await bot.send_document(chat_id=message.from_user.id, document=doc)


@dp.callback_query_handler(lambda msg: msg.data == "campaigns_report")
@rate_limit(1)
async def campaigns_report(message: types.CallbackQuery):
    await message.answer()
    doc = await dh.campaigns_report(msg=message)
    await bot.send_document(chat_id=message.from_user.id, document=doc)


@dp.callback_query_handler(lambda msg: re.match(r"^user_(lots|promocodes|deals|transactions)_report [0-9]+$", msg.data))
@rate_limit(1)
async def user_report(message: types.CallbackQuery):
    await message.answer()
    method = message.data.split("_")[1]
    user_id = int(message.data.split()[1])
    separated = method in ("deals", "transactions")
    files = await dh.user_report(msg=message, user_id=user_id, method=method, separated=separated)
    for file in files:
        await bot.send_document(chat_id=message.from_user.id, document=file)


@dp.callback_query_handler(lambda msg: re.match(r"^transit [0-9]+$", msg.data))
@rate_limit(1)
async def transit(message: types.CallbackQuery):
    await message.answer()
    text, _ = await dh.transit(msg=message, user_id=int(message.data.split()[1]))
    await send_message(text=text, chat_id=message.message.chat.id)


@dp.message_handler(lambda msg: msg.text.startswith("/send_notif_all "))
@rate_limit(1)
async def send_to_all(message: types.Message):
    await dh.send_to_all(msg=message, text=message.text)


@dp.callback_query_handler(
    lambda msg: re.match(r"^change_(ban|shadowban|applyshadowban|verification|superverification|skypay|skypayv2|allowsell|allowsalev2|usermessagesban)_status [0-9]+$", msg.data)
)
@rate_limit(1)
async def change_user_status(message: types.CallbackQuery):
    await message.answer()
    meth = message.data.split("_")[1]
    text, k = await getattr(dh, f"change_{meth}_status")(msg=message, user_id=int(message.data.split()[1]))
    await message.message.edit_text(text, reply_markup=k)


@dp.message_handler(commands=["profit"])
@rate_limit(1)
async def profit(message: types.Message):
    text, _ = await dh.profit(msg=message)
    await message.reply(text, reply=False)


@dp.message_handler(commands=["rdisbal"])
@rate_limit(1)
async def reset_imbalance(message: types.Message):
    text, _ = await dh.reset_imbalance(msg=message)
    await message.reply(text, reply=False)


@dp.message_handler(lambda msg: re.match(r"^/add(b|bm|f) [a-zA-Z0-9]+ [0-9,.-]+$", msg.text))
@rate_limit(1)
async def change_balance_frozen(message: types.Message):
    cmd, nickname, amount = message.text.split()
    cmd = cmd[-2:].replace("d", "")
    if cmd == "b":
        method = dh.change_balance
    elif cmd == "bm":
        method = dh.change_balance_m
    elif cmd == "f":
        method = dh.change_frozen
    # elif cmd == 'fm':
    #     method = dh.change_frozen_m
    else:
        return
    text, k = await method(msg=message, nickname=nickname, amount=float(amount))
    await message.reply(text, reply_markup=k)


@dp.message_handler(lambda msg: re.match(r"^/sndtx [a-zA-Z0-9]+ [0-9.]+$", msg.text))
@rate_limit(1)
async def withdraw_from_payments_node(message: types.Message):
    _, address, amount = message.text.split()
    text, k = await dh.withdraw_from_payments_node(msg=message, address=address, amount=float(amount))
    await message.reply(text, reply_markup=k)


@dp.message_handler(lambda msg: re.match(r"^/new_c [а-яa-zА-ЯA-Z0-9_]+$", msg.text))
@rate_limit(1)
async def new_campaign(message: types.Message):
    _, campaign_name = message.text.split()
    text = await dh.new_campaign(msg=message, name=campaign_name)
    await message.reply(text, reply=False)


@dp.message_handler(lambda msg: re.match(r"^/(frozen|balance) [a-zA-Z0-9]+ [0-9,.-]+$", msg.text))
@rate_limit(1)
async def set_balance_frozen(message: types.Message):
    cmd, nickname, amount = message.text.split()
    cmd = cmd[1:]
    text = await getattr(dh, f"set_{cmd}")(msg=message, nickname=nickname, amount=float(amount))
    await message.reply(text)


@dp.message_handler(lambda msg: re.match(r"^/ban_messages_all [0-9]+$", msg.text))
@rate_limit(1)
async def ban_all_messages(message: types.Message):
    _, telegram_id = message.text.split()
    text = await dh.ban_all_messages(msg=message, tg_id=telegram_id)
    await message.reply(text)


@dp.message_handler(lambda msg: re.match(r"^/cban_messages_all [0-9]+$", msg.text))
@rate_limit(1)
async def unban_all_messages(message: types.Message):
    _, telegram_id = message.text.split()
    text = await dh.unban_all_messages(msg=message, tg_id=telegram_id)
    await message.reply(text)


@dp.message_handler(commands=["frozen"])
@rate_limit(1)
async def frozen(message: types.Message):
    text, k = await dh.frozen(msg=message)
    await message.reply(text, reply_markup=k)


@dp.message_handler(commands=["stopw"])
@rate_limit(1)
async def stop_withdraw(message: types.Message):
    text = await dh.stop_withdraw(msg=message)
    await message.reply(text)


@dp.message_handler(commands=["stopfd"])
@rate_limit(1)
async def stop_fast_deal(message: types.Message):
    text = await dh.stop_fast_deal(msg=message)
    await message.reply(text)


@dp.message_handler(commands=["finreport"])
@rate_limit(1)
async def finreport(message: types.Message):
    text = await dh.finreport(msg=message)
    await message.reply(text)


@dp.message_handler(lambda msg: msg.forward_from)
@rate_limit(1)
async def get_user_by_forward(message: types.Message):
    text, k = await dh.get_user_by_forward(msg=message, telegram_id=message.forward_from.id)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.message_handler()
@rate_limit(1)
async def default(message: types.Message, state):
    await state.reset_state(with_data=True)
    text, k = await dh.unknown_command(msg=message)
    await send_message(text=text, chat_id=message.chat.id, reply_markup=k)


@dp.callback_query_handler()
@rate_limit(1)
async def default_inline(message: types.CallbackQuery, state):
    await state.reset_state(with_data=True)
    text, k = await dh.unknown_command(msg=message)
    await send_message(text=text, chat_id=message.message.chat.id, reply_markup=k)


@dp.errors_handler()
async def some_error(update: types.update.Update, error):
    user_telegram_id = update.message.from_user.id if update.message else update.callback_query.from_user.id
    await save_error(traceback.format_exc(), telegram_id=user_telegram_id)
    text, k = await dh.some_error()
    await send_message(chat_id=user_telegram_id, text=text, reply_markup=k)
    s = dp.current_state(user=user_telegram_id, chat=user_telegram_id)
    await s.finish()
    # if IS_TEST:
    #     await send_message(chat_id=user_telegram_id, text=traceback.format_exc(), reply_markup=k)


async def shutdown(dispatcher: Dispatcher):
    await dispatcher.storage.close()
    await dispatcher.storage.wait_closed()


# async def startup(dispatcher: Dispatcher):
#     if IS_TEST:
#         tg_ids = await dh.get_all_telegram_ids()
#         for tg_id in tg_ids:
#             try:
#                 await bot.send_message(chat_id=tg_id, text='Сервер обновлен')
#             except:
#                 pass


if __name__ == "__main__":
    dp.middleware.setup(MessageMiddleware())
    run_scheduler = not bool(os.environ.get('IGNORE_TASKS'))
    if run_scheduler:
        scheduler = AsyncIOScheduler(event_loop=loop)
        scheduler.add_job(dh.get_updates, "interval", seconds=4, max_instances=1)
        scheduler.add_job(dh.get_control_updates, "interval", seconds=10, max_instances=1)
        scheduler.add_job(dh.send_control_queued_messages, "interval", seconds=60, max_instances=1)
        scheduler.add_job(dh.send_queued_messages, "interval", seconds=10, max_instances=1)
        scheduler.add_job(
            dh.get_profit, "interval", minutes=15, max_instances=1, next_run_time=datetime.utcnow() + timedelta(seconds=3)
        )
        scheduler.start()
    executor.start_polling(dp, loop=loop, on_shutdown=shutdown)
