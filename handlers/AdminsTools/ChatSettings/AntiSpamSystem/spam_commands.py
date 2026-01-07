import asyncio
from aiogram.types import Message


async def delete_ref_message(msg: Message):
    """Удаляет сообщение с реф-ссылкой и отправляет предупреждение"""
    try:
        # Удаляем сообщение
        await msg.delete()

        # Отправляем предупреждение пользователю
        warning_text = (
            "⚠️ <b>Внимание!</b>\n\n"
            "Сообщения с реферальными или инвайт-ссылками запрещены в этом чате.\n"
            "Пожалуйста, не публикуйте подобные ссылки."
        )

        warning_msg = await msg.answer(warning_text)

        # Удаляем предупреждение через 10 секунд
        await asyncio.sleep(10)
        await warning_msg.delete()

    except Exception as e:
        print(f"Ошибка при удалении сообщения с реф-ссылкой: {e}")