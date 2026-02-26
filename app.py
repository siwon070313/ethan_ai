from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Ethan AI 준비 완료!"

if __name__ == "__main__":
    app.run(debug=True)
