import argparse
import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen


def fetch_latest_sensor(server_url):
    url = f"{server_url.rstrip('/')}/api/sensor/latest"
    with urlopen(url, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["data"]


def append_csv(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()

    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "label",
                "captured_at",
                "image_path",
                "temperature",
                "humidity",
                "gas_status",
                "gas_value",
                "source",
                "age_seconds",
                "is_stale",
                "note",
            ],
        )
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(
        description="Save a spoiled-chicken image together with the latest MQ135 odor data."
    )
    parser.add_argument(
        "--image",
        required=True,
        help="Path gambar ayam busuk, misalnya static/captures/xxx.jpg atau C:/Users/User/Downloads/ayam.jpg",
    )
    parser.add_argument("--server", default="http://127.0.0.1:5000")
    parser.add_argument("--label", default="ayam_busuk")
    parser.add_argument("--note", default="")
    parser.add_argument("--output-dir", default="data/spoiled_chicken")
    args = parser.parse_args()

    source_image = Path(args.image)
    if not source_image.exists():
        raise FileNotFoundError(f"Gambar tidak ditemukan: {source_image}")

    sensor = fetch_latest_sensor(args.server)
    if sensor.get("is_stale"):
        print("PERINGATAN: data sensor sedang stale/offline.")
        print("Pastikan ESP32 Live agar bau yang tersimpan sesuai kondisi saat gambar diambil.")

    captured_at = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    safe_suffix = source_image.suffix.lower() or ".jpg"
    target_image = image_dir / f"{args.label}-{captured_at}{safe_suffix}"
    shutil.copy2(source_image, target_image)

    row = {
        "label": args.label,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "image_path": str(target_image),
        "temperature": sensor.get("temperature"),
        "humidity": sensor.get("humidity"),
        "gas_status": sensor.get("gas_status"),
        "gas_value": sensor.get("gas_value"),
        "source": sensor.get("source"),
        "age_seconds": sensor.get("age_seconds"),
        "is_stale": sensor.get("is_stale"),
        "note": args.note,
    }

    csv_path = output_dir / "spoiled_chicken_dataset.csv"
    append_csv(csv_path, row)

    json_path = output_dir / f"{args.label}-{captured_at}.json"
    json_path.write_text(json.dumps(row, indent=2), encoding="utf-8")

    print("Sampel ayam busuk tersimpan.")
    print(f"Gambar: {target_image}")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    print(f"Gas value: {row['gas_value']}")
    print(f"Gas status: {row['gas_status']}")
    print(f"Sensor age: {row['age_seconds']} detik")


if __name__ == "__main__":
    main()
