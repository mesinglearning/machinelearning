# MBG Webcam Detector - Codex Instructions

Project ini adalah website deteksi komponen menu MBG berbasis Flask + Supabase + Webcam.

Jangan membuat ulang project dari nol kecuali diminta. Selalu baca struktur file terlebih dahulu.

Komponen dan kualitas menu yang dideteksi:
- fresh_rice / nasi segar
- stale_rice / nasi basi
- fresh_fried_chicken / ayam goreng layak
- spoiled_fried_chicken / ayam goreng tidak layak
- fresh_apple / apel segar
- rotten_apple / apel busuk
- fresh_broccoli / brokoli segar
- rotten_broccoli / brokoli busuk

Stack:
- Backend: Python Flask
- Frontend: HTML, CSS, JavaScript
- Webcam: JavaScript getUserMedia()
- Database: Supabase
- Image storage awal: static/captures
- AI detection: dummy/pretrained YOLO untuk demo, custom YOLO nanti
- Sensor: ESP32 + DHT22 + MQ135 nanti mengirim data ke /api/sensor

Prioritas:
1. Website harus bisa jalan lokal dengan python app.py.
2. Webcam harus bisa Start Camera, Capture & Detect, Stop Camera.
3. Capture harus menyimpan gambar ke static/captures.
4. /api/detect harus tetap jalan walaupun Supabase atau custom YOLO belum aktif.
5. Jangan hapus endpoint sensor.
6. Jangan taruh service_role key Supabase di frontend.
7. Gunakan .env untuk SUPABASE_URL dan SUPABASE_KEY.
8. Jika model YOLO belum ada, gunakan fallback dummy agar demo tetap berjalan.
9. Buat perubahan kecil, aman, dan mudah dites.
10. Setelah mengubah kode, jelaskan file apa yang berubah dan cara mengetesnya.
