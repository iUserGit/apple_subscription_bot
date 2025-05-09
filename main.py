from flask import Flask, request, jsonify
import os
import telegram

app = Flask(__name__)

# Получаем ключи из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Создаем экземпляр бота Telegram
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

# Обработчик для получения уведомлений от App Store
@app.route('/apple-webhook', methods=['POST'])
def apple_webhook():
    data = request.get_json()  # Получаем данные из POST-запроса
    
    if not data:
        return jsonify({'error': 'No data received'}), 400

    # Обработать данные уведомления
    # Это будет ваша логика для извлечения нужной информации
    # Например, мы просто отправим их в Telegram

    product = data.get('product_id', 'Неизвестный продукт')
    bundle_id = data.get('bundle_id', 'Неизвестный Bundle ID')
    version = data.get('version', 'Неизвестная версия')
    purchase_date = data.get('purchase_date', 'Неизвестная дата покупки')

    message = (
        f"> Изменён статус автообновления\n"
        f"📦 Продукт: {product}\n"
        f"📱 Bundle ID: {bundle_id}\n"
        f"📦 Версия приложения: {version}\n"
        f"🕒 Дата покупки: {purchase_date}"
    )

    # Отправка сообщения в Telegram
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    
    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
