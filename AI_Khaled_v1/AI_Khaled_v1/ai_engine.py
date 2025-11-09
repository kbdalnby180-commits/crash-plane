# -*- coding: utf-8 -*-
"""
ai_engine.py — محرك الردود الذكي (معدّل)
تغييرات رئيسية بناءً على طلب المستخدم:
- أزلت ظهور كلمة "[RETRIEVE]" في اللوج واستبدلتها بعلامة أبسط "[MEM]".
- عطّلت استدعاء Markov كـ fallback نهائي حتى ما يحصلش ردود عشوائية مثل "الحمد لله".
- حافظت على بقية البنية والمزايا كما هي (KB, dataset, memory, ML, caching, pending).
- عندما لا يوجد رد مناسب، يُسجَّل السؤال كـ pending وتُعاد رسالة التعلم فقط.
"""
import os
import json
import csv
import random
import logging
import re
import threading
import pickle
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
MEM_PATH = DATA_DIR / "memory.json"
DS_PATH = DATA_DIR / "dataset.csv"
KB_PATH = DATA_DIR / "kb.json"
MODEL_PATH = ROOT / "model" / "khalid_model.pkl"
CONFIG_PATH = DATA_DIR / "config.json"

# إعدادات
SIMILARITY_THRESHOLD_RETRIEVE = 0.45
SIMILARITY_THRESHOLD_DATASET = 0.5
MARKOV_N = 2
MARKOV_MAX_LEN = 40
AUTO_RETRAIN_DEFAULT = False

# logging
LOG_PATH = DATA_DIR / "ai_engine.log"
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [ai_engine] [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()]
)

# تأكد وجود المجلدات والملفات الافتراضية
DATA_DIR.mkdir(parents=True, exist_ok=True)
if not MEM_PATH.exists():
    MEM_PATH.write_text(json.dumps({"sessions": []}, ensure_ascii=False, indent=2), encoding="utf-8")
if not DS_PATH.exists():
    with open(DS_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["question", "answer"])
if not KB_PATH.exists():
    KB_PATH.write_text(json.dumps({"hello":"أهلاً! كيف أقدر أساعدك؟"}, ensure_ascii=False, indent=2), encoding="utf-8")
if not CONFIG_PATH.exists():
    CONFIG_PATH.write_text(json.dumps({"auto_retrain": AUTO_RETRAIN_DEFAULT, "auto_train": True}, ensure_ascii=False, indent=2), encoding="utf-8")

# locks للحماية
_ds_lock = threading.Lock()
_mem_lock = threading.Lock()
_kb_lock = threading.Lock()

# كاش بسيط
_reply_cache = {}  # normalized_text -> reply

# pending map لجلسات التعلم الذاتي
_pending = {}  # session_id -> question

# ------------------------
# أدوات مساعدة
# ------------------------
def _now_ts():
    return int(datetime.now().timestamp())

def _clean_text(t: str) -> str:
    if not isinstance(t, str):
        return ""
    t = t.lower().strip()
    # احتفظ بالحروف العربية والإنجليزية والأرقام والمسافات
    t = re.sub(r"[^\u0600-\u06FFa-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()

def _similarity(a: str, b: str) -> float:
    sa = set(_clean_text(a).split())
    sb = set(_clean_text(b).split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa), len(sb))

def _read_json(path: Path, default):
    try:
        return json.load(open(path, "r", encoding="utf-8"))
    except Exception as e:
        logging.warning(f"failed reading {path}: {e}")
        return default

def _write_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ------------------------
# تحميل KB و dataset (كاش)
# ------------------------
_kb_cache = None
_dataset_cache = None

def _load_kb():
    global _kb_cache
    if _kb_cache is None:
        _kb_cache = _read_json(KB_PATH, {})
    return _kb_cache

def _load_dataset():
    global _dataset_cache
    if _dataset_cache is not None:
        return _dataset_cache
    pairs = []
    try:
        with open(DS_PATH, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if len(row) >= 2:
                    q = row[0].strip()
                    a = row[1].strip()
                    if q and a:
                        pairs.append((q, a))
    except Exception as e:
        logging.warning(f"failed loading dataset.csv: {e}")
    _dataset_cache = pairs
    logging.info(f"dataset loaded: {len(pairs)} pairs")
    return _dataset_cache

def _refresh_dataset_cache():
    global _dataset_cache
    _dataset_cache = None
    return _load_dataset()

# ------------------------
# memory helpers
# ------------------------
def load_memory():
    return _read_json(MEM_PATH, {"sessions": []})

def save_memory(mem):
    with _mem_lock:
        _write_json(MEM_PATH, mem)

# ------------------------
# حفظ زوج جديد (سؤال -> إجابة)
# ------------------------
def save_new_pair(question: str, answer: str, session_id: str = None):
    question = question.strip()
    answer = answer.strip()
    if not question or not answer:
        return False
    # تجنب التكرار
    dataset = _load_dataset()
    if (question, answer) in dataset:
        logging.info("pair already exists, skipping save")
        return False
    # اكتب في CSV
    with _ds_lock:
        try:
            file_exists = DS_PATH.exists()
            with open(DS_PATH, "a", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["question", "answer"])
                writer.writerow([question, answer])
            logging.info(f"[LEARN] saved pair: {question} -> {answer}")
            _refresh_dataset_cache()
        except Exception as e:
            logging.warning(f"failed to append dataset: {e}")
            return False
    # أضف أيضاً للذاكرة
    try:
        mem = load_memory()
        if session_id:
            session = next((s for s in mem.get("sessions", []) if s.get("id") == session_id), None)
        else:
            session = mem.get("sessions")[-1] if mem.get("sessions") else None
        if not session:
            session = {"id": session_id or str(_now_ts()), "messages": []}
            mem.setdefault("sessions", []).append(session)
        session["messages"].append({
            "timestamp": _now_ts(),
            "user_text": question,
            "bot_text": answer
        })
        save_memory(mem)
    except Exception as e:
        logging.warning(f"failed to add to memory: {e}")
    # تحديث KB تلقائي بسيط: إذا السؤال قصير، ضمه كمفتاح
    try:
        if len(question.split()) <= 5:
            with _kb_lock:
                kb = _load_kb()
                if question not in kb:
                    kb[question] = answer
                    _write_json = lambda p,d: open(p,"w",encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=2))
                    _write_json(KB_PATH, kb)
                    global _kb_cache
                    _kb_cache = kb
    except Exception as e:
        logging.warning(f"failed to update kb: {e}")

    # خيار إعادة تدريب تلقائي إن كان مفعلاً
    cfg = _read_json(CONFIG_PATH, {})
    if cfg.get("auto_retrain"):
        try:
            threading.Thread(target=lambda: os.system(f'"{os.sys.executable}" "{ROOT/"train.py"}"'), daemon=True).start()
        except Exception as e:
            logging.warning(f"failed to trigger retrain: {e}")

    return True

# ------------------------
# استرجاع من الذاكرة
# ------------------------
def retrieve(user_text: str, session_id: str = None):
    mem = load_memory()
    best = None; best_score = 0.0
    for sess in mem.get("sessions", []):
        if session_id and sess.get("id") != session_id:
            continue
        for conv in sess.get("messages", []):
            s = _similarity(user_text, conv.get("user_text", ""))
            if s > best_score:
                best_score = s
                best = conv
    if best and best_score >= SIMILARITY_THRESHOLD_RETRIEVE:
        # تم استبدال وسم اللوج إلى وسم أبسط "[MEM]" بدلاً من "[RETRIEVE]"
        logging.info(f"[MEM] score={best_score:.2f}")
        return best.get("bot_text")
    return None

# ------------------------
# dataset lookup (direct match by similarity)
# ------------------------
def dataset_lookup(user_text: str):
    dataset = _load_dataset()
    best_score = 0.0; best_answer = None
    for q,a in dataset:
        s = _similarity(user_text, q)
        if s > best_score:
            best_score = s; best_answer = a
    if best_answer and best_score >= SIMILARITY_THRESHOLD_DATASET:
        logging.info(f"[DATASET] match score={best_score:.2f}")
        return best_answer
    return None

# ------------------------
# KB lookup
# ------------------------
def kb_lookup(user_text: str):
    kb = _load_kb()
    text = _clean_text(user_text)
    for key, val in kb.items():
        if key and _clean_text(key) in text:
            logging.info(f"[KB] matched key='{key}'")
            return val
    return None

# ------------------------
# Markov fallback (n-grams) -- تابع موجود لكن لن يُستدعى تلقائياً الآن
# ------------------------
def markov_fallback(seed: str, n: int = MARKOV_N, max_len: int = MARKOV_MAX_LEN):
    corpus = []
    # from dataset
    for q,a in _load_dataset():
        corpus.append(q); corpus.append(a)
    # from memory
    mem = load_memory()
    for sess in mem.get("sessions", []):
        for m in sess.get("messages", []):
            corpus.append(m.get("user_text","")); corpus.append(m.get("bot_text",""))
    text = " ".join([c for c in corpus if c])
    tokens = _clean_text(text).split()
    if len(tokens) < n:
        return ""
    trans = {}
    for i in range(len(tokens)-n):
        key = tuple(tokens[i:i+n])
        trans.setdefault(key, []).append(tokens[i+n])
    seed_toks = _clean_text(seed).split()[:n]
    if len(seed_toks) < n:
        key = random.choice(list(trans.keys()))
    else:
        key = tuple(seed_toks)
        if key not in trans:
            key = random.choice(list(trans.keys()))
    out = list(key)
    for _ in range(max_len):
        nxts = trans.get(tuple(out[-n:]))
        if not nxts: break
        out.append(random.choice(nxts))
    return " ".join(out)

# ------------------------
# ML model attempt (safe)
# ------------------------
def try_ml_model(user_text: str):
    try:
        if MODEL_PATH.exists():
            vec, model = pickle.load(open(MODEL_PATH, "rb"))
            Xv = vec.transform([user_text])
            pred = model.predict(Xv)
            if pred and len(pred) > 0:
                logging.info("[ML] model returned an answer")
                return pred[0]
    except Exception as e:
        logging.warning(f"ML error: {e}")
    return None

# ------------------------
# واجهات pending management للعمل مع app.py
# ------------------------
def is_waiting_for_answer(session_id: str) -> bool:
    return session_id in _pending

def provide_answer_for_pending(session_id: str, answer: str):
    """
    يعالج إجابة المستخدم لسؤال تم طلب تعليمه مسبقاً.
    يعيد (True, message) لو نجح، وإلا (False, error_message)
    """
    if session_id not in _pending:
        return False, "ما كانش فيه سؤال مستني إجابة."
    question = _pending.pop(session_id)
    ok = save_new_pair(question, answer, session_id=session_id)
    if ok:
        return True, "تمام ✅ حفظت الإجابة وهفتكرها المرة الجاية."
    else:
        return False, "محصلش حفظ — ممكن تجرب تاني؟"

# ------------------------
# الكاش: قراءة وكتابة
# ------------------------
def _cache_get(user_text: str):
    return _reply_cache.get(_clean_text(user_text))

def _cache_set(user_text: str, reply: str):
    _reply_cache[_clean_text(user_text)] = reply

# ------------------------
# الدالة الرئيسية: توليد الرد
# ------------------------
def generate_reply(user_text: str, session_id: str = None) -> str:
    """
    ترتيب المحاولات:
    1) cache
    2) KB
    3) memory retrieval
    4) dataset lookup
    5) ML model
    6) (Markov مُعطّل هنا)
    7) Ask user to teach (register pending)
    """
    if not user_text or not isinstance(user_text, str):
        return "معلش مش قادر أجاوب دلوقتي."

    # cache
    c = _cache_get(user_text)
    if c:
        logging.info("[CACHE] hit")
        return c

    # KB
    kb_ans = kb_lookup(user_text)
    if kb_ans:
        _cache_set(user_text, kb_ans)
        return kb_ans

    # memory retrieval
    mem_ans = retrieve(user_text, session_id)
    if mem_ans:
        _cache_set(user_text, mem_ans)
        return mem_ans

    # dataset lookup
    ds_ans = dataset_lookup(user_text)
    if ds_ans:
        _cache_set(user_text, ds_ans)
        return ds_ans

    # ML
    ml_ans = try_ml_model(user_text)
    if ml_ans:
        _cache_set(user_text, ml_ans)
        return ml_ans

    # Markov fallback مُعطّل: لا نستخدمه لإعطاء رد عشوائي
    # إذا لايوجد شيء مناسب -> نسجل كـ pending ونطلب من المستخدم يساعدنا بالتعليم
    sid = session_id or str(_now_ts())
    _pending[sid] = user_text
    logging.info(f"[TEACH_REQUEST] session={sid} question='{user_text}'")
    return "🤔 مش متأكد من الإجابة، ممكن تقولّي الإجابة الصح علشان أتعلمها؟"

# ------------------------
# init load
# ------------------------
_load_kb = _load_kb  # alias to load at import time
_load_dataset = _load_dataset
_load_kb()
_load_dataset()
logging.info("ai_engine initialized.")
