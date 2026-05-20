import os
import json
import uuid
import random
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

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Supabase Configuration - Lazy load to avoid import issues
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "captures")
HAS_SUPABASE = False
SUPABASE_CLIENT_TRIED = False

def get_supabase_client():
    """Lazy load Supabase client"""
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
    return bool(SUPABASE_URL and SUPABASE_KEY)


def upload_capture_to_supabase(image_path, filename):
    """Upload a captured image to Supabase Storage and return its public URL."""
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
    """Call Supabase REST API directly when the Python client is unavailable."""
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


# Configuration
CAPTURES_DIR = Path("static/captures")
CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
CUSTOM_MODEL_PATH = Path("models/best.pt")
YOLO_CONFIDENCE_THRESHOLD = 0.18
YOLO_IMAGE_SIZE = 640
LOCAL_DETECTION_HISTORY = []
LOCAL_SENSOR_HISTORY = []
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


def parse_iso_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def sensor_timestamp(data):
    return parse_iso_datetime((data or {}).get("created_at"))


def enrich_sensor_data(data, source="local"):
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
    available = [
        (source, data)
        for source, data in sensor_sources
        if data and sensor_timestamp(data) is not None
    ]

    if not available:
        return enrich_sensor_data(LATEST_SENSOR_DATA, "local")

    source, data = max(available, key=lambda item: sensor_timestamp(item[1]))
    return enrich_sensor_data(data, source)

# Menu components
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

MIN_CONFIDENCE_BY_CLASS = {
    "fresh_rice": 0.25,
    "stale_rice": 0.25,
    "fresh_fried_chicken": 0.10,
    "spoiled_fried_chicken": 0.10,
    "fresh_apple": 0.30,
    "rotten_apple": 0.30,
    "fresh_broccoli": 0.18,
    "rotten_broccoli": 0.18,
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
    """Return True when recent MQ135 status indicates spoiled-food odor."""
    enriched = enrich_sensor_data(sensor_data, sensor_data.get("source", "local"))
    if enriched.get("is_stale"):
        return False

    gas_status = str(enriched.get("gas_status") or "").lower()
    if "warming" in gas_status:
        return False

    return any(keyword in gas_status for keyword in GAS_SPOILAGE_KEYWORDS)


def apply_sensor_quality_context(detection_result):
    """
    Fuse visual detection with MQ135 odor status.
    YOLO identifies visible food; MQ135 adds freshness/odor context.
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
    """Return the standard detection shape for all required menu items."""
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
    """Normalize detection results and calculate menu completeness and quality."""
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
    """Return lightweight runtime status for the dashboard."""
    model_exists = CUSTOM_MODEL_PATH.exists() and CUSTOM_MODEL_PATH.stat().st_size > 0
    return {
        "model_available": model_exists,
        "model_path": str(CUSTOM_MODEL_PATH),
        "model_mode": "custom-yolo" if model_exists else "dummy",
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


def dummy_detect_menu(image_path):
    """
    Safe demo detector used when a custom YOLO model is not available.
    The result is deterministic per image path, so repeated reads are stable.
    """
    seed = Path(image_path).name
    rng = random.Random(seed)
    detections = {}

    for item_key, item_info in MENU_ITEMS.items():
        detected = rng.random() >= 0.35
        acceptable = detected and rng.random() >= 0.2
        quality = "fresh" if acceptable else "bad"
        detections[item_key] = {
            "detected": detected,
            "name": item_info["name"],
            "confidence": round(rng.uniform(0.65, 0.95), 2) if detected else 0.0,
            "quality": quality if detected else "unknown",
            "quality_label": (
                item_info["fresh_label"] if acceptable else item_info["bad_label"]
            ) if detected else "Belum Terdeteksi",
            "acceptable": acceptable,
            "detected_class": (
                item_info["fresh_class"] if acceptable else item_info["bad_class"]
            ) if detected else None
        }

    return build_detection_response(detections, "dummy")


def normalize_class_name(class_name):
    return class_name.strip().lower().replace("-", "_").replace(" ", "_")


def parse_roi_config(raw_config):
    if not raw_config:
        return None

    try:
        config = json.loads(raw_config)
    except (TypeError, json.JSONDecodeError):
        return None

    parsed = {}
    for item_key in MENU_ITEMS.keys():
        roi = config.get(item_key)
        if not isinstance(roi, dict):
            continue

        try:
            left = float(roi.get("left"))
            top = float(roi.get("top"))
            width = float(roi.get("width"))
            height = float(roi.get("height"))
        except (TypeError, ValueError):
            continue

        left = max(0, min(left, 95))
        top = max(0, min(top, 95))
        width = max(5, min(width, 100 - left))
        height = max(5, min(height, 100 - top))
        parsed[item_key] = {
            "left": left,
            "top": top,
            "width": width,
            "height": height
        }

    return parsed or None


def roi_percent_to_box(roi, width, height):
    x1 = int(width * roi["left"] / 100)
    y1 = int(height * roi["top"] / 100)
    x2 = int(width * (roi["left"] + roi["width"]) / 100)
    y2 = int(height * (roi["top"] + roi["height"]) / 100)
    return (x1, y1, x2, y2)


def apple_region_looks_fresh(image_path, roi_config=None):
    """Use a simple color sanity check to reduce false rotten-apple detections."""
    try:
        image = Image.open(image_path).convert("RGB")
        width, height = image.size

        if roi_config and "apple" in roi_config:
            crop_box = roi_percent_to_box(roi_config["apple"], width, height)
        else:
            crop_box = (
                int(width * 0.12),
                int(height * 0.06),
                int(width * 0.46),
                int(height * 0.45)
            )

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


def apply_visual_sanity_checks(detection_result, image_path, roi_config=None):
    """Correct obvious visual false positives without changing the YOLO model."""
    apple = detection_result.get("detections", {}).get("apple")
    if not apple:
        return detection_result

    if (
        apple.get("detected_class") == "rotten_apple"
        and apple.get("confidence", 0) < 0.82
        and apple_region_looks_fresh(image_path, roi_config)
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


def build_yolo_input_paths(image_path, roi_config=None):
    """
    Return the full frame plus temporary crops for tray-style images.
    The crop pass helps small food compartments get analyzed at a larger scale.
    """
    paths = [str(image_path)]
    temp_dir = None

    try:
        image = Image.open(image_path)
        width, height = image.size

        if width < 360 or height < 260:
            return paths, temp_dir

        temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(temp_dir.name)

        enhanced_image = ImageOps.autocontrast(image.convert("RGB"))
        enhanced_image = ImageEnhance.Sharpness(enhanced_image).enhance(1.6)
        enhanced_image = ImageEnhance.Contrast(enhanced_image).enhance(1.18)
        enhanced_path = temp_path / "enhanced_full.jpg"
        enhanced_image.save(enhanced_path, quality=94)
        paths.append(str(enhanced_path))

        # Fixed tray layout ROIs based on the current plate position:
        # apple top-left, rice top-right, broccoli bottom-left, chicken bottom-middle.
        crop_boxes = [
            (int(width * 0.12), int(height * 0.06), int(width * 0.46), int(height * 0.45)),
            (int(width * 0.28), int(height * 0.06), int(width * 0.58), int(height * 0.46)),
            (int(width * 0.12), int(height * 0.40), int(width * 0.50), int(height * 0.90)),
            (int(width * 0.33), int(height * 0.38), int(width * 0.68), int(height * 0.94)),
        ]

        if roi_config:
            for roi in roi_config.values():
                crop_boxes.append(roi_percent_to_box(roi, width, height))

        for index, box in enumerate(crop_boxes, start=1):
            x1, y1, x2, y2 = box
            if x2 - x1 < 120 or y2 - y1 < 120:
                continue

            crop = image.crop((x1, y1, x2, y2))
            crop_path = temp_path / f"crop_{index}.jpg"
            crop.save(crop_path, quality=92)
            paths.append(str(crop_path))
    except Exception as crop_error:
        print(f"YOLO crop helper skipped: {crop_error}")

    return paths, temp_dir


def detect_menu(image_path, roi_config=None):
    """
    Menu detection for food items.
    Uses custom YOLO when models/best.pt exists, otherwise uses safe dummy data.
    
    Args:
        image_path: Path to the captured image
        
    Returns:
        dict: Detection results with detected items and confidence scores
    """
    try:
        # Verify image exists
        if not Path(image_path).exists():
            return {
                "status": "error",
                "message": "Image file not found",
                "detections": build_empty_detections(),
                "menu_status": "Menu Belum Lengkap",
                "menu_complete": False
        }

        if not CUSTOM_MODEL_PATH.exists():
            print("YOLO model not found, using dummy detection")
            return dummy_detect_menu(image_path)

        try:
            from ultralytics import YOLO
        except Exception as import_error:
            print(f"YOLO error, fallback to dummy detection: {import_error}")
            return dummy_detect_menu(image_path)
        
        # Map class names to visual quality classes
        # This mapping can be customized based on YOLO model training
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
        model = YOLO(str(CUSTOM_MODEL_PATH))
        
        # Run inference
        input_paths, temp_dir = build_yolo_input_paths(image_path, roi_config=roi_config)
        try:
            results = model.predict(
                input_paths,
                conf=YOLO_CONFIDENCE_THRESHOLD,
                imgsz=YOLO_IMAGE_SIZE,
                verbose=False
            )
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()
        
        # Process results
        detections = {}
        detected_items = set()
        
        for result in results:
            if result.boxes is not None:
                for box in result.boxes:
                    # Get class name and confidence
                    class_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    
                    # Get class name from model
                    class_name = model.names.get(class_id, "unknown")
                    normalized_class_name = normalize_class_name(class_name)
                    
                    # Map to quality class
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

                        detected_items.add(menu_item)
                        detections[menu_item] = {
                            "detected": True,
                            "name": MENU_ITEMS[menu_item]["name"],
                            "confidence": round(confidence, 2),
                            "quality": class_info["quality"],
                            "quality_label": class_info["quality_label"],
                            "acceptable": class_info["acceptable"],
                            "detected_class": quality_class
                        }
        
        return build_detection_response(detections, "custom-yolo")
    
    except Exception as e:
        print(f"YOLO error, fallback to dummy detection: {e}")
        return dummy_detect_menu(image_path)


def save_to_supabase(image_url, menu_status, detections):
    """
    Save detection results to Supabase detection_history table.
    
    Args:
        image_url: URL or path to the image
        menu_status: "Menu Lengkap" or "Menu Belum Lengkap"
        detections: dict with detection results
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
        
        return insert_supabase_row("detection_history", data)
    except Exception as e:
        print(f"Error saving to Supabase: {e}")
        return None


# Routes

@app.route("/")
def index():
    """Render main dashboard"""
    return render_template("index.html")


@app.route("/api/detect", methods=["POST"])
def api_detect():
    """
    Detect menu items from uploaded image.
    
    Expected: FormData with 'image' field (JPEG/PNG)
    """
    try:
        if "image" not in request.files:
            return jsonify({"status": "error", "message": "No image provided"}), 400
        
        image_file = request.files["image"]
        
        if image_file.filename == "":
            return jsonify({"status": "error", "message": "No image selected"}), 400
        
        # Generate unique filename
        filename = f"{uuid.uuid4().hex}.jpg"
        image_path = CAPTURES_DIR / filename
        
        # Save image
        image_file.save(str(image_path))
        roi_config = parse_roi_config(request.form.get("roi_config"))
        
        # Run detection
        detection_result = detect_menu(str(image_path), roi_config=roi_config)
        detection_result = apply_visual_sanity_checks(
            detection_result,
            str(image_path),
            roi_config=roi_config
        )
        detection_result = apply_sensor_quality_context(detection_result)
        
        # Upload image to Supabase Storage when configured.
        local_image_url = f"/static/captures/{filename}"
        image_url = upload_capture_to_supabase(image_path, filename) or local_image_url
        menu_status = detection_result.get("menu_status", "Unknown")
        detections = detection_result.get("detections", {})
        
        history_record = {
            "id": uuid.uuid4().hex,
            "image_url": image_url,
            "menu_status": menu_status,
            "detections": detections,
            "created_at": datetime.now(UTC).isoformat()
        }

        LOCAL_DETECTION_HISTORY.insert(0, history_record)
        del LOCAL_DETECTION_HISTORY[5:]

        # Save to Supabase (if configured)
        save_to_supabase(image_url, menu_status, detections)
        
        # Return result
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
            "timestamp": history_record["created_at"]
        })
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/preview-detect", methods=["POST"])
def api_preview_detect():
    """
    Lightweight detection for live ROI guidance.
    It does not save images, history, or Supabase records.
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

        roi_config = parse_roi_config(request.form.get("roi_config"))
        detection_result = detect_menu(temp_path, roi_config=roi_config)
        detection_result = apply_visual_sanity_checks(
            detection_result,
            temp_path,
            roi_config=roi_config
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
    Receive sensor data from ESP32.
    
    Expected JSON:
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
        
        # Validation
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

        # Save to Supabase (if configured)
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
    Get latest sensor data.
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
    """Get recent sensor readings for dashboard trends."""
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
    Get last 5 detection history records.
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
    """Return dashboard runtime status."""
    return jsonify({
        "status": "success",
        "data": get_model_state()
    }), 200


@app.route("/api/capture-request", methods=["POST"])
def api_capture_request():
    """
    Receive a physical capture button trigger from ESP32.
    The browser polls the latest trigger and runs webcam capture locally.
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
    """Return the latest physical capture button trigger."""
    return jsonify({
        "status": "success",
        "data": CAPTURE_REQUEST_STATE
    }), 200


# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"status": "error", "message": "Endpoint not found"}), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({"status": "error", "message": "Internal server error"}), 500


if __name__ == "__main__":
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")
    app.run(debug=True, host="0.0.0.0", port=5000)
