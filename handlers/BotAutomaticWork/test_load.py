# peak_load_test.py
import asyncio
import time
from aiogram import Bot

BOT_TOKEN = "8277713159:AAHUN9FtoPX02G2bNaOUb3HMRuE4LcZRYbY"
CHAT_ID = -1003223396462     # чат для теста

async def send_load(bot: Bot, chat_id: int, rate: int, duration: int):
    """Отправить нагрузку с заданной частотой"""
    start = time.time()
    sent = 0
    for i in range(rate * duration):
        try:
            await bot.send_message(chat_id, f"Load test msg #{i+1}")
            sent += 1
        except Exception as e:
            print(f"❌ Error at {i+1}: {e}")
            break
        if (i + 1) % rate == 0:
            await asyncio.sleep(1)  # 1 секунда = rate сообщений
    took = time.time() - start
    print(f"✅ Sent {sent} in {took:.2f}s → {sent/took:.2f} msg/s")
    return sent, took

async def find_peak_load(bot: Bot, chat_id: int):
    """Найти пиковую нагрузку"""
    rates = [1, 2, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100]  # msg/s
    duration = 10  # секунд на каждую итерацию

    for rate in rates:
        print(f"\n🧪 Testing {rate} msg/s for {duration}s...")
        sent, took = await send_load(bot, chat_id, rate, duration)

        # Ждём 5 сек, чтобы очередь "успокоилась"
        await asyncio.sleep(5)

        # Проверь команду !актив ботов вручную или через API
        # Если очередь > 5с или ошибки > 0 — это предел
        print(f"📊 Result: {sent/took:.2f} msg/s achieved")

        # Если хочешь — можно автоматически читать !актив ботов через API
        # Но проще смотреть вручную

async def main():
    bot = Bot(token=BOT_TOKEN)
    try:
        await find_peak_load(bot, CHAT_ID)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())