from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def marriage_proposal_keyboard(user2_id: int, user1_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Согласен", callback_data=f"marry_accept:{user2_id}:{user1_id}"),
         InlineKeyboardButton(text="❌ Отказ", callback_data="marry_decline")]
    ])

def buy_action_keyboard(user_id: int, action_name: str, cost: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"💎 Купить за {cost} сапф.",
            callback_data=f"buy_act:{user_id}:{action_name}"
        )]
    ])