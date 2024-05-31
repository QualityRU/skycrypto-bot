from datetime import datetime, timezone, timedelta

from aiogram.types.inline_keyboard import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types.reply_keyboard import ReplyKeyboardMarkup

from constants import DealTypes
from settings import CURRENCIES, PROMOCODE_TYPES, SUPPORT, SYMBOL
from translations import translate
from utils.helpers import parse_utc_datetime
from utils.sky_math import math

LOT_ACTIVATION_STATUS = {True: "🌕", False: "🌑"}
LOT_USER_VERIFICATION_STATUS = {True: "✅", False: ""}


class Keyboards:
    def inl_b(self, name, lang="ru", action=None, link=None, **kwargs):
        if link is not None:
            return InlineKeyboardButton(self.label(name, lang, **kwargs), url=link)

        elif action is not None:
            return InlineKeyboardButton(self.label(name, lang, **kwargs), callback_data=action)

        else:
            return InlineKeyboardButton(self.label(name, lang, **kwargs), callback_data=name)

    def label(self, name, lang, **kwargs):
        t = translate(f"menu_misc.{name}", locale=lang, **kwargs)
        if "menu_misc" in t:
            return name
        else:
            return t

    def get_kb(self, btns, lang, **kwargs):
        formed_btns = []
        for row in btns:
            formed_btns.append([self.label(name, lang) for name in row])
        return ReplyKeyboardMarkup(formed_btns, resize_keyboard=True, **kwargs)

    def get_btns_for_ik(self, btns, lang):
        formed_btns = []
        for row in btns:
            formed_btns.append([self.inl_b(name, lang) for name in row])
        return formed_btns

    async def main_menu(self, lang):
        _kb = self.get_kb([["wallet"], ["about", "settings"]], lang)
        _kb.keyboard[0].insert(1, self.label("exchange", lang, symbol=SYMBOL.upper()))
        return _kb

    async def confirm_policy(self, lang):
        return self.get_kb([["confirm_policy"]], lang)

    async def wallet(self, lang):
        btns = [["deposit", "withdraw"], ["promocodes", "reports"]]
        if SYMBOL == 'usdt':
            btns.append(["deposit_rub"])
        btns = self.get_btns_for_ik(btns, lang)

        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def buy_sell_k(self, lang):
        btns = [[self.inl_b("buy", lang, "buy 1"), self.inl_b("sell", lang, "sell 1")]]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def exchange(self, lang, active_deals_count, lots_cnt):
        _kb = InlineKeyboardMarkup(row_width=2)
        _kb.inline_keyboard.append([self.inl_b("buy", lang, "buy 1"), self.inl_b("sell", lang, "sell 1")])
        _kb.add(self.inl_b("handle_lots" if lots_cnt > 0 else "create_lot_", lang, "handle_lots 1"))
        if active_deals_count > 0:
            _kb.add(self.inl_b("active_deals", lang, cnt=active_deals_count))
        return _kb

    async def active_deals(self, lang, active_deals):
        btns = []
        for deal in active_deals:
            name = "active_deal"
            print(deal)
            if deal["dispute_exists"]:
                name += "_dispute"
            elif deal["state"] == "paid":
                name += "_paid"
            btns.append(
                [
                    self.inl_b(
                        name,
                        lang,
                        f'deal {deal["identificator"]}',
                        broker=deal["broker"],
                        value_currency=deal["amount_currency"],
                        currency=deal["currency"].upper(),
                    )
                ]
            )
        btns.append([self.inl_b("back", lang, "exchange")])
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def handle_lots(self, lang, is_trading_active, lots, rates, page, pages):
        _kb = InlineKeyboardMarkup(row_width=1)
        trading_status_button = "deactivate_trading" if is_trading_active else "activate_trading"
        first_button = self.inl_b(trading_status_button, lang, "change_trading_activity_status")
        _kb.add(first_button)

        for lot in lots:
            t = self.label(f'lot_{lot["type"]}', lang)
            if lot["coefficient"]:
                percents_difference = round((lot["coefficient"] - 1) * 100, 2)
            else:
                percents_difference = await math.get_percents_diff_rate(rates[lot["currency"]], lot["rate"])
            activation_status = LOT_ACTIVATION_STATUS[lot["is_active"] if is_trading_active else False]
            lot_btn = self.inl_b(
                "user_lot",
                lang,
                f'lot {lot["identificator"]}',
                type=t,
                broker=lot["broker"],
                percent=percents_difference,
                currency=lot["currency"].upper(),
                rate=lot["rate"],
                activation_sm=activation_status,
            )
            _kb.add(lot_btn)
        try:
            pagination_btns = await self.get_pagination_buttons(
                page, pages, base_str=f"handle_lots", lang=lang
            )
        except IndexError:
            pagination_btns = [self.inl_b("cancel_lots", lang, "exchange", page=1)]
        _kb.inline_keyboard.append(pagination_btns)
        _kb.inline_keyboard.append([self.inl_b("create_lot", lang, "create_lot")])
        return _kb

    async def create_lot_choose_type(self, lang):
        _kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        _kb.add(self.label("you_wanna_sell", lang, symbol=SYMBOL.upper()))
        _kb.add(self.label("you_wanna_buy", lang, symbol=SYMBOL.upper()))
        _kb.add(self.label("cancel", lang))
        return _kb

    async def create_lot_choose_broker(self, lang, brokers):
        _kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for b in brokers:
            _kb.add(b)
        _kb.keyboard.append([self.label("cancel", lang)])
        return _kb

    async def get_cancel(self, lang):
        return self.get_kb([["cancel"]], lang)

    async def withdraw(self, lang, last_address):
        if last_address is not None:
            return self.get_kb([[last_address], ["cancel"]], lang)
        else:
            return self.get_kb([["cancel"]], lang)

    async def get_pagination_buttons(self, page, pages, base_str, lang, back="exchange"):
        if page + 1 > pages:
            b_next = 1
            b_prev = page - 1
        elif page - 1 < 1:
            b_next = page + 1
            b_prev = pages
        else:
            b_next = page + 1
            b_prev = page - 1
        prev_btn = self.inl_b(f"⬅️ {b_prev}/{pages}", lang, f"{base_str} {b_prev}")
        next_btn = self.inl_b(f"➡️ {b_next}/{pages}", lang, f"{base_str} {b_next}")
        decline_btn = self.inl_b("cancel_lots", lang, back, page=page)
        return prev_btn, decline_btn, next_btn

    async def market(self, lang, lots, page, pages, cur, t):
        _kb = InlineKeyboardMarkup(row_width=1)
        for l in lots:
            if l["cnt"] > 0:
                _kb.add(
                    self.inl_b(
                        f"lot_buy_sell_menu",
                        lang,
                        f'lots {t} {l["broker"]["id"]} 1',
                        broker=l["broker"]["name"],
                        rate=l["rate"],
                        currency=cur,
                        cnt=l["cnt"],
                    )
                )
            else:
                _kb.add(self.inl_b("lot_buy_sell_menu_empty", lang, f"lots empty", broker=l["broker"]["name"]))
        pagination_btns = await self.get_pagination_buttons(page, pages, base_str=t, lang=lang)
        _kb.inline_keyboard.append(pagination_btns)
        return _kb

    async def _get_sm_before_lot(self, user, lot):
        smiles = ["🔵", "🌕", "⚪️", "✅"]
        if lot["owner"]:
            sm = smiles[0]
        elif lot["is_verify"]:
            sm = smiles[3]
        else:
            sm = smiles[1] if lot["is_online"] else smiles[2]
        return sm

    async def menu_lots_buy_from_broker(self, lang, lots, page, pages, user, broker):
        _kb = InlineKeyboardMarkup(row_width=1)
        for lot in lots:
            sm = await self._get_sm_before_lot(user, lot)
            _kb.add(
                self.inl_b(
                    "lot_buy_sell_menu_broker",
                    lang,
                    f'lot {lot["identificator"]}',
                    rate=lot["rate"],
                    currency=lot["currency"].upper(),
                    limit_from=lot["limit_from"],
                    limit_to=lot["limit_to"],
                    sm=sm,
                )
            )
        try:
            pagination_btns = await self.get_pagination_buttons(
                page, pages, base_str=f"lots buy {broker}", lang=lang, back=f"buy 1"
            )
        except IndexError:
            pagination_btns = [self.inl_b("cancel_lots", lang, "exchange", page=1)]
        _kb.inline_keyboard.append(pagination_btns)
        return _kb

    async def menu_lots_sell_from_broker(self, lang, lots, page, pages, user, broker):
        _kb = InlineKeyboardMarkup(row_width=1)
        for lot in lots:
            sm = await self._get_sm_before_lot(user, lot)
            _kb.add(
                self.inl_b(
                    "lot_buy_sell_menu_broker",
                    lang,
                    f'lot {lot["identificator"]}',
                    rate=lot["rate"],
                    currency=lot["currency"].upper(),
                    limit_from=lot["limit_from"],
                    limit_to=lot["limit_to"],
                    sm=sm,
                )
            )
        try:
            pagination_btns = await self.get_pagination_buttons(
                page, pages, base_str=f"lots sell {broker}", lang=lang, back=f"sell 1"
            )
        except IndexError:
            pagination_btns = [self.inl_b("cancel_lots", lang, "exchange", page=1)]
        _kb.inline_keyboard.append(pagination_btns)
        return _kb

    async def lot(self, lang, is_enough_money, are_users_active, lot_id, allow_deal):
        if not allow_deal:
            btn = self.inl_b("cant_begin_deal", lang, "lots empty")
        elif not is_enough_money:
            btn = self.inl_b("cant_begin_deal_balance", lang, "lots empty")
        elif not are_users_active:
            btn = self.inl_b("cant_begin_deal", lang, "lots empty")
        else:
            btn = self.inl_b("begin_deal", lang, f"begin_deal {lot_id}")
        return InlineKeyboardMarkup(inline_keyboard=[[btn]])

    async def self_lot(self, lang, lot):
        btns = [
            [
                self.inl_b("limits", lang, f'change_limits {lot["identificator"]}'),
                self.inl_b("rate", lang, f'change_rate {lot["identificator"]}'),
                self.inl_b("conditions", lang, f'change_conditions {lot["identificator"]}'),
            ],
            [self.inl_b("back", lang, "handle_lots 1"), self.inl_b("delete", lang, f'delete_lot {lot["identificator"]}')],
        ]
        if lot["is_active"]:
            btns[-1].append(self.inl_b("lot_off", lang, f'change_lot_status {lot["identificator"]}'))
        else:
            btns[-1].append(self.inl_b("lot_on", lang, f'change_lot_status {lot["identificator"]}'))
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def get_yes_no_kb(self, lang):
        return self.get_kb([["yes", "no"]], lang, one_time_keyboard=True)

    async def get_req(self, lang, reqs):
        _kb = ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        if reqs:
            _kb.add(reqs[0])
        _kb.add(self.label("cancel", lang))
        return _kb

    async def deal(self, user, deal, is_admin, required_mask, mask):
        lang = user["lang"]
        deal_id = deal["identificator"]

        _kb = []

        if (
            deal['type'] == DealTypes.sky_pay_v2 and user['id'] == deal['buyer']['id']
            or
            deal['type'] == DealTypes.sky_sale_v2 and user['id'] == deal['seller']['id']
        ):
            return

        if (
            deal["state"] == "confirmed"
            and deal["seller"]["id"] == user["id"]
            and deal['type'] in (DealTypes.sky_pay, DealTypes.sky_pay_v2)
            and not required_mask
        ):
            _kb += [[self.inl_b("send_crypto_without_agreement", lang, f"send_crypto_wo_agreement {deal_id}")]]

        if deal["state"] == "proposed" and deal["lot"]["user_id"] == user["id"]:
            _kb += [
                [
                    self.inl_b("accept_deal", lang, f"accept_deal {deal_id}"),
                    self.inl_b("decline_deal", lang, f"cancel_deal {deal_id}"),
                ]
            ]
        elif deal["state"] == "proposed":
            _kb += [[self.inl_b("cancel_deal", lang, f"cancel_deal {deal_id}")]]
        elif deal["state"] == "confirmed" and deal["buyer"]["id"] == user["id"]:
            if required_mask:
                _kb += [[self.inl_b("cancel_deal", lang, f"cancel_deal {deal_id}")]]
            else:
                _kb += [
                    [self.inl_b("confirm_sent_fiat", lang, f"confirm_sent_fiat {deal_id}")],
                    [self.inl_b("cancel_deal", lang, f"cancel_deal {deal_id}")],
                ]
        elif deal["state"] == "confirmed" and deal["seller"]["id"] == user["id"]:
            _kb += []
        elif deal["state"] == "paid" and deal["seller"]["id"] == user["id"]:
            _kb += [
                [self.inl_b("send_crypto", lang, f"send_crypto {deal_id}")],
            ]
            if deal['seller']['rating'] > 0:
                if deal['type'] in (DealTypes.fast.value, DealTypes.sky_pay.value, DealTypes.sky_pay_v2.value):
                    if deal["seller"]["id"] == user["id"] and parse_utc_datetime(deal['created']) < datetime.now(timezone.utc) - timedelta(minutes=5):
                        _kb.append([self.inl_b("open_dispute", lang, f"open_dispute {deal_id}")])
                else:
                    _kb.append([self.inl_b("open_dispute", lang, f"open_dispute {deal_id}")])

        elif deal["state"] == "paid" and deal["buyer"]["id"] == user["id"] and (deal['buyer']['rating'] > 0 or deal['buyer']['is_verify']):
            _kb += [[self.inl_b("open_dispute", lang, f"open_dispute {deal_id}")]]
        if is_admin and deal["state"] == "paid":
            _kb += [
                [self.inl_b("Закрыть в пользу покупателя", action=f"cancel_deal {deal_id} buyer")],
                [self.inl_b("Закрыть в пользу продавца", action=f"cancel_deal {deal_id} seller")],
            ]

        if (
            deal["state"] == "deleted"
            and (deal["seller"]["id"] == user["id"] or is_admin)
            # and "fd" in deal["buyer"]["nickname"]
            and deal['type'] in (DealTypes.sky_pay, DealTypes.plain)
            and deal["requisite"]
        ):
            if required_mask and not mask:
                _kb += [[self.inl_b("run_payment_with_req", lang, f"run_payment_with_req {deal_id}")]]
            else:
                _kb += [[self.inl_b("run_payment", lang, f"run_payment {deal_id}")]]

        if not _kb:
            _kb = None
        return InlineKeyboardMarkup(inline_keyboard=_kb)

    async def accept_or_decline_deal(self, lang, deal_id):
        btns = [
            [
                self.inl_b("accept_deal", lang, f"accept_deal {deal_id}"),
                self.inl_b("decline_deal", lang, f"cancel_deal {deal_id}"),
            ]
        ]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def confirm_sent_fiat(self, lang, deal_id, required_mask=False):
        if required_mask:
            btns = [[self.inl_b("cancel_deal", lang, f"cancel_deal {deal_id}")]]
        else:
            btns = [
                [self.inl_b("confirm_sent_fiat", lang, f"confirm_sent_fiat {deal_id}")],
                [self.inl_b("cancel_deal", lang, f"cancel_deal {deal_id}")],
            ]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def check_fiat(self, lang, deal_id, is_show_dispute_button: bool = True):
        btns = [[self.inl_b("send_crypto", lang, f"send_crypto {deal_id}")]]
        if is_show_dispute_button:
            btns.append([self.inl_b("open_dispute", lang, f"open_dispute {deal_id}")])

        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def open_dispute(self, lang, deal_id):
        btns = [[self.inl_b("open_dispute", lang, f"open_dispute {deal_id}")]]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def like_dislike_k(self, lang, target_user_id, deal_id):
        btns = [
            [
                self.inl_b("like", lang, f"like {target_user_id} {deal_id}"),
                self.inl_b("dislike", lang, f"dislike {target_user_id} {deal_id}"),
            ]
        ]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def other_bots(self, lang):
        btns = [
            [self.inl_b("SKY BTC BANKER", lang, link="t.me/sky_btc_bot")],
            [self.inl_b("SKY ETH BANKER", lang, link="t.me/sky_eth_bot")],
            [self.inl_b("SKY USDT BANKER", lang, link="t.me/sky_usdt_bot")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def about(self, lang):
        btns = [
            [self.inl_b("communication", lang), self.inl_b("friends", lang)],
            [
                self.inl_b("affiliate", lang),
                self.inl_b("conditions", lang, link="https://skycrypto.me/doc/term-of-use-ru.pdf"),
            ],
            [
                self.inl_b("support", lang, link=f"t.me/{SUPPORT[1:]}"),
                self.inl_b("verification", lang, link=f"t.me/{SUPPORT[1:]}"),
            ]
        ]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def communication(self, lang):
        btns = [
            [
                self.inl_b("world_chat", lang, link="https://t.me/SKYchatEN"),
                self.inl_b("ru_chat", lang, link="https://t.me/SkyChatRu"),
            ],
            [self.inl_b("back", lang, "about"), self.inl_b("news_channel", lang, link="https://t.me/sky_banker")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def friends(self, lang):
        btns = [
            [self.inl_b("SKY CRYPTO", lang, link="https://skycrypto.me/partner")],
            [self.inl_b("SKY PAY", lang, link="https://skycrypto.me/sky-pay")],
            [self.inl_b("education", lang, link="https://skycrypto.me/training")],
            [self.inl_b("FAQ", lang, link="https://skycrypto.me/faq")],
            [self.inl_b("back", lang, "about")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def affiliate(self, lang):
        btns = [[self.inl_b("get_code", lang)], [self.inl_b("back", lang, "about")]]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def invite_friend(self, lang):
        btns = [[self.inl_b("get_code", lang)]]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def settings(self, lang):
        btns = [
            [self.inl_b("lang", lang, "lang_settings"), self.inl_b("rate", lang, "rate_settings")],
            [self.inl_b("currency_settings", lang)],
        ]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def lang_settings(self, lang):
        btns = [
            [self.inl_b("lang_ru", lang, "lang_ru")],
            [self.inl_b("lang_en", lang, "lang_en")],
            [self.inl_b("back", lang, "settings")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def rate_settings(self, lang):
        btns = [[self.inl_b("back", lang, "settings")]]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def currency_settings(self, lang, currencies):
        btns = [
            [self.inl_b(cur["id"].upper(), lang, f'choose_currency {cur["id"]}') for cur in currencies],
            [self.inl_b("back", lang, "settings")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def delete_promocode(self, lang, p_id):
        btns = [[self.inl_b("delete", lang, f"delete_promocode {p_id}")]]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def user(self, lang, user_info, is_admin, allow_messages, is_baned_messages):
        btns = []
        if is_admin:
            verification_label = "unverify" if user_info["is_verify"] else "verify"
            verification_b = self.inl_b(verification_label, lang, f'change_verification_status {user_info["id"]}')

            superverification_label = "unsuperverify" if user_info["super_verify_only"] else "superverify"
            superverification_b = self.inl_b(superverification_label, lang, f'change_superverification_status {user_info["id"]}')

            sky_pay_label = "sky_pay_off" if user_info["sky_pay"] else "sky_pay_on"
            sky_pay_b = self.inl_b(sky_pay_label, lang, f'change_skypay_status {user_info["id"]}')

            sky_pay_v2_label = "sky_pay_v2_off" if user_info["allow_super_buy"] else "sky_pay_v2_on"
            sky_pay_v2_b = self.inl_b(sky_pay_v2_label, lang, f'change_skypayv2_status {user_info["id"]}')

            allow_sell_label = "disallow_sell" if user_info["allow_sell"] else "allow_sell"
            allow_sell_b = self.inl_b(allow_sell_label, lang, f'change_allowsell_status {user_info["id"]}')

            allow_sale_v2_label = "disallow_sale_v2" if user_info["allow_sale_v2"] else "allow_sale_v2"
            allow_sale_v2_b = self.inl_b(allow_sale_v2_label, lang, f'change_allowsalev2_status {user_info["id"]}')

            ban_label = "unban" if user_info["is_baned"] else "ban"
            shadow_ban_label = "shadow_unban" if user_info["shadow_ban"] else "shadow_ban"
            apply_shadow_ban_label = "apply_shadow_unban" if user_info["apply_shadow_ban"] else "apply_shadow_ban"
            ban_b = self.inl_b(ban_label, lang, f'change_ban_status {user_info["id"]}')
            shadow_ban_b = self.inl_b(shadow_ban_label, lang, f'change_shadowban_status {user_info["id"]}')
            apply_shadow_ban_b = self.inl_b(apply_shadow_ban_label, lang, f'change_applyshadowban_status {user_info["id"]}')
            btns.append([ban_b])
            btns.append([verification_b, superverification_b])
            btns.append([sky_pay_b, sky_pay_v2_b])
            btns.append([allow_sell_b, allow_sale_v2_b])
            btns.append([shadow_ban_b])
            btns.append([apply_shadow_ban_b])
        if allow_messages:
            btns.append([self.inl_b("write_message", lang, f'write_message {user_info["id"]}')])
        btns.append(
            [
                self.inl_b(
                    "unban_messages" if is_baned_messages else "ban_messages",
                    lang,
                    f'change_usermessagesban_status {user_info["id"]}',
                )
            ]
        )
        if is_admin:
            btns.append(
                [
                    self.inl_b("transactions", lang, action=f'user_transactions_report {user_info["id"]}'),
                    self.inl_b("deals", lang, action=f'user_deals_report {user_info["id"]}'),
                ]
            )
            btns.append(
                [
                    self.inl_b("lots", lang, action=f'user_lots_report {user_info["id"]}'),
                    self.inl_b("promo_codes", lang, action=f'user_promocodes_report {user_info["id"]}'),
                    self.inl_b("transit", lang, action=f'transit {user_info["id"]}'),
                ]
            )
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def answer(self, lang, receiver_id):
        btns = [[self.inl_b("answer", lang, f"write_message {receiver_id}")]]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def answer_dispute(self, lang, deal_id, can_decline):
        btns = [[self.inl_b("answer_dispute", lang, f"open_dispute {deal_id}")]]
        if can_decline:
            btns.append([self.inl_b("decline_dispute", lang, f"decline_dispute {deal_id}")])
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def promocodes(self, lang, cnt):
        btns = [
            [self.inl_b("create_promocode", lang), self.inl_b("activate_promocode", lang)],
            [self.inl_b("back", lang, "wallet")],
        ]

        if cnt > 0:
            btns.insert(-1, [self.inl_b("active_promocodes", lang, cnt=cnt)])

        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def create_promocode(self, lang, currency):
        btns = [
            [
                self.inl_b(SYMBOL.upper(), lang, f"create_promocode {PROMOCODE_TYPES[0]}"),
                self.inl_b(currency.upper(), lang, f"create_promocode {PROMOCODE_TYPES[1]}"),
            ],
            [self.inl_b("back", lang, "promocodes")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def admin_menu(self):
        btns = [
            [self.inl_b("Пользователи", action="users_report"), self.inl_b("Заявки", action="lots_report")],
            [self.inl_b("Сделки", action="deals_report"), self.inl_b("Промокоды", action="promocodes_report")],
            [self.inl_b("Транзакции", action="transactions_report"), self.inl_b("Финансы", action="financial_report")],
            [self.inl_b("Обмены", action="exchange_report")],
            [self.inl_b("Ком. мерчантов", action="merchant_report")],
            [self.inl_b("Кампании", action="campaigns_report")],
        ]
        return InlineKeyboardMarkup(inline_keyboard=btns)

    async def propose_resolving(self, lang, res_id):
        k = [
            [
                self.inl_b("yes", lang, f"confirm_resolving {res_id}"),
                self.inl_b("no", lang, f"decline_resolving {res_id}"),
            ]
        ]
        return InlineKeyboardMarkup(inline_keyboard=k)

    async def propose_transaction(self, lang, res_id):
        k = [
            [
                self.inl_b("yes", lang, f"confirm_transaction {res_id}"),
                self.inl_b("no", lang, f"decline_transaction {res_id}"),
            ]
        ]
        return InlineKeyboardMarkup(inline_keyboard=k)

    async def get_token_kb(self, lang, token):
        k = [[self.inl_b("yes", lang, f"show {token}"), self.inl_b("no", lang, f"decline_token")]]
        return InlineKeyboardMarkup(inline_keyboard=k)


kb = Keyboards()
