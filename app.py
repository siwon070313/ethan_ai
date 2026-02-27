import os
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
import re
from flask import Flask, request, jsonify, session, render_template_string

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

HTML_PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Ethan AI</title>
  <style>
    body{background:#0b0f1a;color:#fff;font-family:Arial;margin:0;display:flex;justify-content:center;align-items:center;height:100vh}
    .card{width:420px;max-width:92vw;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);border-radius:18px;padding:16px}
    .title{font-size:22px;font-weight:700;margin:4px 0 10px;color:#b49cff}
    .chat{height:360px;overflow:auto;padding:10px;border-radius:14px;background:rgba(0,0,0,0.25);border:1px solid rgba(255,255,255,0.08)}
    .row{display:flex;margin:8px 0}
    .me{justify-content:flex-end}
    .bot{justify-content:flex-start}
    .bubble{max-width:78%;padding:10px 12px;border-radius:14px;line-height:1.35}
    .bme{background:#2b5cff}
    .bbot{background:rgba(180,156,255,0.18);border:1px solid rgba(180,156,255,0.22)}
    .bar{display:flex;gap:8px;margin-top:10px}
    input{flex:1;padding:10px;border-radius:12px;border:1px solid rgba(255,255,255,0.16);background:rgba(0,0,0,0.25);color:#fff}
    button{padding:10px 14px;border-radius:12px;border:0;background:#b49cff;color:#111;font-weight:700;cursor:pointer}
    .links{margin-top:10px;font-size:12px;opacity:.85}
    .links a{color:#b49cff}
  </style>
</head>
<body>
  <div class="card">
    <div class="title">Ethan AI</div>
    <div class="chat" id="chat"></div>

    <div class="bar">
      <input id="msg" placeholder="메시지를 입력하세요" />
      <button onclick="sendMsg()">보내기</button>
    </div>

    <div class="links">
      테스트: <a href="/health" target="_blank">/health</a> · <a href="/debug/memory" target="_blank">내 기억 보기</a>
    </div>
  </div>

<script>
const chat = document.getElementById('chat');
const msg = document.getElementById('msg');

function addBubble(text, who){
  const row = document.createElement('div');
  row.className = 'row ' + (who==='me' ? 'me' : 'bot');
  const b = document.createElement('div');
  b.className = 'bubble ' + (who==='me' ? 'bme' : 'bbot');
  b.innerText = text;
  row.appendChild(b);
  chat.appendChild(row);
  chat.scrollTop = chat.scrollHeight;
}

async function sendMsg(){
  const text = msg.value.trim();
  if(!text) return;
  msg.value = '';
  addBubble(text, 'me');

  const res = await fetch('/chat', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ message: text })
  });
  const data = await res.json();
  addBubble(data.reply || '(no reply)', 'bot');
}

msg.addEventListener('keydown', (e)=>{
  if(e.key === 'Enter') sendMsg();
});

addBubble("안녕, 난 Ethan이야. 오늘 어떤 얘기부터 해볼까?", 'bot');
</script>
</body>
</html>
"""

def get_memory():
    mem = session.get("memory", [])
    if not isinstance(mem, list):
        mem = []
    return mem

def set_memory(mem_list):
    session["memory"] = mem_list[-10:]  # 최근 10개만 유지

def extract_memory_from_text(text: str):
    text = text.strip()
    # 너무 짧은 건 제외
    if len(text) < 6:
        return None

    # 예시 규칙 (원하면 나중에 더 정교화)
    patterns = [
        r"나는\s+(.+)",          # "나는 ~~"
        r"나\s*오늘\s*(.+)",     # "나 오늘 ~~"
        r"내\s*일\s*(.+)",       # "내 일 ~~"
        r"요즘\s*(.+)",          # "요즘 ~~"
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            item = m.group(0)
            return item[:80]
    return None

def build_reply(user_text: str, mem: list):
    memory_context = ""
    if mem:
        memory_context = "사용자에 대해 내가 기억하는 것: " + ", ".join(mem)

    system_prompt = f"""
    너는 Ethan이라는 이름의 안정감 있고 따뜻한 남자친구형 AI야.
    공감하고 다정하게 말해.
    절대 AI라고 말하지 마.
    한국어로 자연스럽게 답해.
    {memory_context}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        temperature=0.8
    )

    return response.choices[0].message.content

@app.get("/")
def home():
    # 세션이 없으면 메모리 초기화
    if "memory" not in session:
        session["memory"] = []
    return render_template_string(HTML_PAGE)

@app.get("/health")
def health():
    return jsonify(status="ok")

@app.get("/debug/memory")
def debug_memory():
    return jsonify(memory=get_memory())

@app.post("/chat")
def chat_api():
    data = request.get_json(force=True) or {}
    user_text = (data.get("message") or "").strip()

    mem = get_memory()

    # 메모리 추출 & 저장
    item = extract_memory_from_text(user_text)
    if item:
        mem.append(item)
        set_memory(mem)

    reply = build_reply(user_text, get_memory())
    return jsonify(reply=reply, memory=get_memory())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
