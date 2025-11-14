import os
import threading
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "AI Khaled is Running!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def start_server():
    thread = threading.Thread(target=run_server)
    thread.start()
