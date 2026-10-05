(() => {
    if (window.__todoReminderStarted) return;
    window.__todoReminderStarted = true;

    let alarmTimer = null;
    let vibrationTimer = null;
    let audioContext = null;
    let alarmActive = false;

    const style = document.createElement("style");
    style.textContent = `
        @keyframes todoAlarmPulse {
            from { transform: scale(1); }
            to { transform: scale(1.03); }
        }
        #globalTodoAlarmModal {
            display:none;
            position:fixed;
            inset:0;
            background:rgba(0,0,0,.78);
            z-index:2147483647;
            align-items:center;
            justify-content:center;
            padding:20px;
        }
        #globalTodoAlarmBox {
            width:min(420px,100%);
            background:#181c24;
            color:white;
            border:2px solid #ef4444;
            border-radius:18px;
            padding:28px;
            text-align:center;
            box-shadow:0 20px 60px rgba(0,0,0,.7);
            animation:todoAlarmPulse .8s infinite alternate;
        }
    `;
    document.head.appendChild(style);

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
        </div>
    `;
    document.body.appendChild(modal);

    function playBeep() {
        try {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return;
            if (!audioContext) audioContext = new AC();
            if (audioContext.state === "suspended") audioContext.resume();
            const osc = audioContext.createOscillator();
            const gain = audioContext.createGain();
            osc.type = "sine";
            osc.frequency.value = 900;
            gain.gain.value = 0.25;
            osc.connect(gain);
            gain.connect(audioContext.destination);
            osc.start();
            setTimeout(() => { try { osc.stop(); } catch(e) {} }, 700);
        } catch(e) {}
    }

    function vibrate() {
        if (localStorage.getItem("todoVibration") !== "false" && navigator.vibrate) {
            navigator.vibrate([500,300,500,300,800]);
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
                startAlarm(reminder.title);

                if ("Notification" in window && Notification.permission === "granted") {
                    try {
                        new Notification("⏰ To-Do Reminder", {
                            body: reminder.title + " is due now!",
                            requireInteraction: true
                        });
                    } catch(e) {}
                }
            }
        } catch(e) {
            console.log("Global To-Do reminder check error:", e);
        }
    }

    checkTodoReminders();
    setInterval(checkTodoReminders, 10000);
})();