import os
import telegram
from flask import Flask, request, jsonify

app = Flask(__name__)

# Получаем ключи из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Создаем экземпляр бота Telegram
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

@app.route('/apple_webhook', methods=['POST'])
def apple_webhook():
    data = request.get_json()  # Получаем данные из POST-запроса

    # Логируем данные, чтобы увидеть, что приходит от Apple
    app.logger.info(f"Received data: {data}")

    if not data:
        app.logger.error('No data received!')
        return jsonify({'error': 'No data received'}), 400

    # Пример получения данных из payload (поменяйте на реальные поля из уведомлений)
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

    # Логируем сообщение, которое отправляем в Telegram
    app.logger.info(f"Sending message to Telegram: {message}")

    try:
        # Отправка сообщения в Telegram
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        app.logger.info('Message sent to Telegram successfully.')
    except Exception as e:
        app.logger.error(f"Failed to send message to Telegram: {e}")

    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
