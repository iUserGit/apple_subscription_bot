import os
import json
import base64
import hmac
import hashlib
import asyncio
import telegram
import requests

from quart import Quart, request, jsonify
import jwt
from jwt import InvalidTokenError

app = Quart(__name__)

# Получаем переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Telegram бот
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

# Получаем публичный ключ Apple из JWK по KID
def get_apple_public_key(kid):
    try:
        response = requests.get("https://api.storekit.itunes.apple.com/in-app/receipt/publicKey")
        jwks = response.json().get("keys", [])

        for jwk in jwks:
            if jwk["kid"] == kid:
                return jwt.algorithms.ECAlgorithm.from_jwk(json.dumps(jwk))

        raise Exception("Apple public key not found for kid: " + kid)
    except Exception as e:
        app.logger.error(f"Failed to fetch Apple public key: {e}")
        raise

@app.route("/")
async def index():
    return "Apple webhook server is running!", 200

@app.route("/apple_webhook", methods=["POST"])
async def apple_webhook():
    data = await request.get_json()

    if not data:
        app.logger.error("No data received!")
        return jsonify({"error": "No data received"}), 400

    signed_payload = data.get("signedPayload")

    if not signed_payload:
        app.logger.error("Missing signedPayload")
        return jsonify({"error": "Missing signedPayload"}), 400

    try:
        unverified_headers = jwt.get_unverified_header(signed_payload)
        kid = unverified_headers.get("kid")
        public_key = get_apple_public_key(kid)

        decoded = jwt.decode(
            signed_payload,
            key=public_key,
            algorithms=["ES256"],
            options={"verify_exp": False}  # отключаем проверку срока действия
        )

        app.logger.info(f"Decoded payload: {json.dumps(decoded, indent=2)}")

    except InvalidTokenError as e:
        app.logger.error(f"JWT decode error: {e}")
        return jsonify({"error": "Invalid token"}), 400
    except Exception as e:
        app.logger.error(f"General error decoding JWT: {e}")
        return jsonify({"error": "JWT processing failed"}), 400

    # Пример данных из payload
    notification_type = decoded.get("notificationType", "unknown")
    subtype = decoded.get("subtype", "none")
    bundle_id = decoded.get("data", {}).get("bundleId", "unknown")
    product_id = decoded.get("data", {}).get("productId", "unknown")
    purchase_date = decoded.get("data", {}).get("purchaseDate", "unknown")

    message = (
        f"🔔 Получено уведомление от Apple\n"
        f"📦 Тип уведомления: {notification_type} ({subtype})\n"
        f"📱 Bundle ID: {bundle_id}\n"
        f"🛒 Продукт: {product_id}\n"
        f"🕒 Дата покупки: {purchase_date}"
    )

    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        app.logger.info("Message sent to Telegram successfully.")
    except Exception as e:
        app.logger.error(f"Failed to send message to Telegram: {e}")

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
