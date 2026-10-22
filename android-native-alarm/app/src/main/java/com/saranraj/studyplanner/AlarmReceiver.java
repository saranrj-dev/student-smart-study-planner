package com.saranraj.studyplanner;

import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;

public class AlarmReceiver extends BroadcastReceiver {
    public static final String ACTION_STOP = "com.saranraj.studyplanner.ACTION_STOP_ALARM";

    @Override public void onReceive(Context context, Intent intent) {
        NotificationManager manager = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        int alarmId = intent.getIntExtra("alarm_id", 7001);
        if (ACTION_STOP.equals(intent.getAction())) {
            Intent stop = new Intent(context, AlarmService.class);
            stop.setAction(AlarmService.ACTION_STOP);
            context.startService(stop);
            manager.cancel(alarmId);
            return;
        }

        String title = intent.getStringExtra("title");
        if (title == null || title.trim().isEmpty()) title = "Your task is due now";
        boolean simpleNotification = "notification".equals(intent.getStringExtra("reminder_mode"));

        Intent open = new Intent(context, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent contentIntent = PendingIntent.getActivity(context, alarmId, open,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Notification.Builder builder = new Notification.Builder(context,
            simpleNotification ? "edutrack_reminders_v1" : "edutrack_alarm_v1");
        builder.setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle(simpleNotification ? "Edutrack Reminder" : "Edutrack Task Alarm")
            .setContentText(title)
            .setStyle(new Notification.BigTextStyle().bigText(title))
            .setCategory(simpleNotification ? Notification.CATEGORY_REMINDER : Notification.CATEGORY_ALARM)
            .setPriority(Notification.PRIORITY_MAX)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setAutoCancel(simpleNotification)
            .setContentIntent(contentIntent);

        if (!simpleNotification) {
            Intent stop = new Intent(context, AlarmReceiver.class);
            stop.setAction(ACTION_STOP);
            stop.putExtra("alarm_id", alarmId);
            PendingIntent stopIntent = PendingIntent.getBroadcast(context, alarmId, stop,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            builder.addAction(android.R.drawable.ic_media_pause, "STOP ALARM", stopIntent);
        } else if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            builder.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION));
            builder.setVibrate(new long[]{0,250,150,250});
        }

        manager.notify(alarmId, builder.build());
        if (!simpleNotification) {
            Intent start = new Intent(context, AlarmService.class);
            start.setAction(AlarmService.ACTION_START);
            start.putExtra("title", title);
            start.putExtra("alarm_id", alarmId);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) context.startForegroundService(start);
            else context.startService(start);
        }
    }
}