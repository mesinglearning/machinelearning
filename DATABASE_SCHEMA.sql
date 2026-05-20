-- ============================================================================
-- MBG Menu Detector - Supabase Database Schema
-- ============================================================================
-- 
-- Jalankan SQL queries di bawah ini di Supabase SQL Editor
-- untuk membuat tabel-tabel yang diperlukan.
--
-- ============================================================================


-- ============================================================================
-- 1. Detection History Table
-- ============================================================================
-- Menyimpan riwayat hasil deteksi menu dari webcam

CREATE TABLE IF NOT EXISTS detection_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    image_url TEXT NOT NULL,
    menu_status TEXT NOT NULL,
    detections JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Create index untuk performa query
CREATE INDEX IF NOT EXISTS idx_detection_history_created_at 
    ON detection_history(created_at DESC);

-- ============================================================================
-- 2. Sensor Logs Table
-- ============================================================================
-- Menyimpan data sensor DHT22 dan MQ135 dari ESP32

CREATE TABLE IF NOT EXISTS sensor_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    temperature FLOAT8,
    humidity FLOAT8,
    gas_status TEXT,
    gas_value FLOAT8,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Safe migration jika tabel sudah pernah dibuat tanpa kolom gas_value
ALTER TABLE sensor_logs
    ADD COLUMN IF NOT EXISTS gas_value FLOAT8;

-- Safe migration jika ingin menyimpan asal data sensor, misalnya esp32/local test
ALTER TABLE sensor_logs
    ADD COLUMN IF NOT EXISTS source TEXT;

-- Create index untuk performa query
CREATE INDEX IF NOT EXISTS idx_sensor_logs_created_at 
    ON sensor_logs(created_at DESC);


-- ============================================================================
-- 3. Row Level Security (RLS) - Optional
-- ============================================================================
-- Jika menggunakan authentication, bisa uncomment RLS policies di bawah

-- Enable RLS
-- ALTER TABLE detection_history ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE sensor_logs ENABLE ROW LEVEL SECURITY;

-- Allow all users to read
-- CREATE POLICY "Allow public read on detection_history" ON detection_history
--     FOR SELECT USING (true);
-- CREATE POLICY "Allow public read on sensor_logs" ON sensor_logs
--     FOR SELECT USING (true);

-- Allow all users to insert
-- CREATE POLICY "Allow public insert on detection_history" ON detection_history
--     FOR INSERT WITH CHECK (true);
-- CREATE POLICY "Allow public insert on sensor_logs" ON sensor_logs
--     FOR INSERT WITH CHECK (true);


-- ============================================================================
-- 4. Sample Data (Optional)
-- ============================================================================
-- Uncomment untuk menambahkan sample data

-- Sample detection history
-- INSERT INTO detection_history (image_url, menu_status, detections) VALUES (
--     '/static/captures/sample.jpg',
--     'Menu Lengkap & Layak',
--     '{
--         "rice": {"detected": true, "name": "Nasi", "confidence": 0.95, "quality": "fresh", "quality_label": "Segar", "acceptable": true, "detected_class": "fresh_rice"},
--         "fried_chicken": {"detected": true, "name": "Ayam Goreng", "confidence": 0.89, "quality": "fresh", "quality_label": "Layak", "acceptable": true, "detected_class": "fresh_fried_chicken"},
--         "apple": {"detected": true, "name": "Apel", "confidence": 0.78, "quality": "fresh", "quality_label": "Segar", "acceptable": true, "detected_class": "fresh_apple"},
--         "broccoli": {"detected": true, "name": "Brokoli", "confidence": 0.92, "quality": "fresh", "quality_label": "Segar", "acceptable": true, "detected_class": "fresh_broccoli"}
--     }'
-- );

-- Sample sensor log
-- INSERT INTO sensor_logs (temperature, humidity, gas_status, gas_value) VALUES (
--     29.5,
--     70,
--     'Normal',
--     1200
-- );


-- ============================================================================
-- NOTES:
-- ============================================================================
-- 
-- 1. UUID: Menggunakan UUID untuk ID agar tidak mudah diprediksi
-- 2. JSONB: Format JSONB untuk detections memungkinkan query yang fleksibel
-- 3. Timestamps: Menggunakan TIMESTAMPTZ untuk timezone-aware timestamps
-- 4. Indexes: Indexes pada created_at untuk optimasi query ORDER BY
-- 5. RLS: Row Level Security bisa diaktifkan jika perlu authentication
--
-- ============================================================================
