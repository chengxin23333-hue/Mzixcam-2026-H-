"""比赛接收端页面。内容逐字符复用已通过实机测试的网页，不在本模块修改。"""

PAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>MaixCAM 接收端</title>
    <style>
        :root {
            color-scheme: light;
            --page: #eef1f4;
            --surface: #ffffff;
            --surface-soft: #f7f8fa;
            --text: #17202a;
            --muted: #66717d;
            --border: #d7dde3;
            --primary: #25313d;
            --primary-hover: #101820;
            --success: #087f5b;
            --success-soft: #e6f5ef;
            --danger: #c92a2a;
            --danger-hover: #a51111;
            --warning: #9c6500;
            --warning-soft: #fff4d6;
            --shadow: 0 10px 28px rgba(23, 32, 42, 0.08);
        }

        * {
            box-sizing: border-box;
        }

        html, body {
            margin: 0;
            min-width: 320px;
            min-height: 100%;
        }

        body {
            background: var(--page);
            color: var(--text);
            font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
            font-size: 15px;
            line-height: 1.5;
        }

        button, a {
            font: inherit;
        }

        button:focus-visible, a:focus-visible, video:focus-visible {
            outline: 3px solid rgba(8, 127, 91, 0.28);
            outline-offset: 2px;
        }

        .app-shell {
            margin: 0 auto;
            max-width: 1180px;
            padding: 18px 20px 36px;
            width: 100%;
        }

        .topbar {
            align-items: center;
            display: flex;
            gap: 16px;
            justify-content: space-between;
            margin-bottom: 16px;
        }

        .brand {
            align-items: center;
            display: flex;
            gap: 11px;
            min-width: 0;
        }

        .brand-mark {
            align-items: center;
            background: var(--primary);
            border-radius: 6px;
            color: #ffffff;
            display: inline-flex;
            flex: 0 0 36px;
            font-size: 12px;
            font-weight: 600;
            height: 36px;
            justify-content: center;
        }

        .brand-copy {
            min-width: 0;
        }

        .brand-name {
            font-size: 18px;
            font-weight: 600;
            margin: 0;
        }

        .brand-subtitle, .muted {
            color: var(--muted);
        }

        .brand-subtitle {
            font-size: 13px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .status-group {
            align-items: center;
            display: flex;
            flex-wrap: wrap;
            gap: 9px;
            justify-content: flex-end;
        }

        .status-pill {
            align-items: center;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 999px;
            display: inline-flex;
            font-size: 13px;
            gap: 7px;
            min-height: 32px;
            padding: 5px 10px;
            white-space: nowrap;
        }

        .status-dot {
            background: var(--warning);
            border-radius: 50%;
            display: inline-block;
            height: 8px;
            width: 8px;
        }

        .status-pill.online {
            background: var(--success-soft);
            border-color: rgba(8, 127, 91, 0.28);
            color: var(--success);
        }

        .status-pill.online .status-dot {
            background: var(--success);
        }

        .status-pill.offline {
            color: var(--danger);
        }

        .status-pill.offline .status-dot {
            background: var(--danger);
        }

        .viewer {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            box-shadow: var(--shadow);
            overflow: hidden;
        }

        .stage-shell {
            background: #0b0e12;
            display: grid;
            place-items: center;
            width: 100%;
        }

        .stage {
            aspect-ratio: 5 / 4;
            background: #0b0e12;
            max-width: 900px;
            overflow: hidden;
            position: relative;
            width: min(100%, calc(72vh * 1.25));
        }

        #stream-source {
            height: 1px;
            opacity: 0;
            pointer-events: none;
            position: absolute;
            width: 1px;
        }

        #stream-canvas, #playback-video {
            background: #0b0e12;
            display: block;
            height: 100%;
            inset: 0;
            object-fit: contain;
            position: absolute;
            width: 100%;
        }

        #playback-video[hidden], #stream-canvas[hidden] {
            display: none;
        }

        .stage-overlay {
            align-items: center;
            display: flex;
            gap: 8px;
            left: 12px;
            position: absolute;
            right: 12px;
            top: 12px;
            z-index: 2;
        }

        .live-chip, .time-chip {
            align-items: center;
            background: rgba(11, 14, 18, 0.76);
            border-radius: 4px;
            color: #ffffff;
            display: inline-flex;
            font-size: 13px;
            gap: 7px;
            padding: 5px 8px;
        }

        .live-chip .status-dot {
            background: #20c997;
        }

        .time-chip {
            margin-left: auto;
        }

        .toolbar {
            align-items: center;
            display: flex;
            gap: 14px;
            justify-content: space-between;
            min-height: 68px;
            padding: 12px 14px;
        }

        .stream-meta {
            min-width: 0;
        }

        .stream-title {
            font-weight: 600;
        }

        .stream-address {
            color: var(--muted);
            font-size: 13px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .controls {
            align-items: center;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            justify-content: flex-end;
        }

        .timer {
            color: var(--muted);
            font-variant-numeric: tabular-nums;
            min-width: 58px;
            text-align: right;
        }

        .timer.recording {
            color: var(--danger);
            font-weight: 600;
        }

        .button {
            align-items: center;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text);
            cursor: pointer;
            display: inline-flex;
            gap: 7px;
            justify-content: center;
            min-height: 40px;
            padding: 8px 13px;
            text-decoration: none;
            white-space: nowrap;
        }

        .button[hidden] {
            display: none;
        }

        .button:hover:not(:disabled) {
            background: var(--surface-soft);
        }

        .button:disabled {
            cursor: not-allowed;
            opacity: 0.55;
        }

        .button.primary {
            background: var(--primary);
            border-color: var(--primary);
            color: #ffffff;
        }

        .button.primary:hover:not(:disabled) {
            background: var(--primary-hover);
        }

        .button.recording {
            background: var(--danger);
            border-color: var(--danger);
            color: #ffffff;
        }

        .button.recording:hover:not(:disabled) {
            background: var(--danger-hover);
        }

        .record-symbol {
            background: currentColor;
            border-radius: 50%;
            display: inline-block;
            height: 9px;
            width: 9px;
        }

        .notice {
            border: 1px solid var(--border);
            border-radius: 6px;
            margin-top: 12px;
            padding: 9px 12px;
        }

        .notice[hidden] {
            display: none;
        }

        .notice.warning {
            background: var(--warning-soft);
            border-color: rgba(156, 101, 0, 0.3);
            color: var(--warning);
        }

        .notice.error {
            background: #fff0f0;
            border-color: rgba(201, 42, 42, 0.3);
            color: var(--danger);
        }

        .notice.success {
            background: var(--success-soft);
            border-color: rgba(8, 127, 91, 0.28);
            color: var(--success);
        }

        .recordings {
            margin-top: 26px;
        }

        .section-heading {
            align-items: end;
            display: flex;
            gap: 12px;
            justify-content: space-between;
            margin-bottom: 8px;
        }

        .section-heading h2 {
            font-size: 18px;
            margin: 0;
        }

        .section-meta {
            color: var(--muted);
            font-size: 13px;
            text-align: right;
        }

        .table-wrap {
            overflow-x: auto;
        }

        table {
            border-collapse: collapse;
            width: 100%;
        }

        th, td {
            border-bottom: 1px solid var(--border);
            padding: 12px 10px;
            text-align: left;
            vertical-align: middle;
        }

        th {
            color: var(--muted);
            font-size: 13px;
            font-weight: 600;
        }

        th:first-child, td:first-child {
            padding-left: 0;
        }

        th:last-child, td:last-child {
            padding-right: 0;
        }

        .numeric {
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }

        .actions-cell {
            text-align: right;
        }

        .row-actions {
            display: inline-flex;
            flex-wrap: wrap;
            gap: 6px;
            justify-content: flex-end;
        }

        .row-actions .button {
            min-height: 34px;
            padding: 5px 9px;
        }

        .button.delete {
            color: var(--danger);
        }

        .empty-state {
            border-bottom: 1px solid var(--border);
            color: var(--muted);
            padding: 34px 12px;
            text-align: center;
        }

        .empty-state[hidden] {
            display: none;
        }

        .stage:fullscreen {
            background: #000000;
            height: 100vh;
            max-width: none;
            width: 100vw;
        }

        @media (max-width: 700px) {
            .app-shell {
                padding: 12px 12px 28px;
            }

            .topbar, .toolbar {
                align-items: stretch;
                flex-direction: column;
            }

            .status-group {
                justify-content: flex-start;
            }

            .stage {
                width: 100%;
            }

            .controls {
                justify-content: stretch;
            }

            .controls .button.primary,
            .controls .button.recording {
                flex: 1;
            }

            .timer {
                margin-right: auto;
                text-align: left;
            }

            .hide-narrow {
                display: none;
            }

            th, td {
                padding: 10px 6px;
            }

            .row-actions {
                min-width: 118px;
            }
        }
    </style>
</head>
<body>
    <main class="app-shell">
        <header class="topbar">
            <div class="brand">
                <span class="brand-mark" aria-hidden="true">CAM</span>
                <div class="brand-copy">
                    <h1 class="brand-name">MaixCAM 接收端</h1>
                    <div class="brand-subtitle">车载平衡滚球 · 实时图传与录像</div>
                </div>
            </div>
            <div class="status-group">
                <span class="status-pill" id="connection-status">
                    <span class="status-dot" aria-hidden="true"></span>
                    <span id="connection-text">正在连接</span>
                </span>
                <span class="status-pill" id="resolution-status">等待画面</span>
            </div>
        </header>

        <section class="viewer" aria-label="实时画面与录像控制">
            <div class="stage-shell">
                <div class="stage" id="viewer-stage">
                    <img id="stream-source" src="/stream" alt="" aria-hidden="true">
                    <canvas id="stream-canvas" width="500" height="400" aria-label="MaixCAM 实时画面">
                        当前浏览器不支持 Canvas。
                    </canvas>
                    <video id="playback-video" controls playsinline hidden aria-label="录像回放"></video>
                    <div class="stage-overlay" aria-hidden="true">
                        <span class="live-chip" id="view-mode-chip">
                            <span class="status-dot"></span>
                            <span id="view-mode-text">LIVE</span>
                        </span>
                        <span class="time-chip" id="clock">--:--:--</span>
                    </div>
                </div>
            </div>

            <div class="toolbar">
                <div class="stream-meta">
                    <div class="stream-title" id="stream-title">实时画面</div>
                    <div class="stream-address" id="stream-address">/stream</div>
                </div>
                <div class="controls">
                    <span class="timer" id="record-timer">00:00</span>
                    <button class="button" id="return-live-button" type="button" hidden>返回实时画面</button>
                    <button class="button primary" id="record-button" type="button">
                        <span class="record-symbol" aria-hidden="true"></span>
                        <span id="record-button-text">开始录制</span>
                    </button>
                    <button class="button" id="fullscreen-button" type="button">全屏</button>
                </div>
            </div>
        </section>

        <div class="notice" id="notice" role="status" hidden></div>

        <section class="recordings" aria-labelledby="recordings-title">
            <div class="section-heading">
                <h2 id="recordings-title">本次测试录像</h2>
                <div class="section-meta" id="recordings-summary">0 个录像</div>
            </div>
            <div class="table-wrap">
                <table aria-label="录像列表">
                    <thead>
                        <tr>
                            <th>开始时间</th>
                            <th>时长</th>
                            <th class="hide-narrow">格式</th>
                            <th class="hide-narrow">大小</th>
                            <th class="actions-cell">操作</th>
                        </tr>
                    </thead>
                    <tbody id="recordings-body"></tbody>
                </table>
                <div class="empty-state" id="empty-recordings">暂无录像</div>
            </div>
        </section>
    </main>

    <script>
        (function () {
            "use strict";

            var DB_NAME = "maixcam-receiver";
            var DB_VERSION = 1;
            var STORE_NAME = "recordings";
            var CAPTURE_FPS = 20;
            var VIDEO_BIT_RATE = 2500000;

            var streamSource = document.getElementById("stream-source");
            var streamCanvas = document.getElementById("stream-canvas");
            var canvasContext = streamCanvas.getContext("2d", { alpha: false });
            var playbackVideo = document.getElementById("playback-video");
            var viewerStage = document.getElementById("viewer-stage");
            var connectionStatus = document.getElementById("connection-status");
            var connectionText = document.getElementById("connection-text");
            var resolutionStatus = document.getElementById("resolution-status");
            var viewModeText = document.getElementById("view-mode-text");
            var streamTitle = document.getElementById("stream-title");
            var streamAddress = document.getElementById("stream-address");
            var clock = document.getElementById("clock");
            var recordTimer = document.getElementById("record-timer");
            var recordButton = document.getElementById("record-button");
            var recordButtonText = document.getElementById("record-button-text");
            var returnLiveButton = document.getElementById("return-live-button");
            var fullscreenButton = document.getElementById("fullscreen-button");
            var notice = document.getElementById("notice");
            var recordingsBody = document.getElementById("recordings-body");
            var recordingsSummary = document.getElementById("recordings-summary");
            var emptyRecordings = document.getElementById("empty-recordings");

            var state = {
                connected: false,
                hasFrame: false,
                database: null,
                recordings: new Map(),
                mediaRecorder: null,
                captureTracks: [],
                chunks: [],
                recordingStartedAt: 0,
                timerHandle: null,
                stopping: false,
                playbackId: null,
                playbackUrl: null,
                reconnectHandle: null
            };

            streamAddress.textContent = window.location.host + "/stream";

            function pad2(value) {
                return String(value).padStart(2, "0");
            }

            function formatDuration(milliseconds) {
                var totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
                var hours = Math.floor(totalSeconds / 3600);
                var minutes = Math.floor((totalSeconds % 3600) / 60);
                var seconds = totalSeconds % 60;
                if (hours > 0) {
                    return pad2(hours) + ":" + pad2(minutes) + ":" + pad2(seconds);
                }
                return pad2(minutes) + ":" + pad2(seconds);
            }

            function formatDateTime(milliseconds) {
                var date = new Date(milliseconds);
                return date.getFullYear() + "-" + pad2(date.getMonth() + 1) + "-" +
                    pad2(date.getDate()) + " " + pad2(date.getHours()) + ":" +
                    pad2(date.getMinutes()) + ":" + pad2(date.getSeconds());
            }

            function formatFileSize(bytes) {
                if (bytes < 1024 * 1024) {
                    return (bytes / 1024).toFixed(1) + " KB";
                }
                return (bytes / (1024 * 1024)).toFixed(1) + " MB";
            }

            function recordingFilename(createdAt, mimeType) {
                var date = new Date(createdAt);
                var stamp = date.getFullYear() + pad2(date.getMonth() + 1) +
                    pad2(date.getDate()) + "-" + pad2(date.getHours()) +
                    pad2(date.getMinutes()) + pad2(date.getSeconds());
                var extension = mimeType.indexOf("mp4") >= 0 ? ".mp4" : ".webm";
                return "maixcam-" + stamp + extension;
            }

            function showNotice(message, kind) {
                notice.textContent = message;
                notice.className = "notice " + (kind || "warning");
                notice.hidden = !message;
            }

            function setConnected(connected) {
                if (state.connected === connected) {
                    return;
                }
                state.connected = connected;
                connectionStatus.classList.toggle("online", connected);
                connectionStatus.classList.toggle("offline", !connected);
                connectionText.textContent = connected ? "已连接" : "连接中断";
            }

            function drawStreamFrame() {
                if (streamSource.naturalWidth > 0 && streamSource.naturalHeight > 0) {
                    if (streamCanvas.width !== streamSource.naturalWidth ||
                            streamCanvas.height !== streamSource.naturalHeight) {
                        streamCanvas.width = streamSource.naturalWidth;
                        streamCanvas.height = streamSource.naturalHeight;
                    }
                    canvasContext.drawImage(
                        streamSource,
                        0,
                        0,
                        streamCanvas.width,
                        streamCanvas.height
                    );
                    state.hasFrame = true;
                    setConnected(true);
                    resolutionStatus.textContent = streamCanvas.width + " × " +
                        streamCanvas.height;
                }
                window.requestAnimationFrame(drawStreamFrame);
            }

            function reconnectStream() {
                window.clearTimeout(state.reconnectHandle);
                state.reconnectHandle = window.setTimeout(function () {
                    streamSource.src = "/stream?retry=" + Date.now();
                }, 2000);
            }

            streamSource.addEventListener("load", function () {
                setConnected(true);
            });

            streamSource.addEventListener("error", function () {
                state.hasFrame = false;
                setConnected(false);
                resolutionStatus.textContent = "等待重连";
                reconnectStream();
            });

            function updateClock() {
                var now = new Date();
                clock.textContent = pad2(now.getHours()) + ":" +
                    pad2(now.getMinutes()) + ":" + pad2(now.getSeconds());
            }

            function requestToPromise(request) {
                return new Promise(function (resolve, reject) {
                    request.onsuccess = function () {
                        resolve(request.result);
                    };
                    request.onerror = function () {
                        reject(request.error || new Error("数据库请求失败"));
                    };
                });
            }

            function openDatabase() {
                return new Promise(function (resolve, reject) {
                    if (!("indexedDB" in window)) {
                        reject(new Error("浏览器不支持 IndexedDB"));
                        return;
                    }
                    var request = indexedDB.open(DB_NAME, DB_VERSION);
                    request.onupgradeneeded = function () {
                        var database = request.result;
                        if (!database.objectStoreNames.contains(STORE_NAME)) {
                            database.createObjectStore(STORE_NAME, { keyPath: "id" });
                        }
                    };
                    request.onsuccess = function () {
                        resolve(request.result);
                    };
                    request.onerror = function () {
                        reject(request.error || new Error("无法打开浏览器录像库"));
                    };
                });
            }

            function runStoreTransaction(mode, action) {
                return new Promise(function (resolve, reject) {
                    if (!state.database) {
                        resolve();
                        return;
                    }
                    var transaction = state.database.transaction(STORE_NAME, mode);
                    transaction.oncomplete = function () {
                        resolve();
                    };
                    transaction.onerror = function () {
                        reject(transaction.error || new Error("录像库写入失败"));
                    };
                    action(transaction.objectStore(STORE_NAME));
                });
            }

            function loadStoredRecordings() {
                if (!state.database) {
                    return Promise.resolve();
                }
                var transaction = state.database.transaction(STORE_NAME, "readonly");
                var request = transaction.objectStore(STORE_NAME).getAll();
                return requestToPromise(request).then(function (records) {
                    records.forEach(function (record) {
                        state.recordings.set(record.id, record);
                    });
                });
            }

            function saveRecording(record) {
                state.recordings.set(record.id, record);
                renderRecordings();
                return runStoreTransaction("readwrite", function (store) {
                    store.put(record);
                });
            }

            function removeStoredRecording(id) {
                return runStoreTransaction("readwrite", function (store) {
                    store.delete(id);
                }).then(function () {
                    state.recordings.delete(id);
                    renderRecordings();
                });
            }

            function createActionButton(label, action, id, danger) {
                var button = document.createElement("button");
                button.type = "button";
                button.className = "button" + (danger ? " delete" : "");
                button.textContent = label;
                button.dataset.action = action;
                button.dataset.id = id;
                return button;
            }

            function renderRecordings() {
                var records = Array.from(state.recordings.values()).sort(function (a, b) {
                    return b.createdAt - a.createdAt;
                });
                recordingsBody.textContent = "";
                emptyRecordings.hidden = records.length !== 0;
                var totalSize = records.reduce(function (sum, record) {
                    return sum + record.size;
                }, 0);
                recordingsSummary.textContent = records.length + " 个录像" +
                    (records.length ? " · " + formatFileSize(totalSize) : "");

                records.forEach(function (record) {
                    var row = document.createElement("tr");
                    var createdCell = document.createElement("td");
                    var durationCell = document.createElement("td");
                    var formatCell = document.createElement("td");
                    var sizeCell = document.createElement("td");
                    var actionsCell = document.createElement("td");
                    var actions = document.createElement("span");

                    createdCell.textContent = formatDateTime(record.createdAt);
                    createdCell.className = "numeric";
                    durationCell.textContent = formatDuration(record.durationMs);
                    durationCell.className = "numeric";
                    formatCell.textContent = record.mimeType.indexOf("mp4") >= 0 ? "MP4" : "WebM";
                    formatCell.className = "hide-narrow";
                    sizeCell.textContent = formatFileSize(record.size);
                    sizeCell.className = "numeric hide-narrow";
                    actionsCell.className = "actions-cell";
                    actions.className = "row-actions";
                    actions.appendChild(createActionButton("回放", "play", record.id, false));
                    actions.appendChild(createActionButton("下载", "download", record.id, false));
                    actions.appendChild(createActionButton("删除", "delete", record.id, true));
                    actionsCell.appendChild(actions);
                    row.appendChild(createdCell);
                    row.appendChild(durationCell);
                    row.appendChild(formatCell);
                    row.appendChild(sizeCell);
                    row.appendChild(actionsCell);
                    recordingsBody.appendChild(row);
                });
            }

            function selectMimeType() {
                var candidates = [
                    "video/webm;codecs=vp9",
                    "video/webm;codecs=vp8",
                    "video/webm"
                ];
                for (var index = 0; index < candidates.length; index += 1) {
                    if (MediaRecorder.isTypeSupported(candidates[index])) {
                        return candidates[index];
                    }
                }
                return "";
            }

            function setRecordingUi(recording, saving) {
                recordButton.classList.toggle("recording", recording || saving);
                recordTimer.classList.toggle("recording", recording || saving);
                recordButton.disabled = Boolean(saving);
                if (saving) {
                    recordButtonText.textContent = "正在保存";
                } else {
                    recordButtonText.textContent = recording ? "停止录制" : "开始录制";
                }
            }

            function updateRecordingTimer() {
                if (!state.mediaRecorder || state.mediaRecorder.state !== "recording") {
                    return;
                }
                recordTimer.textContent = formatDuration(Date.now() - state.recordingStartedAt);
            }

            function stopCaptureTracks() {
                state.captureTracks.forEach(function (track) {
                    track.stop();
                });
                state.captureTracks = [];
            }

            function finishRecording(recorder) {
                window.clearInterval(state.timerHandle);
                state.timerHandle = null;
                stopCaptureTracks();
                var createdAt = state.recordingStartedAt;
                var durationMs = Math.max(1, Date.now() - createdAt);
                var mimeType = recorder.mimeType || "video/webm";
                var blob = new Blob(state.chunks, { type: mimeType });
                state.mediaRecorder = null;
                state.chunks = [];
                state.stopping = false;
                recordTimer.textContent = "00:00";
                setRecordingUi(false, false);

                if (!blob.size) {
                    showNotice("录像为空，请确认画面正常后重试。", "error");
                    return;
                }

                var record = {
                    id: String(createdAt) + "-" + Math.random().toString(16).slice(2),
                    createdAt: createdAt,
                    durationMs: durationMs,
                    mimeType: mimeType,
                    size: blob.size,
                    blob: blob
                };

                saveRecording(record).then(function () {
                    showNotice("录像已保存，可直接回放或下载。", "success");
                }).catch(function () {
                    showNotice("录像可在当前页面使用，但浏览器持久化保存失败。", "warning");
                });
            }

            function startRecording() {
                if (!state.hasFrame) {
                    showNotice("尚未收到有效画面，暂时不能开始录制。", "warning");
                    return;
                }
                if (!("MediaRecorder" in window) || !streamCanvas.captureStream) {
                    showNotice("当前浏览器不支持网页录像，请使用最新版 Edge 或 Chrome。", "error");
                    return;
                }

                returnToLive();
                var captureStream = streamCanvas.captureStream(CAPTURE_FPS);
                var mimeType = selectMimeType();
                var options = { videoBitsPerSecond: VIDEO_BIT_RATE };
                if (mimeType) {
                    options.mimeType = mimeType;
                }

                var recorder;
                try {
                    recorder = new MediaRecorder(captureStream, options);
                } catch (error) {
                    recorder = new MediaRecorder(captureStream);
                }

                state.mediaRecorder = recorder;
                state.captureTracks = captureStream.getTracks();
                state.chunks = [];
                state.recordingStartedAt = Date.now();
                state.stopping = false;

                recorder.ondataavailable = function (event) {
                    if (event.data && event.data.size > 0) {
                        state.chunks.push(event.data);
                    }
                };
                recorder.onerror = function () {
                    showNotice("录像过程发生错误，请停止后重新录制。", "error");
                };
                recorder.onstop = function () {
                    finishRecording(recorder);
                };
                recorder.start(1000);
                setRecordingUi(true, false);
                recordTimer.textContent = "00:00";
                state.timerHandle = window.setInterval(updateRecordingTimer, 250);
                showNotice("", "success");
            }

            function stopRecording() {
                if (!state.mediaRecorder || state.mediaRecorder.state !== "recording" || state.stopping) {
                    return;
                }
                state.stopping = true;
                setRecordingUi(false, true);
                state.mediaRecorder.stop();
            }

            function releasePlaybackUrl() {
                if (state.playbackUrl) {
                    URL.revokeObjectURL(state.playbackUrl);
                    state.playbackUrl = null;
                }
            }

            function playRecording(id) {
                var record = state.recordings.get(id);
                if (!record) {
                    return;
                }
                releasePlaybackUrl();
                state.playbackId = id;
                state.playbackUrl = URL.createObjectURL(record.blob);
                playbackVideo.src = state.playbackUrl;
                playbackVideo.hidden = false;
                streamCanvas.hidden = true;
                returnLiveButton.hidden = false;
                viewModeText.textContent = "PLAYBACK";
                streamTitle.textContent = "录像回放";
                playbackVideo.play().catch(function () {
                    showNotice("请点击播放器中的播放按钮开始回放。", "warning");
                });
            }

            function returnToLive() {
                playbackVideo.pause();
                playbackVideo.removeAttribute("src");
                playbackVideo.load();
                playbackVideo.hidden = true;
                streamCanvas.hidden = false;
                returnLiveButton.hidden = true;
                viewModeText.textContent = "LIVE";
                streamTitle.textContent = "实时画面";
                state.playbackId = null;
                releasePlaybackUrl();
            }

            function downloadRecording(id) {
                var record = state.recordings.get(id);
                if (!record) {
                    return;
                }
                var url = URL.createObjectURL(record.blob);
                var link = document.createElement("a");
                link.href = url;
                link.download = recordingFilename(record.createdAt, record.mimeType);
                document.body.appendChild(link);
                link.click();
                link.remove();
                window.setTimeout(function () {
                    URL.revokeObjectURL(url);
                }, 1000);
            }

            function deleteRecording(id) {
                if (!window.confirm("删除这段录像？此操作无法撤销。")) {
                    return;
                }
                if (state.playbackId === id) {
                    returnToLive();
                }
                removeStoredRecording(id).catch(function () {
                    showNotice("删除失败，请刷新页面后重试。", "error");
                });
            }

            recordButton.addEventListener("click", function () {
                if (state.mediaRecorder && state.mediaRecorder.state === "recording") {
                    stopRecording();
                } else {
                    startRecording();
                }
            });

            returnLiveButton.addEventListener("click", returnToLive);

            fullscreenButton.addEventListener("click", function () {
                if (document.fullscreenElement) {
                    document.exitFullscreen();
                } else if (viewerStage.requestFullscreen) {
                    viewerStage.requestFullscreen();
                }
            });

            document.addEventListener("fullscreenchange", function () {
                fullscreenButton.textContent = document.fullscreenElement ? "退出全屏" : "全屏";
            });

            recordingsBody.addEventListener("click", function (event) {
                var button = event.target.closest("button[data-action]");
                if (!button) {
                    return;
                }
                var id = button.dataset.id;
                if (button.dataset.action === "play") {
                    playRecording(id);
                } else if (button.dataset.action === "download") {
                    downloadRecording(id);
                } else if (button.dataset.action === "delete") {
                    deleteRecording(id);
                }
            });

            window.addEventListener("beforeunload", function (event) {
                if (state.mediaRecorder || state.stopping) {
                    event.preventDefault();
                    event.returnValue = "";
                }
            });

            document.addEventListener("visibilitychange", function () {
                if (document.hidden && state.mediaRecorder &&
                        state.mediaRecorder.state === "recording") {
                    showNotice("录制时请保持本页面位于前台，以免浏览器降低画面更新频率。", "warning");
                }
            });

            if (!("MediaRecorder" in window) || !streamCanvas.captureStream) {
                recordButton.disabled = true;
                showNotice("当前浏览器不支持网页录像，请使用最新版 Edge 或 Chrome。", "error");
            }

            if (!viewerStage.requestFullscreen) {
                fullscreenButton.disabled = true;
            }

            openDatabase().then(function (database) {
                state.database = database;
                return loadStoredRecordings();
            }).then(function () {
                renderRecordings();
            }).catch(function () {
                renderRecordings();
                showNotice("浏览器持久化存储不可用；本页仍可录制、回放和下载。", "warning");
            });

            window.addEventListener("unload", function () {
                releasePlaybackUrl();
                stopCaptureTracks();
                if (state.database) {
                    state.database.close();
                }
            });

            updateClock();
            window.setInterval(updateClock, 1000);
            window.requestAnimationFrame(drawStreamFrame);
            renderRecordings();
        }());
    </script>
</body>
</html>
"""
