# -*- coding: utf-8 -*-
"""
train.py — تدريب نموذج الذكاء الصناعي
يقرأ من data/dataset.csv و data/memory.json
ويحفظ النموذج في model/khalid_model.pkl
يتعرف تلقائيًا على أسماء الأعمدة (question/answer أو user_text/bot_text)
يتطلب scikit-learn
"""
import os, json, pickle, csv
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DS_PATH = DATA_DIR / "dataset.csv"
MEM_PATH = DATA_DIR / "memory.json"
MODEL_DIR = ROOT / "model"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

pairs = []

# ------------------------
# Load dataset.csv
# ------------------------
if DS_PATH.exists():
    try:
        with open(DS_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                # يدعم كلا التنسيقين
                q = row.get("question") or row.get("user_text") or ""
                a = row.get("answer") or row.get("bot_text") or ""
                q, a = q.strip(), a.strip()
                if q and a:
                    pairs.append((q, a))
                    count += 1
            print(f"✅ تم تحميل {count} زوج من dataset.csv")
    except Exception as e:
        print(f"⚠️ خطأ في قراءة dataset.csv: {e}")
else:
    print("⚠️ ملف dataset.csv غير موجود بعد.")

# ------------------------
# Load memory.json
# ------------------------
if MEM_PATH.exists():
    try:
        mem = json.load(open(MEM_PATH, "r", encoding="utf-8"))
        mem_count = 0
        for sess in mem.get("sessions", []):
            for conv in sess.get("messages", []):
                u = conv.get("user_text", "").strip()
                b = conv.get("bot_text", "").strip()
                if u and b:
                    pairs.append((u, b))
                    mem_count += 1
        print(f"🧠 تم إضافة {mem_count} زوج من الذاكرة")
    except Exception as e:
        print(f"⚠️ خطأ في تحميل الذاكرة: {e}")
else:
    print("⚠️ ملف memory.json غير موجود بعد.")

# ------------------------
# Check data
# ------------------------
if not pairs:
    print("🚫 لا توجد بيانات كافية للتدريب. أضف أسئلة إلى dataset.csv أو تحدث مع البوت أولًا.")
    exit(0)

X, y = zip(*pairs)
print(f"🔧 بدء التدريب على {len(pairs)} جملة من الأسئلة والأجوبة...")

# ------------------------
# Import scikit-learn
# ------------------------
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.neighbors import KNeighborsClassifier
except Exception:
    print("❌ لم يتم العثور على scikit-learn. ثبّتها عبر: pip install scikit-learn")
    exit(1)

# ------------------------
# Train Model
# ------------------------
vec = TfidfVectorizer(analyzer="word", ngram_range=(1, 3))
Xv = vec.fit_transform(X)
model = KNeighborsClassifier(n_neighbors=3)
model.fit(Xv, y)

# ------------------------
# Save model
# ------------------------
model_file = MODEL_DIR / "khalid_model.pkl"
with open(model_file, "wb") as f:
    pickle.dump((vec, model), f)

print(f"✅ انتهى التدريب بنجاح. تم حفظ النموذج في: {model_file}")
