# -*- coding: utf-8 -*-
"""
AI Khaled — Enhanced app.py
Features added:
- Safe CSV/memory writes with threading.Lock
- /api/teach endpoint to provide answer for a pending teach request
- /api/dataset endpoints (list, add, delete, export)
- /api/retrain to trigger training in background
- /api/config to read/update config (auto_train, auto_retrain, debug...)
- improved backup (includes kb.json and config.json)
- better stats (top questions, learned count)
- input filtering (bad words)
- persistent last_session tracking
"""
import threading
import webview
import time
import json
import os
import datetime
import csv
import logging
import shutil
from flask import Flask, render_template, request, jsonify, Response
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
MEM_PATH = DATA_DIR / "memory.json"
CONFIG_PATH = DATA_DIR / "config.json"
CSV_PATH = DATA_DIR / "dataset.csv"
MODEL_PATH = ROOT / "model" / "khalid_model.pkl"
BACKUP_DIR = DATA_DIR / "backups"
KB_PATH = DATA_DIR / "kb.json"
LAST_SESSION_PATH = DATA_DIR / "last_session.txt"
LOG_PATH = DATA_DIR / "logs.txt"

# ------------------------
# Logging setup
# ------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()]
)

app = Flask(__name__, template_folder="templates", static_folder="assets")

# ------------------------
# Ensure directories & default files
# ------------------------
for p in [DATA_DIR, BACKUP_DIR]:
    p.mkdir(parents=True, exist_ok=True)

def ensure_json(path, default):
    if not path.exists():
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")

def ensure_csv_with_header(path, header_row):
    if not path.exists():
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header_row)

ensure_json(MEM_PATH, {"sessions": []})
ensure_json(CONFIG_PATH, {"debug": False, "language": "ar", "auto_reply": True, "auto_train": True, "auto_retrain": False})
ensure_csv_with_header(CSV_PATH, ["question", "answer"])
ensure_json(KB_PATH, {"hello": "أهلاً! كيف أقدر أساعدك؟"})
if not LAST_SESSION_PATH.exists():
    LAST_SESSION_PATH.write_text("", encoding="utf-8")

# ------------------------
# Locks for safe concurrent writes
# ------------------------
_csv_lock = threading.Lock()
_mem_lock = threading.Lock()
_config_lock = threading.Lock()

# ------------------------
# Load dataset into memory (cache)
# ------------------------
def load_dataset():
    pairs = []
    if CSV_PATH.exists():
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if len(row) >= 2:
                    q = row[0].strip()
                    a = row[1].strip()
                    if q and a:
                        pairs.append((q, a))
    return pairs

_dataset_cache = load_dataset()  # kept in memory; updated on writes
def refresh_dataset_cache():
    global _dataset_cache
    _dataset_cache = load_dataset()

# ------------------------
# Utilities
# ------------------------
BAD_WORDS = ["كسم", "قحب", "منيك", "شرموط", "كس", "زب"]
def clean_text(t: str) -> str:
    txt = (t or "").strip()
    for w in BAD_WORDS:
        if w in txt:
            return "***"
    return txt

def read_json(path):
    try:
        return json.load(open(path, "r", encoding="utf-8"))
    except Exception:
        return None

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def append_csv_pair(question, answer):
    # writes with lock and avoids duplicate header
    with _csv_lock:
        exists = CSV_PATH.exists()
        with open(CSV_PATH, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if not exists:
                writer.writerow(["question", "answer"])
            writer.writerow([question, answer])
        refresh_dataset_cache()

def save_memory(mem):
    with _mem_lock:
        write_json(MEM_PATH, mem)

def get_last_session_id():
    try:
        return LAST_SESSION_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""

def set_last_session_id(sid):
    try:
        LAST_SESSION_PATH.write_text(str(sid), encoding="utf-8")
    except Exception:
        pass

def trigger_train_background():
    try:
        logging.info("🚀 تشغيل train.py في الخلفية...")
        threading.Thread(target=lambda: os.system(f'"{os.sys.executable}" "{ROOT/"train.py"}"'), daemon=True).start()
    except Exception as e:
        logging.warning(f"فشل تشغيل التدريب في الخلفية: {e}")

# ------------------------
# Count learned pairs (from dataset file)
# ------------------------
def count_learned():
    return len(_dataset_cache)

# ------------------------
# Flask routes
# ------------------------
@app.route("/")
def index():
    hour = datetime.datetime.now().hour
    greeting = "صباح الخير!" if hour < 12 else "مساء الخير!"
    return render_template("index.html", greeting=greeting)

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    text_raw = data.get("text", "")
    text = clean_text(text_raw)
    if not text:
        return jsonify({"error": "empty"}), 400

    # load memory
    mem = read_json(MEM_PATH) or {"sessions": []}

    session_id = data.get("session_id") or str(int(time.time()))
    session = next((s for s in mem["sessions"] if s.get("id") == session_id), None)
    if not session:
        session = {"id": session_id, "messages": []}
        mem["sessions"].append(session)
        set_last_session_id(session_id)

    # check awaiting_answer flag in session (legacy support)
    if session.get("awaiting_answer"):
        question = session.pop("awaiting_answer")
        answer = text
        append_csv_pair(question, answer)
        # also add to memory messages
        session["messages"].append({
            "timestamp": int(time.time()),
            "user_text": question,
            "bot_text": answer
        })
        save_memory(mem)
        logging.info(f"[LEARN] (via chat) {question} -> {answer}")
        # optionally retrain
        cfg = read_json(CONFIG_PATH) or {}
        if cfg.get("auto_retrain"):
            trigger_train_background()
        return jsonify({"reply": "✅ تم الحفظ! شكراً لتعليمك لي ❤️", "session_id": session_id})

    # call ai_engine
    from ai_engine import generate_reply, is_waiting_for_answer, provide_answer_for_pending
    # If ai_engine is using pending mechanism, check it
    try:
        # if engine expects answer and session already waiting, let app handle
        if callable(is_waiting_for_answer) and is_waiting_for_answer(session_id):
            # pass this text as the answer
            ok, msg = provide_answer_for_pending(session_id, text)
            if ok:
                # save in memory
                session["messages"].append({
                    "timestamp": int(time.time()),
                    "user_text": text,
                    "bot_text": msg
                })
                save_memory(mem)
                # retrain optional
                cfg = read_json(CONFIG_PATH) or {}
                if cfg.get("auto_retrain"):
                    trigger_train_background()
                return jsonify({"reply": msg, "session_id": session_id})
    except Exception:
        # engine may not implement those helpers — ignore gracefully
        pass

    # normal reply
    reply = generate_reply(text, session_id)

    # If engine asked to teach (string contains special prompt) — detect and set awaiting
    teach_prompts = ["ممكن تقول", "مش متأكد", "ماتعرفش", "ممكن تقولّي الإجابة"]
    if any(p in reply for p in teach_prompts):
        session["awaiting_answer"] = text
        save_memory(mem)
        logging.info(f"[TEACH_REQUEST] session={session_id} question={text}")
        return jsonify({"reply": reply, "session_id": session_id})

    # otherwise save conversation
    session["messages"].append({
        "timestamp": int(time.time()),
        "user_text": text,
        "bot_text": reply
    })
    save_memory(mem)

    # Auto-learn: if enabled and reply is not from KB/model and user accepted auto save,
    cfg = read_json(CONFIG_PATH) or {}
    if cfg.get("auto_train") and reply and text and (text, reply) not in _dataset_cache:
        # append automatically
        append_csv_pair(text, reply)
        logging.info(f"[AUTO_LEARN] auto-saved pair for '{text}'")

        if cfg.get("auto_retrain"):
            trigger_train_background()

    logging.info(f"[CHAT] {text} -> {reply}")
    return jsonify({"reply": reply, "session_id": session_id})

# ------------------------
# Teach endpoint (explicit): client can call to provide answer for a pending question
# ------------------------
@app.route("/api/teach", methods=["POST"])
def teach():
    data = request.get_json() or {}
    session_id = data.get("session_id")
    question = data.get("question")
    answer = data.get("answer")
    if not session_id or not question or not answer:
        return jsonify({"error": "session_id, question, answer required"}), 400

    append_csv_pair(question, answer)
    # update memory
    mem = read_json(MEM_PATH) or {"sessions": []}
    session = next((s for s in mem["sessions"] if s.get("id") == session_id), None)
    if not session:
        session = {"id": session_id, "messages": []}
        mem["sessions"].append(session)
    session["messages"].append({
        "timestamp": int(time.time()),
        "user_text": question,
        "bot_text": answer
    })
    save_memory(mem)
    cfg = read_json(CONFIG_PATH) or {}
    if cfg.get("auto_retrain"):
        trigger_train_background()
    logging.info(f"[TEACH_API] saved {question} -> {answer} (session={session_id})")
    return jsonify({"status": "saved"})

# ------------------------
# Dataset management endpoints
# ------------------------
@app.route("/api/dataset", methods=["GET"])
def dataset_list():
    # return first N pairs for UI (with option ?limit=all)
    limit = request.args.get("limit", "100")
    pairs = _dataset_cache.copy()
    if limit != "all":
        try:
            limit = int(limit)
            pairs = pairs[:limit]
        except:
            pairs = pairs[:100]
    return jsonify({"count": len(_dataset_cache), "pairs": pairs})

@app.route("/api/dataset/add", methods=["POST"])
def dataset_add():
    data = request.get_json() or {}
    q = data.get("question", "").strip()
    a = data.get("answer", "").strip()
    if not q or not a:
        return jsonify({"error": "question and answer required"}), 400
    append_csv_pair(q, a)
    logging.info(f"[DATASET_ADD] {q} -> {a}")
    return jsonify({"status": "added"})

@app.route("/api/dataset/delete", methods=["POST"])
def dataset_delete():
    data = request.get_json() or {}
    q = data.get("question", "").strip()
    a = data.get("answer", "").strip()
    if not q:
        return jsonify({"error": "question required"}), 400
    # remove matching pairs
    removed = 0
    with _csv_lock:
        pairs = load_dataset()
        new_pairs = [p for p in pairs if not (p[0] == q and (not a or p[1] == a))]
        if len(new_pairs) != len(pairs):
            # overwrite file
            with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["question", "answer"])
                for row in new_pairs:
                    writer.writerow(list(row))
            refresh_dataset_cache()
            removed = len(pairs) - len(new_pairs)
    logging.info(f"[DATASET_DELETE] removed {removed} items for question='{q}'")
    return jsonify({"removed": removed})

@app.route("/api/dataset/export", methods=["GET"])
def dataset_export():
    # return CSV content to download
    def generate():
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                yield line
    return Response(generate(), mimetype="text/csv")

# ------------------------
# Config endpoints
# ------------------------
@app.route("/api/config", methods=["GET", "POST"])
def manage_config():
    if request.method == "POST":
        new_cfg = request.get_json() or {}
        with _config_lock:
            cfg = read_json(CONFIG_PATH) or {}
            cfg.update(new_cfg)
            write_json = lambda p,data: open(p,"w",encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=2))
            write_json(CONFIG_PATH, cfg)
        logging.info(f"[CONFIG] updated: {new_cfg}")
        return jsonify({"status": "updated", "config": cfg})
    else:
        cfg = read_json(CONFIG_PATH) or {}
        return jsonify(cfg)

# ------------------------
# Retrain trigger
# ------------------------
@app.route("/api/retrain", methods=["POST"])
def retrain():
    threading.Thread(target=trigger_train_background, daemon=True).start()
    return jsonify({"status": "retraining started"})

# ------------------------
# Stats & backup & reset
# ------------------------
@app.route("/api/stats", methods=["GET"])
def stats():
    try:
        mem = read_json(MEM_PATH) or {"sessions": []}
        total_sessions = len(mem.get("sessions", []))
        total_messages = sum(len(s.get("messages", [])) for s in mem.get("sessions", []))
        # top questions
        counter = Counter()
        for s in mem.get("sessions", []):
            for m in s.get("messages", []):
                q = m.get("user_text", "")
                if q:
                    counter[q] += 1
        top = counter.most_common(5)
        return jsonify({
            "sessions": total_sessions,
            "messages": total_messages,
            "learned_pairs": count_learned(),
            "top_questions": top,
            "last_session": get_last_session_id()
        })
    except Exception as e:
        logging.error(f"Stats error: {e}")
        return jsonify({"error": "failed"}), 500

@app.route("/api/backup", methods=["GET"])
def backup():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    created = []
    for src in [MEM_PATH, CSV_PATH, KB_PATH, CONFIG_PATH]:
        try:
            dst = BACKUP_DIR / f"{src.stem}_{timestamp}{src.suffix}"
            shutil.copy(src, dst)
            created.append(str(dst))
        except Exception as e:
            logging.warning(f"Backup failed for {src}: {e}")
    logging.info(f"[BACKUP] created {len(created)} files")
    return jsonify({"status": "ok", "files": created})

@app.route("/api/reset", methods=["POST"])
def reset_all():
    confirm = request.args.get("confirm")
    if confirm != "yes":
        return jsonify({"error": "confirmation required: ?confirm=yes"}), 400
    # keep kb and config, reset memory and dataset
    write_json = lambda p,data: open(p,"w",encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=2))
    write_json(MEM_PATH, {"sessions": []})
    with _csv_lock:
        with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["question", "answer"])
        refresh_dataset_cache()
    logging.warning("[RESET] system reset performed")
    return jsonify({"status": "reset"})

# ------------------------
# Server & WebView
# ------------------------
def start_server():
    cfg = read_json(CONFIG_PATH) or {}
    debug = cfg.get("debug", False)
    app.run(port=5000, debug=debug)

if __name__ == "__main__":
    threading.Thread(target=start_server, daemon=True).start()
    time.sleep(0.5)
    print("🚀 AI Khaled جاهز ومُحسّن على http://127.0.0.1:5000")
    webview.create_window("AI Khaled — Smart Edition", "http://127.0.0.1:5000", width=980, height=740)
    webview.start()
