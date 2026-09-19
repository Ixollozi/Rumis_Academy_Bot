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
    set_limit = State()
    set_prices = State()
    set_result = State()
