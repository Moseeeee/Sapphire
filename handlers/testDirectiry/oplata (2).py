from aiogram import *
from aiogram.types import *
from flask import *
from handlers.BotAutomaticWork.universal_bot import bot

oplat = Router()

def create_oplata_link(user_id, price) -> str:
    oplata_link = f'https://pay.cloudtips.ru/p/3b388399?amount={price}&user_id={user_id}'
    return oplata_link


@oplat.message(F.text.lower().startswith('купить'))
async def oplatit(msg: Message):
    try:
        xz = msg.text.split(maxsplit=1)
        if len(xz) > 1:

            price_oplata = xz[1]
            user_id = msg.from_user.id
            price = price_oplata
            if int(price) < 50:
                await msg.reply('Нельзя купить валюту ниже 50 единиц.')
                return
            link = create_oplata_link(user_id, price)

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Оплатить", url=link)]
            ])

            await msg.answer(f'Вы хотите купить {price} единиц валюты.', reply_markup=keyboard)
        else:
            await msg.reply('❌ Что-то пошло не так, проверьте правильность написания команды.')
    except Exception as e:
        await msg.reply(f'Введите число правильно! Например: Купить 50')
        print(f'Произошла ошибка с оплатой:\n{e}')



app = Flask(__name__)

@app.route('/webhook/cloudtips', methods=['POST'])
def webhook():
    data = request.json
    user_id = data.get('user_id')
    price = data.get('amount')
    status = data.get('status')

    if status == "success":
        bot.send_message(chat_id=user_id, text='🥳')
        return jsonify({"status": "ok"})
    return jsonify({"status": "false"})