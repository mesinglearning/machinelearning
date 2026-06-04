import os
import json
import uuid
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from PIL import Image, ImageEnhance, ImageOps

# Membaca konfigurasi dari file .env, misalnya URL dan API key Supabase.
load_dotenv()

# Membuat aplikasi Flask sebagai backend utama dan mengaktifkan CORS
# agar endpoint API bisa diakses dari dashboard web.
app = Flask(__name__)
CORS(app)

# Konfigurasi Supabase.
# Nilai ini diambil dari .env agar data rahasia tidak ditulis langsung di kode.
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "captures")
HAS_SUPABASE = False
SUPABASE_CLIENT_TRIED = False

def get_supabase_client():
    """Membuat koneksi Supabase saat benar-benar dibutuhkan."""
    global supabase, HAS_SUPABASE, SUPABASE_CLIENT_TRIED
    
    if supabase is not None or SUPABASE_CLIENT_TRIED or not SUPABASE_URL or not SUPABASE_KEY:
        return supabase
    
    SUPABASE_CLIENT_TRIED = True
    try:
        from supabase import create_client as sb_create_client
        supabase = sb_create_client(SUPABASE_URL, SUPABASE_KEY)
        HAS_SUPABASE = True
        print("Supabase Python client connected successfully")
    except Exception as e:
        print(f"Supabase Python client not available: {e}")
        supabase = None
        HAS_SUPABASE = False
    
    return supabase

supabase = None


def has_supabase_config():
    """Mengecek apakah konfigurasi Supabase sudah tersedia."""
    return bool(SUPABASE_URL and SUPABASE_KEY)


def upload_capture_to_supabase(image_path, filename):
    """Mengunggah gambar capture ke Supabase Storage dan mengembalikan URL publik."""
    if not has_supabase_config():
        return None

    object_path = f"{datetime.now(UTC).strftime('%Y-%m-%d')}/{filename}"
    encoded_object_path = quote(object_path, safe="/")
    bucket = quote(SUPABASE_STORAGE_BUCKET, safe="")
    base_url = SUPABASE_URL.rstrip("/")
    upload_url = f"{base_url}/storage/v1/object/{bucket}/{encoded_object_path}"

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "image/jpeg",
    }

    try:
        image_bytes = Path(image_path).read_bytes()
        req = Request(upload_url, data=image_bytes, headers=headers, method="POST")
        with urlopen(req, timeout=20):
            public_url = f"{base_url}/storage/v1/object/public/{bucket}/{encoded_object_path}"
            print(f"Uploaded capture to Supabase Storage: {public_url}")
            return public_url
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"Supabase Storage upload error ({e.code}): {detail}")
    except URLError as e:
        print(f"Supabase Storage connection error: {e}")
    except Exception as e:
        print(f"Supabase Storage upload error: {e}")

    return None


def supabase_rest_request(table, method="GET", params=None, data=None, prefer=None):
    """Mengakses Supabase REST API sebagai cadangan jika client Python gagal."""
    if not has_supabase_config():
        return None

    base_url = SUPABASE_URL.rstrip("/")
    url = f"{base_url}/rest/v1/{table}"
    if params:
        url = f"{url}?{urlencode(params)}"

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer

    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = Request(url, data=body, headers=headers, method=method)

    try:
        with urlopen(req, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else []
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"Supabase REST error ({e.code}): {detail}")
    except URLError as e:
        print(f"Supabase REST connection error: {e}")
    except Exception as e:
        print(f"Supabase REST error: {e}")

    return None


def insert_supabase_row(table, data):
    """Menyimpan satu baris data ke tabel Supabase."""
    supabase_client = get_supabase_client()
    if supabase_client:
        try:
            response = supabase_client.table(table).insert(data).execute()
            print(f"Saved row to Supabase table: {table}")
            return response
        except Exception as e:
            print(f"Supabase Python insert failed, trying REST fallback: {e}")

    response = supabase_rest_request(
        table,
        method="POST",
        data=data,
        prefer="return=minimal"
    )
    if response is not None:
        print(f"Saved row to Supabase table via REST: {table}")
    return response


def select_supabase_latest(table, limit=1):
    """Mengambil data terbaru dari tabel Supabase berdasarkan created_at."""
    supabase_client = get_supabase_client()
    if supabase_client:
        try:
            return supabase_client.table(table).select("*").order("created_at", desc=True).limit(limit).execute().data
        except Exception as e:
            print(f"Supabase Python select failed, trying REST fallback: {e}")

    return supabase_rest_request(
        table,
        params={
            "select": "*",
            "order": "created_at.desc",
            "limit": str(limit)
        }
    )


# Konfigurasi folder, model YOLO, cache lokal, dan data sensor terbaru.
CAPTURES_DIR = Path("static/captures")
CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
CUSTOM_MODEL_PATH = Path("models/best.pt")
YOLO_CONFIDENCE_THRESHOLD = 0.12
YOLO_IMAGE_SIZE = 832
LOCAL_DETECTION_HISTORY = []
LOCAL_SENSOR_HISTORY = []
LAST_YOLO_ERROR = None
YOLO_MODEL = None
YOLO_MODEL_MTIME = None
LATEST_SENSOR_DATA = {
    "temperature": None,
    "humidity": None,
    "gas_status": "Waiting for ESP32",
    "gas_value": None,
    "created_at": None,
    "source": "local"
}
SENSOR_STALE_AFTER_SECONDS = 60
CAPTURE_REQUEST_STATE = {
    "id": None,
    "requested_at": None
}
GAS_BASELINE_ADC = 300
GAS_WARNING_ADC = 350
GAS_DANGER_ADC = 400
GAS_DANGER_EXPOSURE_HOURS = 10

FRESHNESS_THRESHOLDS = {
    "rice": {
        "temperature_max": 35,
        "temperature_ideal": 25,
        "humidity_max": 80,
        "humidity_ideal": 60,
        "gas_max": GAS_BASELINE_ADC,
        "gas_raw_ideal": GAS_BASELINE_ADC,
        "gas_raw_warning": GAS_WARNING_ADC,
        "gas_raw_max": GAS_DANGER_ADC,
        "base_hours": 4,
    },
    "fried_chicken": {
        "temperature_max": 30,
        "temperature_ideal": 25,
        "humidity_max": 75,
        "humidity_ideal": 60,
        "gas_max": GAS_BASELINE_ADC,
        "gas_raw_ideal": GAS_BASELINE_ADC,
        "gas_raw_warning": GAS_WARNING_ADC,
        "gas_raw_max": GAS_DANGER_ADC,
        "base_hours": 3,
    },
    "broccoli": {
        "temperature_max": 32,
        "temperature_ideal": 24,
        "humidity_max": 85,
        "humidity_ideal": 70,
        "gas_max": GAS_BASELINE_ADC,
        "gas_raw_ideal": GAS_BASELINE_ADC,
        "gas_raw_warning": GAS_WARNING_ADC,
        "gas_raw_max": GAS_DANGER_ADC,
        "base_hours": 5,
    },
    "apple": {
        "temperature_max": 28,
        "temperature_ideal": 22,
        "humidity_max": 70,
        "humidity_ideal": 55,
        "gas_max": GAS_BASELINE_ADC,
        "gas_raw_ideal": GAS_BASELINE_ADC,
        "gas_raw_warning": GAS_WARNING_ADC,
        "gas_raw_max": GAS_DANGER_ADC,
        "base_hours": 8,
    },
}

# Bobot per faktor untuk menghitung Freshness Score.
# Gas diberi bobot paling besar karena bau/gas pembusukan cukup penting
# untuk menentukan kelayakan makanan.
FRESHNESS_WEIGHTS = {
    "temperature": 0.35,
    "humidity": 0.25,
    "gas": 0.40,
}


def parse_iso_datetime(value):
    """Mengubah teks waktu ISO dari Supabase/Flask menjadi objek datetime."""
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def sensor_timestamp(data):
    """Mengambil timestamp created_at dari data sensor."""
    return parse_iso_datetime((data or {}).get("created_at"))


def enrich_sensor_data(data, source="local"):
    """Melengkapi data sensor dengan umur data dan status koneksi."""
    sensor_data = dict(data or {})
    sensor_data.setdefault("temperature", None)
    sensor_data.setdefault("humidity", None)
    sensor_data.setdefault("gas_status", "Waiting for ESP32")
    sensor_data.setdefault("gas_value", None)
    sensor_data.setdefault("created_at", None)
    sensor_data["source"] = source

    timestamp = sensor_timestamp(sensor_data)
    if timestamp is None:
        sensor_data["age_seconds"] = None
        sensor_data["is_stale"] = True
        sensor_data["connection_status"] = "Menunggu ESP32"
        return sensor_data

    age_seconds = max(0, int((datetime.now(UTC) - timestamp).total_seconds()))
    is_stale = age_seconds > SENSOR_STALE_AFTER_SECONDS
    sensor_data["age_seconds"] = age_seconds
    sensor_data["is_stale"] = is_stale
    sensor_data["connection_status"] = "Offline" if is_stale else "Live"
    return sensor_data


def freshest_sensor_data(*sensor_sources):
    """Memilih data sensor yang paling baru dari beberapa sumber."""
    available = [
        (source, data)
        for source, data in sensor_sources
        if data and sensor_timestamp(data) is not None
    ]

    if not available:
        return enrich_sensor_data(LATEST_SENSOR_DATA, "local")

    source, data = max(available, key=lambda item: sensor_timestamp(item[1]))
    return enrich_sensor_data(data, source)


def latest_sensor_for_prediction():
    """Mengambil data sensor terbaru untuk digunakan pada prediksi kesegaran."""
    sources = [
        (LATEST_SENSOR_DATA.get("source", "local"), LATEST_SENSOR_DATA),
        ("local-history", LOCAL_SENSOR_HISTORY[0] if LOCAL_SENSOR_HISTORY else None),
    ]

    if has_supabase_config():
        try:
            rows = select_supabase_latest("sensor_logs", limit=1)
            if rows:
                latest = rows[0]
                sources.append((
                    "supabase",
                    {
                        "temperature": latest.get("temperature"),
                        "humidity": latest.get("humidity"),
                        "gas_status": latest.get("gas_status"),
                        "gas_value": latest.get("gas_value"),
                        "created_at": latest.get("created_at"),
                    }
                ))
        except Exception as e:
            print(f"Prediction sensor fetch skipped: {e}")

    return freshest_sensor_data(*sources)

# Daftar menu yang menjadi target deteksi YOLO.
MENU_ITEMS = {
    "rice": {
        "id": 1,
        "name": "Nasi",
        "fresh_class": "fresh_rice",
        "bad_class": "stale_rice",
        "fresh_label": "Segar",
        "bad_label": "Basi"
    },
    "fried_chicken": {
        "id": 2,
        "name": "Ayam Goreng",
        "fresh_class": "fresh_fried_chicken",
        "bad_class": "spoiled_fried_chicken",
        "fresh_label": "Layak",
        "bad_label": "Tidak Layak"
    },
    "apple": {
        "id": 3,
        "name": "Apel",
        "fresh_class": "fresh_apple",
        "bad_class": "rotten_apple",
        "fresh_label": "Segar",
        "bad_label": "Busuk"
    },
    "broccoli": {
        "id": 4,
        "name": "Brokoli",
        "fresh_class": "fresh_broccoli",
        "bad_class": "rotten_broccoli",
        "fresh_label": "Segar",
        "bad_label": "Busuk"
    }
}

# Mapping kelas YOLO ke item menu dan status kualitasnya.
QUALITY_CLASSES = {
    item_info["fresh_class"]: {
        "item_key": item_key,
        "quality": "fresh",
        "quality_label": item_info["fresh_label"],
        "acceptable": True
    }
    for item_key, item_info in MENU_ITEMS.items()
}
QUALITY_CLASSES.update({
    item_info["bad_class"]: {
        "item_key": item_key,
        "quality": "bad",
        "quality_label": item_info["bad_label"],
        "acceptable": False
    }
    for item_key, item_info in MENU_ITEMS.items()
})

# Batas minimal confidence tiap kelas agar deteksi YOLO yang terlalu lemah diabaikan.
MIN_CONFIDENCE_BY_CLASS = {
    "fresh_rice": 0.25,
    "stale_rice": 0.32,
    "fresh_fried_chicken": 0.12,
    "spoiled_fried_chicken": 0.22,
    "fresh_apple": 0.22,
    "rotten_apple": 0.38,
    "fresh_broccoli": 0.16,
    "rotten_broccoli": 0.30,
}


GAS_SPOILAGE_KEYWORDS = (
    "bau busuk",
    "busuk",
    "bahaya",
    "danger",
    "warning",
    "waspada"
)


def sensor_indicates_spoilage(sensor_data):
    """Mengembalikan True jika sensor MQ135 mendeteksi indikasi bau busuk."""
    enriched = enrich_sensor_data(sensor_data, sensor_data.get("source", "local"))
    if enriched.get("is_stale"):
        return False

    gas_status = str(enriched.get("gas_status") or "").lower()
    if "warming" in gas_status:
        return False

    return any(keyword in gas_status for keyword in GAS_SPOILAGE_KEYWORDS)


def clamp_number(value, minimum=0, maximum=100):
    """Membatasi angka agar tetap berada pada rentang minimum dan maksimum."""
    return max(minimum, min(maximum, value))


def score_against_threshold(value, ideal, maximum):
    """Menghitung skor 0-100 berdasarkan nilai ideal dan batas maksimum."""
    if value is None:
        return None

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None

    if numeric_value <= ideal:
        return 100
    if numeric_value >= maximum:
        return 0

    usable_range = max(0.1, maximum - ideal)
    return clamp_number(((maximum - numeric_value) / usable_range) * 100)


def score_gas_value(value, maximum=None, raw_ideal=None, raw_max=None):
    """Menghitung skor gas dari MQ135 berdasarkan ambang hasil praktik."""
    if value is None:
        return None

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None

    if numeric_value <= GAS_BASELINE_ADC:
        return 100
    if numeric_value >= GAS_DANGER_ADC:
        return 0

    if numeric_value <= GAS_WARNING_ADC:
        progress = (numeric_value - GAS_BASELINE_ADC) / (GAS_WARNING_ADC - GAS_BASELINE_ADC)
        return clamp_number(100 - (progress * 40))

    progress = (numeric_value - GAS_WARNING_ADC) / (GAS_DANGER_ADC - GAS_WARNING_ADC)
    return clamp_number(60 - (progress * 45))


def estimate_gas_exposure_hours(value):
    """Memperkirakan lama makanan terbiar berdasarkan nilai MQ135."""
    if value is None:
        return None

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None

    if numeric_value <= 0:
        return 0
    if numeric_value <= GAS_BASELINE_ADC:
        return round((numeric_value / GAS_BASELINE_ADC) * 1.5, 2)
    if numeric_value <= GAS_WARNING_ADC:
        progress = (numeric_value - GAS_BASELINE_ADC) / (GAS_WARNING_ADC - GAS_BASELINE_ADC)
        return round(1.5 + (progress * 3.5), 2)
    if numeric_value <= GAS_DANGER_ADC:
        progress = (numeric_value - GAS_WARNING_ADC) / (GAS_DANGER_ADC - GAS_WARNING_ADC)
        return round(5 + (progress * 5), 2)

    extra_hours = (numeric_value - GAS_DANGER_ADC) / 20
    return round(min(12, GAS_DANGER_EXPOSURE_HOURS + extra_hours), 2)


def freshness_status(score, emergency=False):
    """Menentukan label status kelayakan berdasarkan Freshness Score."""
    if emergency:
        return {
            "label": "BUSUK / JANGAN DIMAKAN",
            "level": "danger",
            "action": "Distribusi harus dihentikan dan data insiden disimpan."
        }

    if score >= 75:
        return {
            "label": "AMAN",
            "level": "safe",
            "action": "Monitoring normal."
        }
    if score >= 50:
        return {
            "label": "WASPADA",
            "level": "warning",
            "action": "Pantau lebih sering dan siapkan notifikasi penanggung jawab."
        }
    if score >= 25:
        return {
            "label": "SEGERA HABISKAN",
            "level": "urgent",
            "action": "Prioritaskan konsumsi dan catat ke log."
        }

    return {
        "label": "BUSUK / JANGAN DIMAKAN",
        "level": "danger",
        "action": "Distribusi harus dihentikan dan data insiden disimpan."
    }


def format_remaining_time_message(hours):
    """Mengubah sisa waktu dalam jam menjadi kalimat yang mudah dibaca."""
    try:
        numeric_hours = float(hours)
    except (TypeError, ValueError):
        return "Waktu kelayakan belum bisa dihitung karena data sensor belum lengkap."

    if numeric_hours <= 0:
        return "Makanan ini sudah tidak layak dikonsumsi."

    total_minutes = int(round(numeric_hours * 60))
    hour_part = total_minutes // 60
    minute_part = total_minutes % 60

    if hour_part <= 0:
        time_text = f"{minute_part} menit"
    elif minute_part == 0:
        time_text = f"{hour_part} jam"
    else:
        time_text = f"{hour_part} jam {minute_part} menit"

    return f"{time_text} lagi makanan ini tidak layak dikonsumsi."


def calculate_item_freshness(item_key, detection, sensor_data):
    """Menghitung Freshness Score dan estimasi waktu untuk satu jenis makanan."""
    threshold = FRESHNESS_THRESHOLDS[item_key]
    temperature = sensor_data.get("temperature")
    humidity = sensor_data.get("humidity")
    gas_value = sensor_data.get("gas_value")

    temp_score = score_against_threshold(
        temperature,
        threshold["temperature_ideal"],
        threshold["temperature_max"]
    )
    humidity_score = score_against_threshold(
        humidity,
        threshold["humidity_ideal"],
        threshold["humidity_max"]
    )
    gas_score = score_gas_value(
        gas_value,
        threshold["gas_max"],
        threshold.get("gas_raw_ideal"),
        threshold.get("gas_raw_max")
    )
    gas_exposure_hours = estimate_gas_exposure_hours(gas_value)

    component_scores = {
        "temperature": temp_score,
        "humidity": humidity_score,
        "gas": gas_score,
    }
    available_scores = {
        key: value
        for key, value in component_scores.items()
        if value is not None
    }

    if not available_scores:
        weighted_score = 0
    else:
        used_weight = sum(FRESHNESS_WEIGHTS[key] for key in available_scores.keys())
        weighted_score = sum(
            available_scores[key] * FRESHNESS_WEIGHTS[key]
            for key in available_scores.keys()
        ) / used_weight

    visual_penalty = 0
    if detection.get("detected") and not detection.get("acceptable"):
        visual_penalty = 35

    score = clamp_number(round(weighted_score - visual_penalty, 1))

    emergency = False
    try:
        emergency = gas_value is not None and float(gas_value) >= GAS_DANGER_ADC
    except (TypeError, ValueError):
        emergency = False

    if sensor_indicates_spoilage(sensor_data):
        score = min(score, 24)
    elif gas_value is not None:
        try:
            numeric_gas = float(gas_value)
            if numeric_gas >= GAS_WARNING_ADC:
                score = min(score, 60)
            elif numeric_gas >= GAS_BASELINE_ADC:
                score = min(score, 78)
        except (TypeError, ValueError):
            pass

    if emergency:
        score = 0

    temp_factor = 1
    try:
        if temperature is not None:
            temp_factor = 0.5 ** max(0, (float(temperature) - threshold["temperature_ideal"]) / 10)
    except (TypeError, ValueError):
        temp_factor = 1

    humidity_factor = 1
    try:
        if humidity is not None and float(humidity) > threshold["humidity_ideal"]:
            humidity_range = max(1, threshold["humidity_max"] - threshold["humidity_ideal"])
            humidity_ratio = (float(humidity) - threshold["humidity_ideal"]) / humidity_range
            humidity_factor = clamp_number(1 - (humidity_ratio * 0.55), 0.15, 1)
    except (TypeError, ValueError):
        humidity_factor = 1

    if gas_exposure_hours is None:
        remaining_base_hours = threshold["base_hours"]
    else:
        remaining_base_hours = max(0, GAS_DANGER_EXPOSURE_HOURS - gas_exposure_hours)

    remaining_hours = round(remaining_base_hours * temp_factor * humidity_factor, 2)

    status = freshness_status(score, emergency=emergency)
    return {
        "item_key": item_key,
        "name": detection.get("name", MENU_ITEMS[item_key]["name"]),
        "score": score,
        "status": status["label"],
        "level": status["level"],
        "action": status["action"],
        "remaining_hours": remaining_hours,
        "time_message": format_remaining_time_message(remaining_hours),
        "threshold": threshold,
        "component_scores": component_scores,
        "estimated_exposure_hours": gas_exposure_hours,
        "detected_quality": detection.get("quality_label"),
        "visual_acceptable": detection.get("acceptable"),
        "emergency_gas_trigger": emergency,
    }


def calculate_freshness_prediction(detection_result, sensor_data):
    """Menghitung prediksi kesegaran semua makanan yang terdeteksi."""
    enriched_sensor = enrich_sensor_data(sensor_data, sensor_data.get("source", "local"))
    detections = detection_result.get("detections", {})
    detected_items = [
        item_key
        for item_key in MENU_ITEMS.keys()
        if detections.get(item_key, {}).get("detected")
    ]

    if not detected_items:
        return {
            "status": "waiting",
            "message": "Belum ada menu terdeteksi dari gambar.",
            "sensor": enriched_sensor,
            "items": [],
            "overall": None,
        }

    has_sensor_values = any(
        enriched_sensor.get(field) is not None
        for field in ("temperature", "humidity", "gas_value")
    )
    detected_names = [
        detections[item_key].get("name", MENU_ITEMS[item_key]["name"])
        for item_key in detected_items
    ]

    if not has_sensor_values:
        return {
            "status": "waiting_sensor",
            "message": "Menu terdeteksi, tetapi data sensor ESP32 belum masuk.",
            "sensor": enriched_sensor,
            "detected_menu": detected_names,
            "items": [
                {
                    "item_key": item_key,
                    "name": detections[item_key].get("name", MENU_ITEMS[item_key]["name"]),
                    "score": None,
                    "status": "Menunggu sensor",
                    "level": "waiting",
                    "remaining_hours": None,
                    "time_message": "Menunggu data suhu, kelembapan, dan gas dari ESP32.",
                    "component_scores": {
                        "temperature": None,
                        "humidity": None,
                        "gas": None,
                    },
                }
                for item_key in detected_items
            ],
            "overall": None,
        }

    items = [
        calculate_item_freshness(item_key, detections[item_key], enriched_sensor)
        for item_key in detected_items
    ]
    worst_item = min(items, key=lambda item: item["score"])
    shortest_time = min(item["remaining_hours"] for item in items)
    overall_status = freshness_status(worst_item["score"])

    if any(item["emergency_gas_trigger"] for item in items):
        overall_status = freshness_status(0, emergency=True)
        worst_item = min(items, key=lambda item: item["remaining_hours"])

    return {
        "status": "success",
        "message": "Prediksi otomatis dari gambar dan sensor IoT.",
        "sensor": enriched_sensor,
        "items": items,
        "overall": {
            "score": worst_item["score"],
            "status": overall_status["label"],
            "level": overall_status["level"],
            "action": overall_status["action"],
            "remaining_hours": round(shortest_time, 2),
            "time_message": format_remaining_time_message(shortest_time),
            "critical_item": worst_item["name"],
            "sensor_live": not enriched_sensor.get("is_stale"),
        },
    }


def apply_sensor_quality_context(detection_result):
    """
    Menggabungkan hasil deteksi visual YOLO dengan status bau dari MQ135.
    YOLO mengenali makanan yang terlihat, sedangkan MQ135 menambah konteks bau.
    """
    if not sensor_indicates_spoilage(LATEST_SENSOR_DATA):
        detection_result["sensor_quality_warning"] = False
        return detection_result

    detections = detection_result.get("detections", {})
    sensor_overrides = {
        "rice": {
            "quality_label": "Indikasi Basi",
            "detected_class": "sensor_indicated_stale_rice",
            "sensor_note": "Nasi terlihat, tetapi sensor gas mendeteksi bau busuk.",
            "sensor_assisted_note": "Sensor gas mendeteksi bau busuk pada area menu nasi."
        },
        "fried_chicken": {
            "quality_label": "Indikasi Tidak Layak",
            "detected_class": "sensor_indicated_spoiled_fried_chicken",
            "sensor_note": "Ayam goreng terlihat, tetapi sensor gas mendeteksi bau busuk.",
            "sensor_assisted_note": "Ayam goreng belum terbaca visual, tetapi sensor gas mendeteksi bau busuk pada area menu."
        }
    }

    for item_key, override in sensor_overrides.items():
        item = detections.get(item_key)
        if not item:
            continue

        if item.get("detected") and item.get("acceptable"):
            item.update({
                "quality": "bad",
                "quality_label": override["quality_label"],
                "acceptable": False,
                "detected_class": override["detected_class"],
                "quality_source": "MQ135",
                "sensor_note": override["sensor_note"]
            })
        elif item_key == "fried_chicken" and not item.get("detected"):
            item.update({
                "detected": True,
                "confidence": 0.0,
                "quality": "bad",
                "quality_label": override["quality_label"],
                "acceptable": False,
                "detected_class": override["detected_class"],
                "quality_source": "MQ135",
                "sensor_note": override["sensor_assisted_note"]
            })

    detection_result["sensor_quality_warning"] = True
    detection_result["sensor_quality_note"] = (
        "Sensor MQ135 mendeteksi indikasi bau busuk. Menu ditandai tidak layak."
    )

    menu_complete = all(detections[item]["detected"] for item in MENU_ITEMS.keys())
    detection_result["menu_complete"] = menu_complete
    detection_result["visual_quality_ok"] = False
    detection_result["menu_status"] = (
        "Menu Tidak Layak - Bau Busuk Terdeteksi"
        if menu_complete
        else "Menu Belum Lengkap - Bau Busuk Terdeteksi"
    )
    return detection_result


def build_empty_detections():
    """Membuat struktur hasil kosong untuk semua menu yang wajib dicek."""
    return {
        item_key: {
            "detected": False,
            "name": item_info["name"],
            "confidence": 0.0,
            "quality": "unknown",
            "quality_label": "Belum Terdeteksi",
            "acceptable": False,
            "detected_class": None
        }
        for item_key, item_info in MENU_ITEMS.items()
    }


def build_detection_response(detections, model_used):
    """Menormalkan hasil deteksi dan menghitung status kelengkapan menu."""
    for item_key, item_info in MENU_ITEMS.items():
        detections.setdefault(item_key, {
            "detected": False,
            "name": item_info["name"],
            "confidence": 0.0,
            "quality": "unknown",
            "quality_label": "Belum Terdeteksi",
            "acceptable": False,
            "detected_class": None
        })

    menu_complete = all(detections[item]["detected"] for item in MENU_ITEMS.keys())
    visual_quality_ok = menu_complete and all(
        detections[item]["acceptable"] for item in MENU_ITEMS.keys()
    )

    if not menu_complete:
        menu_status = "Menu Belum Lengkap"
    elif visual_quality_ok:
        menu_status = "Menu Lengkap & Layak"
    else:
        menu_status = "Menu Tidak Layak"

    return {
        "status": "success",
        "detections": detections,
        "menu_status": menu_status,
        "menu_complete": menu_complete,
        "visual_quality_ok": visual_quality_ok,
        "model_used": model_used
    }


def get_model_state():
    """Mengirim status ringan model dan konfigurasi untuk dashboard."""
    model_exists = CUSTOM_MODEL_PATH.exists() and CUSTOM_MODEL_PATH.stat().st_size > 0
    try:
        import ultralytics  # noqa: F401
        yolo_import_available = True
        yolo_import_error = None
    except Exception as error:
        yolo_import_available = False
        yolo_import_error = str(error)

    return {
        "model_available": model_exists,
        "model_path": str(CUSTOM_MODEL_PATH),
        "model_mode": "custom-yolo" if model_exists else "yolo-error",
        "yolo_import_available": yolo_import_available,
        "yolo_import_error": yolo_import_error,
        "last_yolo_error": LAST_YOLO_ERROR,
        "supabase_configured": has_supabase_config(),
        "menu_items": [
            {
                "key": item_key,
                "name": item_info["name"],
                "fresh_class": item_info["fresh_class"],
                "bad_class": item_info["bad_class"]
            }
            for item_key, item_info in MENU_ITEMS.items()
        ]
    }


def yolo_error_response(message):
    """Membuat respons kosong ketika YOLO tidak bisa dijalankan."""
    return {
        **build_detection_response(build_empty_detections(), "yolo-error"),
        "message": message
    }


def get_yolo_model():
    """Memuat model YOLO sekali saja dan memuat ulang jika file model berubah."""
    global YOLO_MODEL, YOLO_MODEL_MTIME

    model_mtime = CUSTOM_MODEL_PATH.stat().st_mtime
    if YOLO_MODEL is None or YOLO_MODEL_MTIME != model_mtime:
        from ultralytics import YOLO
        YOLO_MODEL = YOLO(str(CUSTOM_MODEL_PATH))
        YOLO_MODEL_MTIME = model_mtime
        print(f"Loaded YOLO model: {CUSTOM_MODEL_PATH}")

    return YOLO_MODEL


def normalize_class_name(class_name):
    """Menyeragamkan nama kelas YOLO agar mudah dicocokkan dengan mapping."""
    return class_name.strip().lower().replace("-", "_").replace(" ", "_")


def apple_region_looks_fresh(image_path):
    """Cek warna sederhana untuk mengurangi salah deteksi apel busuk."""
    try:
        image = Image.open(image_path).convert("RGB")
        width, height = image.size

        crop_box = (0, 0, width, height)

        crop = image.crop(crop_box)
        crop.thumbnail((96, 96))
        pixels = list(crop.getdata())
        if not pixels:
            return False

        red_like = 0
        bright_like = 0
        dark_like = 0
        for red, green, blue in pixels:
            if red > 95 and red > green * 1.12 and red > blue * 1.12:
                red_like += 1
            if red + green + blue > 260:
                bright_like += 1
            if red + green + blue < 115:
                dark_like += 1

        total = len(pixels)
        red_ratio = red_like / total
        bright_ratio = bright_like / total
        dark_ratio = dark_like / total
        return red_ratio >= 0.12 and bright_ratio >= 0.28 and dark_ratio <= 0.38
    except Exception as e:
        print(f"Apple color sanity check skipped: {e}")
        return False


def apply_visual_sanity_checks(detection_result, image_path):
    """Mengoreksi false positive visual sederhana tanpa mengubah model YOLO."""
    apple = detection_result.get("detections", {}).get("apple")
    if not apple:
        return detection_result

    if (
        apple.get("detected_class") == "rotten_apple"
        and apple.get("confidence", 0) < 0.82
        and apple_region_looks_fresh(image_path)
    ):
        apple.update({
            "quality": "fresh",
            "quality_label": "Segar",
            "acceptable": True,
            "detected_class": "fresh_apple_color_corrected",
            "sensor_note": "Koreksi visual: warna apel masih dominan segar."
        })
        detection_result = build_detection_response(
            detection_result.get("detections", {}),
            detection_result.get("model_used", "custom-yolo")
        )

    return detection_result


def build_yolo_input_paths(image_path):
    """
    Membuat beberapa versi gambar untuk YOLO.
    Gambar penuh dan crop membantu makanan kecil tetap terbaca oleh model.
    """
    paths = [str(image_path)]
    temp_dir = None

    try:
        image = Image.open(image_path).convert("RGB")
        width, height = image.size

        if width < 240 or height < 180:
            return paths, temp_dir

        temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(temp_dir.name)

        enhanced_image = ImageOps.autocontrast(image)
        enhanced_image = ImageEnhance.Sharpness(enhanced_image).enhance(1.6)
        enhanced_image = ImageEnhance.Contrast(enhanced_image).enhance(1.18)
        enhanced_path = temp_path / "enhanced_full.jpg"
        enhanced_image.save(enhanced_path, quality=94)
        paths.append(str(enhanced_path))

        crop_boxes = []
        if width >= 480 and height >= 360:
            side_w = int(width * 0.72)
            side_h = int(height * 0.72)
            center_left = max(0, (width - side_w) // 2)
            center_top = max(0, (height - side_h) // 2)
            crop_boxes.append((center_left, center_top, center_left + side_w, center_top + side_h))

            half_w = int(width * 0.58)
            half_h = int(height * 0.58)
            crop_boxes.extend([
                (0, 0, half_w, half_h),
                (width - half_w, 0, width, half_h),
                (0, height - half_h, half_w, height),
                (width - half_w, height - half_h, width, height),
            ])

        for index, crop_box in enumerate(crop_boxes):
            crop = image.crop(crop_box)
            crop = ImageOps.autocontrast(crop)
            crop = ImageEnhance.Sharpness(crop).enhance(1.35)
            crop_path = temp_path / f"crop_{index}.jpg"
            crop.save(crop_path, quality=94)
            paths.append(str(crop_path))
    except Exception as crop_error:
        print(f"YOLO image enhancement skipped: {crop_error}")

    return paths, temp_dir


def detect_menu(image_path):
    """
    Mendeteksi menu makanan dari gambar menggunakan model YOLO custom.
    Model wajib tersedia di models/best.pt.
    
    Args:
        image_path: lokasi file gambar yang akan dianalisis
        
    Returns:
        dict: hasil deteksi makanan beserta confidence dan status kualitas
    """
    global LAST_YOLO_ERROR

    try:
        # Pastikan file gambar benar-benar tersedia sebelum diproses.
        if not Path(image_path).exists():
            return {
                "status": "error",
                "message": "Image file not found",
                "detections": build_empty_detections(),
                "menu_status": "Menu Belum Lengkap",
                "menu_complete": False
        }

        if not CUSTOM_MODEL_PATH.exists() or CUSTOM_MODEL_PATH.stat().st_size == 0:
            LAST_YOLO_ERROR = f"Model not found: {CUSTOM_MODEL_PATH}"
            print(f"YOLO model not found: {CUSTOM_MODEL_PATH}")
            return yolo_error_response(
                "Model YOLO models/best.pt tidak ditemukan atau file kosong."
            )

        try:
            from ultralytics import YOLO
        except Exception as import_error:
            LAST_YOLO_ERROR = f"Import error: {import_error}"
            print(f"YOLO import error: {import_error}")
            return yolo_error_response(
                "Dependency YOLO gagal dimuat. Install requirements lalu restart server."
            )
        
        # Mapping nama kelas YOLO ke kelas kualitas visual yang dipakai sistem.
        class_mapping = {
            "fresh_rice": "fresh_rice",
            "nasi_segar": "fresh_rice",
            "stale_rice": "stale_rice",
            "nasi_basi": "stale_rice",
            "fresh_fried_chicken": "fresh_fried_chicken",
            "fried_chicken": "fresh_fried_chicken",
            "chicken": "fresh_fried_chicken",
            "ayam": "fresh_fried_chicken",
            "ayam_goreng": "fresh_fried_chicken",
            "ayam_layak": "fresh_fried_chicken",
            "ayam_goreng_layak": "fresh_fried_chicken",
            "spoiled_fried_chicken": "spoiled_fried_chicken",
            "spoiled_chicken": "spoiled_fried_chicken",
            "rotten_chicken": "spoiled_fried_chicken",
            "bad_chicken": "spoiled_fried_chicken",
            "ayam_busuk": "spoiled_fried_chicken",
            "ayam_tidak_layak": "spoiled_fried_chicken",
            "ayam_goreng_tidak_layak": "spoiled_fried_chicken",
            "fresh_apple": "fresh_apple",
            "apel_segar": "fresh_apple",
            "rotten_apple": "rotten_apple",
            "apel_busuk": "rotten_apple",
            "fresh_broccoli": "fresh_broccoli",
            "brokoli_segar": "fresh_broccoli",
            "rotten_broccoli": "rotten_broccoli",
            "brokoli_busuk": "rotten_broccoli",
        }
        
        print("Using custom YOLO model")
        model = get_yolo_model()
        
        # Jalankan inferensi YOLO pada gambar asli dan variasi preprocessing.
        input_paths, temp_dir = build_yolo_input_paths(image_path)
        try:
            results = model.predict(
                input_paths,
                conf=YOLO_CONFIDENCE_THRESHOLD,
                imgsz=YOLO_IMAGE_SIZE,
                iou=0.55,
                max_det=40,
                verbose=False
            )
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()
        
        # Proses setiap bounding box hasil YOLO.
        detections = {}
        
        for result in results:
            if result.boxes is not None:
                for box in result.boxes:
                    # Ambil ID kelas dan confidence dari output YOLO.
                    class_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    
                    # Ambil nama kelas berdasarkan ID kelas dari model.
                    class_name = model.names.get(class_id, "unknown")
                    normalized_class_name = normalize_class_name(class_name)
                    
                    # Cocokkan kelas YOLO dengan menu dan status kualitas.
                    quality_class = None
                    if normalized_class_name in QUALITY_CLASSES:
                        quality_class = normalized_class_name
                    else:
                        for key_name, mapped_class in sorted(
                            class_mapping.items(),
                            key=lambda item: len(item[0]),
                            reverse=True
                        ):
                            if key_name in normalized_class_name:
                                quality_class = mapped_class
                                break

                    if quality_class and quality_class in QUALITY_CLASSES:
                        min_confidence = MIN_CONFIDENCE_BY_CLASS.get(
                            quality_class,
                            YOLO_CONFIDENCE_THRESHOLD
                        )
                        if confidence < min_confidence:
                            continue

                        class_info = QUALITY_CLASSES[quality_class]
                        menu_item = class_info["item_key"]
                        current_confidence = detections.get(menu_item, {}).get("confidence", -1)
                        if confidence <= current_confidence:
                            continue

                        detections[menu_item] = {
                            "detected": True,
                            "name": MENU_ITEMS[menu_item]["name"],
                            "confidence": round(confidence, 2),
                            "quality": class_info["quality"],
                            "quality_label": class_info["quality_label"],
                            "acceptable": class_info["acceptable"],
                            "detected_class": quality_class
                        }
        
        LAST_YOLO_ERROR = None
        return build_detection_response(detections, "custom-yolo")
    
    except Exception as e:
        LAST_YOLO_ERROR = f"{type(e).__name__}: {e}"
        print(f"YOLO error: {e}")
        if CUSTOM_MODEL_PATH.exists() and CUSTOM_MODEL_PATH.stat().st_size > 0:
            return yolo_error_response(
                "Model YOLO tersedia, tetapi gagal menjalankan deteksi. Cek log server."
            )
        return yolo_error_response(
            "Model YOLO models/best.pt tidak ditemukan atau file kosong."
        )


def save_to_supabase(image_url, menu_status, detections, freshness_prediction=None):
    """
    Menyimpan hasil deteksi ke tabel detection_history di Supabase.
    
    Args:
        image_url: URL atau path gambar
        menu_status: status menu hasil deteksi
        detections: data hasil deteksi
        freshness_prediction: data prediksi kesegaran jika kolom Supabase tersedia
    """
    if not has_supabase_config():
        return None
    
    try:
        data = {
            "image_url": image_url,
            "menu_status": menu_status,
            "detections": detections,
            "created_at": datetime.now(UTC).isoformat()
        }
        if freshness_prediction is not None:
            data["freshness_prediction"] = freshness_prediction
        
        response = insert_supabase_row("detection_history", data)
        if response is not None or freshness_prediction is None:
            return response

        data.pop("freshness_prediction", None)
        print("Retrying detection_history save without freshness_prediction field")
        return insert_supabase_row("detection_history", data)
    except Exception as e:
        print(f"Error saving to Supabase: {e}")
        return None


# Daftar route/API Flask yang dipakai dashboard dan ESP32.

@app.route("/")
def index():
    """Menampilkan halaman utama dashboard."""
    return render_template("index.html")


@app.route("/api/detect", methods=["POST"])
def api_detect():
    """
    Menerima gambar dari upload/webcam, menjalankan YOLO, dan menghitung prediksi.
    
    Format input: FormData dengan field image berisi file JPEG/PNG.
    """
    try:
        if "image" not in request.files:
            return jsonify({"status": "error", "message": "No image provided"}), 400
        
        image_file = request.files["image"]
        
        if image_file.filename == "":
            return jsonify({"status": "error", "message": "No image selected"}), 400
        
        # Buat nama file unik agar gambar capture tidak saling menimpa.
        filename = f"{uuid.uuid4().hex}.jpg"
        image_path = CAPTURES_DIR / filename
        
        # Simpan gambar ke folder static/captures.
        image_file.save(str(image_path))
        try:
            normalized_image = Image.open(image_path).convert("RGB")
            normalized_image.save(image_path, "JPEG", quality=92)
        except Exception as image_error:
            image_path.unlink(missing_ok=True)
            return jsonify({
                "status": "error",
                "message": f"File gambar tidak valid: {image_error}"
            }), 400
        # Jalankan deteksi YOLO dan koreksi kualitas berdasarkan sensor/visual.
        detection_result = detect_menu(str(image_path))
        detection_result = apply_visual_sanity_checks(
            detection_result,
            str(image_path)
        )
        detection_result = apply_sensor_quality_context(detection_result)
        freshness_prediction = calculate_freshness_prediction(
            detection_result,
            latest_sensor_for_prediction()
        )
        
        # Upload gambar ke Supabase Storage jika konfigurasi tersedia.
        local_image_url = f"/static/captures/{filename}"
        image_url = upload_capture_to_supabase(image_path, filename) or local_image_url
        menu_status = detection_result.get("menu_status", "Unknown")
        detections = detection_result.get("detections", {})
        
        history_record = {
            "id": uuid.uuid4().hex,
            "image_url": image_url,
            "menu_status": menu_status,
            "detections": detections,
            "freshness_prediction": freshness_prediction,
            "created_at": datetime.now(UTC).isoformat()
        }

        LOCAL_DETECTION_HISTORY.insert(0, history_record)
        del LOCAL_DETECTION_HISTORY[5:]

        # Simpan history deteksi dan prediksi ke Supabase jika aktif.
        save_to_supabase(image_url, menu_status, detections, freshness_prediction)
        
        # Kirim hasil akhir ke dashboard dalam format JSON.
        return jsonify({
            "status": "success",
            "image_url": image_url,
            "menu_status": menu_status,
            "menu_complete": detection_result.get("menu_complete", False),
            "visual_quality_ok": detection_result.get("visual_quality_ok", False),
            "sensor_quality_warning": detection_result.get("sensor_quality_warning", False),
            "sensor_quality_note": detection_result.get("sensor_quality_note"),
            "model_used": detection_result.get("model_used", "unknown"),
            "detections": detections,
            "freshness_prediction": freshness_prediction,
            "timestamp": history_record["created_at"]
        })
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/freshness-prediction", methods=["POST"])
def api_freshness_prediction():
    """Menghitung ulang prediksi kesegaran memakai data sensor terbaru."""
    try:
        data = request.get_json(silent=True) or {}
        detections = data.get("detections")
        if not isinstance(detections, dict):
            return jsonify({
                "status": "error",
                "message": "detections object is required"
            }), 400

        prediction = calculate_freshness_prediction(
            {"detections": detections},
            latest_sensor_for_prediction()
        )

        return jsonify({
            "status": "success",
            "freshness_prediction": prediction
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/preview-detect", methods=["POST"])
def api_preview_detect():
    """
    Deteksi ringan untuk fitur auto-capture.
    Gambar preview tidak disimpan ke history atau Supabase.
    """
    temp_path = None
    try:
        if "image" not in request.files:
            return jsonify({"status": "error", "message": "No image provided"}), 400

        image_file = request.files["image"]
        if image_file.filename == "":
            return jsonify({"status": "error", "message": "No image selected"}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
            temp_path = temp_file.name
            image_file.save(temp_path)

        detection_result = detect_menu(temp_path)
        detection_result = apply_visual_sanity_checks(
            detection_result,
            temp_path
        )
        detection_result = apply_sensor_quality_context(detection_result)

        return jsonify({
            "status": "success",
            "detections": detection_result.get("detections", {}),
            "menu_status": detection_result.get("menu_status"),
            "menu_complete": detection_result.get("menu_complete", False),
            "model_used": detection_result.get("model_used", "unknown")
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception as cleanup_error:
                print(f"Preview cleanup skipped: {cleanup_error}")


@app.route("/api/sensor", methods=["POST"])
def api_sensor():
    """
    Menerima data sensor yang dikirim ESP32.
    
    Format JSON yang diharapkan:
    {
        "temperature": 29.5,
        "humidity": 70,
        "gas_status": "Normal"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"status": "error", "message": "No JSON data provided"}), 400
        
        temperature = data.get("temperature")
        humidity = data.get("humidity")
        gas_status = data.get("gas_status", "Unknown")
        gas_value = data.get("gas_value")
        source = data.get("source", "esp32")
        
        # Validasi agar request benar-benar membawa nilai sensor.
        if temperature is None and humidity is None and gas_value is None:
            return jsonify({"status": "error", "message": "No sensor values provided"}), 400
        
        sensor_data = {
            "temperature": temperature,
            "humidity": humidity,
            "gas_status": gas_status,
            "gas_value": gas_value,
            "created_at": datetime.now(UTC).isoformat(),
            "source": source
        }

        LATEST_SENSOR_DATA.update(sensor_data)
        LOCAL_SENSOR_HISTORY.insert(0, sensor_data)
        del LOCAL_SENSOR_HISTORY[30:]

        # Simpan data sensor ke Supabase jika konfigurasi tersedia.
        if has_supabase_config():
            try:
                supabase_sensor_data = {
                    "temperature": sensor_data["temperature"],
                    "humidity": sensor_data["humidity"],
                    "gas_status": sensor_data["gas_status"],
                    "gas_value": sensor_data["gas_value"],
                    "created_at": sensor_data["created_at"]
                }
                insert_supabase_row("sensor_logs", supabase_sensor_data)
                return jsonify({"status": "success", "message": "Sensor data saved"}), 201
            except Exception as e:
                print(f"Error saving sensor data to Supabase: {e}")
                return jsonify({
                    "status": "warning",
                    "message": "Sensor data saved locally, Supabase save failed",
                    "data": sensor_data
                }), 200

        return jsonify({
            "status": "success",
            "message": "Sensor data saved locally",
            "data": sensor_data
        }), 201
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/sensor/latest", methods=["GET"])
def api_sensor_latest():
    """
    Mengambil data sensor terbaru untuk ditampilkan di dashboard.
    """
    if not has_supabase_config():
        return jsonify({
            "status": "warning",
            "message": "Supabase not configured",
            "data": enrich_sensor_data(
                LATEST_SENSOR_DATA,
                LATEST_SENSOR_DATA.get("source", "local")
            )
        }), 200
    
    try:
        data = select_supabase_latest("sensor_logs", limit=1)
        
        if data is None:
            return jsonify({
                "status": "warning",
                "message": "Supabase fetch failed, returning local sensor data",
                "data": enrich_sensor_data(
                    LATEST_SENSOR_DATA,
                    LATEST_SENSOR_DATA.get("source", "local")
                )
            }), 200

        if len(data) > 0:
            latest = data[0]
            supabase_sensor_data = {
                "temperature": latest.get("temperature"),
                "humidity": latest.get("humidity"),
                "gas_status": latest.get("gas_status"),
                "gas_value": latest.get("gas_value"),
                "created_at": latest.get("created_at")
            }
            sensor_data = freshest_sensor_data(
                ("supabase", supabase_sensor_data),
                (LATEST_SENSOR_DATA.get("source", "local"), LATEST_SENSOR_DATA)
            )
            return jsonify({
                "status": "success",
                "data": sensor_data
            }), 200
        else:
            return jsonify({
                "status": "success",
                "data": enrich_sensor_data({
                    "temperature": None,
                    "humidity": None,
                    "gas_status": "Waiting for ESP32",
                    "gas_value": None,
                    "created_at": None
                }, "local")
            }), 200
    
    except Exception as e:
        print(f"Error fetching sensor data: {e}")
        return jsonify({
            "status": "warning",
            "message": "Supabase fetch failed, returning local sensor data",
            "data": enrich_sensor_data(
                LATEST_SENSOR_DATA,
                LATEST_SENSOR_DATA.get("source", "local")
            )
        }), 200


@app.route("/api/sensor/history", methods=["GET"])
def api_sensor_history():
    """Mengambil riwayat sensor untuk grafik tren di dashboard."""
    limit = request.args.get("limit", default=20, type=int)
    limit = max(1, min(limit, 50))

    if not has_supabase_config():
        return jsonify({
            "status": "success",
            "message": "Supabase not configured",
            "data": [
                enrich_sensor_data(item, item.get("source", "local"))
                for item in LOCAL_SENSOR_HISTORY[:limit]
            ]
        }), 200

    try:
        data = select_supabase_latest("sensor_logs", limit=limit)
        if data is None:
            return jsonify({
                "status": "warning",
                "message": "Supabase fetch failed, returning local sensor history",
                "data": [
                    enrich_sensor_data(item, item.get("source", "local"))
                    for item in LOCAL_SENSOR_HISTORY[:limit]
                ]
            }), 200

        supabase_history = [
            enrich_sensor_data({
                "temperature": item.get("temperature"),
                "humidity": item.get("humidity"),
                "gas_status": item.get("gas_status"),
                "gas_value": item.get("gas_value"),
                "created_at": item.get("created_at")
            }, "supabase")
            for item in data
        ]

        local_by_time = {
            item.get("created_at"): enrich_sensor_data(item, item.get("source", "local"))
            for item in LOCAL_SENSOR_HISTORY[:limit]
            if item.get("created_at")
        }
        merged = {item.get("created_at"): item for item in supabase_history if item.get("created_at")}
        merged.update(local_by_time)
        sensor_history = sorted(
            merged.values(),
            key=lambda item: sensor_timestamp(item) or datetime.min.replace(tzinfo=UTC),
            reverse=True
        )[:limit]

        return jsonify({
            "status": "success",
            "data": sensor_history
        }), 200
    except Exception as e:
        print(f"Error fetching sensor history: {e}")
        return jsonify({
            "status": "warning",
            "message": "Sensor history fetch failed, returning local history",
            "data": [
                enrich_sensor_data(item, item.get("source", "local"))
                for item in LOCAL_SENSOR_HISTORY[:limit]
            ]
        }), 200


@app.route("/api/history", methods=["GET"])
def api_history():
    """
    Mengambil 5 riwayat deteksi terbaru.
    """
    if not has_supabase_config():
        return jsonify({
            "status": "success",
            "message": "Supabase not configured",
            "data": LOCAL_DETECTION_HISTORY[:5]
        }), 200
    
    try:
        data = select_supabase_latest("detection_history", limit=5)
        if data is None:
            return jsonify({
                "status": "warning",
                "message": "Supabase fetch failed, returning local history",
                "data": LOCAL_DETECTION_HISTORY[:5]
            }), 200
        
        return jsonify({
            "status": "success",
            "data": data if data else []
        }), 200
    
    except Exception as e:
        print(f"Error fetching history: {e}")
        return jsonify({
            "status": "warning",
            "message": "Supabase fetch failed, returning local history",
            "data": LOCAL_DETECTION_HISTORY[:5]
        }), 200


@app.route("/api/status", methods=["GET"])
def api_status():
    """Mengirim status runtime aplikasi, model YOLO, dan Supabase."""
    return jsonify({
        "status": "success",
        "data": get_model_state()
    }), 200


@app.route("/api/capture-request", methods=["POST"])
def api_capture_request():
    """
    Menerima trigger tombol fisik dari ESP32.
    Browser membaca trigger terbaru lalu menjalankan capture webcam.
    """
    requested_at = datetime.now(UTC).isoformat()
    CAPTURE_REQUEST_STATE.update({
        "id": uuid.uuid4().hex,
        "requested_at": requested_at
    })

    print(f"Capture request received at {requested_at}")
    return jsonify({
        "status": "success",
        "message": "Capture request saved",
        "data": CAPTURE_REQUEST_STATE
    }), 201


@app.route("/api/capture-request/latest", methods=["GET"])
def api_capture_request_latest():
    """Mengirim trigger tombol capture terbaru ke dashboard."""
    return jsonify({
        "status": "success",
        "data": CAPTURE_REQUEST_STATE
    }), 200


# Handler error agar respons API tetap berbentuk JSON.
@app.errorhandler(404)
def not_found(error):
    return jsonify({"status": "error", "message": "Endpoint not found"}), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({"status": "error", "message": "Internal server error"}), 500


if __name__ == "__main__":
    # Mode ini dipakai saat aplikasi dijalankan lokal dengan perintah python app.py.
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")
    app.run(debug=True, host="0.0.0.0", port=5000)
