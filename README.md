---
title: MBG Menu Detector
emoji: 🍱
colorFrom: green
colorTo: blue
sdk: docker
app_port: 8080
---

# 🍚 MBG Menu Detector - Flask + Supabase

Aplikasi web untuk deteksi kelengkapan menu makanan seimbang (Makanan Bergizi) menggunakan Flask, Supabase, dan webcam browser.

> Current demo mode: app memakai dummy detection yang aman saat `models/best.pt`
> belum tersedia. Dengan begitu Flask, webcam capture, history lokal, dan
> placeholder sensor tetap bisa berjalan tanpa dependency YOLO. Untuk produksi,
> install optional AI packages dan taruh custom model di `models/best.pt`.

Class YOLO final untuk kualitas visual menu:

```text
fresh_rice
stale_rice
fresh_fried_chicken
spoiled_fried_chicken
fresh_apple
rotten_apple
fresh_broccoli
rotten_broccoli
```

## 📋 Fitur

### Saat Ini (v1.0 - YOLO-ready Detection)
- ✅ Live webcam streaming dari browser
- ✅ **YOLO v8 custom model support** via `models/best.pt`
- ✅ Dummy detection fallback untuk demo tanpa model
- ✅ Auto-mapping dari YOLO classes ke menu items
- ✅ Capture dan detection menu items dengan confidence scores
- ✅ Sensor monitoring dashboard (placeholder untuk ESP32)
- ✅ Detection history (5 data terakhir)
- ✅ Responsive design untuk desktop & mobile
- ✅ Integration dengan Supabase untuk data persistence
- ✅ API endpoints siap untuk ESP32

### Akan Datang
- 🔜 Custom trained YOLO model untuk akurasi maksimal
- 🔜 ESP32 sensor integration (DHT22 & MQ135)
- 🔜 Supabase Storage untuk image backup
- 🔜 User authentication & dashboard user
- 🔜 Real-time monitoring & alerts

## 🛠️ Stack Teknologi

### Backend
- **Framework**: Flask 2.3.3
- **Database**: Supabase (PostgreSQL)
- **ORM**: Supabase Python Client
- **Image Processing**: OpenCV
- **CORS**: flask-cors

### Frontend
- **HTML5**: Semantic markup
- **CSS3**: Modern responsive design
- **JavaScript**: Vanilla (no framework)
- **API**: Fetch API

### Infrastructure
- **Image Storage**: Static folder (siap untuk Supabase Storage)
- **AI Model**: YOLO (placeholder, siap untuk upgrade)

## 📦 Struktur Project

```
mbg-webcam-detector/
├── app.py                      # Flask main application
├── requirements.txt            # Python dependencies
├── .env.example               # Environment variables template
├── DATABASE_SCHEMA.sql        # Supabase table schemas
├── FOOD_FRESHNESS_SYSTEM.md   # Dokumentasi logika prediksi kelayakan makanan
├── ESP32_SENSOR_SETUP.md      # ESP32 DHT22 + MQ135 setup guide
├── README.md                  # This file
├── templates/
│   └── index.html            # Main dashboard
├── static/
│   ├── css/
│   │   └── style.css         # Main stylesheet
│   ├── js/
│   │   └── main.js           # Frontend JavaScript
│   └── captures/             # Local image storage
└── models/
    └── best.pt               # YOLO model (placeholder)
└── esp32/
    └── MBG_Sensor_Node/
        └── MBG_Sensor_Node.ino
```

## 🧠 Dokumentasi Sistem Prediksi

Logika prediksi kelayakan makanan berbasis YOLO, DHT22, MQ-135, threshold per menu, Freshness Score, prediksi sisa waktu layak konsumsi, status klasifikasi, dan kalibrasi sensor dijelaskan di:

```text
FOOD_FRESHNESS_SYSTEM.md
```

## 🚀 Quick Start

### 1. Clone / Download Project
```bash
cd "d:\A. SEM 6\MESIN LEARNING\DeteksiMenuMBG"
```

### 2. Setup Python Environment

#### Option A: Using venv (Recommended for Windows)
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

#### Option B: Using conda
```bash
conda create -n mbg-detector python=3.11
conda activate mbg-detector
```

> Disarankan menggunakan Python 3.11 atau 3.12 untuk Supabase dan beberapa library AI.

### 3. Install Dependencies

Untuk menjalankan website saja:
```bash
pip install -r requirements.txt
```

Jika ingin menggunakan Supabase Python client dan environment compatible:
```bash
pip install supabase==2.0.2
```

Jika ingin menggunakan YOLO custom model:
```bash
pip install -r requirements-ai.txt
```

Untuk mengaktifkan YOLO custom model:
```bash
pip install -r requirements-ai.txt
```

Simpan model custom YOLO di:
```text
models/best.pt
```

### 4. Setup Environment Variables
```bash
# Copy .env.example ke .env
copy .env.example .env

# Edit .env dan masukkan Supabase credentials
# SUPABASE_URL=your_supabase_url
# SUPABASE_KEY=your_supabase_anon_key
```

### 5. Setup Supabase Database

Buka [Supabase Dashboard](https://app.supabase.com):

1. Buat project baru atau gunakan existing
2. Buka **SQL Editor**
3. Copy-paste seluruh kode dari `DATABASE_SCHEMA.sql`
4. Jalankan query
5. Copy **Project URL** dan **Anon Key** ke `.env`

### 6. Run Application
```bash
python app.py
```

Output akan seperti:
```
 * Running on http://0.0.0.0:5000
 * Debug mode: on
```

### 7. Akses Web
Buka browser dan buka: **http://localhost:5000**

## 📱 Cara Menggunakan

### Webcam Detection
1. Klik **Start Camera** - ijinkan browser akses webcam
2. Posisikan menu di depan kamera
3. Klik **Capture & Detect** - capture frame & kirim ke backend
4. Lihat hasil deteksi dengan confidence scores
5. Klik **Stop Camera** untuk berhenti

### API Endpoints

#### 1. GET `/` - Main Dashboard
```
http://localhost:5000/
```

#### 2. POST `/api/detect` - Detect Menu
```bash
curl -X POST http://localhost:5000/api/detect \
  -F "image=@capture.jpg"
```

Response:
```json
{
  "status": "success",
  "image_url": "/static/captures/uuid.jpg",
  "menu_status": "Menu Lengkap",
  "menu_complete": true,
  "detections": {
    "rice": {
      "detected": true,
      "name": "Nasi",
      "confidence": 0.95
    },
    "fried_chicken": {
      "detected": true,
      "name": "Ayam Goreng",
      "confidence": 0.89
    },
    "apple": {
      "detected": false,
      "name": "Apel",
      "confidence": 0.0
    },
    "broccoli": {
      "detected": true,
      "name": "Brokoli",
      "confidence": 0.92
    }
  },
  "timestamp": "2024-01-15T10:30:45.123456"
}
```

#### 3. POST `/api/sensor` - Add Sensor Data (untuk ESP32)
```bash
curl -X POST http://localhost:5000/api/sensor \
  -H "Content-Type: application/json" \
  -d '{
    "temperature": 29.5,
    "humidity": 70,
    "gas_status": "Normal",
    "gas_value": 1200
  }'
```

Response:
```json
{
  "status": "success",
  "message": "Sensor data saved"
}
```

#### 4. GET `/api/sensor/latest` - Get Latest Sensor Data
```bash
curl http://localhost:5000/api/sensor/latest
```

Response:
```json
{
  "status": "success",
  "data": {
    "temperature": 29.5,
    "humidity": 70,
    "gas_status": "Normal",
    "created_at": "2024-01-15T10:30:45.123456"
  }
}
```

#### 5. GET `/api/history` - Get Detection History (5 Latest)
```bash
curl http://localhost:5000/api/history
```

Response:
```json
{
  "status": "success",
  "data": [
    {
      "id": "uuid-1",
      "image_url": "/static/captures/uuid.jpg",
      "menu_status": "Menu Lengkap",
      "detections": {...},
      "created_at": "2024-01-15T10:30:45.123456"
    },
    ...
  ]
}
```

## 🔧 Configuration

### Flask Settings (dalam app.py)
```python
app.run(debug=True, host="0.0.0.0", port=5000)
```

### Menu Items (dalam app.py)
```python
MENU_ITEMS = {
    "rice": {"id": 1, "name": "Nasi"},
    "fried_chicken": {"id": 2, "name": "Ayam Goreng"},
    "apple": {"id": 3, "name": "Apel"},
    "broccoli": {"id": 4, "name": "Brokoli"}
}
```

## 🎯 Development Roadmap

### Phase 1: Setup (✅ Done)
- [x] Flask backend dengan endpoints
- [x] Frontend dashboard dengan webcam
- [x] Dummy detection function
- [x] Supabase integration
- [x] Responsive UI

### Phase 2: AI Enhancement (✅ Done)
- [x] YOLO v8 model integration
- [x] Pre-trained model support (YOLOv8n)
- [x] Auto-mapping dari YOLO classes ke menu items
- [x] Confidence filtering & scoring
- [ ] Custom model training guide
- [ ] Model optimization untuk real-time
- [ ] Better detection accuracy
- [ ] Confidence threshold tuning

### Phase 3: ESP32 Integration (🔜 After AI)
- [x] DHT22 sensor code
- [x] MQ135 sensor code
- [ ] Real sensor data logging
- [ ] Data visualization

### Phase 4: Production (🔜 Final)
- [ ] Supabase Storage integration
- [ ] User authentication
- [ ] Mobile app (optional)
- [ ] Cloud deployment

## 📚 Dokumentasi Lebih Lanjut

### YOLO v8 Integration ✅ (SUDAH DONE)

**Status**: YOLO v8 detection sudah fully integrated dengan app.py!

**Model saat ini:**
- Custom YOLO dipakai jika `models/best.pt` tersedia
- Dummy detection dipakai jika model belum ada atau dependency YOLO belum terinstall

**Cara mengupgrade ke custom model:**
1. Baca [YOLO_SETUP.md](YOLO_SETUP.md) untuk panduan training
2. Training custom model dengan dataset menu items
3. Install dependency AI dengan `pip install -r requirements-ai.txt`
4. Copy `best.pt` ke `models/best.pt`
5. Restart app - akan otomatis menggunakan custom model

**Testing YOLO:**
```bash
# Browser: http://localhost:5000
1. Klik "Start Camera"
2. Ambil foto makanan
3. Klik "Capture & Detect"
4. Lihat hasil deteksi dengan confidence scores
```

Untuk detail lebih lanjut, baca **[YOLO_SETUP.md](YOLO_SETUP.md)** 📖

### Untuk ESP32 Integration

Panduan lengkap ada di **[ESP32_SENSOR_SETUP.md](ESP32_SENSOR_SETUP.md)**.

Sketch Arduino tersedia di:

```text
esp32/MBG_Sensor_Node/MBG_Sensor_Node.ino
```

Gunakan Arduino IDE dan kirim POST request ke `/api/sensor`:

```cpp
// ESP32 Arduino code
void sendSensorData() {
  float temp = dht.readTemperature();
  float humidity = dht.readHumidity();
  
  HTTPClient http;
  http.begin("http://YOUR_SERVER/api/sensor");
  http.addHeader("Content-Type", "application/json");
  
  int gasValue = analogRead(34);
  String payload = "{\"temperature\":" + String(temp) + 
                   ",\"humidity\":" + String(humidity) + 
                   ",\"gas_status\":\"Normal\"," +
                   "\"gas_value\":" + String(gasValue) + "}";
  
  http.POST(payload);
  http.end();
}
```

## 🐛 Troubleshooting

### Webcam tidak bisa diakses
- Pastikan browser sudah grant permission untuk camera
- Coba di browser lain
- Restart browser

### Supabase Python client error pada Python 3.14
- Jika kamu melihat error `typing.Union object has no attribute '__module__'`, itu berarti library Supabase tidak kompatibel dengan Python 3.14.
- Solusi terbaik: gunakan Python 3.11 atau 3.12 dan install `supabase==2.0.2`.
- Jika tetap ingin jalan sekarang, Supabase akan menggunakan REST fallback tanpa client library.

### Supabase error "undefined"
- Cek `.env` file - pastikan SUPABASE_URL dan SUPABASE_KEY benar
- Cek koneksi internet
- Cek quota Supabase

### Port 5000 sudah digunakan
```bash
# Ganti port di app.py
app.run(port=5001)  # atau port lain yang kosong
```

### Image tidak tersimpan
- Cek permission folder `static/captures/`
- Pastikan folder sudah ada (script akan create otomatis)

## 📝 License

MIT License - Bebas digunakan untuk personal & commercial

## 👤 Author

MBG Menu Detector Development Team
Universitas Indonesia - Sem 6

## 📞 Support

Untuk pertanyaan atau issue, buat di folder project atau contact developer.

---

**Happy Coding! 🚀**
