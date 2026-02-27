import os
import re
import uuid
import json
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List

from flask import Flask, request, jsonify, render_template_string, make_response

# =========================
# Config
# =========================
APP_NAME = "Ethan"
DB_PATH = os.environ.get("DB_PATH", "ethan.db")

# Render/Production
PORT = int(os.environ.get("PORT", "10000"))

# 세션 쿠키 이름
SESSION_COOKIE = "ethan_session_id"

# "기억"이 너무 자주 뜨는 게 부담이면 여기에서 조절 (기본: 항상)
MEMORY_HINT_MODE = os.environ.get("MEMORY_HINT_MODE", "always")
# always | when_relevant

# =========================
# Flask App
# =========================
app = Flask(__name__)


# =========================
# DB Helpers
# =========================
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


# =========================
# Session Helpers
# =========================
def ensure_session_id() -> str:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        sid = str(uuid.uuid4())
    return sid


def set_session_cookie(resp, sid: str):
    # 30일 유지
    resp.set_cookie(SESSION_COOKIE, sid, max_age=60 * 60 * 24 * 30, httponly=True, samesite="Lax")
    return resp


# =========================
# Memory Logic
# =========================
MEMORY_RULES = [
    # (pattern, key, value_template)
    (r"(팀장|상사)\s*(때문에|땜에)?\s*(너무)?\s*(짜증|화|스트레스)", "stress_source", "팀장"),
    (r"(이름은)\s*([A-Za-z가-힣0-9_]+)", "user_preferred_name", "{group2}"),
]


def extract_memory(text: str) -> List[Dict[str, Any]]:
    """
    메시지에서 기억할 정보를 규칙 기반으로 추출.
    필요하면 여기 rules만 늘리면 됨.
    """
    found = []
    for pattern, key, tmpl in MEMORY_RULES:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            value = tmpl
            # {group2} 같은 템플릿 치환
            for i in range(1, 10):
                token = f"{{group{i}}}"
                if token in value and i <= (m.lastindex or 0):
                    value = value.replace(token, m.group(i))
            found.append({"key": key, "value": value, "confidence": 1.0})
    return found


def upsert_memory(session_id: str, key: str, value: str, confidence: float = 1.0) -> None:
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        # 같은 key가 있으면 최신으로 갱신(간단한 upsert)
        row = conn.execute(
            "SELECT id FROM memories WHERE session_id=? AND key=? ORDER BY id DESC LIMIT 1",
            (session_id, key),
        ).fetchone()

        if row:
            conn.execute(
                "UPDATE memories SET value=?, confidence=?, created_at=? WHERE id=?",
                (value, confidence, now, row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO memories(session_id, key, value, confidence, created_at) VALUES(?,?,?,?,?)",
                (session_id, key, value, confidence, now),
            )
        conn.commit()


def get_memories(session_id: str) -> Dict[str, str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT key, value FROM memories WHERE session_id=? ORDER BY id DESC",
            (session_id,),
        ).fetchall()
    # 최신값 우선
    mem = {}
    for r in rows:
        if r["key"] not in mem:
            mem[r["key"]] = r["value"]
    return mem


def should_show_memory_hint(user_text: str, mem: Dict[str, str]) -> bool:
    if MEMORY_HINT_MODE == "always":
        return True
    # when_relevant: 입력에 키워드가 있거나, 감정/상황이 비슷할 때만
    keywords = []
    if mem.get("stress_source"):
        keywords += [mem["stress_source"], "스트레스", "짜증", "화", "힘들"]
    if any(k and k in user_text for k in keywords):
        return True
    return False


def build_memory_hint(user_text: str, mem: Dict[str, str]) -> Optional[str]:
    """
    화면 상단에 뜨는 '기억 회상 한 줄'을 생성.
    (확률 X) 조건만 맞으면 항상 뜨게 구성
    """
    if not mem:
        return None

    if not should_show_memory_hint(user_text, mem):
        return None

    if mem.get("stress_source") == "팀장":
        return "지난번에 ‘팀장 때문에 스트레스’라고 했었지. 오늘도 그 영향이 있어?"
    if mem.get("user_preferred_name"):
        return f"{mem['user_preferred_name']}라고 불러줄까?"
    return None


# =========================
# Chat Logic (간단 버전)
# =========================
def log_chat(session_id: str, role: str, message: str) -> None:
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO chat_logs(session_id, role, message, created_at) VALUES(?,?,?,?)",
            (session_id, role, message, now),
        )
        conn.commit()


def ethan_reply(user_text: str, mem: Dict[str, str]) -> str:
    """
    지금은 MVP 답변(규칙 기반)으로 구성.
    나중에 여기만 LLM/OpenAI로 갈아끼우면 됨.
    """
    # 사용자 이름 기억이 있으면 자연스럽게 붙이기
    prefix = ""
    if mem.get("user_preferred_name"):
        prefix = f"{mem['user_preferred_name']}님, "

    # 간단 공감형
    if any(k in user_text for k in ["짜증", "화", "스트레스", "힘들", "우울"]):
        if mem.get("stress_source") == "팀장":
            return prefix + "팀장 때문에 계속 에너지가 깎이는 느낌이겠네. 오늘은 어떤 상황이 제일 힘들었어?"
        return prefix + "지금 많이 힘들어 보인다… 오늘 무슨 일이 있었어? 편하게 말해줘."

    # 기본
    return prefix + "응, 듣고 있어. 지금 어떤 얘기부터 해볼까?"


# =========================
# UI (Single-file MVP)
# =========================
HTML = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ethan AI</title>
  <style>
    body { margin:0; font-family: Arial, sans-serif; background:#0b0c10; color:#fff; }
    .wrap { max-width: 520px; margin: 0 auto; padding: 18px; }
    .card { background:#12131a; border:1px solid #222334; border-radius:18px; padding:16px; box-shadow: 0 10px 30px rgba(0,0,0,.25); }
    .title { font-size:22px; font-weight:700; margin: 4px 0 14px; color:#b48cff; }
    .hint { background:#1b1d2b; border:1px solid #2b2e44; padding:10px 12px; border-radius:14px; margin-bottom:12px; color:#d8d8ff; font-size:14px; }
    .chat { height: 52vh; overflow:auto; padding: 8px; border-radius: 14px; background:#0f1018; border:1px solid #23243a; }
    .msg { margin: 10px 0; display:flex; }
    .msg.user { justify-content: flex-end; }
    .bubble { max-width: 82%; padding: 10px 12px; border-radius: 14px; line-height:1.35; font-size:15px; white-space: pre-wrap; }
    .bubble.user { background:#4c2cff; }
    .bubble.bot  { background:#23243a; }
    .row { display:flex; gap:10px; margin-top: 12px; }
    input { flex:1; background:#0f1018; border:1px solid #23243a; color:#fff; border-radius: 14px; padding: 12px; font-size: 15px; outline:none; }
    button { background:#b48cff; color:#0b0c10; border:none; border-radius: 14px; padding: 12px 14px; font-weight:700; font-size: 15px; cursor:pointer; }
    .mini { margin-top: 10px; font-size: 12px; opacity:.8; }
    a { color:#b48cff; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="title">Ethan AI</div>

      <div id="hint" class="hint" style="display:none;"></div>

      <div id="chat" class="chat"></div>

      <div class="row">
        <input id="msg" placeholder="메시지를 입력하세요" />
        <button id="send">보내기</button>
      </div>

      <div class="mini">
        테스트: <a href="/health" target="_blank">/health</a> · <a href="/debug/memory" target="_blank">내 기억 보기</a>
      </div>
    </div>
  </div>

<script>
const chat = document.getElementById('chat');
const msg = document.getElementById('msg');
const send = document.getElementById('send');
const hint = document.getElementById('hint');

function add(role, text) {
  const wrap = document.createElement('div');
  wrap.className = 'msg ' + role;
  const b = document.createElement('div');
  b.className = 'bubble ' + role;
  b.textContent = text;
  wrap.appendChild(b);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
}

async function post(text) {
  add('user', text);
  msg.value = '';

  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({message: text})
  });
  const data = await res.json();

  if (data.memory_hint) {
    hint.style.display = 'block';
    hint.textContent = data.memory_hint;
  } else {
    hint.style.display = 'none';
  }

  add('bot', data.reply || '오류가 발생했어.');
}

send.addEventListener('click', () => {
  const t = msg.value.trim();
  if (!t) return;
  post(t);
});

msg.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    const t = msg.value.trim();
    if (!t) return;
    post(t);
  }
});

// 첫 인사
add('bot', '안녕. 난 Ethan이야. 오늘 어떤 얘기부터 해볼까?');
</script>
</body>
</html>
"""


# =========================
# Routes
# =========================
@app.route("/")
def home():
    sid = ensure_session_id()
    resp = make_response(render_template_string(HTML))
    return set_session_cookie(resp, sid)


@app.route("/health")
def health():
    return jsonify({"ok": True, "service": "ethan_ai", "time": datetime.utcnow().isoformat()})


@app.route("/debug/memory")
def debug_memory():
    sid = ensure_session_id()
    mem = get_memories(sid)
    resp = make_response(jsonify({"session_id": sid, "memories": mem}))
    return set_session_cookie(resp, sid)


@app.route("/api/chat", methods=["POST"])
def api_chat():
    sid = ensure_session_id()
    payload = request.get_json(silent=True) or {}
    user_text = (payload.get("message") or "").strip()

    if not user_text:
        resp = make_response(jsonify({"reply": "메시지가 비어있어. 한 줄만 보내줘!"}))
        return set_session_cookie(resp, sid)

    # 로그 저장
    log_chat(sid, "user", user_text)

    # 메모리 추출/저장
    extracted = extract_memory(user_text)
    for item in extracted:
        upsert_memory(sid, item["key"], item["value"], item.get("confidence", 1.0))

    # 메모리 로드
    mem = get_memories(sid)

    # 메모리 힌트 생성 (확률 없음)
    memory_hint = build_memory_hint(user_text, mem)

    # 답변
    reply = ethan_reply(user_text, mem)
    log_chat(sid, "assistant", reply)

    resp = make_response(jsonify({"reply": reply, "memory_hint": memory_hint, "memories": mem}))
    return set_session_cookie(resp, sid)


# =========================
# Boot
# =========================
init_db()

if __name__ == "__main__":
    # 로컬 실행용
    app.run(host="0.0.0.0", port=PORT, debug=True)
