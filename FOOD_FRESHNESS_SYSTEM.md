# Struktur Kerja Sistem Prediksi Kelayakan Makanan

Platform: IoT + Web  
Sensor: DHT22 + MQ-135  
Menu: MBG Indonesia

Dokumen ini menjelaskan alur logika sistem prediksi kelayakan makanan pada aplikasi MBG Menu Detector. Fokus utamanya adalah bagaimana hasil deteksi YOLO, pembacaan sensor, threshold per menu, scoring, prediksi waktu layak konsumsi, dan klasifikasi status bekerja sebagai satu sistem.

## 1. Lapisan Pertama - Input Sensor

### DHT22

DHT22 membaca dua data setiap interval waktu tertentu, misalnya setiap 5 menit:

- Suhu udara dalam derajat Celsius di sekitar wadah makanan.
- Kelembapan relatif atau relative humidity dalam persen.

Data suhu digunakan untuk memperkirakan percepatan pembusukan. Data kelembapan digunakan untuk membaca risiko jamur, fermentasi, dan kondisi lingkungan yang mempercepat kerusakan makanan.

### MQ-135

MQ-135 membaca konsentrasi gas dalam satuan ppm atau parts per million. Pada sistem ini, nilai gas dipakai sebagai indikator kondisi udara di sekitar makanan.

Gas yang paling relevan:

- Amonia atau NH3: muncul saat protein membusuk, sangat relevan untuk ayam goreng.
- CO2 berlebih: muncul saat karbohidrat atau gula mulai mengalami fermentasi, relevan untuk nasi dan apel.
- H2S atau hidrogen sulfida: berbau seperti telur busuk dan muncul pada pembusukan lanjut.

### YOLO Camera

YOLO Camera bekerja saat makanan diletakkan atau saat pengguna melakukan pemindaian awal. Kamera mengenali jenis menu secara otomatis:

- Nasi
- Ayam goreng
- Brokoli
- Apel

Hasil deteksi YOLO menjadi kunci pemilihan threshold pada lapisan berikutnya. Setelah makanan terdeteksi, kamera tidak harus terus aktif. Monitoring berikutnya bisa dilakukan oleh sensor DHT22 dan MQ-135 secara berkala.

## 2. Lapisan Kedua - Threshold Map Per Menu

Setiap jenis makanan memiliki batas toleransi yang berbeda. Sistem tidak menggunakan satu threshold global untuk semua makanan.

| Menu | Suhu Maks (C) | RH Maks (%) | Gas Maks (ppm) | Base Time Layak |
| --- | ---: | ---: | ---: | --- |
| Nasi | 35 | 80 | 200 | 4 jam |
| Ayam Goreng | 30 | 75 | 300 | 3 jam |
| Brokoli | 32 | 85 | 150 | 5 jam |
| Apel | 28 | 70 | 100 | 8 jam |

Logika tabel:

- Ayam goreng memiliki batas gas paling besar karena protein hewani menghasilkan gas pembusukan lebih cepat dibanding bahan nabati.
- Apel memiliki base time paling panjang karena kulitnya memberi perlindungan alami.
- Brokoli lebih toleran terhadap kelembapan karena sayuran memiliki kadar air tinggi.
- Nasi sensitif terhadap suhu karena kandungan pati dapat menjadi media tumbuh bakteri.

## 3. Lapisan Ketiga - Scoring Engine

Setelah data sensor masuk dan menu dikenali, sistem menghitung satu nilai utama bernama Freshness Score.

Freshness Score berada pada rentang 0 sampai 100:

- Nilai tinggi berarti makanan masih relatif segar.
- Nilai rendah berarti makanan mendekati atau sudah melewati batas aman.

Formula konseptual:

```text
Freshness Score =
  (Bobot Suhu x Skor Suhu)
  + (Bobot RH x Skor RH)
  + (Bobot Gas x Skor Gas)
```

Bobot awal yang disarankan:

| Parameter | Bobot | Alasan |
| --- | ---: | --- |
| Gas | 40% | Gas adalah indikator langsung pembusukan. |
| Suhu | 35% | Suhu tinggi mempercepat reaksi pembusukan. |
| Kelembapan | 25% | Kelembapan memperbesar risiko jamur dan fermentasi. |

Cara menghitung skor per sensor:

```text
Skor Sensor = (Threshold Maks - Nilai Aktual) / Threshold Maks x 100
```

Contoh untuk nasi:

```text
Suhu aktual = 28 C
Suhu maks nasi = 35 C
Skor suhu = (35 - 28) / 35 x 100 = 20
```

Contoh gas untuk nasi:

```text
Gas aktual = 180 ppm
Gas maks nasi = 200 ppm
Skor gas = (200 - 180) / 200 x 100 = 10
```

Catatan implementasi:

- Skor sensor perlu dibatasi pada rentang 0 sampai 100.
- Jika nilai aktual melebihi threshold, skor sensor menjadi 0.
- Semakin dekat nilai aktual ke batas maksimum, semakin rendah skor yang dihasilkan.

## 4. Lapisan Keempat - Time Prediction

Time Prediction menjawab pertanyaan utama sistem:

```text
Berapa jam lagi makanan ini masih layak dimakan?
```

Sistem menggunakan pendekatan berbasis konsep Arrhenius sederhana. Dalam industri pangan, kenaikan suhu umumnya mempercepat laju reaksi pembusukan. Secara praktis, setiap kenaikan sekitar 10 C dapat membuat pembusukan berlangsung jauh lebih cepat.

Formula konseptual:

```text
Sisa Waktu (jam) =
  Waktu Dasar x Faktor Suhu x Faktor Gas x Faktor Kelembapan
```

### Faktor Suhu

Faktor suhu dihitung dari selisih suhu aktual terhadap suhu ideal menu.

- Jika suhu aktual mendekati suhu ideal, faktor tetap tinggi.
- Jika suhu aktual jauh di atas suhu ideal, faktor turun.
- Semakin kecil faktor suhu, semakin pendek sisa waktu layak konsumsi.

### Faktor Gas

Faktor gas dihitung dari rasio gas aktual terhadap batas maksimum.

- Gas sekitar 50% dari batas maksimum berarti kondisi masih cukup baik.
- Gas sekitar 90% dari batas maksimum berarti makanan hampir mencapai batas tidak aman.
- Gas melebihi batas maksimum perlu menurunkan prediksi waktu secara drastis.

### Faktor Kelembapan

Faktor kelembapan memperhitungkan risiko jamur dan fermentasi.

- Kelembapan di bawah batas menu menjaga faktor tetap tinggi.
- Kelembapan di atas batas menu menurunkan faktor.
- Kelembapan sangat tinggi, terutama di atas 85%, harus dianggap berisiko.

Contoh:

```text
Menu: Ayam goreng
Waktu deteksi: 10.00
Suhu kotak: 32 C
Gas: 180 ppm
RH: 70%

Hasil prediksi: 1.8 jam
Batas konsumsi: sekitar 11.48
```

## 5. Lapisan Kelima - Status Klasifikasi

Freshness Score dipakai untuk menentukan status yang tampil di dashboard web.

| Score | Status | Warna | Aksi Sistem |
| --- | --- | --- | --- |
| 75-100 | AMAN | Hijau | Tampilkan sisa waktu dan monitoring normal. |
| 50-74 | WASPADA | Kuning | Kirim notifikasi ke penanggung jawab sekolah. |
| 25-49 | SEGERA HABISKAN | Oranye | Alert prioritas tinggi dan catat ke log. |
| 0-24 | BUSUK / JANGAN DIMAKAN | Merah | Alert darurat, blok distribusi, dan simpan data insiden. |

Trigger darurat:

```text
Jika gas aktual melebihi 150% dari batas maksimum menu,
status langsung menjadi BUSUK / JANGAN DIMAKAN.
```

Trigger ini menjadi pengaman tambahan agar sistem tidak hanya bergantung pada rata-rata skor.

## 6. Timeline Operasional

Alur kerja sistem dari makanan tiba sampai distribusi:

```text
Makanan tiba di sekolah
        |
        v
YOLO scan dan identifikasi menu otomatis
        |
        v
Sensor DHT22 dan MQ-135 mulai merekam setiap interval
        |
        v
Freshness Score dihitung pada setiap pembacaan
        |
        v
Prediksi sisa waktu diperbarui di dashboard web
        |
        v
Notifikasi otomatis muncul jika mendekati batas
        |
        v
Status BUSUK berarti distribusi tidak boleh dilanjutkan
```

## 7. Catatan Kalibrasi Sensor

Kalibrasi wajib dilakukan agar prediksi tidak hanya terlihat bagus di dashboard, tetapi juga akurat di lapangan.

### MQ-135

MQ-135 membutuhkan warm-up awal sekitar 24 sampai 48 jam saat pertama dipakai. Nilai gas belum stabil sebelum proses ini selesai, sehingga tidak disarankan langsung dipakai untuk pengambilan keputusan pada hari pertama pemasangan.

Hal yang perlu dicatat:

- Baseline udara bersih di lokasi sekolah.
- Nilai gas saat tidak ada makanan.
- Nilai gas saat makanan segar.
- Nilai gas saat makanan sengaja diuji dalam kondisi menurun kualitasnya.

### DHT22

DHT22 perlu dibandingkan dengan termometer dan hygrometer referensi.

Hal yang perlu dicatat:

- Offset suhu, misalnya sensor membaca 0.5 C lebih tinggi.
- Offset kelembapan, misalnya sensor membaca 2% lebih rendah.
- Koreksi offset diterapkan pada kode sebelum nilai diproses oleh scoring engine.

### Baseline Lokasi

Baseline gas berbeda di tiap lokasi. Sekolah dekat dapur, jalan raya, atau area industri dapat memiliki kadar gas ambient yang lebih tinggi.

Prosedur awal yang disarankan:

- Rekam baseline minimal 30 menit pada pagi hari sebelum makanan datang.
- Gunakan rata-rata baseline sebagai nilai nol relatif.
- Bandingkan pembacaan makanan terhadap baseline, bukan hanya terhadap angka mentah sensor.

## 8. Data Yang Disimpan Ke Database

Setiap siklus pembacaan sensor perlu menyimpan data berikut:

- Timestamp pembacaan.
- ID alat atau ID sekolah.
- Jenis menu dari hasil YOLO.
- Nilai suhu mentah dan nilai suhu terkoreksi.
- Nilai RH mentah dan nilai RH terkoreksi.
- Nilai gas mentah dan nilai gas relatif terhadap baseline.
- Freshness Score.
- Status klasifikasi.
- Prediksi sisa waktu dalam jam.
- URL gambar capture jika tersedia.

Data ini berguna untuk:

- Audit distribusi makanan.
- Melihat riwayat kualitas makanan.
- Melatih ulang model.
- Menyesuaikan threshold berdasarkan data nyata di lapangan.
- Membandingkan pola antar sekolah atau antar menu.

## 9. Rekomendasi Implementasi Modul

Pembagian logika yang disarankan:

| Modul | Tanggung Jawab |
| --- | --- |
| YOLO detection | Mengenali jenis menu dari gambar. |
| Sensor ingestion | Menerima data DHT22 dan MQ-135 dari ESP32. |
| Threshold map | Menyimpan batas aman per menu. |
| Scoring engine | Menghitung Freshness Score dari sensor dan threshold. |
| Time prediction | Menghitung prediksi sisa waktu layak konsumsi. |
| Classification | Mengubah score menjadi status dashboard. |
| Alerting | Mengirim notifikasi atau menandai kondisi darurat. |
| Persistence | Menyimpan hasil pembacaan dan prediksi ke database. |

Dengan struktur ini, sistem tetap mudah dikembangkan. Threshold bisa diperbaiki tanpa mengubah kamera, scoring bisa ditingkatkan tanpa mengubah ESP32, dan dashboard bisa membaca status akhir tanpa perlu tahu detail rumus sensor.
