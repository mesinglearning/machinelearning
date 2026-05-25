// ============================================================================
// MBG Menu Detector - Frontend JavaScript
// ============================================================================

class MenuDetector {
    constructor() {
        this.video = document.getElementById('webcam');
        this.canvas = document.getElementById('canvas');
        this.startBtn = document.getElementById('startBtn');
        this.captureBtn = document.getElementById('captureBtn');
        this.stopBtn = document.getElementById('stopBtn');
        this.imageUpload = document.getElementById('imageUpload');
        this.uploadDetectBtn = document.getElementById('uploadDetectBtn');
        this.cameraFrame = document.querySelector('.camera-frame');
        this.cameraModeBadge = document.getElementById('cameraModeBadge');
        this.detectProgress = document.getElementById('detectProgress');
        this.detectProgressTitle = document.getElementById('detectProgressTitle');
        this.detectProgressText = document.getElementById('detectProgressText');
        this.startBtnStatus = document.getElementById('startBtnStatus');
        this.captureBtnStatus = document.getElementById('captureBtnStatus');
        this.stopBtnStatus = document.getElementById('stopBtnStatus');
        this.uploadBtnStatus = document.getElementById('uploadBtnStatus');
        this.loading = document.getElementById('loading');
        this.resultsSection = document.getElementById('resultsSection');
        this.detectionItems = document.getElementById('detectionItems');
        this.capturedImage = document.getElementById('capturedImage');
        this.menuStatus = document.getElementById('menuStatus');
        this.historyList = document.getElementById('historyList');
        this.cameraState = document.getElementById('cameraState');
        this.modelState = document.getElementById('modelState');
        this.modelMeta = document.getElementById('modelMeta');
        this.sensorState = document.getElementById('sensorState');
        this.historyCount = document.getElementById('historyCount');
        this.notification = document.getElementById('notification');
        this.analysisSummary = document.getElementById('analysisSummary');
        this.deviceStatusBadge = document.getElementById('deviceStatusBadge');
        this.deviceStatusText = document.getElementById('deviceStatusText');
        this.deviceLastSeen = document.getElementById('deviceLastSeen');
        this.deviceSource = document.getElementById('deviceSource');
        this.captureTriggerState = document.getElementById('captureTriggerState');
        this.tempChart = document.getElementById('tempChart');
        this.humidChart = document.getElementById('humidChart');
        this.gasChart = document.getElementById('gasChart');
        this.freshnessPanel = document.getElementById('freshnessPanel');
        this.freshnessItems = document.getElementById('freshnessItems');

        this.mediaStream = null;
        this.menuKeys = ['rice', 'fried_chicken', 'apple', 'broccoli'];
        this.lastCaptureRequestId = null;
        this.captureRequestReady = false;
        this.isDetecting = false;
        this.notificationTimer = null;
        this.sensorStaleNotified = false;
        this.lastDetections = null;
        this.lastFreshnessSensorAt = null;

        this.initEventListeners();
        this.loadAppStatus();
        this.loadSensorData();
        this.loadSensorHistory();
        this.loadDetectionHistory();
        this.loadCaptureRequest();

        // Auto-load sensor data every 5 seconds
        setInterval(() => this.loadSensorData(), 5000);
        // Auto-load sensor trend data every 10 seconds
        setInterval(() => this.loadSensorHistory(), 10000);
        // Auto-load history every 10 seconds
        setInterval(() => this.loadDetectionHistory(), 10000);
        // Poll physical ESP32 capture button every second
        setInterval(() => this.loadCaptureRequest(), 1000);
    }

    // ========================================================================
    // Event Listeners
    // ========================================================================

    initEventListeners() {
        this.startBtn.addEventListener('click', () => this.startCamera());
        this.captureBtn.addEventListener('click', () => this.captureAndDetect());
        this.stopBtn.addEventListener('click', () => this.stopCamera());
        this.imageUpload?.addEventListener('change', () => {
            const hasFile = Boolean(this.imageUpload.files?.length);
            this.uploadDetectBtn.disabled = !hasFile || this.isDetecting;
            this.updateSummary(this.uploadBtnStatus, hasFile ? 'Siap dianalisis' : 'Pilih gambar dulu');
        });
        this.uploadDetectBtn?.addEventListener('click', () => this.detectUploadedImage());
    }

    // ========================================================================
    // Camera Functions
    // ========================================================================

    async startCamera() {
        try {
            this.setDetectionProgress(true, 'Mengaktifkan kamera...', 'Meminta izin kamera dari browser.');
            this.startBtn.disabled = true;
            this.updateSummary(this.startBtnStatus, 'Mengaktifkan...');

            const constraints = {
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    facingMode: 'user'
                },
                audio: false
            };

            this.mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
            this.video.srcObject = this.mediaStream;
            await this.waitForVideoReady();
            await this.video.play();

            // Enable buttons
            this.startBtn.disabled = true;
            this.captureBtn.disabled = false;
            this.stopBtn.disabled = false;
            this.updateSummary(this.cameraState, 'Aktif');
            this.updateSummary(this.cameraModeBadge, 'Kamera aktif');
            this.updateSummary(this.startBtnStatus, 'Aktif');
            this.updateSummary(this.captureBtnStatus, 'Siap capture');
            this.updateSummary(this.stopBtnStatus, 'Klik untuk berhenti');
            this.cameraFrame?.classList.add('camera-active');

            this.setDetectionProgress(false);
            this.showNotification('Kamera aktif. Menu siap dicapture.', 'success');
        } catch (error) {
            console.error('Error accessing camera:', error);
            this.cleanupCameraStream();
            this.startBtn.disabled = false;
            this.captureBtn.disabled = true;
            this.stopBtn.disabled = true;
            this.setDetectionProgress(false);
            this.updateSummary(this.cameraState, 'Error');
            this.updateSummary(this.cameraModeBadge, 'Kamera error');
            this.updateSummary(this.startBtnStatus, 'Coba lagi');
            this.updateSummary(this.captureBtnStatus, 'Kamera belum aktif');
            this.updateSummary(this.stopBtnStatus, 'Tidak aktif');
            this.showNotification('Kamera tidak bisa diakses. Cek izin browser atau perangkat kamera.', 'error');
        }
    }

    stopCamera() {
        this.cleanupCameraStream();

        // Disable buttons
        this.startBtn.disabled = false;
        this.captureBtn.disabled = true;
        this.stopBtn.disabled = true;
        this.updateSummary(this.cameraState, 'Standby');
        this.updateSummary(this.cameraModeBadge, 'Standby');
        this.updateSummary(this.startBtnStatus, 'Standby');
        this.updateSummary(this.captureBtnStatus, 'Aktif setelah kamera menyala');
        this.updateSummary(this.stopBtnStatus, 'Tidak aktif');
        this.showNotification('Kamera dihentikan.', 'info');
    }

    cleanupCameraStream() {
        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
            this.mediaStream = null;
        }

        this.video.srcObject = null;
        this.cameraFrame?.classList.remove('camera-active');
    }

    waitForVideoReady() {
        if (this.video.readyState >= 2 && this.video.videoWidth > 0) {
            return Promise.resolve();
        }

        return new Promise((resolve, reject) => {
            const timeout = window.setTimeout(() => {
                reject(new Error('Camera stream belum mengirim frame.'));
            }, 7000);

            this.video.onloadedmetadata = () => {
                window.clearTimeout(timeout);
                resolve();
            };
        });
    }

    // ========================================================================
    // Capture and Detection
    // ========================================================================

    async captureAndDetect() {
        if (!this.mediaStream || this.video.readyState < 2) {
            this.showNotification('Camera belum aktif. Klik Start Camera dulu.', 'warning');
            return;
        }

        if (!this.video.videoWidth || !this.video.videoHeight) {
            this.showNotification('Frame kamera belum terbaca. Tunggu sebentar lalu coba capture lagi.', 'warning');
            return;
        }

        if (this.isDetecting) {
            return;
        }

        try {
            this.isDetecting = true;
            this.captureBtn.disabled = true;
            this.uploadDetectBtn.disabled = true;
            this.updateSummary(this.captureBtnStatus, 'Mengambil frame...');
            this.setDetectionProgress(true, 'Mengambil gambar...', 'Frame kamera sedang disiapkan untuk YOLO.');

            // Capture frame from video
            const ctx = this.canvas.getContext('2d');
            this.canvas.width = this.video.videoWidth;
            this.canvas.height = this.video.videoHeight;
            ctx.drawImage(this.video, 0, 0);

            // Convert canvas to blob (JPEG)
            const blob = await this.canvasToBlob(this.canvas, 'image/jpeg', 0.9);

            // Send to Flask backend
            await this.sendImageForDetection(blob, 'capture.jpg', 'Menganalisis capture...', 'YOLO membaca menu lalu sistem menggabungkan data sensor.');

            this.setDetectionProgress(false);
        } catch (error) {
            console.error('Error during capture:', error);
            this.updateSummary(this.modelState, 'Error');
            this.showNotification('Capture error: ' + error.message, 'error');
            this.setDetectionProgress(false);
        } finally {
            this.isDetecting = false;
            if (this.mediaStream) {
                this.captureBtn.disabled = false;
                this.updateSummary(this.captureBtnStatus, 'Siap capture lagi');
            }
            this.uploadDetectBtn.disabled = !this.imageUpload?.files?.length;
        }
    }

    async detectUploadedImage() {
        const file = this.imageUpload?.files?.[0];
        if (!file) {
            this.showNotification('Pilih gambar menu terlebih dahulu.', 'warning');
            return;
        }

        if (this.isDetecting) {
            return;
        }

        try {
            this.isDetecting = true;
            this.uploadDetectBtn.disabled = true;
            this.captureBtn.disabled = true;
            this.updateSummary(this.uploadBtnStatus, 'Mengunggah...');
            this.setDetectionProgress(true, 'Menganalisis upload...', 'Gambar menu sedang dikirim ke model deteksi.');
            await this.sendImageForDetection(file, file.name || 'uploaded-menu.jpg', 'Menganalisis upload...', 'YOLO membaca gambar penuh tanpa ROI manual.');
        } catch (error) {
            console.error('Error detecting uploaded image:', error);
            this.updateSummary(this.modelState, 'Error');
            this.showNotification('Upload detection error: ' + error.message, 'error');
            this.setDetectionProgress(false);
        } finally {
            this.isDetecting = false;
            this.uploadDetectBtn.disabled = !this.imageUpload?.files?.length;
            this.captureBtn.disabled = !this.mediaStream;
            this.updateSummary(this.uploadBtnStatus, this.imageUpload?.files?.length ? 'Siap dianalisis lagi' : 'Pilih gambar dulu');
            if (this.mediaStream) {
                this.updateSummary(this.captureBtnStatus, 'Siap capture');
            }
        }
    }

    async sendImageForDetection(imageBlob, filename, title = 'Memproses gambar...', text = 'Menjalankan deteksi dan prediksi kesegaran.') {
        this.setDetectionProgress(true, title, text);
        const formData = new FormData();
        formData.append('image', imageBlob, filename);

        const response = await fetch('/api/detect', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.status === 'success') {
            this.displayResults(result);
            this.loadDetectionHistory();
            this.updateModelMode(result.model_used);
            this.updateSummary(this.uploadBtnStatus, this.imageUpload?.files?.length ? 'Hasil sudah diperbarui' : 'Pilih gambar dulu');
            this.updateSummary(this.captureBtnStatus, this.mediaStream ? 'Hasil sudah diperbarui' : 'Aktif setelah kamera menyala');
            this.showNotification('Deteksi selesai. Hasil analisis sudah diperbarui.', 'success');
        } else {
            this.showNotification('Detection failed: ' + result.message, 'error');
        }

        this.setDetectionProgress(false);
    }

    setDetectionProgress(isVisible, title = '', text = '') {
        if (!this.detectProgress) return;

        this.detectProgress.classList.toggle('hidden', !isVisible);
        this.loading?.classList.add('hidden');
        if (title) this.updateSummary(this.detectProgressTitle, title);
        if (text) this.updateSummary(this.detectProgressText, text);
    }

    canvasToBlob(canvas, type = 'image/jpeg', quality = 0.9) {
        return new Promise(resolve => {
            canvas.toBlob(resolve, type, quality);
        });
    }

    clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    }

    // ========================================================================
    // Display Results
    // ========================================================================

    displayResults(result) {
        // Show results section
        this.resultsSection.style.display = 'block';

        // Display captured image
        this.capturedImage.src = result.image_url;
        this.lastDetections = result.detections || null;
        this.lastFreshnessSensorAt = result.freshness_prediction?.sensor?.created_at || null;
        this.renderAnalysisSummary(result);
        this.renderFreshnessPrediction(result.freshness_prediction);

        // Display detection items
        this.detectionItems.innerHTML = '';
        for (const key of this.menuKeys) {
            const detection = result.detections[key];
            if (!detection) continue;
            const detected = detection.detected;
            const acceptable = detected && detection.acceptable;
            const itemClass = acceptable ? 'detected' : 'not-detected';
            const badgeClass = acceptable ? 'badge-detected' : 'badge-not-detected';
            const badgeText = detected ? detection.quality_label : 'Not Detected';
            const sensorNote = detection.sensor_note
                ? `<div class="detection-confidence sensor-note">${this.escapeHtml(detection.sensor_note)}</div>`
                : '';
            const html = `
                <div class="detection-item ${itemClass}">
                    <div class="detection-info">
                        <div class="detection-name">${this.escapeHtml(detection.name)}</div>
                        <div class="detection-confidence">
                            Confidence: ${(detection.confidence * 100).toFixed(1)}%
                        </div>
                        <div class="detection-confidence">
                            Status: ${this.escapeHtml(detected ? detection.quality_label : 'Belum Terdeteksi')}
                        </div>
                        ${sensorNote}
                    </div>
                    <span class="detection-badge ${badgeClass}">
                        ${this.escapeHtml(badgeText)}
                    </span>
                </div>
            `;
            this.detectionItems.innerHTML += html;
        }

        // Display menu status
        const isComplete = result.menu_complete;
        const isUnsafe = (result.menu_status || '').includes('Tidak Layak') ||
            (result.menu_status || '').includes('Bau Busuk');
        const statusClass = isUnsafe ? 'danger' : (isComplete ? 'complete' : 'incomplete');
        const statusText = result.menu_status;

        this.menuStatus.className = `menu-status ${statusClass}`;
        this.menuStatus.textContent = statusText;

        // Scroll to results
        this.resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    async refreshFreshnessPrediction() {
        if (!this.lastDetections) return;

        try {
            const response = await fetch('/api/freshness-prediction', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ detections: this.lastDetections })
            });
            const result = await response.json();
            if (result.status === 'success') {
                this.renderFreshnessPrediction(result.freshness_prediction);
            }
        } catch (error) {
            console.error('Error refreshing freshness prediction:', error);
        }
    }

    renderFreshnessPrediction(prediction) {
        if (!this.freshnessPanel) return;

        if (!prediction || !prediction.overall) {
            this.freshnessPanel.className = 'freshness-panel';
            this.freshnessItems.innerHTML = prediction?.items?.length
                ? prediction.items.map(item => `
                    <div class="freshness-item freshness-item-waiting">
                        <div>
                            <strong>${this.escapeHtml(item.name)}</strong>
                            <span>${this.escapeHtml(item.time_message || item.status)}</span>
                        </div>
                        <div class="freshness-item-score">--</div>
                        <div class="freshness-detail-grid">
                            <span>Kelayakan: <strong>Menunggu sensor</strong></span>
                            <span>Menuju tidak layak: <strong>--</strong></span>
                            <span>Sensor: <strong>${this.escapeHtml(prediction?.sensor?.connection_status || 'Menunggu ESP32')}</strong></span>
                        </div>
                        <div class="freshness-breakdown">
                            <span>Suhu --</span>
                            <span>RH --</span>
                            <span>Gas --</span>
                        </div>
                    </div>
                `).join('')
                : '<p class="no-data">Belum ada menu yang bisa dihitung.</p>';
            return;
        }

        const overall = prediction.overall;
        const level = overall.level || 'warning';
        this.freshnessPanel.className = `freshness-panel freshness-${level}`;

        this.freshnessItems.innerHTML = (prediction.items || []).map(item => {
            const scores = item.component_scores || {};
            const tempScore = scores.temperature !== null && scores.temperature !== undefined
                ? Number(scores.temperature).toFixed(0)
                : '--';
            const humidityScore = scores.humidity !== null && scores.humidity !== undefined
                ? Number(scores.humidity).toFixed(0)
                : '--';
            const gasScore = scores.gas !== null && scores.gas !== undefined
                ? Number(scores.gas).toFixed(0)
                : '--';

            return `
                <div class="freshness-item freshness-item-${this.escapeHtml(item.level)}">
                    <div>
                        <strong>${this.escapeHtml(item.name)}</strong>
                        <span>${this.escapeHtml(item.time_message || item.status)}</span>
                    </div>
                    <div class="freshness-item-score">${Number(item.score).toFixed(1)}</div>
                    <div class="freshness-detail-grid">
                        <span>Kelayakan: <strong>${this.escapeHtml(item.status || overall.status)}</strong></span>
                        <span>Menuju tidak layak: <strong>${this.formatRemainingHours(item.remaining_hours)}</strong></span>
                        <span>Sensor: <strong>${this.escapeHtml(prediction.sensor?.connection_status || '--')}</strong></span>
                    </div>
                    <div class="freshness-breakdown">
                        <span>Suhu ${this.escapeHtml(tempScore)}</span>
                        <span>RH ${this.escapeHtml(humidityScore)}</span>
                        <span>Gas ${this.escapeHtml(gasScore)}</span>
                    </div>
                </div>
            `;
        }).join('');
    }

    renderAnalysisSummary(result) {
        const detections = result.detections || {};
        const detectedCount = this.menuKeys.filter(key => detections[key]?.detected).length;
        const acceptableCount = this.menuKeys.filter(key => detections[key]?.acceptable).length;
        const modelText = this.formatModelName(result.model_used);
        const timestamp = result.timestamp
            ? new Date(result.timestamp).toLocaleString('id-ID')
            : new Date().toLocaleString('id-ID');

        this.analysisSummary.innerHTML = `
            <div class="summary-row">
                <span>Item terdeteksi</span>
                <strong>${detectedCount}/${this.menuKeys.length}</strong>
            </div>
            <div class="summary-row">
                <span>Item layak</span>
                <strong>${acceptableCount}/${this.menuKeys.length}</strong>
            </div>
            <div class="summary-row">
                <span>Mode model</span>
                <strong>${this.escapeHtml(modelText)}</strong>
            </div>
            <div class="summary-row">
                <span>Waktu</span>
                <strong>${this.escapeHtml(timestamp)}</strong>
            </div>
        `;
    }

    // ========================================================================
    // Sensor Data
    // ========================================================================

    async loadAppStatus() {
        try {
            const response = await fetch('/api/status');
            const result = await response.json();
            if (result.status !== 'success') return;

            const data = result.data;
            this.updateModelMode(data.model_mode);
            if (!data.supabase_configured) {
                this.showNotification('Supabase belum dikonfigurasi. History dan sensor tetap jalan secara lokal.', 'info', 7000);
            }
        } catch (error) {
            console.error('Error loading app status:', error);
        }
    }

    async loadSensorData() {
        try {
            const response = await fetch('/api/sensor/latest');
            const result = await response.json();

            if (result.status === 'success' || result.status === 'warning') {
                const data = result.data;

                // Update DOM
                document.getElementById('tempValue').textContent =
                    data.temperature !== null ? Number(data.temperature).toFixed(1) : '--';
                document.getElementById('humidValue').textContent =
                    data.humidity !== null ? Number(data.humidity).toFixed(1) : '--';
                document.getElementById('gasValue').textContent =
                    data.gas_status || 'Waiting for ESP32';
                this.updateSummary(this.sensorState, data.connection_status || (data.gas_status ? 'Live' : 'Menunggu'));
                this.updateGasState(data.gas_status, data.is_stale);
                document.getElementById('gasRawValue').textContent =
                    data.gas_value !== null && data.gas_value !== undefined
                        ? Number(data.gas_value).toFixed(0)
                        : '--';

                if (data.created_at) {
                    const date = new Date(data.created_at);
                    const ageText = this.formatAge(data.age_seconds);
                    document.getElementById('lastUpdateValue').textContent =
                        `${date.toLocaleTimeString('id-ID')} (${ageText})`;
                } else {
                    document.getElementById('lastUpdateValue').textContent = '--';
                }

                if (data.is_stale && !this.sensorStaleNotified) {
                    this.sensorStaleNotified = true;
                    this.showNotification('Sensor belum mengirim data baru. Cek koneksi ESP32 ke Flask.', 'warning', 7000);
                } else if (!data.is_stale) {
                    this.sensorStaleNotified = false;
                }

                this.updateDeviceStatus(data);

                if (
                    this.lastDetections &&
                    data.created_at &&
                    data.created_at !== this.lastFreshnessSensorAt
                ) {
                    this.lastFreshnessSensorAt = data.created_at;
                    this.refreshFreshnessPrediction();
                }
            }
        } catch (error) {
            console.error('Error loading sensor data:', error);
            this.updateSummary(this.sensorState, 'Offline');
            this.updateSummary(this.deviceStatusText, 'Offline');
            this.updateSummary(this.deviceStatusBadge, 'Offline');
        }
    }

    async loadSensorHistory() {
        try {
            const response = await fetch('/api/sensor/history?limit=20');
            const result = await response.json();

            if (result.status === 'success' || result.status === 'warning') {
                const history = [...(result.data || [])].reverse();
                this.renderSensorCharts(history);
            }
        } catch (error) {
            console.error('Error loading sensor history:', error);
        }
    }

    updateSummary(element, value) {
        if (element) {
            element.textContent = value;
        }
    }

    updateModelMode(modelMode) {
        const isYolo = modelMode === 'custom-yolo';
        this.updateSummary(this.modelState, isYolo ? 'YOLO Aktif' : 'Demo Mode');
        this.updateSummary(this.modelMeta, isYolo ? 'models/best.pt digunakan' : 'Dummy fallback aktif');
    }

    updateDeviceStatus(data) {
        const status = data.connection_status || 'Menunggu';
        this.updateSummary(this.deviceStatusText, status);
        this.updateSummary(this.deviceStatusBadge, status);
        this.updateSummary(this.deviceSource, `${data.source || 'sensor'} / DHT22 + MQ135`);

        if (data.age_seconds !== null && data.age_seconds !== undefined) {
            this.updateSummary(this.deviceLastSeen, `Last seen ${this.formatAge(data.age_seconds)}`);
        } else {
            this.updateSummary(this.deviceLastSeen, 'Last seen --');
        }
    }

    formatModelName(modelMode) {
        if (modelMode === 'custom-yolo') return 'Custom YOLO';
        if (modelMode === 'dummy') return 'Dummy fallback';
        return modelMode || 'Unknown';
    }

    showNotification(message, type = 'info', duration = 4500) {
        if (!this.notification) return;

        window.clearTimeout(this.notificationTimer);
        this.notification.className = `notification notification-${type}`;
        this.notification.textContent = message;

        this.notificationTimer = window.setTimeout(() => {
            this.notification.classList.add('hidden');
        }, duration);
    }

    formatRemainingHours(hours) {
        const numericHours = Number(hours);
        if (!Number.isFinite(numericHours)) {
            return '--';
        }

        if (numericHours <= 0) {
            return '0 menit';
        }

        const totalMinutes = Math.round(numericHours * 60);
        const hourPart = Math.floor(totalMinutes / 60);
        const minutePart = totalMinutes % 60;

        if (hourPart <= 0) {
            return `${minutePart} menit`;
        }

        if (minutePart === 0) {
            return `${hourPart} jam`;
        }

        return `${hourPart} jam ${minutePart} menit`;
    }

    formatAge(ageSeconds) {
        if (ageSeconds === null || ageSeconds === undefined) {
            return 'belum ada data';
        }

        if (ageSeconds < 60) {
            return `${ageSeconds} dtk lalu`;
        }

        const ageMinutes = Math.floor(ageSeconds / 60);
        if (ageMinutes < 60) {
            return `${ageMinutes} mnt lalu`;
        }

        const ageHours = Math.floor(ageMinutes / 60);
        if (ageHours < 24) {
            return `${ageHours} jam lalu`;
        }

        const ageDays = Math.floor(ageHours / 24);
        return `${ageDays} hari lalu`;
    }

    updateGasState(gasStatus, isStale = false) {
        const gasValue = document.getElementById('gasValue');
        const gasItem = gasValue.closest('.sensor-item');
        const status = (gasStatus || '').toLowerCase();

        gasItem.classList.remove('sensor-ok', 'sensor-warning', 'sensor-danger');

        if (isStale) {
            gasItem.classList.add('sensor-warning');
            return;
        }

        if (status.includes('danger') || status.includes('bahaya')) {
            gasItem.classList.add('sensor-danger');
        } else if (status.includes('warning') || status.includes('waspada')) {
            gasItem.classList.add('sensor-warning');
        } else if (status.includes('normal')) {
            gasItem.classList.add('sensor-ok');
        }
    }

    // ========================================================================
    // Physical Capture Button Trigger
    // ========================================================================

    async loadCaptureRequest() {
        try {
            const response = await fetch('/api/capture-request/latest');
            const result = await response.json();

            if (result.status !== 'success' || !result.data || !result.data.id) {
                this.captureRequestReady = true;
                return;
            }

            const requestId = result.data.id;

            if (!this.captureRequestReady) {
                this.lastCaptureRequestId = requestId;
                this.captureRequestReady = true;
                return;
            }

            if (requestId === this.lastCaptureRequestId) {
                return;
            }

            this.lastCaptureRequestId = requestId;

            if (this.mediaStream && !this.isDetecting) {
                this.loading.classList.remove('hidden');
                this.loading.querySelector('p').textContent = 'Physical button pressed...';
                this.updateSummary(this.captureTriggerState, 'Trigger diterima');
                await this.captureAndDetect();
            } else {
                this.updateSummary(this.modelState, 'Trigger diterima');
                this.updateSummary(this.captureTriggerState, 'Trigger diterima');
            }
        } catch (error) {
            console.error('Error loading capture request:', error);
        }
    }

    renderSensorCharts(history) {
        this.renderLineChart(this.tempChart, history, 'temperature', '#ef4444', 'Temperature');
        this.renderLineChart(this.humidChart, history, 'humidity', '#2563eb', 'Humidity');
        this.renderLineChart(this.gasChart, history, 'gas_value', '#0891b2', 'Gas');
    }

    renderLineChart(svg, history, field, color, label) {
        if (!svg) return;

        const points = history
            .filter(item => item[field] !== null && item[field] !== undefined)
            .map(item => ({
                value: Number(item[field]),
                time: item.created_at ? new Date(item.created_at) : null
            }))
            .filter(item => Number.isFinite(item.value));

        if (points.length < 2) {
            svg.innerHTML = `
                <text x="180" y="92" text-anchor="middle" class="chart-empty">
                    Belum cukup data ${this.escapeHtml(label)}
                </text>
            `;
            return;
        }

        const width = 360;
        const height = 180;
        const padding = { top: 18, right: 18, bottom: 32, left: 42 };
        const plotWidth = width - padding.left - padding.right;
        const plotHeight = height - padding.top - padding.bottom;
        const values = points.map(point => point.value);
        const minValue = Math.min(...values);
        const maxValue = Math.max(...values);
        const range = maxValue - minValue || 1;
        const paddedMin = minValue - range * 0.12;
        const paddedMax = maxValue + range * 0.12;
        const paddedRange = paddedMax - paddedMin || 1;

        const coordinates = points.map((point, index) => {
            const x = padding.left + (plotWidth * index) / (points.length - 1);
            const y = padding.top + plotHeight - ((point.value - paddedMin) / paddedRange) * plotHeight;
            return { x, y, ...point };
        });

        const path = coordinates
            .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
            .join(' ');

        const last = coordinates[coordinates.length - 1];
        const firstTime = coordinates[0].time ? coordinates[0].time.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) : '--';
        const lastTime = last.time ? last.time.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) : '--';
        const yMax = maxValue.toFixed(field === 'gas_value' ? 0 : 1);
        const yMin = minValue.toFixed(field === 'gas_value' ? 0 : 1);
        const currentValue = last.value.toFixed(field === 'gas_value' ? 0 : 1);

        svg.innerHTML = `
            <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${padding.top + plotHeight}" class="chart-axis"></line>
            <line x1="${padding.left}" y1="${padding.top + plotHeight}" x2="${padding.left + plotWidth}" y2="${padding.top + plotHeight}" class="chart-axis"></line>
            <line x1="${padding.left}" y1="${padding.top + plotHeight / 2}" x2="${padding.left + plotWidth}" y2="${padding.top + plotHeight / 2}" class="chart-grid-line"></line>
            <text x="10" y="${padding.top + 4}" class="chart-label">${this.escapeHtml(yMax)}</text>
            <text x="10" y="${padding.top + plotHeight}" class="chart-label">${this.escapeHtml(yMin)}</text>
            <text x="${padding.left}" y="${height - 8}" class="chart-label">${this.escapeHtml(firstTime)}</text>
            <text x="${padding.left + plotWidth}" y="${height - 8}" text-anchor="end" class="chart-label">${this.escapeHtml(lastTime)}</text>
            <path d="${path}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
            ${coordinates.map(point => `
                <circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="3.5" fill="${color}"></circle>
            `).join('')}
            <circle cx="${last.x.toFixed(1)}" cy="${last.y.toFixed(1)}" r="6" fill="${color}" opacity="0.18"></circle>
            <text x="${width - 18}" y="24" text-anchor="end" class="chart-current">${this.escapeHtml(currentValue)}</text>
        `;
    }

    async loadFieldMonitoringHistory() {
        if (!this.fieldLatest) return;

        try {
            const response = await fetch('/api/field-monitoring/history?limit=3');
            const result = await response.json();
            if (result.status === 'success' && result.data?.length) {
                this.renderFieldLatest(result.data);
            }
        } catch (error) {
            console.error('Error loading field monitoring history:', error);
        }
    }

    renderFieldLatest(records) {
        if (!this.fieldLatest) return;

        if (!records || records.length === 0) {
            this.fieldLatest.innerHTML = '<p class="no-data">Belum ada data lapangan tersimpan.</p>';
            return;
        }

        this.fieldLatest.innerHTML = records.map(record => {
            const createdAt = record.created_at
                ? new Date(record.created_at).toLocaleString('id-ID')
                : '--';
            const temperature = record.temperature !== null && record.temperature !== undefined
                ? `${Number(record.temperature).toFixed(1)}°C`
                : '--';
            const humidity = record.humidity !== null && record.humidity !== undefined
                ? `${Number(record.humidity).toFixed(1)}%`
                : '--';
            const gasValue = record.gas_value !== null && record.gas_value !== undefined
                ? Number(record.gas_value).toFixed(0)
                : '--';
            const imageLink = record.image_url
                ? `<a href="${this.escapeHtml(record.image_url)}" target="_blank" rel="noopener">Foto</a>`
                : '<span>Tidak ada foto</span>';

            return `
                <div class="field-record">
                    <div>
                        <strong>${this.escapeHtml(record.stage || '--')} - ${this.escapeHtml(record.stage_label || '')}</strong>
                        <span>${this.escapeHtml(createdAt)}</span>
                    </div>
                    <div class="field-record-grid">
                        <span>Gas: <strong>${this.escapeHtml(gasValue)}</strong></span>
                        <span>Status: <strong>${this.escapeHtml(record.gas_status || '--')}</strong></span>
                        <span>Suhu: <strong>${this.escapeHtml(temperature)}</strong></span>
                        <span>Kelembapan: <strong>${this.escapeHtml(humidity)}</strong></span>
                        <span>Lokasi: <strong>${this.escapeHtml(record.location_name || '--')}</strong></span>
                        ${imageLink}
                    </div>
                </div>
            `;
        }).join('');
    }

    // ========================================================================
    // Detection History
    // ========================================================================

    async loadDetectionHistory() {
        try {
            const response = await fetch('/api/history');
            const result = await response.json();

            if (result.status === 'success' && result.data.length > 0) {
                this.displayHistory(result.data);
                this.updateSummary(this.historyCount, `${result.data.length} data`);
            } else {
                this.historyList.innerHTML = '<p class="no-data">No history yet</p>';
                this.updateSummary(this.historyCount, '0 data');
            }
        } catch (error) {
            console.error('Error loading history:', error);
        }
    }

    displayHistory(historyData) {
        this.historyList.innerHTML = '';

        historyData.forEach(item => {
            const date = new Date(item.created_at);
            const isComplete = item.menu_status === 'Menu Lengkap' ||
                item.menu_status === 'Menu Lengkap & Layak';
            const isUnsafe = (item.menu_status || '').includes('Tidak Layak') ||
                (item.menu_status || '').includes('Bau Busuk');
            const statusClass = isUnsafe ? 'danger' : (isComplete ? 'complete' : 'incomplete');

            const html = `
                <div class="history-item">
                    <div class="history-item-info">
                        <div class="detection-name">${this.escapeHtml(item.menu_status)}</div>
                        <div class="history-timestamp">${date.toLocaleString('id-ID')}</div>
                    </div>
                    <span class="history-status ${statusClass}">
                        ${isUnsafe ? 'Tidak Layak' : (isComplete ? 'Complete' : 'Incomplete')}
                    </span>
                </div>
            `;
            this.historyList.innerHTML += html;
        });
    }

    escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');
    }
}

// ============================================================================
// Initialize App
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    new MenuDetector();
});
