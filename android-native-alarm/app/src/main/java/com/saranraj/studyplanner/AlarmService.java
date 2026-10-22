package com.saranraj.studyplanner;

import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.IBinder;

public class AlarmService extends Service {
    public static final String ACTION_START = "com.saranraj.studyplanner.ACTION_START_ALARM";
    public static final String ACTION_STOP = "com.saranraj.studyplanner.ACTION_STOP_ALARM_SERVICE";
    private static final int FOREGROUND_ID = 8801;
    private Ringtone ringtone;

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopRingtone();
            ((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).cancel(FOREGROUND_ID);
            stopForeground(true);
            stopSelf();
            return START_NOT_STICKY;
        }
        String title = intent == null ? "Study task reminder" : intent.getStringExtra("title");
        int alarmId = intent == null ? 7001 : intent.getIntExtra("alarm_id", 7001);
        Intent stop = new Intent(this, AlarmReceiver.class);
        stop.setAction(AlarmReceiver.ACTION_STOP);
        stop.putExtra("alarm_id", alarmId);
        PendingIntent stopIntent = PendingIntent.getBroadcast(this, alarmId, stop,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
            ? new Notification.Builder(this, "edutrack_alarm_v1")
            : new Notification.Builder(this);
        Notification notification = builder
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle("Edutrack Task Alarm")
            .setContentText(title == null ? "Task due now" : title)
            .setCategory(Notification.CATEGORY_ALARM)
            .setOngoing(true)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .addAction(android.R.drawable.ic_media_pause, "STOP ALARM", stopIntent)
            .build();
        startForeground(FOREGROUND_ID, notification);
        stopRingtone();
        Uri sound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
        ringtone = RingtoneManager.getRingtone(getApplicationContext(), sound);
        if (ringtone != null) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) ringtone.setLooping(true);
            ringtone.play();
        }
        return START_STICKY;
    }
    private void stopRingtone() {
        if (ringtone != null) {
            try { if (ringtone.isPlaying()) ringtone.stop(); } catch (Exception ignored) { }
            ringtone = null;
        }
    }
    @Override public void onDestroy() { stopRingtone(); super.onDestroy(); }
    @Override public IBinder onBind(Intent intent) { return null; }
}