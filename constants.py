from enum import IntEnum

from settings import SYMBOL


def create_const(name):
    return f"{name}_{SYMBOL}"


CONFIRM_POLICY = create_const("confirm_policy")
NEW_LOT_TYPE = create_const("new_lot_type")
NEW_LOT_BROKER = create_const("new_lot_broker")
NEW_LOT_RATE = create_const("new_lot_rate")
NEW_LOT_LIMITS = create_const("new_lot_limits")

ENTER_SUM_DEAL = create_const("enter_sum_deal")
ENTER_REQ_DEAL = create_const("enter_req_deal")
ENTER_REQ_DEAL_WHILE_ACCEPTING = create_const("enter_req_deal_while_accepting")
ENTER_REQ_DEAL_WHILE_ACCEPTING_CONFIRM = create_const("enter_req_deal_while_accepting_confirm")
CONFIRMATION_DEAL = create_const("confirmation_deal")

CONFIRMATION_FIAT_SENDING = create_const("confirmation_fiat_sending")
CONFIRMATION_CRYPTO_SENDING = create_const("confirmation_crypto_sending")
CRYPTO_SENDING_NO_CONFIRMATION = create_const("crypto_sending_no_confirmation")
CRYPTO_SENDING_FD_DECLINED_DEAL = create_const("crypto_sending_fd_declined")

CRYPTO_SENDING_FD_DECLINED_DEAL_WITH_REQ = create_const("crypto_sending_fd_declined_with_req")
CRYPTO_SENDING_FD_DECLINED_DEAL_WITH_REQ_CONFIRMATION = create_const("crypto_sending_fd_declined_with_req_confirmation")

CONFIRMATION_DECLINE_DEAL = create_const("confirmation_decline_deal")

CONFIRMATION_DELETE_LOT = create_const("confirmation_delete_lot")

CHOOSE_ADDRESS_WITHDRAW = create_const("choose_address_withdraw")
CHOOSE_AMOUNT_WITHDRAW = create_const("choose_amount_withdraw")
CONFIRMATION_WITHDRAW = create_const("confirmation_withdraw")

PROMOCODES_COUNT = create_const("choose_promocodes_count")
PROMOCODES_AMOUNT = create_const("choose_promocodes_amount")

ACTIVATE_PROMOCODE = create_const("activate_promocode")

WRITE_MESSAGE = create_const("write_message")

CHANGE_LIMITS = create_const("change_limits")
CHANGE_RATE = create_const("change_rate")
CHANGE_CONDITIONS = create_const("change_conditions")

DECLINE_DISPUTE = create_const("decline_dispute")

CONFIRM_START_WITHDRAW = create_const("confirm_withdraw")


class DealTypes(IntEnum):
    plain = 0
    fast = 1
    sky_pay = 2
    sky_sell = 3
    sky_sale_v2 = 4
    sky_pay_v2 = 5
