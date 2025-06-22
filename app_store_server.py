import base64
import json
import os

import requests
from authlib.jws import verify
from authlib.jose.errors import JoseError
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import padding
from flask import Flask, jsonify, request

# Загрузка переменных окружения для production-среды
# В production следует использовать переменные окружения для хранения чувствительных данных.
# Например, bundle ID и environment для дополнительной проверки.
# BUNDLE_ID = os.environ.get("APP_BUNDLE_ID")
# APP_ENVIRONMENT = os.environ.get("APP_ENVIRONMENT") # "Production" or "Sandbox"
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

app = Flask(__name__)

# Словари для перевода кодов уведомлений в понятный текст
NOTIFICATION_TYPE_MAP = {
    "CONSUMPTION_REQUEST": "Запрос информации о потреблении",
    "DID_CHANGE_RENEWAL_PREF": "Изменение настроек автопродления",
    "DID_CHANGE_RENEWAL_STATUS": "Изменение статуса подписки",
    "DID_FAIL_TO_RENEW": "Ошибка продления подписки",
    "DID_RENEW": "Успешное продление подписки",
    "EXPIRED": "Подписка истекла",
    "GRACE_PERIOD_EXPIRED": "Льготный период истек",
    "OFFER_REDEEMED": "Активировано специальное предложение",
    "PRICE_INCREASE": "Повышение цены на подписку",
    "REFUND": "Оформлен возврат средств",
    "REFUND_DECLINED": "В возврате средств отказано",
    "REFUND_REVERSED": "Возврат средств был отменен",
    "REVOCATION": "Транзакция отозвана Apple",
    "SUBSCRIBED": "Оформлена новая подписка",
    "TEST": "Тестовое уведомление от Apple",
}

SUBTYPE_MAP = {
    "INITIAL_BUY": "Первая покупка",
    "RESUBSCRIBE": "Повторная подписка",
    "DOWNGRADE": "Понижение плана",
    "UPGRADE": "Повышение плана",
    "AUTO_RENEW_ENABLED": "Автопродление включено",
    "AUTO_RENEW_DISABLED": "Автопродление отключено",
    "VOLUNTARY": "Добровольная отмена",
    "BILLING_RETRY": "Ошибка оплаты",
    "PRICE_INCREASE": "Несогласие с повышением цены",
    "PRODUCT_NOT_FOR_SALE": "Продукт снят с продажи",
    "PENDING": "Ожидается согласие пользователя",
    "ACCEPTED": "Пользователь согласился",
}

def escape_markdown(text):
    """Экранирует специальные символы для MarkdownV2 в Telegram."""
    if not text:
        return ''
    text = str(text)
    # Спецсимволы в MarkdownV2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return "".join(['\\' + char if char in escape_chars else char for char in text])

# URL для загрузки корневого сертификата Apple.
# Рекомендуется кэшировать его, чтобы не загружать при каждом запуске.
APPLE_ROOT_CA_G3_URL = "https://www.apple.com/certificateauthority/AppleRootCA-G3.cer"
apple_root_ca_g3_cert = None

def download_apple_root_ca_cert():
    """Загружает и парсит корневой сертификат Apple."""
    global apple_root_ca_g3_cert
    try:
        response = requests.get(APPLE_ROOT_CA_G3_URL, timeout=10)
        response.raise_for_status()
        apple_root_ca_g3_cert = x509.load_der_x509_certificate(response.content, default_backend())
        print("Apple Root CA G3 certificate downloaded successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Failed to download Apple Root CA G3 certificate: {e}")
    except Exception as e:
        print(f"Failed to parse Apple Root CA G3 certificate: {e}")


def send_telegram_message(message):
    """Отправляет отформатированное сообщение в чат Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram bot token or chat ID is not configured. Skipping message sending.")
        return

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'MarkdownV2'  # Используем Markdown для форматирования
    }
    try:
        response = requests.post(api_url, json=payload, timeout=10)
        if response.status_code == 200:
            print("Notification successfully sent to Telegram.")
        else:
            print(f"Failed to send notification to Telegram. Status: {response.status_code}, Response: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending message to Telegram: {e}")


def verify_certificate_chain(cert_chain_base64, root_ca_cert):
    """
    Проверяет цепочку сертификатов из JWS-заголовка.
    Цепочка состоит из конечного сертификата и промежуточного.
    Проверяем, что промежуточный подписан корневым (доверенным),
    а конечный - промежуточным.
    """
    if not root_ca_cert:
        return False, "Root CA certificate is not available."

    try:
        decoded_certs = [base64.b64decode(cert_str) for cert_str in cert_chain_base64]
        certs = [x509.load_der_x509_certificate(cert_bytes, default_backend()) for cert_bytes in decoded_certs]

        if len(certs) < 2:
            return False, "Certificate chain must contain at least a leaf and an intermediate certificate."

        leaf_cert = certs[0]
        intermediate_cert = certs[1]

        # 1. Проверяем подпись промежуточного сертификата корневым
        root_ca_cert.public_key().verify(
            intermediate_cert.signature,
            intermediate_cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            intermediate_cert.signature_hash_algorithm,
        )

        # 2. Проверяем подпись конечного сертификата промежуточным
        intermediate_cert.public_key().verify(
            leaf_cert.signature,
            leaf_cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            leaf_cert.signature_hash_algorithm,
        )
        
        # TODO: Добавить другие проверки (срок действия, отзыв и т.д.)
        #
        # from datetime import datetime
        # now = datetime.utcnow()
        # if not (leaf_cert.not_valid_before <= now <= leaf_cert.not_valid_after):
        #     return False, "Leaf certificate is expired or not yet valid."
        # if not (intermediate_cert.not_valid_before <= now <= intermediate_cert.not_valid_after):
        #     return False, "Intermediate certificate is expired or not yet valid."


        return True, "Certificate chain is valid."

    except Exception as e:
        return False, f"Certificate chain validation failed: {e}"


def format_notification_for_telegram(decoded_payload, transaction_info):
    """Форматирует полезную нагрузку уведомления в читаемое сообщение для Telegram."""
    notification_type = decoded_payload.get('notificationType')
    subtype = decoded_payload.get('subtype')
    data = decoded_payload.get('data', {})

    readable_type = NOTIFICATION_TYPE_MAP.get(notification_type, notification_type)
    readable_subtype = SUBTYPE_MAP.get(subtype, subtype) if subtype else None

    # Извлекаем данные из расшифрованной транзакции
    transaction_id = transaction_info.get('transactionId')
    product_id = transaction_info.get('productId')
    purchase_date_ms = transaction_info.get('purchaseDate')

    # Извлекаем данные из основной полезной нагрузки
    app_account_token = data.get('appAccountToken') # UUID пользователя, если вы его устанавливаете
    environment = data.get('environment', 'N/A').capitalize()

    # Конвертируем дату
    purchase_date_str = None
    if purchase_date_ms:
        from datetime import datetime
        dt_object = datetime.fromtimestamp(purchase_date_ms / 1000)
        purchase_date_str = dt_object.strftime('%d.%m.%Y %H:%M:%S UTC')

    # Собираем сообщение
    title = f"🔔 *{escape_markdown(readable_type)}*"
    lines = [title]

    if readable_subtype:
        lines.append(f"*{escape_markdown('Детали')}:* `{escape_markdown(readable_subtype)}`")
    
    lines.append(f"*{escape_markdown('Окружение')}:* `{escape_markdown(environment)}`")

    if product_id:
        lines.append(f"*{escape_markdown('ID продукта')}:* `{escape_markdown(product_id)}`")
    if transaction_id:
        lines.append(f"*{escape_markdown('ID транзакции')}:* `{escape_markdown(transaction_id)}`")
    if purchase_date_str:
        lines.append(f"*{escape_markdown('Дата покупки')}:* `{escape_markdown(purchase_date_str)}`")
    if app_account_token:
        lines.append(f"*{escape_markdown('Токен пользователя')}:* `{escape_markdown(app_account_token)}`")
    
    return "\n\n".join(lines)


@app.route('/apple_webhook', methods=['POST'])
def handle_app_store_notification():
    """Обрабатывает входящие уведомления от App Store."""
    if not request.is_json:
        return jsonify({'status': 'error', 'message': 'Request must be JSON.'}), 400

    data = request.get_json()
    signed_payload = data.get('signedPayload')

    if not signed_payload:
        return jsonify({'status': 'error', 'message': 'Missing signedPayload.'}), 400

    try:
        # Декодируем заголовок JWS, чтобы получить цепочку сертификатов 'x5c'
        header_b64, _, _ = signed_payload.split('.', 2)
        header_json = base64.urlsafe_b64decode(header_b64 + '==').decode('utf-8')
        header = json.loads(header_json)
        
        if 'x5c' not in header:
            return jsonify({'status': 'error', 'message': 'x5c header not found in JWS.'}), 400

        cert_chain = header['x5c']
        
        # 1. Проверяем цепочку сертификатов
        is_chain_valid, chain_error = verify_certificate_chain(cert_chain, apple_root_ca_g3_cert)
        if not is_chain_valid:
            print(f"Certificate chain validation failed: {chain_error}")
            return jsonify({'status': 'error', 'message': f'Certificate chain validation failed: {chain_error}'}), 400

        # 2. Извлекаем публичный ключ из конечного сертификата
        leaf_cert_bytes = base64.b64decode(cert_chain[0])
        leaf_cert = x509.load_der_x509_certificate(leaf_cert_bytes, default_backend())
        public_key = leaf_cert.public_key()

        # 3. Проверяем подпись JWS
        # Apple использует алгоритм ES256
        payload_bytes = verify(signed_payload.encode('utf-8'), public_key, header)
        decoded_payload = json.loads(payload_bytes)

        # На этом этапе уведомление считается проверенным.
        # Теперь расшифруем вложенную информацию о транзакции.
        transaction_info = {}
        notification_data = decoded_payload.get('data', {})
        if notification_data and notification_data.get('signedTransactionInfo'):
            try:
                signed_transaction_info = notification_data['signedTransactionInfo']
                # Для проверки вложенного JWS нужно передать алгоритм, т.к. в его заголовке он отсутствует
                transaction_payload_bytes = verify(signed_transaction_info.encode('utf-8'), public_key, {'alg': 'ES256'})
                transaction_info = json.loads(transaction_payload_bytes)
            except JoseError as e:
                print(f"Failed to decode signedTransactionInfo: {e}")
            except Exception as e:
                print(f"An unexpected error occurred while decoding transaction info: {e}")

        # Обрабатываем полезную нагрузку
        notification_type = decoded_payload.get('notificationType')
        subtype = decoded_payload.get('subtype')
        
        print("---")
        print(f"✅ Received and verified notification:")
        print(f"  Type: {notification_type}")
        print(f"  Subtype: {subtype}")
        print("---")
        
        # Форматируем и отправляем сообщение в Telegram
        try:
            message_to_telegram = format_notification_for_telegram(decoded_payload, transaction_info)
            send_telegram_message(message_to_telegram)
        except Exception as e:
            print(f"Error formatting message for Telegram: {e}")

        return jsonify({'status': 'success'}), 200

    except JoseError as e:
        print(f"JWS validation error: {e}")
        return jsonify({'status': 'error', 'message': f'JWS validation error: {e}'}), 400
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({'status': 'error', 'message': f'An unexpected error occurred: {e}'}), 500


if __name__ == '__main__':
    download_apple_root_ca_cert()
    if apple_root_ca_g3_cert is None:
        print("Could not start server due to missing Apple Root CA certificate.")
    else:
        # Для production используйте Gunicorn или другой WSGI сервер.
        # Пример: gunicorn --bind 0.0.0.0:8000 app_store_server:app
        app.run(port=5000, debug=True) 
