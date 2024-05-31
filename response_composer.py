import datetime
from decimal import Decimal

from dateutil.parser import parse

from keyboards import kb
from settings import (BUYER_COMMISSION, BUYER_REFERRAL_COMMISSION_FROM_COMMISSION, SELLER_COMMISSION, SUPPORT, SYMBOL,
                      SYMBOL_NAME)
from translations import translate
from utils.helpers import get_correct_value, truncate, get_commission_exponent

verify_sm = {True: "✅", False: "❌"}


class ResponseComposer:
    async def _get(self, lang, *, var_name, **kwargs):
        assert isinstance(lang, str)
        for k, v in kwargs.items():
            if isinstance(v, (Decimal, float)):
                kwargs[k] = "{}".format(float(v))
        return translate(f"misc.{var_name}", locale=lang, symbol=SYMBOL.upper(), **kwargs).expandtabs(2)

    async def _big_number_str(self, value):
        return "{:,}".format(value)

    async def confirm_policy(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="confirm_policy")
        k = await kb.confirm_policy(lang)
        return text, k

    async def start(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="start", channel_link="t.me/sky_banker", chat_link="t.me/skychatru")
        k = await kb.main_menu(lang)
        return text, k

    async def start_second(self, user, username):
        lang = user["lang"]
        text = await self._get(lang, var_name="start_second", tg_username=username, coin_name=SYMBOL_NAME.upper())
        k = None
        return text, k

    async def wallet(
            self,
            user,
            *,
            balance,
            frozen,
            deposited,
            withdrawn,
            about,
            deal_cnt,
            revenue,
            days_registered,
            likes,
            dislikes,
            rating,
            rating_sm,
            is_bound,
    ):
        lang = user["lang"]
        frozen_str = (
            await self._get(
                lang,
                var_name="frozen",
                frozen=frozen,
            )
            if frozen > 0
            else ""
        )
        text = await self._get(
            lang,
            var_name="wallet",
            balance="{0:.8f}".format(balance),
            frozen_str=frozen_str,
            deposited=deposited,
            withdrawn=withdrawn,
            likes=likes,
            dislikes=dislikes,
            nick=user["nickname"],
            verify_sm=verify_sm[user["is_verify"]],
            sky_pay_sm=verify_sm[user["sky_pay"]],
            about="{0:.2f}".format(about),
            deals_done=deal_cnt,
            currency=user["currency"].upper(),
            revenue=revenue,
            days_registered=days_registered,
            rating_sm=rating_sm,
            rating_points=rating,
            bind_sm=verify_sm[is_bound],
        )
        k = await kb.wallet(lang)
        return text, k

    async def new_income(self, user, val):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="new_income",
            amount=val,
        )
        k = None
        return text, k

    async def exchange(self, user, rate, active_deals_count, lots_cnt):
        lang = user["lang"]
        text = await self._get(lang, var_name="exchange", rate=str(rate), currency=user["currency"].upper(), cnt=1)
        k = await kb.exchange(lang, active_deals_count, lots_cnt)
        return text, k

    async def active_deals(self, user, active_deals):
        lang = user["lang"]
        text = None
        k = await kb.active_deals(lang, active_deals)
        return text, k

    async def deposit(self, user, min_deposit):
        lang = user["lang"]
        text = await self._get(lang, var_name="deposit")
        if SYMBOL == "usdt":
            text += "\n\n"
            text += await self._get(lang, var_name="trc_only")
        if min_deposit:
            text += "\n\n"
            text += await self._get(lang, var_name="min_deposit", min_deposit=min_deposit)

        k = None

        return text, k

    async def withdraw(self, symbol, user, last_address):
        lang = user["lang"]
        add_str = ''
        if symbol == 'usdt':
            add_str = ' (TRC-20)'
        text = await self._get(lang, var_name="withdraw", support=SUPPORT, add_str=add_str)
        k = await kb.withdraw(lang, last_address)
        return text, k

    async def not_enoungh_funds(self, user, min_to_withdraw, balance):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="not_enoung_funds_withdraw",
            min_to_withdraw=min_to_withdraw,
            balance=balance,
        )
        k = await kb.buy_sell_k(lang)
        return text, k

    async def confirmation_start_tx(self, user, address, amount):
        lang = user["lang"]
        text = await self._get(lang, var_name="confirmation_start_tx", amount=amount, address=address)
        k = await kb.get_yes_no_kb(lang)
        return text, k

    async def not_enough_funds_tx(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="not_enoung_funds_tx")
        k = await kb.buy_sell_k(lang)
        return text, k

    async def not_enoung_funds_promocode(self, user, cancel=False):
        lang = user["lang"]
        text = await self._get(lang, var_name="not_enoung_funds_promocode")
        if cancel:
            k = await kb.get_cancel(lang)
        else:
            k = await kb.main_menu(lang)
        return text, k

    async def promocode_limit(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="promocode_limit")
        k = await kb.main_menu(lang)
        return text, k

    async def cancel_withdraw(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="cancel_withdraw")
        k = await kb.main_menu(lang)
        return text, k

    async def wrong_address(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="wrong_address")
        k = await kb.get_cancel(lang)
        return text, k

    async def pre_deposit_rub_text(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="pre_deposit_rub_text")
        k = None
        return text, k

    async def choose_amount_withdraw(self, user, balance, chosen_address, min_to_withdraw, commission, dynamic_commissions):
        lang = user["lang"]
        var_name = "choose_amount_withdraw"
        max_withdraw = 10000
        if SYMBOL == "eth":
            var_name += "_short"
            max_withdraw = 5
            commission_string = f"{commission} ETH"
        elif SYMBOL == "btc":
            max_withdraw = 1
            commission_string = await self._get(
                lang,
                var_name="commission_string_btc",
                dynamic_commission_1="{0:.{prec}f}".format(
                    dynamic_commissions[3][1], prec=get_commission_exponent(dynamic_commissions[3][1])
                ),
                dynamic_commission_2="{0:.{prec}f}".format(
                    dynamic_commissions[2][1], prec=get_commission_exponent(dynamic_commissions[2][1])
                ),
                dynamic_commission_3="{0:.{prec}f}".format(
                    dynamic_commissions[1][1], prec=get_commission_exponent(dynamic_commissions[1][1])
                ),
                dynamic_commission_4="{0:.{prec}f}".format(
                    dynamic_commissions[0][1], prec=get_commission_exponent(dynamic_commissions[0][1])
                ),
            )

        elif SYMBOL == "usdt":
            commission_string = await self._get(
                lang,
                var_name="commission_string_usdt",
                dynamic_commission_1=dynamic_commissions[1][1],
                dynamic_commission_2=dynamic_commissions[0][1]
            )
        else:
            commission_string = f"{commission} {SYMBOL.upper()}"

        to_withdraw = min(truncate(balance - commission, 6), max_withdraw)

        text = await self._get(
            lang,
            var_name=var_name,
            chosen_address=chosen_address,
            min_sum=min_to_withdraw,
            available=balance,
            commission=commission_string,
            to_withdraw=to_withdraw,
        )
        k = await kb.get_cancel(lang)
        return text, k

    async def withdrawal_confirmation(self, user, amount, address):
        lang = user["lang"]
        var_name = "withdrawal_confirmation"
        text = await self._get(lang, var_name=var_name, amount=amount, address=address)
        k = await kb.get_yes_no_kb(lang)
        return text, k

    async def transaction_in_queue(self, user):
        lang = user["lang"]
        var_name = "transaction_in_queue"
        if SYMBOL == "btc":
            var_name += "_long"
        text = await self._get(lang, var_name=var_name)
        k = await kb.main_menu(lang)
        return text, k

    async def transaction_processed(self, user, link):
        lang = user["lang"]
        text = await self._get(lang, var_name="transaction_processed", link=link)
        k = None
        return text, k

    async def handle_lots(self, user, lots, is_trading_active, rates, page, pages):
        lang = user["lang"]
        text = await self._get(
            lang, var_name="exchange", rate=rates[user["currency"]], currency=user["currency"].upper(), cnt=1
        )
        k = await kb.handle_lots(lang, is_trading_active, lots, rates, page, pages)
        return text, k

    async def cancel_create_lot(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="cancel_create_lot")
        k = await kb.main_menu(lang)
        return text, k

    async def cancel_create_deal(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="cancel_create_deal")
        k = await kb.main_menu(lang)
        return text, k

    async def cancel_enter_req(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="cancel_enter_req")
        k = await kb.main_menu(lang)
        return text, k

    async def choose_type(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="choose_new_lot_type")
        k = await kb.create_lot_choose_type(lang)
        return text, k

    async def wrong_lot_type(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="wrong_lot_type")
        k = await kb.create_lot_choose_type(lang)
        return text, k

    async def choose_broker(self, user, brokers):
        lang = user["lang"]
        text = await self._get(lang, var_name="choose_broker", support=SUPPORT)
        k = await kb.create_lot_choose_broker(lang, brokers)
        return text, k

    async def wrong_broker(self, user, brokers):
        lang = user["lang"]
        text = await self._get(lang, var_name="wrong_broker")
        k = await kb.create_lot_choose_broker(lang, brokers)
        return text, k

    async def choose_rate(self, user, rate):
        lang = user["lang"]
        text = await self._get(lang, var_name="choose_rate", rate=str(rate), cnt=1, currency=user["currency"].upper())
        k = await kb.get_cancel(lang)
        return text, k

    async def action_canceled(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="action_canceled")
        k = await kb.main_menu(lang)
        return text, k

    async def price_now(self, user, now_price):
        lang = user["lang"]
        text = await self._get(
            lang, var_name="price_now", value=get_correct_value(now_price), currency=user["currency"].upper()
        )
        k = None
        return text, k

    async def wrong_rate(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="wrong_rate")
        k = await kb.get_cancel(lang)
        return text, k

    async def choose_limits(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="choose_limits", currency=user["currency"].upper())
        k = await kb.get_cancel(lang)
        return text, k

    async def wrong_limits(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="wrong_limits")
        k = await kb.get_cancel(lang)
        return text, k

    async def lot_created(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="lot_created")
        k = await kb.main_menu(lang)
        return text, k

    async def new_lot(self, user, lot):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="new_lot",
            cnt=1,
            number=lot["identificator"],
            rate=str(lot["rate"]),
            limit_from=lot["limit_from"],
            limit_to=lot["limit_to"],
            currency=lot["currency"].upper(),
            broker=lot["broker"],
        )
        k = await kb.main_menu(lang)
        return text, k

    async def market(self, user, lots, page, pages, rate, t):
        lang = user["lang"]
        text = await self._get(lang, var_name=f"exchange_{t}", rate=str(rate), currency=user["currency"].upper(), cnt=1)
        k = await kb.market(lang, lots, page, pages, user["currency"].upper(), t)
        return text, k

    async def menu_lots_buy_from_broker(self, user, lots, page, pages, broker):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="menu_lots_buy_from_broker",
            coin_name=SYMBOL.upper(),
            lots_count=len(lots),
            broker=broker["name"],
        )
        k = await kb.menu_lots_buy_from_broker(lang, lots, page, pages, user, broker["id"])
        return text, k

    async def menu_lots_sell_from_broker(self, user, lots, page, pages, broker):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="menu_lots_sell_from_broker",
            coin_name=SYMBOL.upper(),
            lots_count=len(lots),
            broker=broker["name"],
        )
        k = await kb.menu_lots_sell_from_broker(lang, lots, page, pages, user, broker["id"])
        return text, k

    async def no_such_lot(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="no_such_lot")
        k = None
        return text, k

    async def session_closed(self):
        lang = "ru"
        text = await self._get(lang, var_name="session_closed_deal")
        k = await kb.main_menu(lang)
        return text, k

    async def lot(self, user, lot, lot_user_info, is_enough_money, are_users_active, limit_to, allow_deal):
        lang = user["lang"]
        t = await self._get(lang, var_name=f'reverse_{lot["type"]}')
        conditions_str = (
            await self._get(lang, var_name="lot_conditions", conditions=lot["details"]) if lot["details"] else ""
        )
        text = await self._get(
            lang,
            var_name="lot",
            likes=lot_user_info["likes"],
            dislikes=lot_user_info["dislikes"],
            broker=lot["broker"],
            nick=lot_user_info["nickname"],
            verify_sm=verify_sm[lot_user_info["is_verify"]],
            deals_done=lot_user_info["deals"],
            currency=lot["currency"].upper(),
            revenue=lot_user_info["revenue"],
            days_registered=lot_user_info["days_registered"],
            limit_from=lot["limit_from"],
            limit_to=limit_to,
            type=t,
            rate=str(lot["rate"]),
            cnt=1,
            type_lowercase=t.lower(),
            rating_points=lot_user_info["rating"],
            rating_sm=lot_user_info["rating_logo"],
            conditions_str=conditions_str,
        )
        k = await kb.lot(lang, is_enough_money, are_users_active, lot["identificator"], allow_deal)
        return text, k

    async def self_lot(self, user, lot):
        lang = user["lang"]
        conditions_str = (
            await self._get(lang, var_name="lot_conditions", conditions=lot["details"]) if lot["details"] else ""
        )
        text = await self._get(
            lang,
            var_name="self_lot",
            broker=lot["broker"],
            rate=str(lot["rate"]),
            cnt=1,
            currency=lot["currency"].upper(),
            limit_from=lot["limit_from"],
            limit_to=lot["limit_to"],
            identificator=lot["identificator"],
            conditions_str=conditions_str,
        )
        k = await kb.self_lot(lang, lot)
        return text, k

    async def new_income_from_admin(self, user, value):
        lang = user["lang"]
        text = await self._get(lang, var_name="new_income_from_admin", value=value)
        k = None
        return text, k

    async def error(self, user, cancel=False):
        lang = user["lang"]
        text = await self._get(lang, var_name="error")
        if cancel:
            k = await kb.get_cancel(lang)
        else:
            k = await kb.main_menu(lang)
        return text, k

    async def rate_changed(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="rate_changed")
        k = await kb.main_menu(lang)
        return text, k

    async def too_much_deals(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="too_much_deals")
        k = await kb.main_menu(lang)
        return text, k

    async def enter_sum_deal(self, user, lot):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name=f'enter_sum_lot_type_{lot["type"]}',
            limit_from=lot["limit_from"],
            limit_to=lot["limit_to"],
            currency=lot["currency"].upper(),
        )
        k = await kb.get_cancel(lang)
        return text, k

    async def wrong_sum(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="wrong_sum")
        k = await kb.get_cancel(lang)
        return text, k

    async def agreement_deal(self, user, lot, value_units, value_currency):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name=f'agreement_lot_type_{lot["type"]}',
            value_units=value_units,
            cnt=1,
            value_currency=value_currency,
            currency=lot["currency"].upper(),
            rate=str(lot["rate"]),
        )
        k = await kb.get_yes_no_kb(lang)
        return text, k

    async def enter_req_deal(self, user, lot, last_requisites):
        lang = user["lang"]
        text = await self._get(lang, var_name="enter_req_deal", broker=lot["broker"])
        k = await kb.get_req(lang, last_requisites)
        return text, k

    async def confirm_requisite_deal(self, user, requisite):
        lang = user["lang"]
        text = await self._get(lang, var_name="confirm_requisite_deal", requisite=requisite)
        k = await kb.get_yes_no_kb(lang)
        return text, k

    async def confirm_sent_fiat(self, user, deal, long_limit, required_mask=False):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="confirm_sent_fiat",
            broker=deal["lot"]["broker"],
            value_currency=deal["amount_currency"],
            currency=deal["lot"]["currency"].upper(),
            long_limit=long_limit,
            req=deal["requisite"],
        )
        k = await kb.confirm_sent_fiat(lang, deal["identificator"], required_mask)
        return text, k

    async def opponent_confirmed_deal(self, user, deal, long_limit):
        lang = user["lang"]
        opponent = deal["seller"] if user["id"] == deal["buyer"]["id"] else deal["buyer"]
        text = await self._get(
            lang,
            var_name=f'opponent_confirmed_deal_lot_type_{deal["lot"]["type"]}',
            broker=deal["lot"]["broker"],
            nickname=opponent["nickname"],
            long_limit=long_limit,
            value_currency=deal["amount_currency"],
            currency=deal["lot"]["currency"].upper(),
        )
        k = await kb.main_menu(lang)
        return text, k

    async def are_you_sure_sent_fiat(self, user, deal):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="are_you_sure_sent_fiat",
            broker=deal["lot"]["broker"],
            nickname=deal["seller"]["nickname"],
            value_currency=deal["amount_currency"],
            currency=deal["lot"]["currency"].upper(),
        )
        k = await kb.get_yes_no_kb(lang)
        return text, k

    async def back_to_main_menu(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="back_to_main_menu")
        k = await kb.main_menu(lang)
        return text, k

    async def please_check_fiat(
        self, user, deal, mask, var_name: str = "please_check_fiat", is_show_dispute_button: bool = True
    ):
        lang = user["lang"]
        mask_text = ""
        if mask:
            mask_text = f"\n\n⚠️ <b>Реквизиты отправителя:</b> {mask}"
        text = await self._get(
            lang,
            var_name=var_name,
            value_currency=deal["amount_currency"],
            currency=deal["lot"]["currency"].upper(),
            broker=deal["lot"]["broker"],
            deal_identificator=deal["identificator"],
            buyer_nickname=deal["buyer"]["nickname"],
            mask_text=mask_text,
        )

        k = await kb.check_fiat(lang, deal["identificator"], is_show_dispute_button)
        return text, k

    async def notify_dispute_is_ready(self, user, deal):
        lang = user["lang"]
        text = await self._get(lang, var_name="dispute_ready", deal_identificator=deal["identificator"])
        k = await kb.open_dispute(lang, deal["identificator"])
        return text, k

    async def error_open_dispute_without_waiting(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="error_open_dispute_without_waiting")
        k = await kb.main_menu(lang)
        return text, k

    async def opponent_notified(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="opponent_notified", support=SUPPORT)
        k = await kb.main_menu(lang)
        return text, k

    async def deal_confirmation(self, user, deal):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="deal_confirmation",
            value_currency=deal["amount_currency"],
            buyer_nickname=deal["buyer"]["nickname"],
            value_units=deal["amount"],
            currency=deal["lot"]["currency"].upper(),
            support=SUPPORT,
        )
        k = await kb.get_yes_no_kb(lang)
        return text, k

    async def deal_confirmation_enter_req(self, user):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="deal_confirmation_enter_req",
        )
        k = await kb.get_cancel(lang)
        return text, k

    async def you_sent_crypto(self, user, deal):
        lang = user["lang"]
        received = deal["amount"]
        text = await self._get(
            lang, var_name="you_sent_crypto", buyer_nickname=deal["buyer"]["nickname"], value_units=received
        )
        k = await kb.like_dislike_k(lang, deal["buyer"]["id"], deal["identificator"])
        return text, k

    async def you_received_crypto(self, user, deal):
        lang = user["lang"]
        # received = deal['amount'] - deal['buyer_commission']
        text = await self._get(
            lang, var_name="you_received_crypto", seller_nickname=deal["seller"]["nickname"], value_units=deal["amount"]
        )
        k = await kb.like_dislike_k(lang, deal["seller"]["id"], deal["identificator"])
        return text, k

    async def deal(self, user, deal, is_admin, required_mask, mask):
        lang = user["lang"]
        creation_date = (parse(deal["created"]) + datetime.timedelta(hours=3)).strftime("%c")
        t = ""
        if deal["end_time"]:
            end_time = (parse(deal["end_time"]) + datetime.timedelta(hours=3)).strftime("%c")
            t = await self._get(lang, var_name=f'deal_{deal["state"]}_at', d=end_time)

        text = ''
        if deal['payment_v2_id']:
            text += '‼️<b>Автоматическая сделка payments v2</b>\n\n'
        deal_status = await self._get(lang, var_name=f'deal_{deal["state"]}')
        text += await self._get(
            lang,
            var_name="deal",
            creation_date=creation_date,
            end_time_str=t,
            identificator=deal["identificator"],
            value_currency=deal["amount_currency"],
            value_units=deal["amount"],
            lot=deal["lot"]["identificator"],
            deal_status=deal_status,
            currency=deal["lot"]["currency"].upper(),
            requisite=deal["requisite"],
            buyer=deal["buyer"]["nickname"],
            seller=deal["seller"]["nickname"],
        )
        k = await kb.deal(user, deal, is_admin, required_mask, mask)
        return text, k

    async def deal_run(self, user, deal):
        lang = user["lang"]
        text = await self._get(lang, var_name="deal_run", identificator=deal["identificator"])
        k = await kb.main_menu(lang)
        return text, k

    async def propose_deal(self, user, lot, deal, opponent, limit_for_deal):
        lang = user["lang"]
        commission = "{0:.8f}".format(float(deal[f'{lot["type"]}er_commission']))
        text = await self._get(
            lang,
            var_name=f'propose_deal_lot_type_{lot["type"]}',
            opponent=opponent,
            value_currency=deal["amount_currency"],
            currency=lot["currency"].upper(),
            broker=lot["broker"],
            cnt=1,
            value_units=deal["amount"],
            limit_for_deal=limit_for_deal,
            commission=commission,
            rate=str(deal["rate"]),
        )
        k = await kb.accept_or_decline_deal(lang, deal["identificator"])
        return text, k

    async def message_about_deal_timeout(self, user, identificator):
        lang = user["lang"]
        text = await self._get(lang, var_name="message_about_deal_timeout", deal_identificator=identificator)
        k = None
        return text, k

    async def cancel_deal(self, user, deal):
        lang = user["lang"]
        text = await self._get(lang, var_name="cancel_deal", deal_identificator=deal["identificator"])
        k = await kb.get_yes_no_kb(lang)
        return text, k

    async def deal_canceled(self, user, deal):
        lang = user["lang"]
        text = await self._get(lang, var_name="deal_canceled", deal_identificator=deal["identificator"])
        k = await kb.main_menu(lang)
        return text, k

    async def opponent_canceled_deal(self, user, identificator):
        lang = user["lang"]
        text = await self._get(lang, var_name="opponent_canceled_deal", deal_identificator=identificator)
        k = await kb.main_menu(lang)
        return text, k

    async def decline_cancel_deal(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="decline_cancel_deal")
        k = await kb.main_menu(lang)
        return text, k

    async def about(self, user):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="about",
            nickname=user["nickname"],
            coin_name=SYMBOL_NAME.upper(),
            support=SUPPORT,
            site="www.skycrypto.me",
        )
        k = await kb.about(lang)
        return text, k

    async def communication(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="communication")
        k = await kb.communication(lang)
        return text, k

    async def friends(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="friends")
        k = await kb.friends(lang)
        return text, k

    async def affiliate(self, user, *, invited_cnt, earned_from_ref, earned_in_currency):
        lang = user["lang"]
        commission = int(BUYER_REFERRAL_COMMISSION_FROM_COMMISSION * 100)
        text = await self._get(
            lang,
            var_name="affiliate",
            currency=user["currency"].upper(),
            invited_cnt=invited_cnt,
            earned_from_ref=get_correct_value(earned_from_ref),
            earned_in_currency=round(earned_in_currency, 2),
            percents_commission=commission,
        )
        k = await kb.affiliate(lang)
        return text, k

    async def settings(self, user):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="settings",
            nickname=user["nickname"],
            verification_sm=verify_sm[user["is_verify"]],
            sky_pay_sm=verify_sm[user["sky_pay"]],
        )
        k = await kb.settings(lang)
        return text, k

    async def lang_settings(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="lang_settings")
        k = await kb.lang_settings(lang)
        return text, k

    async def done(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="done")
        k = await kb.main_menu(lang)
        return text, k

    async def rate_settings(self, user, rate):
        lang = user["lang"]
        text = await self._get(lang, var_name="rate_settings", cnt=1, rate=str(rate), currency=user["currency"].upper())
        k = await kb.rate_settings(lang)
        return text, k

    async def currency_settings(self, user, currencies):
        lang = user["lang"]
        text = await self._get(lang, var_name="currency_settings", currency=user["currency"].upper())
        k = await kb.currency_settings(lang, currencies)
        return text, k

    async def promocodes(self, user, promocodes_cnt):
        lang = user["lang"]
        text = await self._get(lang, var_name="promocodes", currency=user["currency"].upper())
        k = await kb.promocodes(lang, promocodes_cnt)
        return text, k

    async def create_promocode(self, user, balance_units, balance_currency):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="create_promocode",
            currency=user["currency"].upper(),
            balance_units=balance_units,
            balance_currency=balance_currency,
        )
        k = await kb.create_promocode(lang, user["currency"])
        return text, k

    async def choose_count(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="choose_count")
        k = await kb.get_cancel(lang)
        return text, k

    async def wrong_count(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="wrong_count")
        k = await kb.get_cancel(lang)
        return text, k

    async def choose_amount(self, user, promocode_type):
        lang = user["lang"]
        t = SYMBOL.upper() if promocode_type == "crypto" else user["currency"].upper()
        text = await self._get(lang, var_name="choose_amount", t=t)
        k = await kb.get_cancel(lang)
        return text, k

    async def wrong_amount(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="wrong_amount")
        k = await kb.get_cancel(lang)
        return text, k

    async def promocode_created(self, user, code, count, amount, currency_amount):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="promocode_created",
            code=code,
            count=count,
            amount="{0:.8f}".format(amount),
            currency_amount="{0:.2f}".format(currency_amount),
            currency=user["currency"].upper()
        )
        k = await kb.main_menu(lang)
        return text, k

    async def activate_promocode(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="activate_promocode")
        k = await kb.get_cancel(lang)
        return text, k

    async def cancel_activate_promocode(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="cancel_activate_promocode")
        k = await kb.main_menu(lang)
        return text, k

    async def cancel_create_promocode(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="cancel_create_promocode")
        k = await kb.main_menu(lang)
        return text, k

    async def promocode_activated(self, user, amount, creator_nickname):
        lang = user["lang"]
        text = await self._get(
            lang, var_name="promocode_activated", amount="{0:.8f}".format(amount), nickname=creator_nickname
        )
        k = await kb.main_menu(lang)
        return text, k

    async def promocode_activated_by(self, user, activator_nickname, amount, code):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="promocode_activated_by",
            nickname=activator_nickname,
            amount="{0:.8f}".format(amount),
            code=code,
        )
        k = await kb.main_menu(lang)
        return text, k

    async def wrong_promocode(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="wrong_promocode")
        k = await kb.main_menu(lang)
        return text, k

    async def promocode(self, user, promocode_id, code, amount, count, activations):
        lang = user["lang"]
        text = await self._get(
            lang, var_name="promocode", amount="{0:.8f}".format(amount), count=count, code=code, activations=activations
        )
        k = await kb.delete_promocode(lang, promocode_id)
        return text, k

    async def promocode_deleted(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="promocode_deleted")
        k = await kb.main_menu(lang)
        return text, k

    async def user_does_not_exists(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="user_does_not_exists")
        k = await kb.invite_friend(lang)
        return text, k

    async def user_deleted(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="user_deleted")
        k = await kb.main_menu(lang)
        return text, k

    async def deal_does_not_exists(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="deal_does_not_exists")
        k = None
        return text, k

    async def user(self, user, user_info, allow_messages, is_baned_messages):
        lang = user["lang"]
        balance_str = ""
        if user["is_admin"]:
            balance_str += await self._get(lang, var_name="balance", balance=user_info["balance"])
            balance_str += await self._get(lang, var_name="allow_sell", allow_sell=verify_sm[user_info["allow_sell"]])
            balance_str += await self._get(lang, var_name="allow_sale_v2", allow_sale_v2=verify_sm[user_info["allow_sale_v2"]])
            balance_str += await self._get(lang, var_name="sky_pay", sky_pay=verify_sm[user_info["sky_pay"]])
            balance_str += await self._get(lang, var_name="sky_pay_v2", sky_pay_v2=verify_sm[user_info["allow_super_buy"]])
            balance_str += await self._get(lang, var_name="super_verification", super_verification=verify_sm[user_info["super_verify_only"]])
        verification_sm = verify_sm[user_info["is_verify"]]
        sky_pay_sm = verify_sm[user_info["sky_pay"]]
        del user_info["lang"]
        user_info.pop('symbol', None)
        text = await self._get(
            lang,
            var_name="user",
            balance_str=balance_str,
            verification_sm=verification_sm,
            sky_pay_sm=sky_pay_sm,
            **user_info,
        )
        k = await kb.user(lang, user_info, user["is_admin"], allow_messages, is_baned_messages)
        return text, k

    async def write_message(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="write_message")
        k = await kb.get_cancel(lang)
        return text, k

    async def cancel_write_message(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="cancel_write_message")
        k = await kb.main_menu(lang)
        return text, k

    async def message_sent(self, user, to_user):
        lang = user["lang"]
        text = await self._get(lang, var_name="message_sent", nickname=to_user)
        k = await kb.main_menu(lang)
        return text, k

    async def user_baned_messages_from_you(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="user_baned_messages_from_you")
        k = await kb.main_menu(lang)
        return text, k

    async def message_received(self, receiver, sender, text):
        lang = receiver["lang"]
        text = await self._get(lang, var_name="message_received", text=text, nickname=sender["nickname"])
        k = await kb.answer(lang, sender["id"])
        return text, k

    async def photo_received(self, receiver, sender):
        lang = receiver["lang"]
        text = await self._get(lang, var_name="photo_received", nickname=sender["nickname"])
        k = await kb.answer(lang, sender["id"])
        return text, k

    async def new_accounts_join(self, tg_account, web_account, token):
        lang = tg_account["lang"]
        text = await self._get(
            lang,
            var_name="new_accounts_join",
            first_nickname=web_account["nickname"],
            second_nickname=tg_account["nickname"],
        )
        k = await kb.get_token_kb(lang, token)
        return text, k

    async def user_sent_you_photo(self, receiver, sender):
        lang = receiver["lang"]
        text = await self._get(lang, var_name="user_sent_you_photo", nickname=sender.nickname)
        k = await kb.answer(lang, sender.id)
        return text, k

    async def opponent_opened_dispute(self, user, identificator, dispute_time, can_decline=False):
        lang = user["lang"]
        text = await self._get(lang, var_name="opponent_opened_dispute", identificator=identificator, t=dispute_time)
        k = await kb.answer_dispute(lang, identificator, can_decline)
        return text, k

    async def confirm_decline_dispute(self, user, deal_identificator):
        lang = user["lang"]
        text = await self._get(lang, var_name="confirm_decline_dispute", identificator=deal_identificator)
        k = await kb.get_yes_no_kb(lang)
        return text, k

    async def dispute_declined(self, user, deal_identificator):
        lang = user["lang"]
        text = await self._get(lang, var_name="dispute_declined", identificator=deal_identificator)
        k = await kb.main_menu(lang)
        return text, k

    async def cancel_decline_dispute(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="cancel_decline_dispute")
        k = await kb.main_menu(lang)
        return text, k

    async def dispute_opened(self, user, identificator, dispute_time):
        lang = user["lang"]
        text = await self._get(lang, var_name="dispute_opened", identificator=identificator, t=dispute_time)
        k = None
        return text, k

    async def dispute_opened_notification(self, user, identificator):
        lang = user["lang"]
        text = await self._get(lang, var_name="dispute_opened_notification", identificator=identificator)
        k = None
        return text, k

    async def dispute_already_opened(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="dispute_already_opened")
        k = None
        return text, k

    async def both_opened_dispute(self, user, identificator):
        lang = user["lang"]
        text = await self._get(lang, var_name="both_opened_dispute", identificator=identificator, support=SUPPORT)
        k = None
        return text, k

    async def deal_closed_by_dispute(self, user, identificator, won):
        lang = user["lang"]
        text = await self._get(lang, var_name=f"deal_closed_by_dispute_{won}", identificator=identificator)
        k = None
        return text, k

    async def deal_closed_by_dispute_admin(self, user, identificator, won):
        lang = user["lang"]
        text = await self._get(lang, var_name=f"deal_closed_by_dispute_{won}_admin", identificator=identificator)
        k = None
        return text, k

    async def change_limits(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="change_limits")
        k = await kb.get_cancel(lang)
        return text, k

    async def change_rate(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="change_rate")
        k = await kb.get_cancel(lang)
        return text, k

    async def change_conditions(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="change_conditions")
        k = await kb.get_cancel(lang)
        return text, k

    async def delete_lot_confirmation(self, user, lot):
        lang = user["lang"]
        text = await self._get(
            lang, var_name="delete_lot_confirmation", lot_id=lot["identificator"], broker=lot["broker"]
        )
        k = await kb.get_yes_no_kb(lang)
        return text, k

    async def cancel_delete_lot(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="cancel_delete_lot")
        k = await kb.main_menu(lang)
        return text, k

    async def lot_deleted(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="lot_deleted")
        k = await kb.main_menu(lang)
        return text, k

    async def lot_deactivated(self, user, identificator):
        lang = user["lang"]
        text = await self._get(lang, var_name="lot_deactivated", identificator=identificator)
        k = None
        return text, k

    async def cancel_change_lot(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="cancel_change_lot")
        k = await kb.main_menu(lang)
        return text, k

    async def new_referral(self, user, referral):
        lang = user["lang"]
        text = await self._get(lang, var_name="new_referral", identificator=referral)
        k = await kb.invite_friend(lang)
        return text, k

    async def referral_earning(self, user, referral, earning):
        lang = user["lang"]
        text = await self._get(
            lang, var_name="referral_earning", identificator=referral["nickname"], earning="{0:.8f}".format(earning)
        )
        k = await kb.invite_friend(lang)
        return text, k

    async def payment_for_support(self, data):
        text = (
            f'<b>Платеж:</b> {data["id"]}\n'
            f'<b>Мерчант:</b> /u{data["merchant"]}\n'
            f'<b>Сумма:</b> {data["amount"]}\n'
            f'<b>Сумма в валюте:</b> {data["is_currency_amount"]}\n'
            f'<b>Криптовалюта:</b> {data["symbol"].upper()}\n'
            f'<b>Валюта:</b> {data["currency"].upper()}\n'
            f'<b>Адрес:</b> {data["address"]}\n'
            f'<b>Статус:</b> {data["status"]}\n'
            f"<b>Сделки:</b>\n"
        )
        for deal in data["deals"]:
            text += f'\t/d{deal["identificator"]}, {deal["buyer_email"]}\n'
        return text.expandtabs()

    async def sale_for_support(self, data):
        text = (
            f'<b>Продажа:</b> {data["id"]}\n'
            f'<b>Мерчант:</b> /u{data["merchant"]}\n'
            f'<b>Сумма:</b> {data["amount"]}\n'
            f'<b>Криптовалюта:</b> {data["symbol"].upper()}\n'
            f'<b>Валюта:</b> {data["currency"].upper()}\n'
            f'<b>Статус:</b> {data["status"]}\n'
            f"<b>Сделки:</b>\n"
        )
        for deal in data["deals"]:
            text += f'\t/d{deal["identificator"]}\n'
        return text.expandtabs()

    async def sale_v2_for_support(self, data):
        text = (
            f'<b>Продажа:</b> {data["id"]}\n'
            f'<b>Мерчант:</b> /u{data["merchant"]}\n'
            f'<b>Сумма:</b> {data["amount"]}\n'
            f'<b>Криптовалюта:</b> {data["symbol"].upper()}\n'
            f'<b>Валюта:</b> {data["currency"].upper()}\n'
            f'<b>Статус:</b> {data["status"]}\n'
            f"<b>Сделки:</b>\n"
        )
        for deal in data["deals"]:
            text += f'\t/d{deal["identificator"]}\n'
        return text.expandtabs()

    async def cpayment_for_support(self, data):
        text = (
            f'<b>CPayment:</b> {data["id"]}\n'
            f'<b>Мерчант:</b> /u{data["merchant"]}\n'
            f'<b>Сумма:</b> {data["amount"]}\n'
            f'<b>Криптовалюта:</b> {data["symbol"].upper()}\n'
            f'<b>Валюта:</b> {data["currency"].upper()}\n'
            f'<b>Статус:</b> {data["status"]}\n'
        )
        return text.expandtabs()

    async def withdrawal_for_support(self, data):
        text = (
            f'<b>Вывод v2:</b> {data["id"]}\n'
            f'<b>Мерчант:</b> /u{data["merchant"]}\n'
            f'<b>Сумма:</b> {data["amount"]}\n'
            f'<b>Криптовалюта:</b> {data["symbol"].upper()}\n'
            f'<b>Статус:</b> {data["status"]}\n'
            f'<b>Адрес:</b> {data["address"]}\n'
        )
        return text.expandtabs()

    async def admin_menu(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="admin_menu")
        k = await kb.admin_menu()
        return text, k

    async def get_node_transaction(self, data):
        text = (
            f"<pre>Транзакция {data['txid']}\n"
            f"Зарегистрирована {datetime.datetime.utcfromtimestamp(data['timereceived']).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Проведена {datetime.datetime.utcfromtimestamp(data['blocktime']).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Сумма {data['amount']}\n"
            f"Комиссия {'{0:.8f}'.format(abs(data['fee']))}</pre>"
        )
        return text

    async def propose_resolving(self, user, res_id, api_nick):
        lang = user["lang"]
        text = await self._get(lang, var_name="propose_resolving", nick=api_nick)
        k = await kb.propose_resolving(lang, res_id)
        return text, k

    async def propose_transaction(self, user, prop_id, api_nick, amount, amount_cur):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="propose_transaction",
            nick=api_nick,
            amount=amount,
            amount_cur=amount_cur,
            cur=user["currency"].upper(),
        )
        k = await kb.propose_transaction(lang, prop_id)
        return text, k

    async def transaction_approved(self, user, amount):
        lang = user["lang"]
        text = await self._get(
            lang,
            var_name="transaction_approved",
            amount=amount,
        )
        k = await kb.main_menu(lang)
        return text, k

    @staticmethod
    async def you_are_baned(user):
        lang = user["lang"]
        text = translate("misc.you_are_baned", locale=lang, support=f"t.me/{SUPPORT[1:]}")
        k = None
        return text, k

    async def withdrawal_limit_reached(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="withdrawal_limit_reached")
        k = await kb.main_menu(lang)
        return text, k

    async def unknown_command(self, user, withdraw_commission):
        lang = user["lang"]
        buy_commission = round(BUYER_COMMISSION * 100, 1)
        sell_commission = round(SELLER_COMMISSION * 100, 1)
        if SYMBOL == "btc":
            withdraw_commission_text = (
                "(динамичная комиссия)\n"
                "От 0.0001 BTC до 0.0005 BTC -> 0.00007 BTC\n"
                "От 0.0005 BTC до 0.001 BTC -> 0.0001 BTC\n"
                "От 0.001 BTC до 0.1 BTC -> 0.0002 BTC\n"
                "От 0.1 BTC до 1 BTC -> 0.0003 BTC"
            )
        else:
            withdraw_commission_text = f"(комиссия сети) - {withdraw_commission}"
        text = await self._get(
            lang,
            var_name="unknown_command",
            buy_commission=buy_commission,
            sell_commission=sell_commission,
            support=SUPPORT,
            withdraw_commission_text=withdraw_commission_text,
        )
        k = await kb.main_menu(lang)
        return text, k

    async def unknown_error(self):
        lang = "ru"
        text = await self._get(lang, var_name="unknown_error")
        k = await kb.main_menu(lang)
        return text, k

    async def service_unavailable_error(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="service_unavailable_message")
        k = await kb.main_menu(lang)
        return text, k

    async def lot_not_active(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="lot_not_active")
        k = await kb.main_menu(lang)
        return text, k

    async def javascript_in_pdf(self, user):
        lang = user["lang"]
        text = await self._get(lang, var_name="javascript_in_pdf")
        k = await kb.main_menu(lang)
        return text, k


rc = ResponseComposer()
