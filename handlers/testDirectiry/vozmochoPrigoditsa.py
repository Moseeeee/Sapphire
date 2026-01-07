from aiogram import *
from aiogram.types import *
from aiogram.filters import *




dp = Router()



@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Создаем Inline-клавиатуру
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Вставить текст 1",
            switch_inline_query_current_chat="Это текст 1"
        )],
        [InlineKeyboardButton(
            text="Вставить текст 2",
            switch_inline_query_current_chat="Это текст 2"
        )]
    ])
    await message.answer("Нажмите кнопку, чтобы вставить текст:", reply_markup=keyboard)




@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Клавиатура удалена",
        reply_markup=types.ReplyKeyboardRemove()  # Передаем экземпляр ReplyKeyboardRemove
    )