from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    choosing_service = State()
    description = State()
    materials = State()
    deadline = State()
    budget = State()
    comment = State()
    referral = State()
    confirm = State()
