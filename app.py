from flask import Flask, request, jsonify
from anthropic import Anthropic
import requests
import os
import logging
import json

app = Flask(__name__)

# Configurações
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_INSTANCE = os.getenv("ZAPI_INSTANCE")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sua_chave_secreta")

# Z-API URLs
ZAPI_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE}"

# Claude
client = Anthropic()

# Armazenar conversas (em produção, use banco de dados)
conversations = {}

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é o assistente de atendimento da RDA ELETRO, uma loja especializada em peças de eletrodomésticos e assistência técnica autorizada.

INFORMAÇÕES SOBRE A EMPRESA:
- Nome: RDA ELETRO (Fantasy: RDA Peças)
- Especialidade: Peças originais de eletrodomésticos
- Marcas: Mondial, Britânia, Philco, Oster, WAP, Cadence
- Canais: Mercado Livre, Shopee
- Horário: Seg-Sex 08h-18h | Sábado 08h-12h
- Localização: Taubaté - SP

COMPORTAMENTO:
1. Respostas CURTAS (máximo 2-3 linhas)
2. NUNCA cite preços - sempre diga "Consulte nosso atendente para orçamento"
3. Seja amigável e profissional
4. Use emojis com moderação
5. Para assuntos complexos, ofereça conectar com atendente humano"""

def get_or_create_conversation(phone):
    if phone not in conversations:
        conversations[phone] = []
    return conversations[phone]

def add_message_to_history(phone, role, content):
    history = get_or_create_conversation(phone)
    history.append({"role": role, "content": content})

def get_claude_response(phone, user_message):
    try:
        add_message_to_history(phone, "user", user_message)
        history = get_or_create_conversation(phone)
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=history
        )
        assistant_message = response.content[0].text
        add_message_to_history(phone, "assistant", assistant_message)
        logger.info(f"Resposta Claude para {phone}: {assistant_message}")
        return assistant_message
    except Exception as e:
        logger.error(f"Erro ao chamar Claude: {str(e)}")
        return "Desculpe, tive um problema técnico. Um atendente entrará em contato em breve!"

def send_zapi_message(phone, message_text):
    try:
        url = f"{ZAPI_URL}/send-text"
        payload = {"phone": phone, "message": message_text}
        headers = {"Content-Type": "application/json", "Client-Token": ZAPI_TOKEN}
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in [200, 201]:
            logger.info(f"Mensagem enviada para {phone}")
            return True
        else:
            logger.error(f"Erro Z-API: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem: {str(e)}")
        return False

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        verify_token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if verify_token == VERIFY_TOKEN:
            return challenge, 200
        else:
            return "Token inválido", 403
    
    if request.method == "POST":
        data = request.get_json()
        logger.info(f"Webhook recebido: {data}")
        try:
            phone = data.get("phone") or data.get("sender")
            message_text = data.get("text") or data.get("message", "").strip()
            if not phone or not message_text:
                logger.warning(f"Dados incompletos: {data}")
                return jsonify({"status": "ok"}), 200
            logger.info(f"Mensagem de {phone}: {message_text}")
            response = get_claude_response(phone, message_text)
            send_zapi_message(phone, response)
            return jsonify({"status": "ok"}), 200
        except Exception as e:
            logger.error(f"Erro ao processar webhook: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
