# ESP32 Sensor Setup - DHT22 + MQ135

Panduan ini menyiapkan ESP32 agar mengirim data sensor ke Flask endpoint:

```text
POST /api/sensor
```

Data yang dikirim:

```json
{
  "temperature": 29.5,
  "humidity": 70.0,
  "gas_status": "Normal",
  "gas_value": 1200
}
```

## 1. Hardware

Komponen:

- ESP32 DevKit
- DHT22
- MQ135 module
- Push button momentary / self reset
- Resistor 10k ohm untuk pull-up DHT22 jika modul DHT22 belum punya pull-up
- Kabel jumper
- Adaptor 5V minimal 1A, disarankan 5V 2A jika memakai MQ135

## 2. Wiring

### DHT22

| DHT22 | ESP32 |
|---|---|
| VCC | 3V3 atau 5V |
| GND | GND |
| DATA | GPIO 4 |

Jika memakai sensor DHT22 polos, pasang resistor 10k antara VCC dan DATA.

### MQ135

| MQ135 | ESP32 |
|---|---|
| VCC | 5V atau 3V3 sesuai modul |
| GND | GND |
| AO | GPIO 34 |

Penting: ADC ESP32 maksimal 3.3V. Jika output AO modul MQ135 bisa mencapai 5V,
gunakan voltage divider sebelum masuk GPIO 34.

### Push Button Capture

Sketch memakai internal pull-up ESP32, jadi tidak perlu resistor tambahan.

| Push Button | ESP32 |
|---|---|
| Pin 1 / COM | GPIO 27 |
| Pin 2 / NO | GND |

Jika tombol memiliki terminal `COM`, `NO`, dan `NC`, gunakan `COM` dan `NO`.
Saat tombol ditekan, GPIO 27 tersambung ke GND dan ESP32 akan mengirim request ke:

```text
POST /api/capture-request
```

### Power Adapter 5V

Adaptor 5V 2A cukup untuk ESP32 + DHT22 + MQ135 selama koneksinya benar.

- Jika memakai kabel USB ke port ESP32, adaptor 5V aman digunakan.
- Jika masuk lewat pin board, hubungkan adaptor 5V ke pin `VIN` / `5V`, dan ground adaptor ke `GND`.
- Jangan masukkan 5V ke pin `3V3`.
- Pastikan polaritas adaptor benar. Umumnya adaptor center-positive: tengah `+`, luar `-`.
- Saat ESP32 hanya pakai adaptor, Serial Monitor tidak bisa dibaca, tetapi sketch tetap berjalan dan tetap bisa kirim data lewat WiFi.

## 3. Arduino IDE

Install board:

```text
ESP32 by Espressif Systems
```

Install library:

```text
DHT sensor library by Adafruit
Adafruit Unified Sensor
```

## 4. Upload Sketch

Buka file:

```text
esp32/MBG_Sensor_Node/MBG_Sensor_Node.ino
```

Ubah bagian ini:

```cpp
const char* WIFI_SSID = "NAMA_WIFI_KAMU";
const char* WIFI_PASSWORD = "PASSWORD_WIFI_KAMU";
const char* SERVER_URL = "http://192.168.18.8:5000/api/sensor";
```

Gunakan IP laptop yang menjalankan Flask. Jangan pakai `localhost` di ESP32.

Cek IP laptop Windows:

```powershell
ipconfig
```

Cari `IPv4 Address`, misalnya:

```text
192.168.18.8
```

Maka server URL:

```cpp
const char* SERVER_URL = "http://192.168.18.8:5000/api/sensor";
```

## 5. Jalankan Flask

Di laptop:

```powershell
.\.venv312\Scripts\Activate.ps1
python app.py
```

Flask harus berjalan di:

```text
http://0.0.0.0:5000
```

Jika ESP32 tidak bisa connect, pastikan firewall Windows mengizinkan Python/port 5000.

## 6. Test Endpoint Tanpa ESP32

PowerShell:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:5000/api/sensor" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"temperature":29.5,"humidity":70,"gas_status":"Waspada Bau Busuk","gas_value":430}'
```

Lalu cek:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/sensor/latest"
```

## 7. Kalibrasi MQ135

Nilai awal di sketch:

```cpp
const int GAS_WARNING_THRESHOLD = 400;
const int GAS_DANGEROUS_THRESHOLD = 430;
const int GAS_SAMPLE_COUNT = 8;
const int GAS_CONFIRM_READINGS = 2;
```

Nilai ini disesuaikan untuk rangkaian yang memakai voltage divider 10k/20k pada output
AO MQ135. Dengan konfigurasi ini, gas di bawah 400 ADC dianggap `Normal`, 400-429
menjadi `Waspada Bau Busuk`, dan 430 ke atas menjadi `Bahaya Bau Busuk`.

Sketch membaca MQ135 sebanyak 8 kali dalam satu siklus lalu mengambil rata-ratanya.
Status gas juga harus muncul 2 siklus berturut-turut sebelum dianggap valid. Dengan
interval kirim 10 detik, perubahan status membutuhkan sekitar 20 detik agar lebih stabil
dan tidak mudah berubah karena noise sesaat.

Cara kalibrasi sederhana:

1. Nyalakan MQ135 beberapa menit agar stabil.
2. Catat nilai `gas_value` di udara normal.
3. Uji dekat sumber bau/gas yang aman.
4. Sesuaikan threshold agar status menjadi:
   - `Normal`
   - `Waspada Bau Busuk`
   - `Bahaya Bau Busuk`

MQ135 tidak mengenali jenis makanan secara spesifik. Sensor ini membaca perubahan gas/bau
di udara, jadi status gas sebaiknya dipakai sebagai indikator pendukung kelayakan, sedangkan
jenis/visual menu tetap dibaca oleh YOLO.

### Kalibrasi Khusus Sampel Busuk

Jika hanya tersedia makanan busuk, ambil data range busuk dengan program:

```powershell
.\.venv312\Scripts\python.exe calibrate_spoiled_gas.py --samples 18 --interval 10
```

Langkahnya:

1. Jalankan Flask server.
2. Pastikan ESP32 `Live` di dashboard.
3. Dekatkan makanan busuk ke MQ135 dan biarkan stabil.
4. Jalankan command di atas.
5. Program akan menyimpan sampel ke `data/spoiled_gas_samples.csv` dan ringkasan ke
   `data/spoiled_gas_samples.summary.json`.

Program akan memberi rekomendasi:

```cpp
const int GAS_WARNING_THRESHOLD = ...;
const int GAS_DANGEROUS_THRESHOLD = ...;
```

Karena data normal belum tersedia, threshold dari program ini dibuat agar range bau busuk
yang diuji masuk kategori `Waspada Bau Busuk` atau `Bahaya Bau Busuk`.
