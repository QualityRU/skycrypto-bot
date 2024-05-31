from typing import Union

import aiohttp
import requests
from aiohttp.client_exceptions import ContentTypeError

from errors import BadRequestError
from settings import API_HOST, API_KEY
from utils.logger import logger


class API:
    async def _call_api(
        self, address, method: Union["get", "post", "patch", "delete"] = "get", _json=None, data=None, content_type=None
    ):
        url = API_HOST + address
        headers = {"Token": API_KEY}
        if content_type:
            headers["Content-Type"] = content_type

        async with aiohttp.ClientSession() as session:
            if content_type == "multipart/form-data" and method == "post":
                with aiohttp.MultipartWriter("mixed") as mpwriter:
                    mpwriter.append(data["file"].raw, {"Content-Type": "multipart/form-data"})
                    resp = await session.post(url, headers=headers, data=mpwriter)
            else:
                resp = await getattr(session, method)(url, headers=headers, json=_json)

            if resp.status == 403:
                data = await resp.json()
                raise BadRequestError(data.get("detail", ""))

            try:
                resp.raise_for_status()
            except Exception as e:
                logger.error(e)
                raise e

            try:
                j = await resp.json()
            except ContentTypeError:
                j = await resp.text()
                logger.info(j)

            return j

    async def get_updates(self):
        return await self._call_api("/updates")

    async def get_control_updates(self):
        return await self._call_api("/control-updates")

    async def get_all_telegram_ids(self):
        return await self._call_api("/all_telegram_ids")

    async def get_payment_info(self, payment_id):
        return await self._call_api(f"/payment-info/{payment_id}")

    async def get_payment_v2_info(self, payment_id):
        return await self._call_api(f"/payment-v2-info/{payment_id}")

    async def get_sale_info(self, sale_id):
        return await self._call_api(f"/sale-info/{sale_id}")

    async def get_sale_v2_info(self, sale_v2_id):
        return await self._call_api(f"/sale_v2-info/{sale_v2_id}")

    async def get_cpayment_info(self, cpayment_id):
        return await self._call_api(f"/cpayment-info/{cpayment_id}")

    async def get_withdrawal_info(self, withdrawal_id):
        return await self._call_api(f"/withdrawal-info/{withdrawal_id}")

    async def get_user(self, telegram_id=None, user_id=None):
        if telegram_id is not None:
            return await self._call_api(f"/user?telegram_id={telegram_id}")
        elif user_id is not None:
            return await self._call_api(f"/user/{user_id}")
        else:
            raise ValueError("telegram_id or user_id must be provided")

    async def get_user_info(self, nickname):
        return await self._call_api(f"/user-info/{nickname}")

    async def get_is_usermessages_baned(self, user_id, target_id):
        return (await self._call_api(f"/usermessages-ban-status/{target_id}?user_id={user_id}"))["is_baned"]

    async def set_usermessages_ban_status(self, user_id, target_id, status):
        data = {"user_id": user_id, "target_user_id": target_id, "status": status}
        return await self._call_api(f"/usermessages-ban-status", method="patch", _json=data)

    async def user_stat(self, user_id):
        return await self._call_api(f"/user-stat/{user_id}")

    async def get_affiliate(self, user_id):
        return await self._call_api(f"/affiliate/{user_id}")

    async def get_active_deals(self, user_id):
        return await self._call_api(f"/active-deals/{user_id}")

    async def get_active_deals_count(self, user_id):
        return (await self._call_api(f"/active-deals-count/{user_id}"))["count"]

    async def get_lots(self, user_id, t):
        return await self._call_api(f"/lots/{t}?user_id={user_id}")

    async def get_lot(self, identificator):
        return await self._call_api(f"/lot/{identificator}")

    async def update_lot(
        self,
        identificator,
        user_id,
        limit_from=None,
        limit_to=None,
        rate=None,
        coefficient=None,
        details=None,
        activity_status=None,
    ):
        data = {
            "identificator": identificator,
            "user_id": user_id,
            "limit_from": limit_from,
            "limit_to": limit_to,
            "rate": rate,
            "coefficient": coefficient,
            "details": details,
            "activity_status": activity_status,
        }
        return await self._call_api(f"/lot", method="patch", _json=data)

    async def delete_lot(self, identificator, user_id):
        data = {"identificator": identificator, "user_id": user_id}
        return await self._call_api(f"/lot", method="delete", _json=data)

    async def get_user_lots(self, user_id):
        return await self._call_api(f"/user-lots/{user_id}")

    async def get_broker_lots(self, user_id, t, broker):
        return await self._call_api(f"/broker-lots/{t}?broker={broker}&user_id={user_id}")

    async def get_active_promocodes_count(self, user_id):
        return (await self._call_api(f"/active-promocodes-count/{user_id}"))["count"]

    async def get_active_promocodes(self, user_id):
        return await self._call_api(f"/active-promocodes/{user_id}")

    async def activate_promocode(self, user_id, code):
        return await self._call_api(f"/promocode-activation", method="post", _json={"user_id": user_id, "code": code})

    async def create_promocode(self, user_id, activations, amount):
        return await self._call_api(
            f"/new-promocode",
            method="post",
            _json={"user_id": user_id, "activations": activations, "amount": str(amount)},
        )

    async def delete_promocode(self, user_id, promocode_id):
        return await self._call_api(
            f"/promocode", method="delete", _json={"user_id": user_id, "promocode_id": promocode_id}
        )

    async def get_rate(self, currency):
        return await self._call_api(f"/rate?currency={currency}")

    async def get_settings(self):
        return await self._call_api(f"/settings")

    async def get_withdraw_commission(self, amount):
        return await self._call_api(f"/commission?amount={amount}")

    async def get_currencies(self):
        return await self._call_api(f"/currencies")

    async def get_last_requisites(self, user_id, currency, broker):
        return await self._call_api(f"/last-requisites/{broker}?user_id={user_id}&currency={currency}")

    async def create_wallet_if_not_exists(self, user_id):
        return await self._call_api(f"/create-wallet-if-not-exists", method="post", _json={"user_id": user_id})

    async def get_brokers(self, currency=None):
        add_str = f"?currency={currency}" if currency is not None else ""
        return await self._call_api(f"/brokers{add_str}")

    async def is_user_exist(self, telegram_id):
        return (await self._call_api(f"/user-exists?telegram_id={telegram_id}"))["exists"]

    async def is_user_exist_nickname(self, nickname):
        return (await self._call_api(f"/user-exists/{nickname}"))["exists"]

    async def new_user(self, telegram_id, *, campaign=None, ref_code=None):
        return await self._call_api(
            f"/new-user?telegram_id={telegram_id}", method="post", _json={"ref_code": ref_code, "campaign": campaign}
        )

    async def create_lot(self, *, _type, limit_from, limit_to, broker, rate, coefficient=None, user_id):
        data = {
            "type": _type,
            "limit_from": limit_from,
            "limit_to": limit_to,
            "broker": broker,
            "rate": rate,
            "user_id": user_id,
        }
        if coefficient:
            data["coefficient"] = coefficient
        return await self._call_api(f"/new-lot", method="post", _json=data)

    async def create_deal(self, *, rate, lot_id, user_id, amount_currency, amount, requisite):
        data = {
            "lot_id": lot_id,
            "amount_currency": amount_currency,
            "amount": amount,
            "requisite": requisite,
            "rate": rate,
            "user_id": user_id,
        }
        return await self._call_api(f"/new-deal", method="post", _json=data)

    async def get_deal(self, deal_id, expand_email=False, with_merchant=False):
        endpoint = f"/deal/{deal_id}"
        if expand_email:
            endpoint += "?expand_email=1"
        if with_merchant:
            endpoint += "?with_merchant=1"
        return await self._call_api(endpoint)

    async def get_mask(self, deal_id):
        return (await self._call_api(f"/deal/{deal_id}/mask"))["mask"]

    async def set_mask(self, deal_id, mask):
        return await self._call_api(f"/deal/{deal_id}/mask", method="post", _json={'mask': mask})

    async def stop_deal(self, deal_id):
        return await self._call_api(f"/stop-deal", method="post", _json={"deal_id": deal_id})

    async def cancel_deal(self, user_id, deal_id):
        return await self._call_api(f"/cancel-deal", method="post", _json={"deal_id": deal_id, "user_id": user_id})

    async def update_deal_req(self, user_id, deal_id, req):
        return await self._call_api(
            f"/deal-requisite", method="patch", _json={"deal_id": deal_id, "user_id": user_id, "requisite": req}
        )

    async def update_deal_state(self, user_id, deal_id):
        return await self._call_api(f"/deal-state", method="patch", _json={"deal_id": deal_id, "user_id": user_id})

    async def send_crypto_wo_agreement(self, user_id, deal_id):
        return await self._call_api(
            f"/deal-confirmation-no-agreement", method="post", _json={"deal_id": deal_id, "user_id": user_id}
        )

    async def confirm_declined_fd_deal(self, user_id, deal_id):
        return await self._call_api(f"/fd-deal-confirm", method="post", _json={"deal_id": deal_id, "user_id": user_id})

    async def get_dispute(self, deal_id):
        return await self._call_api(f"/dispute/{deal_id}")

    async def create_dispute(self, user_id, deal_id):
        return await self._call_api(f"/new-dispute", method="post", _json={"user_id": user_id, "deal_id": deal_id})

    async def rate_user(self, rate_from, rate_to, deal_id, method):
        return await self._call_api(
            f"/user-rate",
            method="patch",
            _json={"from": rate_from, "to": rate_to, "method": method, "deal_id": deal_id},
        )

    async def new_usermessage(self, *, sender_id, receiver_id, message="", media_id=None):
        return await self._call_api(
            f"/new-usermessage",
            method="post",
            _json={"sender_id": sender_id, "receiver_id": receiver_id, "message": message, "media_id": media_id},
        )

    async def send_transaction(self, user_id, amount, address, with_proxy=False, token=None):
        return await self._call_api(
            f"/send-transaction",
            method="post",
            _json={
                "user_id": user_id,
                "amount": float(amount),
                "address": address,
                "with_proxy": with_proxy,
                "token": token,
            },
        )

    async def update_user(
        self, user_id, currency=None, is_deleted=None,
        is_verify=None, super_verify_only=None, is_baned=None,
        allow_sell=None, allow_sale_v2=None,
        sky_pay=None, allow_super_buy=None, lang=None,
        shadow_ban=None, apply_shadow_ban=None
    ):
        data = {
            "user_id": user_id,
            "currency": currency,
            "is_deleted": is_deleted,
            "is_verify": is_verify,
            "super_verify_only": super_verify_only,
            "allow_sell": allow_sell,
            "allow_sale_v2": allow_sale_v2,
            "is_baned": is_baned,
            "shadow_ban": shadow_ban,
            "apply_shadow_ban": apply_shadow_ban,
            "sky_pay": sky_pay,
            "allow_super_buy": allow_super_buy,
            "lang": lang
        }
        return await self._call_api(f"/user", method="patch", _json=data)

    async def change_balance(self, user_id, admin_id, amount, with_operation=False):
        data = {"to_user_id": user_id, "admin_id": admin_id, "amount": amount, "with_operation": with_operation}
        return await self._call_api(f"/balance", method="patch", _json=data)

    async def withdraw_from_payments_node(self, admin_id, address, amount):
        data = {
            "address": address,
            "admin_id": admin_id,
            "amount": amount,
        }
        return await self._call_api(f"/withdraw-from-payments-node", method="post", _json=data)

    async def change_frozen(self, user_id, admin_id, amount):
        data = {
            "to_user_id": user_id,
            "admin_id": admin_id,
            "amount": amount,
        }
        return await self._call_api(f"/frozen", method="patch", _json=data)

    async def set_frozen(self, user_id, admin_id, amount):
        data = {
            "to_user_id": user_id,
            "admin_id": admin_id,
            "amount": amount,
        }
        return await self._call_api(f"/frozen-fixed", method="patch", _json=data)

    async def set_balance(self, user_id, admin_id, amount):
        data = {
            "to_user_id": user_id,
            "admin_id": admin_id,
            "amount": amount,
        }
        return await self._call_api(f"/balance-fixed", method="patch", _json=data)

    async def create_campaign(self, admin_id, name):
        data = {
            "admin_id": admin_id,
            "name": name,
        }
        return await self._call_api(f"/campaigns", method="post", _json=data)

    async def reset_imbalance(self, admin_id):
        data = {
            "admin_id": admin_id,
        }
        return await self._call_api(f"/reset-imbalance", method="post", _json=data)

    async def get_frozen(self):
        return await self._call_api(f"/frozen-all")

    async def stop_withdraw(self):
        return await self._call_api(f"/change-withdraw-status", method="post")

    async def stop_fast_deal(self):
        return await self._call_api(f"/change-fast-deal-status", method="post")

    async def profit(self):
        return await self._call_api(f"/profit")

    async def finreport(self):
        return await self._call_api(f"/finreport")

    async def change_trading_status(self, user_id):
        return await self._call_api(f"/trading-status", method="patch", _json={"user_id": user_id})

    async def close_deal_admin(self, deal_id, winner):
        return await self._call_api(f"/close-deal-admin", method="post", _json={"winner": winner, "deal_id": deal_id})

    async def get_wallet(self, user_id):
        return await self._call_api(f"/wallet/{user_id}")

    async def deposit_rub(self, user_id):
        return await self._call_api(f"/deposit-rub", method="post", _json={'user_id': user_id})

    async def address_validation_check(self, address):
        return await self._call_api(f"/address-validation/{address}")

    async def is_web_bound(self, user_id):
        return await self._call_api(f"/bind-status/{user_id}")

    async def get_transit(self, user_id):
        return await self._call_api(f"/transit/{user_id}")

    async def get_reports(self, user_id):
        return await self._call_api(f"/reports/{user_id}")

    async def get_all_reports(self, t, from_date=None, to_date=None):
        params = f"?from={from_date}&to={to_date}" if from_date and to_date else ""
        return await self._call_api(f"/reports-all/{t}{params}")

    async def get_node_transaction(self, tx_hash):
        return await self._call_api(f"/node-transaction/{tx_hash}")

    async def message(self, *, message_id, text, telegram_id, bot):
        return await self._call_api(
            f"/message?telegram_id={telegram_id}",
            method="post",
            _json={"message_id": message_id, "text": text, "bot": bot},
        )

    async def error(self, *, text, telegram_id):
        return await self._call_api(f"/error", method="post", _json={"text": text, "telegram_id": telegram_id})

    async def upload_photo(self, user_id, photo, content_type):
        url = API_HOST + f"/user/{user_id}/media"
        if content_type:
            url += f'?content_type={content_type}'
        headers = {"Token": API_KEY}
        res = requests.post(url, files={"file": photo}, headers=headers)

        if res.status_code == 400:
            data = res.json()
            raise BadRequestError(data.get("detail", ""), 400)
        res.raise_for_status()
        return res.json()

    def send_transaction_sync(self, user_id, amount, address, with_proxy=False, token=None):
        url = API_HOST + "/send-transaction"
        headers = {"Token": API_KEY}
        res = requests.post(
            url,
            headers=headers,
            json={
                "user_id": user_id,
                "amount": float(amount),
                "address": address,
                "with_proxy": with_proxy,
                "token": token,
            },
        )
        res.raise_for_status()
        return res.json()


api = API()
