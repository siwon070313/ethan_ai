from flask import Flask, render_template_string

app = Flask(__name__)

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Ethan AI</title>
    <style>
        body {
            background-color: #0f0f14;
            color: white;
            font-family: Arial, sans-serif;
            text-align: center;
            padding-top: 100px;
        }
        .box {
            background: #1c1c24;
            padding: 40px;
            border-radius: 12px;
            display: inline-block;
        }
        h1 {
            color: #9b5cff;
        }
    </style>
</head>
<body>
    <div class="box">
        <h1>Ethan AI</h1>
        <p>감정 기반 AI 대화 서비스</p>
        <p>곧 채팅 기능이 추가됩니다.</p>
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

if __name__ == "__main__":
    app.run(debug=True)
