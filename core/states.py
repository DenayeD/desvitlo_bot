from aiogram.fsm.state import State, StatesGroup

class BroadcastStates(StatesGroup):
    waiting_for_message = State()

class AddressStates(StatesGroup):
    waiting_for_new_name = State()
    waiting_for_new_queue = State()
    waiting_for_edit_name = State()
    waiting_for_edit_queue = State()

class ManualScheduleStates(StatesGroup):
    waiting_for_date = State()
    waiting_for_subqueue = State()
    waiting_for_guaranteed = State()
    waiting_for_possible = State()
    waiting_for_confirm = State()