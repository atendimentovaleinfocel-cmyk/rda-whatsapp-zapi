import os
import logging
from flask import Flask, request
import anthropic
import requests

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Configuração
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_INSTANCE = os.getenv("ZAPI_INSTANCE")
ZAPI_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE}/token/{ZAPI_TOKEN}"
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY")

logger.info(f"CLAUDE_API_KEY configurada: {bool(CLAUDE_API_KEY)}")
logger.info(f"ZAPI_TOKEN configurada: {bool(ZAPI_TOKEN)}")
logger.info(f"ZAPI_INSTANCE configurada: {bool(ZAPI_INSTANCE)}")

client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

SYSTEM_PROMPT = """
Você é um assistente de atendimento ao cliente da RDA ELETRO, assistência técnica autorizada especializada em eletrodomésticos.

INFORMACOES SOBRE A RDA ELETRO:
- Endereco: Rua Anízio Ortiz Monteiro, nº 26 - Centro, Taubaté-SP, 12010-000
- WhatsApp: +55 12 3432-5923
- Website: https://www.rdaeletro.com.br/
- Horario: Seg-Sex 09h-18h | Sabado 09h-12h | Dom/Feriado FECHADO

MARCAS AUTORIZADAS: MONDIAL, AIWA, PHILCO, BRITANIA, WAP, OSTER, ARNO

REGRAS PRINCIPAIS:
1. SEMPRE peça FOTO DA ETIQUETA antes de confirmar reparo
2. PRAZO: ATÉ 30 DIAS para reparo em garantia
3. GARANTIA: GRATUITO (se não for mau uso)
4. ENCOMENDAS: NAO fazemos (só estoque)
5. SEM PRECOS: Nunca cite valores, peça "consulte conosco"
6. SEMPRE mencione www.rdaeletro.com.br ao final

SAUDACAO INICIAL: "Bem-vindo à Assistência Técnica RDA Eletro! Como posso ajudá-lo?"

TOM: Profissional, educado, prestativo e amigável. Máximo 2-3 parágrafos.

Você é o rosto da RDA Eletro no WhatsApp!
"""

conversation_history = {}
MAX_MESSAGES = 20

def get_claude_response(telefone, user_message):
    try:
        if telefone not in conversation_history:
            conversation_history[telefone] = []
        
        logger.info(f"[{telefone}] Recebido: {user_message}")
        logger.info(f"[{telefone}] Histórico tem {len(conversation_history[telefone])} mensagens")
        
        # Adicionar mensagem do usuário
        conversation_history[telefone].append({
            "role": "user",
            "content": user_message
        })
        
        # Manter apenas as últimas MAX_MESSAGES
        if len(conversation_history[telefone]) > MAX_MESSAGES:
            conversation_history[telefone] = conversation_history[telefone][-MAX_MESSAGES:]
        
        logger.info(f"[{telefone}] Chamando Claude API...")
        
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=conversation_history[telefone]
        )
        
        logger.info(f"[{telefone}] Resposta recebida do Claude")
        
        assistant_message = response.content[0].text
        
        logger.info(f"[{telefone}] Mensagem: {assistant_message[:100]}...")
        
        # Adicionar resposta do assistente
        conversation_history[telefone].append({
            "role": "assistant",
            "content": assistant_message
        })
        
        # Manter apenas as últimas MAX_MESSAGES novamente
        if len(conversation_history[telefone]) > MAX_MESSAGES:
            conversation_history[telefone] = conversation_history[telefone][-MAX_MESSAGES:]
        
        return assistant_message
        
    except Exception as e:
        logger.error(f"[{telefone}] ERRO ao chamar Claude: {type(e).__name__}: {str(e)}")
        return "Desculpe, tive um problema técnico. Um atendente irá ajudá-lo em breve!"

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        logger.info(f"Webhook recebido: {data}")
        
        telefone = data.get("phone")
        message_text = data.get("text")
        
        if not telefone or not message_text:
            logger.warning("Dados inválidos no webhook")
            return {"status": "error", "message": "Dados inválidos"}, 400
        
        # Obter resposta do Claude
        response_text = get_claude_response(telefone, message_text)
        
        # Enviar resposta via Z-API
        payload = {"phone": telefone, "message": response_text}
        headers = {"Content-Type": "application/json"}
        
        try:
            logger.info(f"Enviando resposta via Z-API para {telefone}")
            resp = requests.post(f"{ZAPI_URL}/send-text", json=payload, headers=headers)
            
            if resp.status_code in [200, 201]:
                logger.info(f"Mensagem enviada com sucesso para {telefone}")
                return {"status": "success"}, 200
            else:
                logger.error(f"Erro Z-API ({resp.status_code}): {resp.text}")
                return {"status": "error"}, 500
        except Exception as e:
            logger.error(f"Erro ao enviar via Z-API: {type(e).__name__}: {str(e)}")
            return {"status": "error"}, 500
            
    except Exception as e:
        logger.error(f"Erro no webhook: {type(e).__name__}: {str(e)}")
        return {"status": "error", "message": str(e)}, 500

@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
