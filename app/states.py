from aiogram.fsm.state import State, StatesGroup


class OnboardingSG(StatesGroup):
    language = State()
    phone = State()


class BookingSG(StatesGroup):
    full_name = State()
    birth_date = State()
    exam_date = State()
    slot = State()
    confirm = State()


class AdminSG(StatesGroup):
    add_date = State()
    pick_slots = State()
    set_limit = State()
    set_prices = State()
    set_result = State()
    broadcast = State()
    add_admin = State()
    add_examiner = State()


class PaymentSG(StatesGroup):
    await_receipt = State()
