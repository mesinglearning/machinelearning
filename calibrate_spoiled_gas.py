import argparse
import csv
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen


def fetch_latest_sensor(server_url):
    url = f"{server_url.rstrip('/')}/api/sensor/latest"
    with urlopen(url, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["data"]


def percentile(values, percent):
    if not values:
        return None

    sorted_values = sorted(values)
    index = (len(sorted_values) - 1) * percent
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()

    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "label",
                "captured_at",
                "temperature",
                "humidity",
                "gas_status",
                "gas_value",
                "source",
                "age_seconds",
                "is_stale",
            ],
        )
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Collect MQ135 samples from spoiled food and recommend gas thresholds."
    )
    parser.add_argument("--server", default="http://127.0.0.1:5000")
    parser.add_argument("--samples", type=int, default=18)
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--label", default="busuk")
    parser.add_argument(
        "--output",
        default="data/spoiled_gas_samples.csv",
        help="CSV output path for collected samples.",
    )
    args = parser.parse_args()

    rows = []
    gas_values = []

    print("Mulai ambil data bau busuk dari sensor.")
    print("Dekatkan makanan busuk ke MQ135 dan biarkan posisinya stabil.")
    print(f"Target: {args.samples} sampel, interval {args.interval} detik.\n")

    for index in range(1, args.samples + 1):
        data = fetch_latest_sensor(args.server)
        gas_value = data.get("gas_value")

        row = {
            "label": args.label,
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "temperature": data.get("temperature"),
            "humidity": data.get("humidity"),
            "gas_status": data.get("gas_status"),
            "gas_value": gas_value,
            "source": data.get("source"),
            "age_seconds": data.get("age_seconds"),
            "is_stale": data.get("is_stale"),
        }
        rows.append(row)

        if gas_value is not None:
            gas_values.append(float(gas_value))

        print(
            f"[{index}/{args.samples}] gas={gas_value} "
            f"status={data.get('gas_status')} age={data.get('age_seconds')}s "
            f"stale={data.get('is_stale')}"
        )

        if index < args.samples:
            time.sleep(args.interval)

    output_path = Path(args.output)
    write_csv(output_path, rows)

    if not gas_values:
        print("\nTidak ada gas_value valid. Cek ESP32 dan endpoint /api/sensor/latest.")
        return

    min_value = min(gas_values)
    max_value = max(gas_values)
    avg_value = sum(gas_values) / len(gas_values)
    p10_value = percentile(gas_values, 0.10)
    p25_value = percentile(gas_values, 0.25)

    warning_threshold = max(0, round(p10_value - 10))
    dangerous_threshold = round(avg_value + ((max_value - avg_value) * 0.5))
    if dangerous_threshold <= warning_threshold:
        dangerous_threshold = warning_threshold + 60

    summary = {
        "label": args.label,
        "samples": len(gas_values),
        "min": round(min_value, 2),
        "p10": round(p10_value, 2),
        "p25": round(p25_value, 2),
        "average": round(avg_value, 2),
        "max": round(max_value, 2),
        "recommended_warning_threshold": warning_threshold,
        "recommended_dangerous_threshold": dangerous_threshold,
    }

    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\nRingkasan data busuk:")
    print(f"- Min: {summary['min']}")
    print(f"- Rata-rata: {summary['average']}")
    print(f"- Max: {summary['max']}")
    print("\nRekomendasi awal untuk sketch ESP32:")
    print(f"const int GAS_WARNING_THRESHOLD = {warning_threshold};")
    print(f"const int GAS_DANGEROUS_THRESHOLD = {dangerous_threshold};")
    print(f"\nSampel tersimpan di: {output_path}")
    print(f"Ringkasan tersimpan di: {summary_path}")


if __name__ == "__main__":
    main()
