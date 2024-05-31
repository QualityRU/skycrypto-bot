import asyncio
import calendar
import csv
import io
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal

import pandas as pd
from aiogram.utils.exceptions import CantParseEntities
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta

from api import api
from constants import DealTypes
from errors import BadRequestError
from response_composer import rc
from settings import (CONTROL_CHAT_ID, DEAL_CONTROL_CHAT_ID, EARNINGS_CHAT_ID, IS_TEST, LOTS_ON_PAGE, MESSAGES_CHAT_ID,
                      MIN_PROMOCODE_AMOUNT_CRYPTO, MIN_PROMOCODE_AMOUNT_FIAT, PROFIT_CHAT_ID, PROMOCODE_TYPES, STATES,
                      SUPPORT_ID, SYMBOL, bot, controller_bot, internal_controller_bot, redis_general)
from translations import get_trans_list
from utils.click import click
from utils.helpers import get_correct_value, save_message, utc_now, parse_utc_datetime
from utils.logger import logger
from utils.sky_math import math as sky_math
from utils.validators import validate_amount_precision_right_for_symbol

MESSAGE_QUEUE = []
CONTROL_MESSAGE_QUEUE_V2 = []


def admin_only(method):
    async def wrapper(*args, **kw):
        if not kw["user"]["is_admin"]:
            return await rc.error(kw["user"])
        return await method(*args, **kw)

    return wrapper


async def send_message(
    text,
    chat_id,
    reply_markup=None,
    save=True,
    silent=True,
    is_control=False,
    queue_on_fail=False,
    tries=0,
    is_internal_control=False,
):
    try:
        if is_control:
            message = await controller_bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        elif is_internal_control:
            message = await internal_controller_bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        else:
            message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        # if save:
        #     bot.loop.create_task(save_message(message))
    except Exception as e:
        logger.exception(e)
        logger.warning(f"TEXT: {text}, chat_id: {chat_id}")
        if queue_on_fail:
            MESSAGE_QUEUE.append(
                {
                    "chat_id": chat_id,
                    "text": text,
                    "reply_markup": reply_markup,
                    "save": save,
                    "silent": silent,
                    "is_control": is_control,
                    "queue_on_fail": False,
                    "tries": tries + 1,
                    "is_internal_control": True,
                }
            )
        if not silent:
            raise


START_TXS_DATETIME = {}


class DataHandler:
    async def send_queued_messages(self):
        while MESSAGE_QUEUE:
            item = MESSAGE_QUEUE.pop()
            if item["tries"] < 10:
                await send_message(**item)
                await asyncio.sleep(0.1)

    async def send_control_queued_messages(self):
        while CONTROL_MESSAGE_QUEUE_V2:
            coroutine, kw = CONTROL_MESSAGE_QUEUE_V2.pop()
            success = False
            while not success:
                try:
                    await coroutine(**kw)
                    success = True
                    await asyncio.sleep(0.5)
                except CantParseEntities:
                    success = True
                except Exception as e:
                    logger.exception(e)
                    await asyncio.sleep(5)

    async def transaction_updates(self, updates):
        for update in updates:
            amount = update["amount"]
            t = update["type"]
            user = await api.get_user(user_id=update["user_id"])
            if t == "in":
                text, k = await rc.new_income(user, amount)
            elif t == "out":
                link = update["link"]
                text, k = await rc.transaction_processed(user, link)
            await send_message(chat_id=user["telegram_id"], text=text, reply_markup=k, queue_on_fail=True)

    async def message_updates(self, updates):
        for update in updates:
            sender = await api.get_user(user_id=update["sender_id"])
            message = update["message"]
            media_url = update["media_url"]
            receiver = await api.get_user(user_id=update["receiver_id"])
            if receiver["telegram_id"]:
                if media_url:
                    try:
                        if media_url[-3:] == 'pdf':
                            await bot.send_document(chat_id=receiver["telegram_id"], document=media_url)
                        else:
                            await bot.send_photo(chat_id=receiver["telegram_id"], photo=media_url)
                    except Exception as e:
                        logger.exception(e)
                    text, k = await rc.photo_received(receiver, sender)
                else:
                    text, k = await rc.message_received(receiver, sender, message)

                await send_message(chat_id=receiver["telegram_id"], text=text, reply_markup=k, queue_on_fail=True)

    async def new_referral_updates(self, updates):
        for update in updates:
            user = await api.get_user(user_id=update["user_id"])
            referral = update["referral"]
            text, k = await rc.new_referral(user, referral)
            await send_message(chat_id=user["telegram_id"], text=text, reply_markup=k)

    async def accounts_join_updates(self, updates):
        for update in updates:
            tg_user = await api.get_user(user_id=update["tg_account"])
            web_user = await api.get_user(user_id=update["web_account"])
            token = update["token"]
            text, k = await rc.new_accounts_join(tg_user, web_user, token)
            await send_message(chat_id=tg_user["telegram_id"], text=text, reply_markup=k)

    async def timeouts_updates(self, updates):
        for update in updates:
            user = await api.get_user(user_id=update["user_id"])
            text, _ = await rc.message_about_deal_timeout(user, update["deal_id"])
            if user["telegram_id"]:
                await send_message(chat_id=user["telegram_id"], text=text)

    async def deal_cancel_updates(self, updates):
        for update in updates:
            user = await api.get_user(user_id=update["user_id"])
            text, _ = await rc.opponent_canceled_deal(user, update["deal_id"])
            if user["telegram_id"]:
                await send_message(chat_id=user["telegram_id"], text=text)

    async def promocode_activation_updates(self, updates):
        for update in updates:
            user = await api.get_user(user_id=update["user_id"])
            text, _ = await rc.promocode_activated_by(user, update["activator"], update["amount"], update["code"])
            await send_message(chat_id=user["telegram_id"], text=text, queue_on_fail=True)

    async def deal_dispute_updates(self, updates):
        for update in updates:
            user = await api.get_user(user_id=update["user_id"])
            dispute = await api.get_dispute(update["deal_id"])
            text = None
            if dispute["opponent"] and dispute["initiator"]:
                text, k = await rc.both_opened_dispute(dispute["initiator"], update["deal_id"])
            else:
                deal = await api.get_deal(update["deal_id"])
                if deal['type'] != DealTypes.sky_pay_v2:
                    can_decline = deal["buyer"]["id"] == user["id"]
                    text, k = await rc.opponent_opened_dispute(
                        user, update["deal_id"], update["dispute_time"], can_decline=can_decline
                    )
            if user["telegram_id"] and text:
                await send_message(chat_id=user["telegram_id"], text=text, reply_markup=k, queue_on_fail=True)

    async def deal_dispute_notifications_updates(self, updates):
        for update in updates:
            user = await api.get_user(user_id=update["user_id"])
            text, k = await rc.dispute_opened_notification(user, update["deal_id"])
            if user["telegram_id"]:
                await send_message(chat_id=user["telegram_id"], text=text, reply_markup=k, queue_on_fail=True)

    async def deal_closed_dispute_updates(self, updates):
        for update in updates:
            user = await api.get_user(user_id=update["user_id"])
            winner = update["winner"]
            if update["admin"]:
                text, k = await rc.deal_closed_by_dispute_admin(user, update["deal_id"], winner)
            else:
                text, k = await rc.deal_closed_by_dispute(user, update["deal_id"], winner)
            if user["telegram_id"]:
                await send_message(chat_id=user["telegram_id"], text=text, reply_markup=k, queue_on_fail=True)

    async def control_updates(self, updates):
        for update in updates:
            update["symbol"] = update["symbol"].upper()
            update["created_at"] = update["created_at"].split(".")[0]
            update["balance"] = round(update["balance"], 6)
            update["frozen"] = round(update["frozen"], 6)
            update["change_balance"] = round(update["change_balance"], 6)
            update["change_frozen"] = round(update["change_frozen"], 6)
            update["message"] = update["message"].replace("<", "").replace(">", "")
            text = (
                "<b>Пользователь:</b> /u{user}\n"
                "<b>Инстанс:</b> {instance}\n"
                "<b>Время:</b> {created_at}\n"
                "<b>Баланс:</b> {change_balance} {symbol}\n"
                "<b>Заморозка:</b> {change_frozen} {symbol}\n"
                "<b>Сообщение:</b> {message}\n"
                "<b>Текущий баланс:</b> {balance} {symbol}\n"
                "<b>Текущая заморозка:</b> {frozen} {symbol}"
            ).format(**update)
            CONTROL_MESSAGE_QUEUE_V2.append(
                (
                    send_message,
                    dict(chat_id=CONTROL_CHAT_ID, text=text, save=False, is_internal_control=True, silent=False),
                )
            )
            for message_type in ("deal", "sky pay", "sale", "processing temp seller balance", "Cpayment"):
                update["message"] = update["message"].replace("<", "").replace(">", "")
                if message_type in update["message"].lower():
                    text = (
                        "<b>Пользователь:</b> /u{user}\n" "<b>Время:</b> {created_at}\n" "<b>Сообщение:</b> {message}"
                    ).format(**update)
                    if "deal" in update["message"].lower():
                        deal_index = update["message"].lower().find("deal")
                        if 'Recreating deal' in update['message']:
                            identificator = update["message"][deal_index + 6 : deal_index + 16]
                        else:
                            identificator = update["message"][deal_index + 5 : deal_index + 15]
                        deal = await api.get_deal(identificator, expand_email=True)
                        email = deal["buyer"]["email"]
                        if email:
                            email = email.replace("<", "").replace(">", "")
                        text += f"\n<b>Сумма в {deal['currency'].upper()}:</b> {deal['amount_currency']}"
                        text += f"\n<b>Реквизиты:</b> {deal['requisite']}"
                        text += f"\n<b>Имейл покупателя:</b> {email}"
                    CONTROL_MESSAGE_QUEUE_V2.append(
                        (
                            send_message,
                            dict(chat_id=DEAL_CONTROL_CHAT_ID, text=text, is_control=True, save=False, silent=False),
                        )
                    )
                    break

    async def control_usermessages(self, updates):
        for update in updates:
            base_text = f'📨  /u{update["sender"]}  ➡️  /u{update["receiver"]}'
            if update["url"]:
                try:
                    if update['url'][-3:] == 'pdf':
                        await bot.send_document(chat_id=MESSAGES_CHAT_ID, document=update['url'], caption=base_text)
                    else:
                        await bot.send_photo(chat_id=MESSAGES_CHAT_ID, photo=update["url"], caption=base_text)
                except Exception:
                    logger.exception("usermessage not controled")
            else:
                text = base_text + f'\n\n{update["message"]}'
                await send_message(text, chat_id=MESSAGES_CHAT_ID, save=False, queue_on_fail=True)

    async def earnings(self, updates):
        for update in updates:
            income = update["income"]
            prefix = "+" if income > 0 else ""
            await send_message(f"{prefix} {income} {SYMBOL.upper()}", chat_id=EARNINGS_CHAT_ID, save=False)

    async def secondary_node_updates(self, updates):
        if SYMBOL != "btc":
            return
        for update in updates:
            amount = update["amount"]
            link = update["link"]
            text = f"<b>Пополнение запаса!</b>\n\n" f"Сумма: {amount} BTC\n" f"Ссылка: {link}"
            await send_message(text, chat_id=PROFIT_CHAT_ID, save=False)

    async def auto_withdrawal_updates(self, updates):
        for update in updates:
            amount = update["amount"]
            link = update["link"]
            symbol = update.get("symbol", "BTC")
            text = f"<b>Автоматика!</b>\n\n" f"Сумма: {amount} {symbol}\n" f"Ссылка: {link}"
            await send_message(text, chat_id=PROFIT_CHAT_ID, save=False)

    async def deals_referrals_updates(self, updates):
        for update in updates:
            user = await api.get_user(user_id=update["user_id"])
            referral = await api.get_user(user_id=update["referral_id"])
            text, k = await rc.referral_earning(user, referral, update["amount"])
            await send_message(chat_id=user["telegram_id"], text=text, reply_markup=k)

    async def _notify_user_dispute_is_ready(self, user, deal):
        text, k = await rc.notify_dispute_is_ready(user, deal)
        await send_message(
            chat_id=user["telegram_id"], text=text, reply_markup=k, queue_on_fail=True
        )

    async def deals_updates(self, updates):
        for update in updates:
            user = await api.get_user(user_id=update["user_id"])
            opponent = await api.get_user(user_id=update["opponent"])
            deal = await api.get_deal(deal_id=update["deal_id"])
            if deal["state"] == STATES[0]:
                limit_for_deal = (await api.get_settings())["base_deal_time"]
                text, k = await rc.propose_deal(user, deal["lot"], deal, opponent["nickname"], limit_for_deal)
            elif deal["state"] == STATES[1]:
                long_limit = (await api.get_settings())["advanced_deal_time"]
                if deal["lot"]["type"] == "buy":
                    text, k = await rc.opponent_confirmed_deal(user, deal, long_limit=long_limit)
                else:
                    deal = await api.get_deal(update["deal_id"], with_merchant=True)
                    required_mask = False
                    if deal["payment_id"] and deal["merchant"]:
                        required_mask = deal["merchant"]["required_mask"]
                    text, k = await rc.confirm_sent_fiat(user, deal, long_limit=long_limit, required_mask=required_mask)
            elif deal["state"] == STATES[2]:
                mask = await api.get_mask(deal["identificator"])

                is_show_dispute_button = user['rating'] > 0 or user['is_verify']
                if (
                    deal["type"] in (DealTypes.sky_pay, DealTypes.fast, DealTypes.sky_pay_v2)
                ):
                    is_show_dispute_button = utc_now() > (parse_utc_datetime(deal["created"]) + timedelta(minutes=5)) and user['rating'] > 0

                if not is_show_dispute_button and user["telegram_id"] and (user['rating'] > 0 or user['is_verify']):
                    async def notify_user(u, d):
                        await asyncio.sleep(300.0)
                        d = await api.get_deal(d['identificator'])
                        if d['state'] == STATES[2]:
                            await self._notify_user_dispute_is_ready(u, d)

                    asyncio.create_task(notify_user(user, deal))

                text_name = "please_check_fiat" if is_show_dispute_button else "please_check_fiat_with_5_min"
                text, k = await rc.please_check_fiat(user, deal, mask, text_name, is_show_dispute_button)
            elif deal["state"] == STATES[3]:
                text, k = await rc.you_received_crypto(user, deal)
            elif deal["state"] == STATES[4]:
                text, k = await rc.opponent_canceled_deal(user, deal["identificator"])
            if user["telegram_id"]:
                await send_message(chat_id=user["telegram_id"], text=text, reply_markup=k, queue_on_fail=True)

    async def parse_updates(self, updates):
        await self.message_updates(updates["messages"])
        await self.new_referral_updates(updates["new-referral"])
        await self.transaction_updates(updates["transactions"])
        await self.accounts_join_updates(updates["accounts_join"])
        await self.timeouts_updates(updates["deals"]["timeouts"])
        await self.deals_referrals_updates(updates["deals"]["referrals"])
        await self.deals_updates(updates["deals"]["deals"])
        await self.deal_cancel_updates(updates["deals"]["cancel"])
        await self.promocode_activation_updates(updates["promocodes"])
        await self.deal_dispute_updates(updates["deals"]["disputes"])
        await self.deal_dispute_notifications_updates(updates["deals"]["dispute_notifications"])
        await self.deal_closed_dispute_updates(updates["deals"]["closed_disputes"])
        await self.control_usermessages(updates["usermessages"])
        await self.earnings(updates["earnings"])
        await self.secondary_node_updates(updates["secondary_node"])
        # await self.auto_withdrawal_updates(updates['autowithdrawal'])

    async def get_updates(self):
        try:
            updates = await api.get_updates()
            await self.parse_updates(updates)
        except Exception as e:
            logger.exception(f"updates failure: {e}")

    async def get_control_updates(self):
        try:
            updates = await api.get_control_updates()
            await self.control_updates(updates)
        except Exception as e:
            logger.exception(f"updates failure: {e}")

    async def get_profit(self):
        text = await self._get_profit_text()
        await send_message(text, chat_id=PROFIT_CHAT_ID, save=False)

    def _get_id_from_start_msg(self, msg, prefix, length):
        param_text = msg.text.split()
        object_id = None
        if len(param_text) == 2:
            param_text = param_text[1]
            if param_text.startswith(prefix) and len(param_text[len(prefix) :]) == length:
                object_id = param_text[len(prefix) :]
        return object_id

    def get_campaign(self, msg):
        return self._get_id_from_start_msg(msg, "c-", 16)

    def get_payment(self, msg):
        return self._get_id_from_start_msg(msg, "p-", 36)

    def get_ref_code(self, msg):
        splited = msg.text.split()
        ref_code = None
        if len(splited) > 1 and len(splited[1]) <= 10:
            ref_code = splited[1]
        return ref_code

    async def start(self, msg):
        user_telegram_id = msg.from_user.id
        print(user_telegram_id)
        is_exist = await api.is_user_exist(user_telegram_id)
        if not is_exist:
            ref_code = self.get_ref_code(msg)
            campaign = self.get_campaign(msg)
            user = await api.new_user(telegram_id=user_telegram_id, campaign=campaign, ref_code=ref_code)
        else:
            user = await api.get_user(telegram_id=user_telegram_id)
        return await rc.confirm_policy(user), None

    @click
    async def confirm_start_tx(self, user, amount, address, token):
        if address in START_TXS_DATETIME and not IS_TEST:
            if START_TXS_DATETIME[address] > datetime.utcnow() - timedelta(minutes=10):
                return await rc.error(user)

        amount = Decimal(amount)
        wallet = await api.get_wallet(user_id=user["id"])
        if amount > wallet["balance"]:
            return await rc.not_enough_funds_tx(user, amount, wallet["balance"])
        else:
            START_TXS_DATETIME[address] = datetime.utcnow()
            api.send_transaction_sync(user["id"], amount, address, with_proxy=True, token=token)
            return await rc.done(user)

    @click
    async def action_declined(self, user):
        return await rc.action_canceled(user)

    @click
    async def wallet(self, user):
        await api.create_wallet_if_not_exists(user["id"])
        stat = await api.user_stat(user["id"])
        wallet = await api.get_wallet(user["id"])

        is_bound = (await api.is_web_bound(user["id"]))["status"]

        return await rc.wallet(
            user,
            balance=wallet["balance"],
            frozen=wallet["frozen"],
            deposited=stat["deposited"],
            withdrawn=stat["withdrawn"],
            about=wallet["balance_currency"],
            deal_cnt=stat["deals"],
            revenue=stat["revenue"],
            days_registered=stat["days_registered"],
            likes=stat["likes"],
            dislikes=stat["dislikes"],
            rating=stat["rating"],
            rating_sm=stat["rating_logo"],
            is_bound=is_bound,
        )

    @click
    async def confirm_policy(self, user, username):
        text, k = await rc.start(user)
        await send_message(chat_id=user["telegram_id"], text=text, reply_markup=k)
        return await rc.start_second(user, username=username)

    @click
    async def exchange(self, user):
        active_deals_count = await api.get_active_deals_count(user["id"])
        lots_cnt = len(await api.get_user_lots(user["id"]))
        rate = await api.get_rate(user["currency"])
        return await rc.exchange(user, rate, active_deals_count, lots_cnt)

    @click
    async def active_deals(self, user):
        active_deals = await api.get_active_deals(user["id"])
        return await rc.active_deals(user, active_deals)

    @click
    async def deal(self, user, deal_id):
        try:
            deal = await api.get_deal(deal_id, with_merchant=True)
            if deal["symbol"] != SYMBOL:
                raise Exception
        except Exception as e:
            return await rc.deal_does_not_exists(user)
        required_mask = False
        mask = None
        if deal["payment_id"] and deal["merchant"]:
            required_mask = deal["merchant"]["required_mask"]
            if required_mask:
                mask = await api.get_mask(deal['identificator'])

        return await rc.deal(user, deal, user["is_admin"], required_mask=required_mask, mask=mask)

    @click
    async def deposit(self, user):
        wallet = await api.get_wallet(user["id"])
        min_deposit = (await api.get_settings())['min_tx_amount']
        text, _ = await rc.deposit(user, min_deposit)
        await send_message(chat_id=user["telegram_id"], text=text)
        return wallet["address"], None

    @click
    async def deposit_rub(self, user):
        try:
            response = await api.deposit_rub(user["id"])
            qr = response["qrBase64"]
            text, _ = await rc.pre_deposit_rub_text(user)
            await send_message(chat_id=user['telegram_id'], text=text)
            return qr
        except:
            text, k = await rc.service_unavailable_error(user)
            await send_message(chat_id=user['telegram_id'], text=text, reply_markup=k)

    @click
    async def withdraw(self, user):
        settings = await api.get_settings()
        min_to_withdraw = settings["min_tx_amount"]
        wallet = await api.get_wallet(user["id"])
        balance = wallet["balance"]
        if balance < min_to_withdraw:
            return await rc.not_enoungh_funds(user, min_to_withdraw=min_to_withdraw, balance=balance), False
        return await rc.withdraw(SYMBOL, user, wallet["last_address"]), True

    @click
    async def cancel_withdraw(self, user):
        return await rc.cancel_withdraw(user)

    @click
    async def handle_address(self, user, address):
        wallet = await api.get_wallet(user["id"])
        is_wallet_valid = (await api.address_validation_check(address))["is_valid"]
        if not is_wallet_valid:
            return await rc.wrong_address(user), None
        settings = await api.get_settings()
        min_to_withdraw = settings["min_tx_amount"]
        balance = wallet["balance"]
        commission = await api.get_withdraw_commission(balance)
        commission, dynamic_commissions = commission['commission'], commission['dynamic_commissions']
        return (
            await rc.choose_amount_withdraw(
                user, balance=balance, commission=commission,
                chosen_address=address, min_to_withdraw=min_to_withdraw,
                dynamic_commissions=dynamic_commissions
            ),
            address,
        )

    @click
    async def handle_amount(self, user, address, text):
        try:
            str_amount = text.replace(" ", "").replace(",", ".")
            amount = Decimal(str_amount)
            validate_amount_precision_right_for_symbol(amount)
        except Exception as e:
            logger.info(f'User {user["id"]} chosen wrong amount of withdraw={text}: {e}')
            return await rc.wrong_sum(user), False

        wallet = await api.get_wallet(user["id"])
        if amount > wallet['withdrawal_limit']:
            return await rc.wrong_sum(user), False

        balance = wallet["balance"]
        settings = await api.get_settings()
        min_to_withdraw = settings["min_tx_amount"]
        if amount > Decimal(str(balance)) or amount < Decimal(str(min_to_withdraw)):
            return await rc.wrong_sum(user), False

        return await rc.withdrawal_confirmation(user, amount, address), True

    @click
    async def handle_withdrawal(self, user, address, text):
        str_amount = text.replace(" ", "").replace(",", ".")
        amount = Decimal(str_amount)

        wallet = await api.get_wallet(user["id"])
        balance = wallet["balance"]
        settings = await api.get_settings()
        min_to_withdraw = settings["min_tx_amount"]

        if amount > Decimal(str(balance)) or amount < Decimal(str(min_to_withdraw)):
            return await rc.wrong_sum(user), False

        try:
            print("Send transaction")
            await api.send_transaction(user["id"], amount=float(amount), address=address)
        except Exception as e:
            print(str(e))
            if "conflict" in str(e).lower():
                return await rc.withdrawal_limit_reached(user), False
            return await rc.error(user), False
        else:
            return await rc.transaction_in_queue(user), True

    def _get_abstract_report(self, data, filename):
        file = io.StringIO()
        pd.DataFrame().from_dict(data).to_csv(file)
        file = io.BytesIO(file.getvalue().encode())
        file.name = filename
        return file

    @click
    async def reports(self, user):
        data = await api.get_reports(user["id"])
        files = [self._get_abstract_report(data_items, f"{name}.csv") for name, data_items in data.items()]
        return files

    @click
    async def handle_lots(self, user, data):
        lots = await api.get_user_lots(user["id"])
        wallet = await api.get_wallet(user["id"])
        currencies = {lot["currency"] for lot in lots}
        currencies.add(user["currency"])
        rates = {}
        for currency in currencies:
            rates[currency] = Decimal(str(await api.get_rate(currency)))

        page = int(data.split()[-1])
        lots_count = len(lots)
        pages = math.ceil(lots_count / LOTS_ON_PAGE)
        lots_page = lots[LOTS_ON_PAGE * (page - 1): LOTS_ON_PAGE * page]

        return await rc.handle_lots(user, lots_page, wallet["is_active"], rates, page, pages)

    @click
    async def change_trading_activity_status(self, user):
        await api.change_trading_status(user["id"])
        data = "handle_lots 1"
        return await self.handle_lots(user=user, data=data)

    @click
    async def choose_type(self, user):
        return await rc.choose_type(user)

    @click
    async def handle_type(self, user, text):
        if text in get_trans_list("you_wanna_buy", symbol=SYMBOL.upper()):
            new_lot_type = "buy"
        elif text in get_trans_list("you_wanna_sell", symbol=SYMBOL.upper()):
            new_lot_type = "sell"
        else:
            return await rc.wrong_lot_type(user), None
        brokers = await api.get_brokers(user["currency"])
        return await rc.choose_broker(user, [b["name"] for b in brokers]), new_lot_type

    @click
    async def handle_broker(self, user, text):
        broker = text
        brokers = await api.get_brokers(user["currency"])
        target_broker = next(filter(lambda b: b["name"] == broker, brokers), None)
        if target_broker is None:
            return await rc.wrong_broker(user, brokers), None
        rate = await api.get_rate(user["currency"])
        return await rc.choose_rate(user, rate), target_broker["id"]

    @click
    async def handle_rate(self, user, text):
        rate = await api.get_rate(user["currency"])
        rate_variation = await self._get_rate_variation(user['currency'])
        try:
            new_lot_rate, coefficient = await sky_math.parse_rate(
                text, Decimal(str(rate)), rate_variation
            )
        except Exception as e:
            return await rc.wrong_rate(user), (None, None)
        if coefficient is not None:
            text, _ = await rc.price_now(user, new_lot_rate)
            await send_message(chat_id=user["telegram_id"], text=text)
        return await rc.choose_limits(user), (new_lot_rate, coefficient)

    @click
    async def handle_creating_lot(self, user, text, data):
        try:
            new_lot_limit_below, new_lot_limit_above = await sky_math.parse_limits(text)
        except ValueError as e:
            return await rc.wrong_limits(user), False
        lot = await api.create_lot(
            _type=data["new_lot_type"],
            limit_from=new_lot_limit_below,
            limit_to=new_lot_limit_above,
            user_id=user["id"],
            broker=data["new_lot_broker"],
            rate=data["new_lot_rate"],
            coefficient=data["coefficient"],
        )
        text, k = await rc.lot_created(user)
        await send_message(chat_id=user["telegram_id"], text=text, reply_markup=k)
        return await rc.new_lot(user, lot), True

    @click
    async def cancel_create_lot(self, user):
        return await rc.cancel_create_lot(user)

    @click
    async def cancel_create_deal(self, user):
        return await rc.cancel_create_deal(user)

    @click
    async def cancel_enter_req(self, user):
        return await rc.cancel_enter_req(user)

    @click
    async def market(self, user, page, t):
        rate = await api.get_rate(user["currency"])
        total_lots = await api.get_lots(user["id"], t)
        lots = total_lots[(page - 1) * LOTS_ON_PAGE : page * LOTS_ON_PAGE]
        pages = math.ceil(len(total_lots) / LOTS_ON_PAGE)
        return await rc.market(user, lots, page, pages, rate, t)

    async def _get_broker(self, broker_id=None, name=None):
        brokers = await api.get_brokers()
        return next(filter(lambda b: b["name"] == name or b["id"] == broker_id, brokers), None)

    @click
    async def menu_lots_buy_from_broker(self, user, data):
        broker = await self._get_broker(broker_id=data.split()[2])
        page = int(data.split()[-1])
        lots = await api.get_broker_lots(user["id"], "buy", broker["id"])
        lots_cnt = len(lots)
        lots = lots[LOTS_ON_PAGE * (page - 1) : LOTS_ON_PAGE * page]
        pages = math.ceil(lots_cnt / LOTS_ON_PAGE)
        return await rc.menu_lots_buy_from_broker(user, lots, page, pages, broker)

    @click
    async def menu_lots_sell_from_broker(self, user, data):
        broker = await self._get_broker(broker_id=data.split()[2])
        page = int(data.split()[-1])
        lots = await api.get_broker_lots(user["id"], "sell", broker["id"])
        lots_cnt = len(list(lots))

        lots = sorted(lots, key=lambda x: (x["is_online"] or x["is_verify"], x["rate"]), reverse=True)

        lots = lots[LOTS_ON_PAGE * (page - 1) : LOTS_ON_PAGE * page]
        pages = math.ceil(lots_cnt / LOTS_ON_PAGE)
        return await rc.menu_lots_sell_from_broker(user, lots, page, pages, broker)

    async def are_users_active(self, lot, user):
        lot_user = await api.get_user(user_id=lot["user_id"])
        return not lot_user["is_baned"] and not user["is_baned"]

    async def is_enough_money(self, lot, user):
        target_money = lot["limit_from"] / lot["rate"]
        seller = lot["user_id"] if lot["type"] == "sell" else user["id"]
        seller_wallet = await api.get_wallet(seller)
        return seller_wallet["balance"] >= target_money

    async def session_closed(self):
        return await rc.session_closed()

    @click
    async def lot(self, user, identificator):
        try:
            lot = await api.get_lot(identificator)
            if lot["symbol"] != SYMBOL:
                raise Exception
        except Exception:
            return await rc.no_such_lot(user)
        if lot["user_id"] == user["id"]:
            return await rc.self_lot(user, lot)
        else:
            lot_user_stat = await api.user_stat(lot["user_id"])
            lot_user = await api.get_user(user_id=lot["user_id"])
            if lot["type"] == "sell":
                wallet = await api.get_wallet(lot["user_id"])
            elif lot["type"] == "buy":
                wallet = await api.get_wallet(user["id"])
            limit_to = await sky_math.get_maximum_limit(lot, wallet["balance"])
            is_enough_money = await self.is_enough_money(lot, user)
            are_users_active = await self.are_users_active(lot, user)
            is_message_baned = await api.get_is_usermessages_baned(user["id"], lot["user_id"])
            return await rc.lot(user, lot, {**lot_user_stat, **lot_user}, is_enough_money, are_users_active, limit_to, not is_message_baned)

    #######################################        DEALS       #######################################

    @click
    async def begin_deal(self, user, lot_id):
        lot = await api.get_lot(lot_id)
        if user['shadow_ban']:
            return await rc.you_are_baned(user), None

        if lot["is_deleted"]:
            return await rc.lot_deleted(user), None

        if not lot["is_active"]:
            return await rc.lot_not_active(user), None

        else:
            seller_id = lot["user_id"] if lot["type"] == "sell" else user["id"]
            wallet = await api.get_wallet(seller_id)
            lot["limit_to"] = await sky_math.get_maximum_limit(lot, wallet["balance"])
            return await rc.enter_sum_deal(user, lot), lot_id

    @click
    async def handle_sum_deal(self, user, text, lot_id):
        if "." in text or "," in text:
            return await rc.wrong_sum(user), None, None, None
        try:
            value_currency = await sky_math.parse_amount(text)
            assert value_currency > 0
        except Exception:
            return await rc.wrong_sum(user), None, None, None
        lot = await api.get_lot(lot_id)

        seller_id = lot["user_id"] if lot["type"] == "sell" else user["id"]
        wallet = await api.get_wallet(seller_id)

        lot["limit_to"] = await sky_math.get_maximum_limit(lot, wallet["balance"])

        if value_currency > lot["limit_to"] or value_currency < lot["limit_from"]:
            return await rc.wrong_sum(user), None, None, None

        value_units = Decimal(value_currency / Decimal(str(lot["rate"]))).quantize(
            Decimal("0.00000001"), rounding=ROUND_DOWN
        )
        value_units = Decimal(get_correct_value(value_units))

        including_requisite_step = lot["type"] == "buy"
        if including_requisite_step:
            broker = await self._get_broker(name=lot["broker"])
            last_reqs = await api.get_last_requisites(user["id"], lot['currency'], broker["id"])
            to_return = await rc.enter_req_deal(user, lot, last_reqs)
        else:
            to_return = await rc.agreement_deal(user, lot, value_units, value_currency)

        return to_return, value_currency, value_units, including_requisite_step

    @click
    async def handle_requisites(self, user, text, lot_id, value_units, value_currency):
        req = text
        lot = await api.get_lot(lot_id)
        return await rc.agreement_deal(user, lot, value_units, value_currency), req

    async def is_rate_changed(self, lot_rate, amount, amount_currency):
        real_rate = amount_currency / amount
        diff = await sky_math.get_percents_diff_rate(real_rate, lot_rate)
        logger.info(
            f"Lot rate: {lot_rate}, "
            f"real_rate: {real_rate}, "
            f"amount_currency: {amount_currency}, "
            f"amount: {amount}, "
            f"diff: {diff}"
        )
        return abs(diff) > 1

    @click
    async def handle_create_deal(self, user, data):
        amount = Decimal(data["value_units"])
        amount_currency = Decimal(data["value_currency"])
        requisite = data.get("req")
        lot = await api.get_lot(data["lot_id"])

        seller_wallet = await api.get_wallet(user["id"] if lot["type"] == "buy" else lot["user_id"])

        lot["limit_to"] = await sky_math.get_maximum_limit(lot, seller_wallet["balance"])
        if amount_currency > lot["limit_to"] or amount > seller_wallet["balance"]:
            return await rc.error(user), False

        if await self.is_rate_changed(lot["rate"], amount, amount_currency):
            return await rc.rate_changed(user), False

        try:
            deal = await api.create_deal(
                rate=lot["rate"],
                lot_id=lot["identificator"],
                user_id=user["id"],
                amount=float(amount),
                amount_currency=float(amount_currency),
                requisite=requisite,
            )
        except:
            return await rc.too_much_deals(user), False

        return await rc.deal_run(user, deal), True

    @click
    async def cancel_deal(self, user, deal_id):
        deal = await api.get_deal(deal_id)
        if (
            user["id"] not in [deal["seller"]["id"], deal["buyer"]["id"]]
            or deal["state"] in STATES[2:]
            or (user["id"] == deal["seller"]["id"] and deal["state"] == STATES[1])
        ):
            return await rc.error(user), None
        return await rc.cancel_deal(user, deal), deal_id

    @click
    async def cancel_deal_confirmed(self, user, deal_id):
        deal = await api.get_deal(deal_id)
        if (
            user["id"] not in [deal["seller"]["id"], deal["buyer"]["id"]]
            or deal["state"] in STATES[2:]
            or (user["id"] == deal["seller"]["id"] and deal["state"] == STATES[1])
        ):
            return await rc.error(user), None
        await api.cancel_deal(user["id"], deal_id)
        return await rc.deal_canceled(user, deal)

    @click
    async def decline_cancel_deal(self, user):
        return await rc.decline_cancel_deal(user)

    @click
    async def cancel_delete_lot(self, user):
        return await rc.cancel_delete_lot(user)

    @click
    async def accept_deal(self, user, deal_id):
        deal = await api.get_deal(deal_id)
        if deal["state"] == STATES[0]:
            if deal["lot"]["type"] == "sell":
                broker = await self._get_broker(name=deal["lot"]["broker"])
                last_req = await api.get_last_requisites(user["id"], deal['currency'], broker["id"])
                return await rc.enter_req_deal(user, deal["lot"], last_requisites=last_req), True, deal_id
            elif deal["lot"]["type"] == "buy":
                await api.update_deal_state(user["id"], deal_id)
                long_limit = (await api.get_settings())["advanced_deal_time"]
                return await rc.confirm_sent_fiat(deal["buyer"], deal, long_limit=long_limit), False, deal_id

        return await rc.error(user), None, None

    @click
    async def enter_req_accepting(self, user, req):
        return await rc.confirm_requisite_deal(user, req)

    @click
    async def enter_req_accepting_confirmed(self, user, req, deal_id):
        deal = await api.get_deal(deal_id)
        if deal["state"] == STATES[0] and deal["lot"]["type"] == "sell":
            await api.update_deal_req(user_id=user["id"], deal_id=deal_id, req=req)
            await api.update_deal_state(user["id"], deal_id)
            long_limit = (await api.get_settings())["advanced_deal_time"]
            return await rc.opponent_confirmed_deal(deal["seller"], deal, long_limit=long_limit)

        return await rc.error(user)

    @click
    async def confirm_sent_fiat(self, user, deal_id):
        deal = await api.get_deal(deal_id)
        if deal["state"] == STATES[1]:
            return await rc.are_you_sure_sent_fiat(deal["buyer"], deal), deal_id

        return await rc.error(user), None

    @click
    async def unconfirm_sent_fiat(self, user):
        return await rc.back_to_main_menu(user)

    @click
    async def confirm_sent_fiat_finaly(self, user, deal_id):
        deal = await api.get_deal(deal_id)
        if deal["state"] == STATES[1]:
            await api.update_deal_state(user_id=user["id"], deal_id=deal_id)
            return await rc.opponent_notified(deal["buyer"])

        return await rc.error(user)

    @click
    async def send_crypto(self, user, deal_id):
        deal = await api.get_deal(deal_id)
        if deal["state"] == STATES[2]:
            return await rc.deal_confirmation(deal["seller"], deal), deal_id
        return await rc.error(user), None

    @click
    async def send_crypto_wo_agreement(self, user, deal_id):
        deal = await api.get_deal(deal_id)
        if deal["state"] == STATES[1]:
            return await rc.deal_confirmation(deal["seller"], deal), deal_id
        return await rc.error(user), None

    @click
    async def run_payment(self, user, deal_id):
        deal = await api.get_deal(deal_id)
        if deal["state"] == STATES[4]:
            return await rc.deal_confirmation(deal["seller"], deal), deal_id
        return await rc.error(user), None

    @click
    async def run_payment_with_req(self, user, deal_id):
        deal = await api.get_deal(deal_id)
        if deal["state"] == STATES[4]:
            return await rc.deal_confirmation_enter_req(deal["seller"]), deal_id
        return await rc.error(user), None

    @click
    async def unconfirm_send_crypto(self, user):
        return await rc.back_to_main_menu(user)

    @click
    async def confirm_send_crypto(self, user, deal_id):
        deal = await api.get_deal(deal_id)
        if deal["state"] == STATES[2]:
            await api.update_deal_state(user["id"], deal["identificator"])
            return await rc.you_sent_crypto(deal["seller"], deal)
        return await rc.error(user)

    @click
    async def confirm_send_crypto_wo_agreement(self, user, deal_id):
        deal = await api.get_deal(deal_id)
        if deal["state"] == STATES[1]:
            await api.send_crypto_wo_agreement(user["id"], deal["identificator"])
            return await rc.you_sent_crypto(deal["seller"], deal)
        return await rc.error(user)

    @click
    async def confirm_run_payment(self, user, deal_id):
        deal = await api.get_deal(deal_id)
        if deal["state"] == STATES[4]:
            try:
                await api.confirm_declined_fd_deal(user["id"], deal["identificator"])
            except:
                return await rc.error(user)
            return await rc.you_sent_crypto(deal["seller"], deal)
        return await rc.error(user)

    @click
    async def confirm_run_payment_with_req(self, user, req, deal_id):
        deal = await api.get_deal(deal_id)
        if deal["state"] == STATES[4]:
            try:
                await api.set_mask(mask=req, deal_id=deal['identificator'])
                await api.confirm_declined_fd_deal(user["id"], deal["identificator"])
            except:
                return await rc.error(user)
            return await rc.you_sent_crypto(deal["seller"], deal)
        return await rc.error(user)

    @click
    async def rate_user(self, user, method, user_id, deal_id):
        try:
            await api.rate_user(rate_from=user["id"], rate_to=user_id, method=method, deal_id=deal_id)
            return await rc.back_to_main_menu(user)
        except:
            pass

    @click
    async def about(self, user):
        return await rc.about(user)

    @click
    async def communication(self, user):
        return await rc.communication(user)

    @click
    async def friends(self, user):
        return await rc.friends(user)

    @click
    async def affiliate(self, user):
        data = await api.get_affiliate(user["id"])
        return await rc.affiliate(
            user,
            invited_cnt=data["invited_count"],
            earned_from_ref=data["earned_from_ref"],
            earned_in_currency=data["earned_from_ref_currency"],
        )

    @click
    async def get_code(self, user):
        bot_ = await bot.get_me()
        data = await api.get_affiliate(user["id"])
        link = f'https://t.me/{bot_.username}?start={data["ref_code"]}'
        return link, None

    @click
    async def settings(self, user):
        return await rc.settings(user)

    @click
    async def lang_settings(self, user):
        return await rc.lang_settings(user)

    @click
    async def update_lang_settings(self, user, new_lang):
        await api.update_user(user['id'], lang=new_lang)
        user['lang'] = new_lang
        text, k = await rc.done(user)
        await send_message(chat_id=user["telegram_id"], text=text, reply_markup=k)
        return await rc.settings(user)

    @click
    async def rate_settings(self, user):
        rate = await api.get_rate(user["currency"])
        return await rc.rate_settings(user, rate)

    @click
    async def currency_settings(self, user):
        currencies = await api.get_currencies()
        return await rc.currency_settings(user, currencies)

    @click
    async def choose_currency(self, user, data):
        new_cur = data.split()[-1]
        await api.update_user(user["id"], currency=new_cur)
        return await rc.settings(user)

    @click
    async def promocodes(self, user):
        active_promocodes_cnt = await api.get_active_promocodes_count(user["id"])
        return await rc.promocodes(user, active_promocodes_cnt)

    @click
    async def create_promocode_(self, user):
        wallet = await api.get_wallet(user["id"])
        return await rc.create_promocode(user, wallet["balance"], wallet["balance_currency"])

    @click
    async def activate_promocode(self, user):
        return await rc.activate_promocode(user)

    @click
    async def cancel_activate_promocode(self, user):
        return await rc.cancel_activate_promocode(user)

    @click
    async def check_promocode(self, user, text):
        try:
            promocode_activation = await api.activate_promocode(user["id"], text)
        except Exception as e:
            logger.info(f"Promocode activation gone bad: {e}")
            return await rc.wrong_promocode(user)

        owner = await api.get_user(user_id=promocode_activation["owner_id"])
        return await rc.promocode_activated(
            user, amount=promocode_activation["amount"], creator_nickname=owner["nickname"]
        )

    @click
    async def create_promocode(self, user, data):
        promocode_type = data.split()[-1]
        if promocode_type not in PROMOCODE_TYPES:
            raise ValueError("Wrong promocode type")
        wallet = await api.get_wallet(user["id"])
        balance = wallet["balance"]

        if balance <= MIN_PROMOCODE_AMOUNT_CRYPTO[SYMBOL]:
            return await rc.not_enoung_funds_promocode(user), None

        return await rc.choose_count(user), promocode_type

    @click
    async def cancel_create_promocode(self, user):
        return await rc.cancel_create_promocode(user)

    @click
    async def handle_count(self, user, text, promocode_type):
        try:
            count = int(text)
            if count <= 0 or count >= 1000:
                raise Exception
        except Exception as e:
            logger.info(f"Cant parse count from {text}: {e}")
            return await rc.wrong_count(user), None
        return await rc.choose_amount(user, promocode_type), count

    def _validate_promocode_amount(self, amount, type_, user_currency):
        min_amount = (
            MIN_PROMOCODE_AMOUNT_CRYPTO[SYMBOL]
            if type_ == PROMOCODE_TYPES[0]
            else MIN_PROMOCODE_AMOUNT_FIAT[user_currency]
        )
        if amount < Decimal(str(min_amount)):
            raise Exception("not enough funds")

    @click
    async def handle_amount_promocode(self, user, text, type_, count):
        try:
            amount = await sky_math.parse_amount(text)
            currency_amount = amount.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            self._validate_promocode_amount(amount, type_, user["currency"])
        except Exception as e:
            return await rc.wrong_amount(user), False

        wallet = await api.get_wallet(user["id"])
        balance = wallet["balance"]
        rate = await api.get_rate(user["currency"])
        if type_ == PROMOCODE_TYPES[1]:
            amount = Decimal(amount / Decimal(str(rate))).quantize(Decimal("0.0000001"), rounding=ROUND_DOWN)
        if balance < amount * count:
            return await rc.not_enoung_funds_promocode(user, cancel=True), False

        try:
            promocode = await api.create_promocode(user["id"], count, amount)
        except BadRequestError as e:
            error_text = e.detail.lower()
            if "promocode limit" == error_text:
                return await rc.promocode_limit(user), False
            if "you don't have enough money" == error_text:
                return await rc.not_enoung_funds_promocode(user, cancel=True), False
            if "you are banned" == error_text:
                return await rc.you_are_baned(user), False
            if "wrong data" == error_text:
                return await rc.wrong_amount(user), False
        except Exception as e:
            logger.error(f"API CALL new-promocode raised error: {e}")
            return await rc.error(user, cancel=True), False

        if type_ == PROMOCODE_TYPES[0]:
            currency_amount = Decimal(amount * Decimal(str(rate))).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

        text, k = await rc.promocode_created(user, promocode["code"], promocode["count"], promocode["amount"], currency_amount)
        await send_message(chat_id=user["telegram_id"], text=text, reply_markup=k)
        return (f"<b>{promocode['code']}</b>", None), True

    @click
    async def active_promocodes(self, user):
        promocodes = await api.get_active_promocodes(user["id"])
        for p in promocodes:
            text, k = await rc.promocode(user, p["id"], p["code"], p["amount"], p["count"], p["activations"])
            await send_message(chat_id=user["telegram_id"], text=text, reply_markup=k)
            await send_message(chat_id=user["telegram_id"], text=f'<b>{p["code"]}</b>')

    @click
    async def delete_promocode(self, user, data):
        p_id = int(data.split()[-1])
        try:
            await api.delete_promocode(user["id"], promocode_id=p_id)
        except Exception as e:
            logger.error(f"API CALL delete promocode raised error: {e}")
            return await rc.error(user)

        return await rc.promocode_deleted(user)

    @click
    async def user(self, user, nickname=None):
        is_exists = await api.is_user_exist_nickname(nickname)
        if not is_exists:
            return await rc.user_does_not_exists(user)
        user_info = await api.get_user_info(nickname)
        is_message_baned = await api.get_is_usermessages_baned(user["id"], user_info["id"])
        is_baned_messages = await api.get_is_usermessages_baned(user_info["id"], user["id"])
        return await rc.user(user, user_info, not is_message_baned, is_baned_messages)

    @click
    async def get_user_by_forward(self, user, telegram_id):
        try:
            target_user = await api.get_user(telegram_id=telegram_id)
        except:
            return await rc.user_does_not_exists(user)
        return await self.user(user=user, nickname=target_user["nickname"])

    @click
    async def write_message(self, user, data):
        user_id = int(data.split()[-1])
        return await rc.write_message(user), user_id

    @click
    async def cancel_write_message(self, user):
        return await rc.cancel_write_message(user)

    @click
    async def send_usermessage(self, user, text, receiver_id):
        try:
            await api.new_usermessage(sender_id=user["id"], receiver_id=receiver_id, message=text)
        except Exception as e:
            if "bad request" in str(e).lower():
                return await rc.user_baned_messages_from_you(user)
        to_user = await api.get_user(user_id=receiver_id)
        return await rc.message_sent(user, to_user=to_user['nickname'])

    @click
    async def send_photo(self, user, photo, receiver_id):
        try:
            content_type = None
            if isinstance(photo, (list, tuple)):
                target = sorted(photo, key=lambda item: item.file_size, reverse=True)[0]
            else:
                content_type = 'application/pdf'
                target = photo
                if target.mime_type != 'application/pdf':
                    raise ValueError('wrong file')
            file = await target.download()
            media = await api.upload_photo(user["id"], open(file.name, "rb"), content_type)
            await api.new_usermessage(sender_id=user["id"], receiver_id=receiver_id, media_id=media["id"])
        except BadRequestError as e:
            error_text = e.detail.lower()
            if error_text == "400 bad request: javascript in pdf":
                return await rc.javascript_in_pdf(user)
        except Exception as e:
            logger.exception(e)
            return await rc.error(user)
        to_user = await api.get_user(user_id=receiver_id)
        return await rc.message_sent(user, to_user=to_user['nickname'])

    @click
    async def open_dispute(self, user, deal_id):
        deal = await api.get_deal(deal_id)
        is_buyer = deal["buyer"]["id"] == user["id"]
        is_seller = deal["seller"]["id"] == user["id"]
        settings = await api.get_settings()
        dispute_time = settings["dispute_time"]
        if deal["state"] != STATES[2] or not (is_seller or is_buyer):
            return await rc.error(user)

        dispute = await api.get_dispute(deal_id)
        was_opened = bool(dispute)

        if was_opened and user["id"] in (dispute["initiator"]["id"], dispute["opponent"].get("id")):
            return await rc.dispute_already_opened(user)

        try:
            dispute = await api.create_dispute(user["id"], deal_id)
        except BadRequestError as e:
            if e.detail.lower() == "you can open a dispute only 5 minutes after the deal":
                return await rc.error_open_dispute_without_waiting(user)

            return await rc.error(user)

        if dispute["initiator"] and dispute["opponent"]:
            return await rc.both_opened_dispute(user, deal["identificator"])
        else:
            return await rc.dispute_opened(user, identificator=deal["identificator"], dispute_time=dispute_time)


    @click
    async def decline_dispute(self, user, deal_id):
        deal = await api.get_deal(deal_id)
        if deal["state"] == STATES[2] and deal["buyer"]["id"] == user["id"]:
            return await rc.confirm_decline_dispute(user, deal_id), deal_id
        else:
            return await rc.error(user), None

    @click
    async def cancel_decline_dispute(self, user):
        return await rc.cancel_decline_dispute(user)

    @click
    async def handle_decline_dispute(self, user, deal_id):
        deal = await api.get_deal(deal_id)
        if deal["state"] == STATES[2] and deal["buyer"]["id"] == user["id"]:
            dispute = await api.get_dispute(deal_id)
            if dispute["initiator"]["id"] == deal["seller"]["id"]:
                await api.cancel_deal(deal["buyer"]["id"], deal_id)
                return await rc.deal_canceled(user, deal)

        return await rc.error(user)

    @click
    @admin_only
    async def admin_cancel_deal(self, user, winner, deal_id):
        deal = await api.get_deal(deal_id)
        if deal["state"] != STATES[2]:
            return await rc.error(user)

        await api.close_deal_admin(deal_id=deal_id, winner=winner)

        return await rc.done(user)

    @click
    async def cancel_change_lot(self, user):
        return await rc.cancel_change_lot(user)

    @click
    async def change_limits(self, user, data):
        lot_id = data.split()[-1]
        return await rc.change_limits(user), lot_id

    @click
    async def change_rate(self, user, data):
        lot_id = data.split()[-1]
        return await rc.change_rate(user), lot_id

    @click
    async def change_conditions(self, user, data):
        lot_id = data.split()[-1]
        return await rc.change_conditions(user), lot_id

    @click
    async def delete_lot_confirmation(self, user, lot_id):
        lot = await api.get_lot(lot_id)
        if lot["user_id"] != user["id"]:
            text, _ = await rc.error(user)
            return text, None
        return await rc.delete_lot_confirmation(user, lot)

    @click
    async def delete_lot(self, user, lot_id):
        lot = await api.get_lot(lot_id)
        if lot["user_id"] != user["id"]:
            text, _ = await rc.error(user)
            return text, None
        await api.delete_lot(lot["identificator"], user["id"])
        return await rc.lot_deleted(user)

    @click
    async def change_lot_status(self, user, data):
        lot_id = data.split()[-1]
        lot = await api.get_lot(lot_id)
        if lot["user_id"] != user["id"]:
            text, _ = await rc.error(user)
            return text, None
        await api.update_lot(
            identificator=lot["identificator"], user_id=user["id"], activity_status=not lot["is_active"]
        )
        return await self.lot(user=user, identificator=lot["identificator"])

    @click
    async def edit_limits(self, user, lot_id, text):
        lot = await api.get_lot(lot_id)
        if lot["user_id"] != user["id"] or lot["is_deleted"]:
            return await rc.error(user)
        try:
            limit_from, limit_to = await sky_math.parse_limits(text)
        except ValueError:
            return await rc.error(user)
        await api.update_lot(
            identificator=lot["identificator"], user_id=user["id"], limit_from=limit_from, limit_to=limit_to
        )
        text, k = await rc.done(user)
        await send_message(chat_id=user["telegram_id"], text=text, reply_markup=k)
        return await self.lot(user=user, identificator=lot["identificator"])

    async def _get_rate_variation(self, currency) -> Decimal:
        settings = await api.get_settings()
        currencies = settings['currencies']
        target_currency = next(filter(lambda x: x['id'] == currency, currencies))
        return Decimal(str(target_currency['rate_variation']))

    @click
    async def edit_rate(self, user, lot_id, text):
        lot = await api.get_lot(lot_id)
        if lot["user_id"] != user["id"] or lot["is_deleted"]:
            return await rc.error(user)
        rates = await api.get_rate(lot["currency"])
        rate_variation = await self._get_rate_variation(lot['currency'])
        print(rate_variation)
        try:
            rate, coefficient = await sky_math.parse_rate(
                text, Decimal(str(rates)), rate_variation
            )
        except Exception as e:
            return await rc.error(user)
        await api.update_lot(
            identificator=lot["identificator"],
            user_id=user["id"],
            rate=float(rate),
            coefficient=float(coefficient) if coefficient else coefficient,
        )
        text, k = await rc.done(user)
        await send_message(chat_id=user["telegram_id"], text=text, reply_markup=k)
        return await self.lot(user=user, identificator=lot["identificator"])

    @click
    async def edit_conditions(self, user, lot_id, text):
        if len(text) > 1024:
            return await rc.error(user)

        lot = await api.get_lot(lot_id)
        if lot["user_id"] != user["id"] or lot["is_deleted"]:
            return await rc.error(user)
        await api.update_lot(identificator=lot["identificator"], user_id=user["id"], details=text)
        text, k = await rc.done(user)
        await send_message(chat_id=user["telegram_id"], text=text, reply_markup=k)
        return await self.lot(user=user, identificator=lot["identificator"])

    @click
    @admin_only
    async def send_to_all(self, user, text):
        text = text[16:]
        all_tg_id = await api.get_all_telegram_ids()
        for telegram_id in all_tg_id:
            await asyncio.sleep(0.5)
            await send_message(chat_id=telegram_id, text=text, save=False)

    @click
    async def get_payment_for_support(self, user, payment_id):
        if user["is_admin"] or user["telegram_id"] in (1790932887, 173724189):
            data = await api.get_payment_info(payment_id)
            return await rc.payment_for_support(data)

    @click
    async def get_payment_v2_for_support(self, user, payment_id):
        if user["is_admin"] or user["telegram_id"] in (1790932887, 173724189):
            data = await api.get_payment_v2_info(payment_id)
            return await rc.payment_v2_for_support(data)

    @click
    async def get_sale_for_support(self, user, sale_id):
        if user["is_admin"] or user["telegram_id"] in (1790932887, 173724189):
            data = await api.get_sale_info(sale_id)
            return await rc.sale_for_support(data)

    @click
    async def get_sale_v2_for_support(self, user, sale_v2_id):
        if user["is_admin"] or user["telegram_id"] in (1790932887, 173724189):
            data = await api.get_sale_v2_info(sale_v2_id)
            return await rc.sale_v2_for_support(data)

    @click
    async def get_cpayment_for_support(self, user, cpayment_id):
        if user["is_admin"] or user["telegram_id"] in (1790932887, 173724189):
            data = await api.get_cpayment_info(cpayment_id)
            return await rc.cpayment_for_support(data)

    @click
    async def get_withdrawal_for_support(self, user, withdrawal_id):
        if user["is_admin"] or user["telegram_id"] in (1790932887, 173724189):
            data = await api.get_withdrawal_info(withdrawal_id)
            return await rc.withdrawal_for_support(data)

    @click
    async def change_verification_status(self, user, user_id):
        target_user = await api.get_user(user_id=user_id)
        await api.update_user(user_id=user_id, is_verify=not target_user["is_verify"])
        return await self.user(user=user, nickname=target_user["nickname"])

    @click
    async def change_superverification_status(self, user, user_id):
        target_user = await api.get_user(user_id=user_id)
        await api.update_user(user_id=user_id, super_verify_only=not target_user["super_verify_only"])
        return await self.user(user=user, nickname=target_user["nickname"])

    @click
    async def change_skypay_status(self, user, user_id):
        target_user = await api.get_user(user_id=user_id)
        await api.update_user(user_id=user_id, sky_pay=not target_user["sky_pay"])
        return await self.user(user=user, nickname=target_user["nickname"])

    @click
    async def change_skypayv2_status(self, user, user_id):
        target_user = await api.get_user(user_id=user_id)
        await api.update_user(user_id=user_id, allow_super_buy=not target_user["allow_super_buy"])
        return await self.user(user=user, nickname=target_user["nickname"])

    @click
    async def change_usermessagesban_status(self, user, user_id):
        current_status = await api.get_is_usermessages_baned(user_id, user["id"])
        await api.set_usermessages_ban_status(user["id"], user_id, not current_status)
        target_user = await api.get_user(user_id=user_id)
        return await self.user(user=user, nickname=target_user["nickname"])

    @click
    async def change_allowsell_status(self, user, user_id):
        target_user = await api.get_user(user_id=user_id)
        await api.update_user(user_id=user_id, allow_sell=not target_user["allow_sell"])
        return await self.user(user=user, nickname=target_user["nickname"])

    @click
    async def change_allowsalev2_status(self, user, user_id):
        target_user = await api.get_user(user_id=user_id)
        await api.update_user(user_id=user_id, allow_sale_v2=not target_user["allow_sale_v2"])
        return await self.user(user=user, nickname=target_user["nickname"])


    @click
    async def change_ban_status(self, user, user_id):
        target_user = await api.get_user(user_id=user_id)
        await api.update_user(user_id=user_id, is_baned=not target_user["is_baned"])
        return await self.user(user=user, nickname=target_user["nickname"])

    @click
    async def change_shadowban_status(self, user, user_id):
        target_user = await api.get_user(user_id=user_id)
        await api.update_user(user_id=user_id, shadow_ban=not target_user["shadow_ban"])
        return await self.user(user=user, nickname=target_user["nickname"])

    @click
    async def change_applyshadowban_status(self, user, user_id):
        target_user = await api.get_user(user_id=user_id)
        await api.update_user(user_id=user_id, apply_shadow_ban=not target_user["apply_shadow_ban"])
        return await self.user(user=user, nickname=target_user["nickname"])

    @click
    @admin_only
    async def change_balance(self, user, nickname, amount):
        target_user = await api.get_user_info(nickname=nickname)
        await api.change_balance(target_user["id"], user["id"], amount)

        if amount > 0:
            text, _ = await rc.new_income_from_admin(target_user, amount)
            await send_message(chat_id=target_user["telegram_id"], text=text)

        wallet = await api.get_wallet(target_user["id"])
        return f'✅ Новый баланс пользователя /u{nickname} {wallet["balance"]} {SYMBOL.upper()}', None

    @click
    @admin_only
    async def change_balance_m(self, user, nickname, amount):
        target_user = await api.get_user_info(nickname=nickname)
        await api.change_balance(target_user["id"], user["id"], amount, with_operation=True)

        if amount > 0:
            text, _ = await rc.new_income_from_admin(target_user, amount)
            await send_message(chat_id=target_user["telegram_id"], text=text)

        wallet = await api.get_wallet(target_user["id"])
        return f'✅ Новый баланс пользователя /u{nickname} {wallet["balance"]} {SYMBOL.upper()}', None

    @click
    @admin_only
    async def withdraw_from_payments_node(self, user, address, amount):
        resp = await api.withdraw_from_payments_node(user["id"], address, amount)
        return resp["link"], None

    @click
    @admin_only
    async def menu(self, user):
        return await rc.admin_menu(user)

    @click
    @admin_only
    async def get_tx(self, user, tx_hash):
        data = await api.get_node_transaction(tx_hash)
        return await rc.get_node_transaction(data)

    @click
    async def get_each_month(self, user, prefix):
        result = []

        today = date.today()
        current = date(2018, 1, 1)

        while current <= today:
            result.append(current)
            current += relativedelta(months=1)

        text = ""
        for item in result:
            text += f"/{prefix}_{item.year}_{item.month}\n"
        return text

    async def _get_report_file(self, data, fields, filename):
        output: io.StringIO = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)
        bytefile = io.BytesIO(output.getvalue().encode())
        bytefile.name = f"{filename}.csv"
        bytefile.seek(0)
        return bytefile

    async def _parse_from_to_dates(self, year, month, day=None):
        if day is None:
            _, to_day = calendar.monthrange(year, month)
            from_date = int(datetime(year, month, 1).timestamp())
            to_date = int(datetime(year, month, to_day, 23, 59, 59).timestamp())
        else:
            from_date = int(datetime(year, month, day).timestamp())
            to_date = int(datetime(year, month, day, 23, 59, 59).timestamp())
        return from_date, to_date

    @click
    @admin_only
    async def report_deals(self, user, year, month):
        from_date, to_date = await self._parse_from_to_dates(year, month)
        data = await api.get_all_reports("deals", from_date, to_date)
        fields = ["id", "lot", "amount", "crypto", "created", "end", "status", "buyer", "seller", "income"]
        return await self._get_report_file(data, fields, "deals")

    @click
    @admin_only
    async def report_promocodes(self, user, year, month):
        from_date, to_date = await self._parse_from_to_dates(year, month)
        data = await api.get_all_reports("promocodes", from_date, to_date)
        fields = ["code", "amount", "count", "activations", "deleted", "created", "user"]
        return await self._get_report_file(data, fields, "promocodes")

    @click
    @admin_only
    async def report_lots(self, user, year, month):
        from_date, to_date = await self._parse_from_to_dates(year, month)
        data = await api.get_all_reports("lots", from_date, to_date)
        fields = ["id", "created_at", "broker", "rate", "user", "created", "active", "coefficient"]
        return await self._get_report_file(data, fields, "lots")

    @click
    @admin_only
    async def report_exchange(self, user, year, month):
        from_date, to_date = await self._parse_from_to_dates(year, month)
        data = await api.get_all_reports("exchange", from_date, to_date)
        fields = [
            "id",
            "created_at",
            "nickname",
            "from_symbol",
            "to_symbol",
            "rate",
            "amount_sent",
            "amount_received",
            "commission",
        ]
        return await self._get_report_file(data, fields, "exchange")

    @click
    @admin_only
    async def report_users(self, user, year, month):
        from_date, to_date = await self._parse_from_to_dates(year, month)
        data = await api.get_all_reports("users", from_date, to_date)
        fields = ["nickname", "lang", "telegram_id", "created", "deleted", "baned", "verify", "rating"]
        return await self._get_report_file(data, fields, "users")

    @click
    @admin_only
    async def report_transactions(self, user, year, month):
        from_date, to_date = await self._parse_from_to_dates(year, month)
        data = await api.get_all_reports("transactions", from_date, to_date)
        fields = [
            "type",
            "to_address",
            "commission",
            "tx_hash",
            "created_at",
            "processed_at",
            "amount",
            "is_confirmed",
            "is_deleted",
        ]
        return await self._get_report_file(data, fields, "transactions")

    @click
    @admin_only
    async def report_financial(self, user, year, month):
        from_date, to_date = await self._parse_from_to_dates(year, month)
        data = await api.get_all_reports("income", from_date, to_date)
        fields = ["date", "transactions_income", "deals_income", "merchants_income", "total_income"]
        return await self._get_report_file(data, fields, "income")

    @click
    @admin_only
    async def report_merchants(self, user, year, month):
        from_date, to_date = await self._parse_from_to_dates(year, month)
        data = await api.get_all_reports("merchants", from_date, to_date)
        fields = ["date", "merchants_income"]
        return await self._get_report_file(data, fields, "merchants")

    @click
    async def report_control(self, user, year, month, day):
        if user["is_admin"] or user["telegram_id"] in (1790932887, 173724189):
            from_date, to_date = await self._parse_from_to_dates(year, month, day)
            data = await api.get_all_reports("control", from_date, to_date)
            fields = [
                "id",
                "buyer",
                "buyer_email",
                "seller",
                "state",
                "requisite",
                "created_at",
                "end_time",
                "amount_currency",
                "payment_id",
                "sell_id",
                "ip",
            ]
            return await self._get_report_file(data, fields, "control")

    @click
    @admin_only
    async def campaigns_report(self, user):
        data = await api.get_all_reports("campaigns")
        fields = ["id", "name", "registrations", "deals", "deals_revenue"]
        return await self._get_report_file(data, fields, "campaigns")

    def _get_separated_reports(self, data, filename):
        separated_data = defaultdict(list)
        for item in data:
            date = parse(item["created"]).date()
            c = f"{date.month}.{date.year}"
            separated_data[c].append(item)
        for date, data in separated_data.items():
            yield self._get_abstract_report(data, f"{date}-{filename}")

    @click
    @admin_only
    async def user_report(self, user, user_id, method, separated):
        data = await api.get_reports(user_id)
        filename = f"{method}.csv"
        if separated:
            return self._get_separated_reports(data[method], filename)
        else:
            return [self._get_abstract_report(data[method], filename)]

    @click
    @admin_only
    async def transit(self, user, user_id):
        transit = await api.get_transit(user_id)
        text = (
            f'Адрес {transit["address"]}\nПриватный ключ {transit["pk"]}\nБаланс {transit["balance"]} {SYMBOL.upper()}'
        )
        return text, None

    @click
    @admin_only
    async def frozen(self, user):
        frozen_all = await api.get_frozen()
        total_frozen = sum([item["frozen"] for item in frozen_all])
        text = f"Всего в заморозке {total_frozen} {SYMBOL.upper()}:\n"
        for item in frozen_all:
            text += f'/u{item["user"]} {item["frozen"]} {SYMBOL.upper()}\n'
        return text, None

    @click
    @admin_only
    async def stop_withdraw(self, user):
        resp = await api.stop_withdraw()
        new_status = resp["status"]
        return f'Вывод {"включен" if new_status else "отключен"}'

    @click
    @admin_only
    async def ban_all_messages(self, user, tg_id):
        redis_general.set(f"is_baned_{tg_id}", "1")
        return f"Юзер забанен"

    @click
    @admin_only
    async def unban_all_messages(self, user, tg_id):
        redis_general.delete(f"is_baned_{tg_id}")
        return f"Юзер разбанен"

    @click
    @admin_only
    async def stop_fast_deal(self, user):
        resp = await api.stop_fast_deal()
        new_status = resp["status"]
        return f'Быстрая сделка {"включена" if new_status else "отключена"}'

    async def _get_profit_text(self):
        resp = await api.profit()
        resp["symbol"] = SYMBOL.upper()
        if SYMBOL == "btc":
            text = (
                "<b>Пользователей:</b> {users}\n"
                "<b>Подтв. баланс:</b> {confirmed} {symbol}\n"
                "<b>Неподтв. баланс:</b> {unconfirmed} {symbol}\n"
                "<b>Баланс запасной:</b> {secondary} {symbol}\n"
                "<b>Баланс платежный:</b> {cpayments} {symbol}\n"
                "<b>Денег в базе:</b> {db_funds} {symbol}\n"
                "<b>Заводы:</b> {deposits} {symbol}\n"
                "<b>Выводы:</b> {withdraws} {symbol}\n"
                "<b>Профит:</b> ~ {profit} {symbol}"
            ).format(
                **{
                    "users": resp["users"],
                    "confirmed": resp["wallet_funds"]["confirmed"],
                    "unconfirmed": resp["wallet_funds"]["unconfirmed"],
                    "secondary": resp["wallet_funds"]["secondary"],
                    "cpayments": resp["wallet_funds"]["cpayments"],
                    "db_funds": resp["db_funds"],
                    "symbol": resp["symbol"],
                    "deposits": resp["wallet_funds"]["deposits"],
                    "withdraws": resp["wallet_funds"]["withdraws"],
                    "profit": resp["profit"],
                    "binance": resp["binance"],
                }
            )
        else:
            text = (
                "<b>Пользователей:</b> {users}\n"
                "<b>Денег на кошельке:</b> {wallet_funds} {symbol}\n"
                "<b>Денег в базе:</b> {db_funds} {symbol}\n"
                "<b>Профит:</b> {profit} {symbol}"
            ).format(**resp)

        if SYMBOL == "usdt":
            text += "\n\n<b>TRX баланс:</b> {trx_balance}".format(**resp)

        text += "\n\n<b>Дисбаланс:</b> {imbalance} {symbol}".format(**resp)

        return text

    @click
    @admin_only
    async def profit(self, user):
        text = await self._get_profit_text()
        return text, None

    async def _campaign_text(self, data):
        base_text = "<b>Название:</b> {name}\n" "<b>Регистраций:</b> {registrations}\n" "<b>Ссылки:</b>\n"
        for link in data["links"]:
            base_text += f"{link}\n"
        return base_text.format(**data)

    @click
    @admin_only
    async def reset_imbalance(self, user):
        await api.reset_imbalance(user["id"])
        text, _ = await rc.done(user)
        return text, None

    @click
    @admin_only
    async def new_campaign(self, user, name):
        campaign = await api.create_campaign(user["id"], name)
        return await self._campaign_text(campaign)

    @click
    @admin_only
    async def finreport(self, user):
        resp = await api.finreport()
        resp["symbol"] = SYMBOL.upper()
        rate = await api.get_rate("usd")
        intervals = ["day", "week", "month", "year"]
        for interval in intervals:
            total = resp[f"transactions_{interval}"] + resp[f"deals_{interval}"] + resp[f"merchants_{interval}"]
            resp[f"total_{interval}"] = round(total, 5)
            resp[f"total_{interval}_est"] = round(rate * total, 2)
        text = (
            "Заработок на транзакциях:\n"
            "Год: {transactions_year} {symbol}\n"
            "Месяц: {transactions_month} {symbol}\n"
            "Неделя: {transactions_week} {symbol}\n"
            "День: {transactions_day} {symbol}\n\n"
            "Заработок на сделках:\n"
            "Год: {deals_year} {symbol}\n"
            "Месяц: {deals_month} {symbol}\n"
            "Неделя: {deals_week} {symbol}\n"
            "День: {deals_day} {symbol}\n\n"
            "Заработок на мерчантах:\n"
            "Год: {merchants_year} {symbol}\n"
            "Месяц: {merchants_month} {symbol}\n"
            "Неделя: {merchants_week} {symbol}\n"
            "День: {merchants_day} {symbol}\n\n"
            "Всего заработано:\n"
            "Год: {total_year} {symbol} ~ {total_year_est}$\n"
            "Месяц: {total_month} {symbol} ~ {total_month_est}$\n"
            "Неделя: {total_week} {symbol} ~ {total_week_est}$\n"
            "День: {total_day} {symbol} ~ {total_day_est}$"
        )
        return text.format(**resp)

    @click
    @admin_only
    async def change_frozen(self, user, nickname, amount):
        target_user = await api.get_user_info(nickname=nickname)
        await api.change_frozen(target_user["id"], user["id"], amount)
        wallet = await api.get_wallet(target_user["id"])
        text = f'Новое количество замороженных средств пользователя /u{nickname} {wallet["frozen"]}'
        return text, None

    @click
    @admin_only
    async def set_frozen(self, user, nickname, amount):
        target_user = await api.get_user_info(nickname=nickname)
        await api.set_frozen(target_user["id"], user["id"], amount)
        wallet = await api.get_wallet(target_user["id"])
        text = f'Новое количество замороженных средств пользователя /u{nickname} {wallet["frozen"]}'
        return text

    @click
    @admin_only
    async def set_balance(self, user, nickname, amount):
        target_user = await api.get_user_info(nickname=nickname)
        await api.set_balance(target_user["id"], user["id"], amount)
        wallet = await api.get_wallet(target_user["id"])
        text = f'Новый баланс пользователя /u{nickname} {wallet["balance"]}'
        return text

    @click
    async def unknown_command(self, user):
        settings = await api.get_settings()
        return await rc.unknown_command(user, withdraw_commission=settings["commission"])

    async def some_error(self):
        return await rc.unknown_error()

    async def get_all_telegram_ids(self):
        while True:
            try:
                return await api.get_all_telegram_ids()
            except Exception:
                await asyncio.sleep(2)


dh = DataHandler()
