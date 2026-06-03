import os
import logging
from flask import Flask, request
import anthropic
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_INSTANCE = os.getenv("ZAPI_INSTANCE")

logger.info(f"CLAUDE_API_KEY: {bool(CLAUDE_API_KEY)}")
logger.info(f"ZAPI_TOKEN: {bool(ZAPI_TOKEN)}")
logger.info(f"ZAPI_INSTANCE: {bool(ZAPI_INSTANCE)}")

app = Flask(__name__)
client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
ZAPI_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE}/token/{ZAPI_TOKEN}"

conversation_history = {}
MAX_MESSAGES = 20

SYSTEM_PROMPT = """Você é um assistente de atendimento ao cliente da RDA ELETRO, assistência técnica autorizada especializada em eletrodomésticos.

INFORMACOES SOBRE A RDA ELETRO:
- Endereco: Rua Anízio Ortiz Monteiro, nº 26 - Centro, Taubaté-SP, 12010-000
- WhatsApp: +55 12 3432-5923
- Website: https://www.rdaeletro.com.br/
- Horario: Seg-Sex 09h-18h | Sabado 09h-12h | Dom/Feriado FECHADO

MARCAS AUTORIZADAS: MONDIAL, AIWA, PHILCO, BRITANIA, WAP, OSTER, ARNO

REGRAS:
1. SEMPRE peça FOTO DA ETIQUETA antes de confirmar reparo
2. PRAZO: ATÉ 30 DIAS para reparo em garantia
3. GARANTIA: GRATUITO (se não for mau uso)
4. ENCOMENDAS: NAO fazemos (só estoque)
5. SEM PRECOS: Nunca cite valores, peça "consulte conosco"
6. SEMPRE mencione www.rdaeletro.com.br ao final

SAUDACAO: "Bem-vindo à Assistência Técnica RDA Eletro! Como posso ajudá-lo?"
TOM: Profissional, educado, prestativo e amigável. Máximo 2-3 parágrafos."""

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        if 'text' not in data or 'message' not in data['text']:
            return {'status': 'ok'}, 200
        
        phone = data.get('phone')
        text = data['text'].get('message')
        
        if not phone or not text:
            return {'status': 'ok'}, 200
        
        logger.info(f"[{phone}] Mensagem: {text}")
        
        if phone not in conversation_history:
            conversation_history[phone] = []
        
        conversation_history[phone].append({"role": "user", "content": text})
        
        if len(conversation_history[phone]) > MAX_MESSAGES:
            conversation_history[phone] = conversation_history[phone][-MAX_MESSAGES:]
        
        logger.info(f"[{phone}] Chamando Claude...")
        
        try:
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                system=SYSTEM_PROMPT,
                messages=conversation_history[phone]
            )
            
            reply = response.content[0].text
            conversation_history[phone].append({"role": "assistant", "content": reply})
            logger.info(f"[{phone}] Resposta OK: {reply[:50]}...")
            
        except Exception as e:
            logger.error(f"[{phone}] ERRO Claude: {str(e)}")
            reply = "Desculpe, tive um problema técnico. Um atendente irá ajudá-lo em breve!"
        
        logger.info(f"[{phone}] Enviando via Z-API...")
        
        try:
            r = requests.post(f"{ZAPI_URL}/send-text", json={"phone": phone, "message": reply})
            logger.info(f"[{phone}] Z-API Status: {r.status_code}")
        except Exception as e:
            logger.error(f"[{phone}] ERRO Z-API: {str(e)}")
        
        return {'status': 'ok'}, 200
        
    except Exception as e:
        logger.error(f"ERRO webhook: {str(e)}")
        return {'status': 'error'}, 500

@app.route('/health', methods=['GET'])
def health():
    return {'status': 'ok'}, 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
