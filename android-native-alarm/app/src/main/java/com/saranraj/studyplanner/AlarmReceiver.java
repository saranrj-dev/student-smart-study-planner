package com.saranraj.studyplanner;

import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.media.RingtoneManager;
import android.media.Ringtone;
import android.net.Uri;
import android.os.Build;

public class AlarmReceiver extends BroadcastReceiver {
    private static Ringtone activeRingtone;
    public static final String ACTION_STOP = "com.saranraj.studyplanner.ACTION_STOP_ALARM";

    @Override public void onReceive(Context context, Intent intent) {
        NotificationManager manager =
            (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        int alarmId = intent.getIntExtra("alarm_id", 7001);

        // The notification's Stop Alarm action dismisses the alarm notification/sound.
        if (ACTION_STOP.equals(intent.getAction())) {
            if (activeRingtone != null) {
                try { if (activeRingtone.isPlaying()) activeRingtone.stop(); } catch (Exception ignored) { }
                activeRingtone = null;
            }
            manager.cancel(alarmId);
            return;
        }

        String title = intent.getStringExtra("title");
        if (title == null || title.trim().isEmpty()) title = "Your task is due now";

        Intent open = new Intent(context, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent contentIntent = PendingIntent.getActivity(context, alarmId, open,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Intent stop = new Intent(context, AlarmReceiver.class);
        stop.setAction(ACTION_STOP);
        stop.putExtra("alarm_id", alarmId);
        PendingIntent stopIntent = PendingIntent.getBroadcast(context, alarmId, stop,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Uri sound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
            ? new Notification.Builder(context, "study_planner_alarms_v2")
            : new Notification.Builder(context);
        builder.setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle("⏰ Study Planner Reminder")
            .setContentText(title)
            .setStyle(new Notification.BigTextStyle().bigText(title + " — your task is due now."))
            .setCategory(Notification.CATEGORY_ALARM)
            .setPriority(Notification.PRIORITY_MAX)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setAutoCancel(true)
            .setContentIntent(contentIntent)
            .addAction(android.R.drawable.ic_media_pause, "Stop Alarm", stopIntent);
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            builder.setSound(sound);
            builder.setVibrate(new long[]{0, 700, 300, 700, 300, 1000});
        }
        // Loop the alarm ringtone until Stop Alarm is tapped.
        if (activeRingtone != null) {
            try { if (activeRingtone.isPlaying()) activeRingtone.stop(); } catch (Exception ignored) { }
        }
        activeRingtone = RingtoneManager.getRingtone(context, sound);
        if (activeRingtone != null) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) activeRingtone.setLooping(true);
            activeRingtone.play();
        }
        // Prevent notification sound from playing a second time.
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) builder.setSound(null);
        manager.notify(alarmId, builder.build());
    }
}
