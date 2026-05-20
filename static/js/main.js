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
        this.editRoiBtn = document.getElementById('editRoiBtn');
        this.saveRoiBtn = document.getElementById('saveRoiBtn');
        this.resetRoiBtn = document.getElementById('resetRoiBtn');
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
        this.roiOverlay = document.querySelector('.roi-overlay');
        this.roiBoxes = document.querySelectorAll('[data-roi-key]');

        this.mediaStream = null;
        this.menuKeys = ['rice', 'fried_chicken', 'apple', 'broccoli'];
        this.defaultRoiConfig = {
            apple: { left: 14, top: 8, width: 30, height: 34 },
            rice: { left: 30, top: 8, width: 26, height: 35 },
            broccoli: { left: 14, top: 43, width: 34, height: 43 },
            fried_chicken: { left: 35, top: 42, width: 30, height: 48 }
        };
        this.roiConfig = this.loadRoiConfig();
        this.isEditingRoi = false;
        this.activeRoiDrag = null;
        this.lastCaptureRequestId = null;
        this.captureRequestReady = false;
        this.isDetecting = false;
        this.notificationTimer = null;
        this.sensorStaleNotified = false;
        this.liveRoiScanTimer = null;
        this.isLiveRoiScanning = false;

        this.applyRoiConfig();
        this.updateRoiOverlay(this.menuKeys);

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
        this.editRoiBtn.addEventListener('click', () => this.enableRoiEditing());
        this.saveRoiBtn.addEventListener('click', () => this.saveRoiEditing());
        this.resetRoiBtn.addEventListener('click', () => this.resetRoiConfig());
        this.roiBoxes.forEach(box => {
            box.addEventListener('pointerdown', event => this.startRoiPointer(event, box));
        });
        window.addEventListener('pointermove', event => this.moveRoiPointer(event));
        window.addEventListener('pointerup', () => this.stopRoiPointer());
    }

    // ========================================================================
    // Camera Functions
    // ========================================================================

    async startCamera() {
        try {
            this.loading.classList.remove('hidden');
            this.loading.querySelector('p').textContent = 'Starting camera...';

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
            this.updateRoiOverlay(this.menuKeys);
            this.startLiveRoiScan();

            this.loading.classList.add('hidden');
            this.showNotification('Kamera aktif. Menu siap dicapture.', 'success');
        } catch (error) {
            console.error('Error accessing camera:', error);
            this.cleanupCameraStream();
            this.startBtn.disabled = false;
            this.captureBtn.disabled = true;
            this.stopBtn.disabled = true;
            this.loading.classList.add('hidden');
            this.updateSummary(this.cameraState, 'Error');
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
        this.showNotification('Kamera dihentikan.', 'info');
    }

    cleanupCameraStream() {
        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
            this.mediaStream = null;
        }

        this.video.srcObject = null;
        this.updateRoiOverlay([]);
        this.stopLiveRoiScan();
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
            this.loading.classList.remove('hidden');
            this.loading.querySelector('p').textContent = 'Capturing...';

            // Capture frame from video
            const ctx = this.canvas.getContext('2d');
            this.canvas.width = this.video.videoWidth;
            this.canvas.height = this.video.videoHeight;
            ctx.drawImage(this.video, 0, 0);

            // Convert canvas to blob (JPEG)
            const blob = await this.canvasToBlob(this.canvas, 'image/jpeg', 0.9);

            // Send to Flask backend
            this.loading.querySelector('p').textContent = 'Processing...';
            const formData = new FormData();
            formData.append('image', blob, 'capture.jpg');
            formData.append('roi_config', JSON.stringify(this.roiConfig));

            const response = await fetch('/api/detect', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.status === 'success') {
                this.displayResults(result);
                this.loadDetectionHistory();
                this.updateModelMode(result.model_used);
                this.showNotification('Deteksi selesai. Hasil analisis sudah diperbarui.', 'success');
            } else {
                this.showNotification('Detection failed: ' + result.message, 'error');
            }

            this.loading.classList.add('hidden');
        } catch (error) {
            console.error('Error during capture:', error);
            this.updateSummary(this.modelState, 'Error');
            this.showNotification('Capture error: ' + error.message, 'error');
            this.loading.classList.add('hidden');
        } finally {
            this.isDetecting = false;
            if (this.mediaStream) {
                this.captureBtn.disabled = false;
            }
        }
    }

    canvasToBlob(canvas, type = 'image/jpeg', quality = 0.9) {
        return new Promise(resolve => {
            canvas.toBlob(resolve, type, quality);
        });
    }

    loadRoiConfig() {
        try {
            const savedConfig = JSON.parse(localStorage.getItem('mbg_roi_config') || '{}');
            return { ...this.defaultRoiConfig, ...savedConfig };
        } catch (error) {
            console.error('Error loading ROI config:', error);
            return { ...this.defaultRoiConfig };
        }
    }

    applyRoiConfig() {
        this.roiBoxes.forEach(box => {
            const key = box.dataset.roiKey;
            const roi = this.roiConfig[key];
            if (!roi) return;

            box.style.left = `${roi.left}%`;
            box.style.top = `${roi.top}%`;
            box.style.width = `${roi.width}%`;
            box.style.height = `${roi.height}%`;
        });
    }

    enableRoiEditing() {
        this.isEditingRoi = true;
        this.stopLiveRoiScan();
        this.roiOverlay.classList.add('roi-editing');
        this.updateRoiOverlay(this.menuKeys);
        this.editRoiBtn.classList.add('hidden');
        this.saveRoiBtn.classList.remove('hidden');
        this.resetRoiBtn.classList.remove('hidden');
        this.showNotification('Mode edit ROI aktif. Geser kotak, tarik sudut kanan bawah untuk ubah ukuran.', 'info', 7000);
    }

    saveRoiEditing() {
        this.isEditingRoi = false;
        this.roiOverlay.classList.remove('roi-editing');
        localStorage.setItem('mbg_roi_config', JSON.stringify(this.roiConfig));
        this.editRoiBtn.classList.remove('hidden');
        this.saveRoiBtn.classList.add('hidden');
        this.resetRoiBtn.classList.add('hidden');
        this.updateRoiOverlay(this.menuKeys);
        if (this.mediaStream) {
            this.startLiveRoiScan();
        }
        this.showNotification('ROI tersimpan dan akan dipakai saat deteksi.', 'success');
    }

    resetRoiConfig() {
        this.roiConfig = { ...this.defaultRoiConfig };
        localStorage.removeItem('mbg_roi_config');
        this.applyRoiConfig();
        this.updateRoiOverlay(this.menuKeys);
        this.showNotification('ROI dikembalikan ke posisi default.', 'info');
    }

    startRoiPointer(event, box) {
        if (!this.isEditingRoi) return;
        event.preventDefault();

        const overlayRect = this.roiOverlay.getBoundingClientRect();
        const boxRect = box.getBoundingClientRect();
        const isResize = event.offsetX >= box.clientWidth - 18 && event.offsetY >= box.clientHeight - 18;

        this.activeRoiDrag = {
            key: box.dataset.roiKey,
            mode: isResize ? 'resize' : 'move',
            startX: event.clientX,
            startY: event.clientY,
            overlayWidth: overlayRect.width,
            overlayHeight: overlayRect.height,
            startLeft: ((boxRect.left - overlayRect.left) / overlayRect.width) * 100,
            startTop: ((boxRect.top - overlayRect.top) / overlayRect.height) * 100,
            startWidth: (boxRect.width / overlayRect.width) * 100,
            startHeight: (boxRect.height / overlayRect.height) * 100
        };
    }

    moveRoiPointer(event) {
        if (!this.activeRoiDrag) return;

        const drag = this.activeRoiDrag;
        const dx = ((event.clientX - drag.startX) / drag.overlayWidth) * 100;
        const dy = ((event.clientY - drag.startY) / drag.overlayHeight) * 100;
        const roi = { ...this.roiConfig[drag.key] };

        if (drag.mode === 'resize') {
            roi.width = this.clamp(drag.startWidth + dx, 10, 70);
            roi.height = this.clamp(drag.startHeight + dy, 10, 70);
        } else {
            roi.left = this.clamp(drag.startLeft + dx, 0, 100 - roi.width);
            roi.top = this.clamp(drag.startTop + dy, 0, 100 - roi.height);
        }

        roi.width = this.clamp(roi.width, 10, 100 - roi.left);
        roi.height = this.clamp(roi.height, 10, 100 - roi.top);
        this.roiConfig[drag.key] = roi;
        this.applyRoiConfig();
    }

    stopRoiPointer() {
        this.activeRoiDrag = null;
    }

    clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    }

    startLiveRoiScan() {
        this.stopLiveRoiScan();
        this.scanLiveRoi();
        this.liveRoiScanTimer = window.setInterval(() => this.scanLiveRoi(), 4000);
    }

    stopLiveRoiScan() {
        if (this.liveRoiScanTimer) {
            window.clearInterval(this.liveRoiScanTimer);
            this.liveRoiScanTimer = null;
        }
        this.isLiveRoiScanning = false;
    }

    async scanLiveRoi() {
        if (
            this.isLiveRoiScanning ||
            this.isDetecting ||
            !this.mediaStream ||
            this.video.readyState < 2 ||
            !this.video.videoWidth ||
            !this.video.videoHeight
        ) {
            return;
        }

        try {
            this.isLiveRoiScanning = true;
            const ctx = this.canvas.getContext('2d');
            this.canvas.width = this.video.videoWidth;
            this.canvas.height = this.video.videoHeight;
            ctx.drawImage(this.video, 0, 0);

            const blob = await this.canvasToBlob(this.canvas, 'image/jpeg', 0.72);
            const formData = new FormData();
            formData.append('image', blob, 'preview.jpg');
            formData.append('roi_config', JSON.stringify(this.roiConfig));

            const response = await fetch('/api/preview-detect', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();

            if (result.status === 'success') {
                const visibleKeys = this.getVisibleRoiKeys(result.detections || {});
                this.updateRoiOverlay(visibleKeys);
            }
        } catch (error) {
            console.error('Error scanning live ROI:', error);
        } finally {
            this.isLiveRoiScanning = false;
        }
    }

    // ========================================================================
    // Display Results
    // ========================================================================

    displayResults(result) {
        // Show results section
        this.resultsSection.style.display = 'block';

        // Display captured image
        this.capturedImage.src = result.image_url;
        this.renderAnalysisSummary(result);
        this.updateRoiOverlay(this.getVisibleRoiKeys(result.detections || {}));

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

    getVisibleRoiKeys(detections) {
        return this.menuKeys.filter(key => detections[key]?.detected);
    }

    updateRoiOverlay(visibleKeys) {
        const visibleSet = new Set(visibleKeys || []);
        this.roiBoxes.forEach(box => {
            const key = box.dataset.roiKey;
            box.classList.toggle('roi-visible', visibleSet.has(key));
        });
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
