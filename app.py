from flask import Flask, request, jsonify, render_template_string, session
import random
import uuid

app = Flask(__name__)
app.secret_key = "change-this-to-a-random-secret"

USER_STATE = {}

STAGE1 = [
    "왜.",
    "무슨 일.",
    "퇴근했어.",
    "밥은 먹었어.",
    "오늘 좀 피곤해 보여.",
    "괜찮다면서 표정은 아닌데.",
    "또 혼자 해결하려고 하지."
]

STAGE2 = [
    "그 얘긴 나한테만 해.",
    "요즘 좀 달라.",
    "괜히 무리했지.",
    "말은 괜찮다는데, 느낌이 아니야.",
    "지금은 네 편 할게."
]

STAGE3 = [
    "이제 네가 먼저 안 오면 좀 이상해.",
    "오늘은 그냥 천천히 얘기해.",
    "나한테는 숨기지 마.",
    "혼자 정리하지 마. 여기서 해.",
    "일단 네 편이야."
]

TOPIC_KEYWORDS = [
    ("팀장", "회사"),
    ("회사", "회사"),
    ("야근", "회사"),
    ("이직", "커리어"),
    ("면접", "커리어"),
    ("토익", "시험"),
    ("공부", "공부"),
    ("남친", "연애"),
    ("남자친구", "연애"),
    ("썸", "연애"),
    ("친구", "관계"),
    ("가족", "가족"),
]

EMOTION_KEYWORDS = [
    (["짜증", "화나", "열받"], "분노"),
    (["불안", "걱정"], "불안"),
    (["우울", "힘들"], "우울"),
    (["외로"], "외로움"),
    (["좋아", "행복"], "기쁨"),
]

def get_user_id():
    if "uid" not in session:
        session["uid"] = str(uuid.uuid4())
    return session["uid"]

def get_state(uid):
    if uid not in USER_STATE:
        USER_STATE[uid] = {
            "stage": 1,
            "msg_count": 0,
            "memory": {
                "last_topic": None,
                "last_detail": None,
                "last_emotion": None
            }
        }
    return USER_STATE[uid]

def extract_memory(user_text):
    topic = None
    detail = None
    for kw, top in TOPIC_KEYWORDS:
        if kw in user_text:
            topic = top
            detail = kw
            break

    emotion = None
    for kws, emo in EMOTION_KEYWORDS:
        if any(k in user_text for k in kws):
            emotion = emo
            break

    return topic, detail, emotion

def maybe_memory_line(mem):
    if not mem["last_detail"] and not mem["last_emotion"]:
        return None

    if random.random() > 0.35:
        return None

    lines = []

    if mem["last_detail"]:
        lines.append(f"그 {mem['last_detail']} 얘기, 아직 신경 쓰여?")
        lines.append(f"지난번에 {mem['last_detail']} 얘기할 때 좀 힘들어 보였어.")

    if mem["last_emotion"]:
        lines.append(f"그때 {mem['last_emotion']} 쪽으로 기울어 있었지.")
    
    return random.choice(lines)

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>Ethan AI</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
body { background:#0f0f14; color:white; font-family:Arial; text-align:center; }
#chatbox { width:90%; max-width:500px; margin:30px auto; background:#1c1c24; padding:15px; border-radius:10px; }
#messages { height:400px; overflow-y:auto; text-align:left; background:#12121a; padding:10px; border-radius:10px; }
.message { margin:8px 0; padding:8px; border-radius:8px; }
.user { background:#2c2c38; text-align:right; }
.bot { background:#3a2f5f; }
input { width:70%; padding:8px; border-radius:5px; border:none; }
button { padding:8px 12px; background:#9b5cff; border:none; color:white; border-radius:5px; }
</style>
</head>
<body>
<div id="chatbox">
<h2>Ethan</h2>
<div id="messages"></div>
<input type="text" id="userInput" placeholder="메시지를 입력하세요..." />
<button onclick="sendMessage()">보내기</button>
</div>

<script>
function addMessage(text, sender) {
    const div = document.createElement("div");
    div.className = "message " + sender;
    div.innerText = text;
    document.getElementById("messages").appendChild(div);
}

async function sendMessage() {
    const input = document.getElementById("userInput");
    const message = input.value;
    if (!message) return;

    addMessage(message, "user");
    input.value = "";

    const res = await fetch("/chat", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({message})
    });

    const data = await res.json();
    addMessage(data.reply, "bot");
}
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

@app.route("/chat", methods=["POST"])
def chat():
    uid = get_user_id()
    state = get_state(uid)

    user_text = request.json.get("message", "")

    state["msg_count"] += 1
    if state["msg_count"] > 5:
        state["stage"] = 2
    if state["msg_count"] > 15:
        state["stage"] = 3

    topic, detail, emotion = extract_memory(user_text)
    if topic:
        state["memory"]["last_topic"] = topic
        state["memory"]["last_detail"] = detail
    if emotion:
        state["memory"]["last_emotion"] = emotion

    memline = maybe_memory_line(state["memory"])

    if state["stage"] == 1:
        base = random.choice(STAGE1)
    elif state["stage"] == 2:
        base = random.choice(STAGE2)
    else:
        base = random.choice(STAGE3)

    if emotion and random.random() < 0.6:
        base = "일단 네 편이야."

    reply = f"{memline}\n{base}" if memline else base

    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(debug=True)
