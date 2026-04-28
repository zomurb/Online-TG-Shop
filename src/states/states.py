from aiogram.fsm.state import StatesGroup, State

class AdminAddProductStates(StatesGroup):
    category = State()
    media = State()
    description = State()
    price = State()
    quantity = State()

class AdminDeleteProductStates(StatesGroup):
    select_product = State()
    confirm = State()

class AdminAddUserStates(StatesGroup):
    username = State()

class AdminPromoStates(StatesGroup):
    code = State()
    kind = State()
    amount = State()
    expires = State()

class AdminOrderStates(StatesGroup):
    select_order = State()
    change_status = State()

class AdminBroadcastStates(StatesGroup):
    content = State()

class AdminEditProductStates(StatesGroup):
    select_product = State()
    select_field = State()
    new_value = State()

class OrderStates(StatesGroup):
    wait_custom_city = State()  
    wait_phone = State() 
    wait_city = State()
    wait_comment = State()
    wait_promo = State()

class SearchStates(StatesGroup):
    waiting_for_query = State()
