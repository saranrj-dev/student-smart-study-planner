(() => {
    if (window.__todoReminderStarted) return;
    window.__todoReminderStarted = true;

    let alarmTimer = null;
    let vibrationTimer = null;
    let audioContext = null;
    let alarmActive = false;
    const notified = new Set();

    const style = document.createElement("style");
    style.textContent = `
        @keyframes todoAlarmPulse { from { transform:scale(1) } to { transform:scale(1.03) } }
        #globalTodoAlarmModal {
            display:none; position:fixed; inset:0; background:rgba(0,0,0,.78);
            z-index:2147483647; align-items:center; justify-content:center; padding:20px;
        }
        #globalTodoAlarmBox {
            width:min(420px,100%); background:#181c24; color:white; border:2px solid #ef4444;
            border-radius:18px; padding:28px; text-align:center;
            box-shadow:0 20px 60px rgba(0,0,0,.7); animation:todoAlarmPulse .8s infinite alternate;
        }
        #todoNotificationEnable {
            position:fixed; right:14px; bottom:14px; z-index:99999; border:0; border-radius:10px;
            padding:12px 15px; background:#2563eb; color:white; font-weight:700;
            box-shadow:0 4px 15px #0004;
        }
    `;
    document.head.appendChild(style);

    const enableButton = document.createElement("button");
    enableButton.id = "todoNotificationEnable";
    enableButton.type = "button";
    enableButton.textContent = "🔔 Enable reminders";
    document.body.appendChild(enableButton);

    function isAndroidWebView() {
        const ua = navigator.userAgent || "";
        return /;\\s*wv\\)|Version\\/\\d+\\.\\d+.*Chrome\\//i.test(ua) ||
               (window.Android !== undefined && !("Notification" in window));
    }

    function updateEnableButton() {
        if (!("Notification" in window)) {
            enableButton.textContent = isAndroidWebView()
                ? "🔔 Open in Chrome for alerts"
                : "🔔 Browser alerts unavailable";
            enableButton.disabled = false;
            enableButton.title = "This browser does not expose system notifications.";
        } else if (Notification.permission === "granted") {
            enableButton.textContent = "🔔 Reminders enabled";
            enableButton.disabled = true;
        } else if (Notification.permission === "denied") {
            enableButton.textContent = "Allow notifications in browser settings";
        }
    }

    enableButton.addEventListener("click", async () => {
        if (!("Notification" in window)) {
            alert("System notifications are not supported in this app's built-in browser (WebView).\\n\\n" +
                "Open the Study Planner website directly in Google Chrome, then tap Enable reminders and allow notifications.\\n\\n" +
                "Important: a website-only alarm cannot reliably ring when the app/page is fully closed. A native Android alarm/notification feature is needed for that.");
            return;
        }
        try {
            const permission = await Notification.requestPermission();
            updateEnableButton();
            if (permission === "granted") {
                new Notification("Study Planner reminders enabled", {
                    body: "Keep this app allowed to send reminders."
                });
            } else {
                alert("Notifications were not allowed. Enable them in your browser/app settings.");
            }
        } catch (e) {
            console.error("Notification permission error:", e);
        }
    });
    updateEnableButton();

    const modal = document.createElement("div");
    modal.id = "globalTodoAlarmModal";
    modal.innerHTML = `
        <div id="globalTodoAlarmBox">
            <div style="font-size:55px">⏰</div>
            <h2 style="margin:10px 0">To-Do Reminder</h2>
            <div id="globalTodoAlarmTitle" style="font-size:20px;font-weight:bold;color:#fbbf24;margin:15px 0"></div>
            <p style="color:#bbb">Your task is due now!</p>
            <button id="globalTodoStopAlarm" type="button"
                style="background:#ef4444;color:white;border:0;border-radius:9px;padding:13px 25px;font-size:17px;cursor:pointer">
                ⏹️ Stop Alarm
            </button>
        </div>`;
    document.body.appendChild(modal);

    async function unlockAudio() {
        try {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return;
            if (!audioContext) audioContext = new AC();
            if (audioContext.state === "suspended") await audioContext.resume();
            // A silent short sound unlocks audio after the user's tap in mobile browsers/WebViews.
            const gain = audioContext.createGain();
            gain.gain.value = 0;
            gain.connect(audioContext.destination);
            const osc = audioContext.createOscillator();
            osc.connect(gain);
            osc.start();
            osc.stop(audioContext.currentTime + 0.02);
        } catch (e) {}
    }

    document.addEventListener("pointerdown", unlockAudio, { once: true });
    document.addEventListener("touchstart", unlockAudio, { once: true, passive: true });

    function playBeep() {
        try {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return;
            if (!audioContext) audioContext = new AC();
            if (audioContext.state === "suspended") {
                audioContext.resume().catch(() => {});
            }
            const osc = audioContext.createOscillator();
            const gain = audioContext.createGain();
            osc.type = "sine";
            osc.frequency.value = 900;
            gain.gain.value = 0.25;
            osc.connect(gain);
            gain.connect(audioContext.destination);
            osc.start();
            setTimeout(() => { try { osc.stop(); } catch (e) {} }, 700);
        } catch (e) {}
    }

    function vibrate() {
        if (localStorage.getItem("todoVibration") !== "false" && navigator.vibrate) {
            navigator.vibrate([500, 300, 500, 300, 800]);
        }
    }

    function stopAlarm() {
        alarmActive = false;
        if (alarmTimer) { clearInterval(alarmTimer); alarmTimer = null; }
        if (vibrationTimer) { clearInterval(vibrationTimer); vibrationTimer = null; }
        if (navigator.vibrate) navigator.vibrate(0);
        modal.style.display = "none";
    }

    function startAlarm(title) {
        if (alarmActive) {
            document.getElementById("globalTodoAlarmTitle").textContent = title || "Your task";
            return;
        }
        alarmActive = true;
        document.getElementById("globalTodoAlarmTitle").textContent = title || "Your task";
        modal.style.display = "flex";
        playBeep();
        vibrate();
        alarmTimer = setInterval(playBeep, 1500);
        vibrationTimer = setInterval(vibrate, 2000);
    }

    document.getElementById("globalTodoStopAlarm").addEventListener("click", stopAlarm);

    async function checkTodoReminders() {
        try {
            const response = await fetch("/todo/reminders", {
                cache: "no-store",
                credentials: "same-origin"
            });
            if (!response.ok) return;
            const data = await response.json();
            if (!data.reminders || !data.reminders.length) return;

            for (const reminder of data.reminders) {
                const title = String(reminder.title || "Your task");
                startAlarm(title);

                // Show one system notification per reminder title while this page is running.
                // Browser notifications may appear while the app is in the background,
                // provided permission is granted and the browser/WebView keeps the page alive.
                const key = title + "|" + (reminder.id ?? reminder.due_at ?? "");
                if ("Notification" in window && Notification.permission === "granted" && !notified.has(key)) {
                    notified.add(key);
                    try {
                        const notification = new Notification("⏰ Study Planner Reminder", {
                            body: title + " is due now!",
                            requireInteraction: true,
                            tag: "study-planner-" + key
                        });
                        notification.onclick = () => {
                            window.focus();
                            notification.close();
                        };
                    } catch (e) {}
                }
            }
        } catch (e) {
            console.log("Global To-Do reminder check error:", e);
        }
    }

    // Re-check immediately when the user returns to the app; mobile browsers throttle timers
    // while backgrounded, so this catches reminders that became due while the page was hidden.
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            if (audioContext && audioContext.state === "suspended") {
                audioContext.resume().catch(() => {});
            }
            checkTodoReminders();
        }
    });
    window.addEventListener("focus", checkTodoReminders);
    window.addEventListener("pageshow", checkTodoReminders);

    checkTodoReminders();
    setInterval(checkTodoReminders, 10000);
})();