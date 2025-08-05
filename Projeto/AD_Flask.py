from flask import Flask, request, jsonify
import pyodbc, json, httpx
from requests.exceptions import ReadTimeout

app = Flask(__name__)

DB_CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;DATABASE=AITest;"
    "UID=sa;PWD=*123456HAS*;"
    "TrustServerCertificate=yes;Encrypt=no;"
)
conn = pyodbc.connect(DB_CONN_STR)
cur = conn.cursor()
cur.execute("SELECT regras FROM AIModel ORDER BY id")
RULES_TEXT = "\n".join(r[0] for r in cur.fetchall())

LM_STUDIO_URL = "http://localhost:3120/v1/chat/completions"

client = httpx.Client(
    http2=True,
    timeout=httpx.Timeout(5.0, read=60.0),
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=10)
)

def generate_text(prompt: str,
                  model: str = "meta-llama/Llama-3.1-8B-Instruct-GGUF",
                  max_tokens: int = 512,
                  temperature: float = 0.0,
                  top_p: float = 1.0,
                  timeout: int = 60) -> dict:
    full_prompt = (
        "Você é um assistente que responde com um JSON contendo as chaves "
        "'mensagem' (texto curto) e 'viewID' (número). "
        "Baseie-se nas regras abaixo, no prompt e em elementos.\n\n"
        f"{RULES_TEXT}\n\n{prompt}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": full_prompt},
            {"role": "user",   "content": ""}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "stream": False
    }
    resp = client.post(LM_STUDIO_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    start = content.find("{")
    end = content.rfind("}") + 1
    return json.loads(content[start:end])

@app.route("/api/assist", methods=["POST"])
def assist():
    js = request.get_json()
    if not js or "pergunta" not in js or "elementos" not in js:
        return jsonify({"error": "Envie 'pergunta' e 'elementos'"}), 400
    pergunta = js["pergunta"]
    elementos = js["elementos"]
    prompt = (
        f"Pergunta: {pergunta}\n"
        "Elementos disponíveis:\n"
        + json.dumps(elementos, ensure_ascii=False)
    )
    try:
        resposta = generate_text(prompt)
    except ReadTimeout:
        return jsonify({"error": "Modelo demorou demais."}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(resposta)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
