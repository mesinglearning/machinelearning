# 🤖 YOLO v8 Integration Guide

Panduan lengkap untuk setup YOLO v8 detection pada MBG Menu Detector.

> Current demo mode: backend memakai dummy detection kalau `models/best.pt`
> belum ada. Install optional YOLO dependencies dan simpan custom model sebagai
> `models/best.pt` saat siap beralih ke deteksi AI produksi.

Gunakan 8 class berikut untuk training kualitas visual menu:

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

---

## 📦 Setup Awal (Sudah Done ✅)

Dependencies yang sudah diinstall:
```bash
pip install ultralytics opencv-python "numpy<2" pillow
```

---

## 🎯 Mode 1: Pre-trained Model (Untuk Testing)

Saat ini, aplikasi menggunakan **YOLOv8n pre-trained model** yang bisa detect objects umum:
- Bowl (untuk rice)
- Chicken (untuk fried chicken)
- Apple
- Broccoli/Brokoli (untuk broccoli)

### Cara Kerja:

1. **Model otomatis download** saat pertama kali app.py dijalankan
2. **Auto-mapping** dari YOLO class names ke menu items
3. **Confidence filtering** di `conf=0.3` (deteksi dengan confidence > 30%)

### Testing:

```bash
# Browser: http://localhost:5000
1. Klik "Start Camera"
2. Posisikan makanan di depan kamera
3. Klik "Capture & Detect"
4. Lihat hasil deteksi dengan confidence scores
```

---

## 🎓 Mode 2: Custom Trained Model (Production)

Untuk akurasi maksimal, perlu training model custom dengan dataset menu items.

### Langkah 1: Persiapkan Dataset

```
dataset/
├── images/
│   ├── train/
│   │   ├── rice_1.jpg
│   │   ├── chicken_1.jpg
│   │   └── ...
│   └── val/
│       └── ...
└── labels/
    ├── train/
    │   ├── rice_1.txt  (YOLO format)
    │   └── ...
    └── val/
        └── ...
```

Format label YOLO (.txt):
```
<class_id> <x_center> <y_center> <width> <height>
0 0.5 0.5 0.3 0.4
```

### Langkah 2: Training Script

Buat file `train_yolo.py`:

```python
from ultralytics import YOLO

# Create model
model = YOLO('yolov8n.pt')  # nano model (fastest)
# or use: 'yolov8s.pt' (small), 'yolov8m.pt' (medium)

# Train
results = model.train(
    data='dataset/data.yaml',  # path ke data config
    epochs=100,
    imgsz=640,
    patience=20,
    device=0,  # GPU device (0 untuk GPU pertama, 'cpu' untuk CPU)
    save=True,
    name='menu_detector'
)

# Test
metrics = model.val()

# Export
model.export(format='pt')  # Export sebagai PyTorch model
```

### Langkah 3: Data Config (data.yaml)

Buat file `dataset/data.yaml`:

```yaml
path: dataset/
train: images/train
val: images/val

nc: 4  # number of classes
names: ['fresh_rice', 'stale_rice', 'fresh_fried_chicken', 'spoiled_fried_chicken', 'fresh_apple', 'rotten_apple', 'fresh_broccoli', 'rotten_broccoli']
```

### Langkah 4: Jalankan Training

```bash
python train_yolo.py
```

Hasil model akan tersimpan di `runs/detect/menu_detector/weights/best.pt`

### Langkah 5: Copy ke Project

```bash
cp runs/detect/menu_detector/weights/best.pt models/best.pt
```

---

## 🔄 Model Selection Guide

| Model | Speed | Accuracy | Size | GPU Memory | Use Case |
|-------|-------|----------|------|-----------|----------|
| **YOLOv8n** | ⚡⚡⚡ Fastest | ⭐⭐⭐ | 6.3MB | Low | Live Detection, Mobile |
| **YOLOv8s** | ⚡⚡ Fast | ⭐⭐⭐⭐ | 22MB | Med | Real-time Detection |
| **YOLOv8m** | ⚡ Med | ⭐⭐⭐⭐⭐ | 50MB | High | Accuracy-focused |
| **YOLOv8l** | Slow | ⭐⭐⭐⭐⭐ | 108MB | High | Best Accuracy |

**Rekomendasi untuk MBG:**
- **Testing**: YOLOv8n (sudah ada)
- **Production**: YOLOv8s (balanced)

---

## 🔧 Code Integration

### Automatic Model Detection:

`app.py` sudah configured untuk:

```python
# Auto-check model existence
model_path = "models/best.pt"

if Path(model_path).exists():
    model = YOLO(model_path)  # Load custom model
    print("Using custom model")
else:
    model = YOLO('yolov8n.pt')  # Fallback to pre-trained
    print("Using pre-trained YOLOv8n")
```

### Class Mapping:

Update `class_mapping` di `detect_menu()` function sesuai dataset training:

```python
class_mapping = {
    "rice": "rice",
    "nasi": "rice",
    "bowl": "rice",
    "chicken": "fried_chicken",
    "ayam": "fried_chicken",
    "fried": "fried_chicken",
    "apple": "apple",
    "apel": "apple",
    "broccoli": "broccoli",
    "brokoli": "broccoli",
    "vegetable": "broccoli",
}
```

---

## 📊 Performance Tips

### Untuk Meningkatkan Akurasi:

1. **More Data** - Minimum 100 images per class
2. **Data Augmentation** - YOLO otomatis melakukan ini
3. **Longer Training** - Increase `epochs` (but watch for overfitting)
4. **Balanced Dataset** - Jumlah gambar per class harus seimbang

### Untuk Meningkatkan Speed:

1. **Smaller Model** - Gunakan YOLOv8n
2. **Lower Resolution** - Gunakan `imgsz=416` atau `imgsz=320`
3. **Batch Inference** - Deteksi multiple images sekaligus

---

## 🧪 Testing Endpoints

### Test dengan Curl:

```bash
# Upload gambar dan deteksi
curl -X POST http://localhost:5000/api/detect \
  -F "image=@test_menu.jpg"
```

Response:
```json
{
  "status": "success",
  "model_used": "yolov8n-pretrained",
  "detections": {
    "rice": {
      "detected": true,
      "name": "Nasi",
      "confidence": 0.87
    },
    "fried_chicken": {
      "detected": true,
      "name": "Ayam Goreng",
      "confidence": 0.92
    },
    "apple": {
      "detected": false,
      "name": "Apel",
      "confidence": 0.0
    },
    "broccoli": {
      "detected": true,
      "name": "Brokoli",
      "confidence": 0.78
    }
  },
  "menu_status": "Menu Belum Lengkap",
  "menu_complete": false,
  "timestamp": "2024-01-15T10:30:45"
}
```

---

## ⚠️ Troubleshooting

### Error: "No such file or directory: models/best.pt"
**Solution**: Normal! App will use pre-trained YOLOv8n. Custom model bisa ditambah nanti.

### Error: "CUDA out of memory"
**Solution**: 
- Gunakan smaller model (YOLOv8n instead of YOLOv8m)
- Reduce batch size
- Reduce image resolution

### Error: "ModuleNotFoundError: No module named 'torch'"
**Solution**: 
```bash
pip install torch torchvision torchaudio
```

### Detection terlalu lambat
**Solution**:
- Use YOLOv8n untuk inference
- Run on GPU (if available)
- Reduce confidence threshold

---

## 📚 Resources

- [Ultralytics YOLO Docs](https://docs.ultralytics.com/)
- [YOLO Training Guide](https://docs.ultralytics.com/modes/train/)
- [Roboflow for Dataset Labeling](https://roboflow.com/)
- [CVAT for Annotation](https://cvat.org/)

---

## 🚀 Next Steps

1. **For Development**: Current setup dengan YOLOv8n sudah cukup untuk testing
2. **For Production**: Collect dataset & train custom model
3. **For Deployment**: Export model & optimize untuk edge devices (if needed)

---

**Status: ✅ YOLO v8 Integration Ready!**

Silakan test detection dengan "Capture & Detect" di website! 📷

