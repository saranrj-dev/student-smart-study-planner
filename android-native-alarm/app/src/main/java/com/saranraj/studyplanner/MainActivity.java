package com.saranraj.studyplanner;

import android.Manifest;
import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.app.AlarmManager;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import android.os.Handler;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

public class MainActivity extends Activity {
    private static final String SITE_URL = "https://student-smart-study-planner-2.onrender.com/login";
    private WebView webView;
    private FrameLayout rootLayout;
    private View splashView;
    private final Handler splashHandler = new Handler();

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        createChannel();
        requestNotificationPermission();
        rootLayout = new FrameLayout(this);
        rootLayout.setBackgroundColor(Color.rgb(10, 18, 32));
        webView = new WebView(this);
        rootLayout.addView(webView, new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        splashView = createSplashScreen();
        rootLayout.addView(splashView, new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        setContentView(rootLayout);
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.setWebChromeClient(new WebChromeClient());
        webView.addJavascriptInterface(new NativeAlarmBridge(this), "NativeAlarm");
        webView.setWebViewClient(new WebViewClient() {
            @Override public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                injectReminderHooks(view);
                // Keep the native Edutrack splash visible while Render's sleeping service wakes up.
                view.evaluateJavascript(
                    "(function(){var t=((document.title||'')+' '+(document.body?document.body.innerText:'')).toLowerCase();return (t.includes('application loading')||t.includes('service waking up')||t.includes('start building on render')||t.includes('steady hands. clean logs'));})()",
                    value -> {
                        boolean renderWakeScreen = "true".equals(value);
                        if (renderWakeScreen) {
                            splashHandler.postDelayed(() -> {
                                if (webView != null && splashView != null) webView.reload();
                            }, 4500);
                        } else if (splashView != null) {
                            splashView.animate().alpha(0f).setDuration(300).withEndAction(() -> {
                                if (rootLayout != null && splashView != null) rootLayout.removeView(splashView);
                                splashView = null;
                            }).start();
                        }
                    });
            }
        });
        webView.loadUrl(SITE_URL);
    }


    private View createSplashScreen() {
        FrameLayout frame = new FrameLayout(this);
        frame.setBackgroundColor(Color.rgb(10, 18, 32));

        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setGravity(Gravity.CENTER);
        content.setPadding(32, 32, 32, 32);

        ImageView logo = new ImageView(this);
        logo.setImageResource(com.saranraj.studyplanner.R.drawable.edutrack_logo);
        LinearLayout.LayoutParams logoParams = new LinearLayout.LayoutParams(124, 124);
        logoParams.bottomMargin = 24;
        content.addView(logo, logoParams);

        TextView name = new TextView(this);
        name.setText("Edutrack");
        name.setTextColor(Color.WHITE);
        name.setTextSize(32);
        name.setTypeface(Typeface.create("sans-serif", Typeface.BOLD));
        name.setGravity(Gravity.CENTER);
        content.addView(name);

        TextView tagline = new TextView(this);
        tagline.setText("Plan smarter. Learn better.");
        tagline.setTextColor(Color.rgb(174, 190, 211));
        tagline.setTextSize(15);
        tagline.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams tagParams = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        tagParams.topMargin = 8;
        content.addView(tagline, tagParams);

        ProgressBar progress = new ProgressBar(this);
        progress.setIndeterminate(true);
        progress.setIndeterminateTintList(android.content.res.ColorStateList.valueOf(Color.rgb(54, 211, 153)));
        LinearLayout.LayoutParams progressParams = new LinearLayout.LayoutParams(48, 48);
        progressParams.topMargin = 32;
        content.addView(progress, progressParams);

        TextView loading = new TextView(this);
        loading.setText("Preparing your study space…");
        loading.setTextColor(Color.rgb(174, 190, 211));
        loading.setTextSize(13);
        loading.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams loadingParams = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        loadingParams.topMargin = 12;
        content.addView(loading, loadingParams);

        FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT);
        frame.addView(content, params);
        return frame;
    }

    private void injectReminderHooks(WebView view) {
        String js = "(function(){if(window.__edutrackReminderHooks)return;window.__edutrackReminderHooks=true;" +
          "function hook(){document.querySelectorAll('form').forEach(function(f){" +
          "if(f.dataset.edutrackHooked)return;" +
          "var subject=f.querySelector('[name=subject]');var title=f.querySelector('[name=title]');" +
          "var due=f.querySelector('[name=due_datetime]');var dueDate=f.querySelector('[name=due_date]');" +
          "var examDate=f.querySelector('[name=exam_date]');var studyDate=f.querySelector('[name=study_date]');" +
          "var start=f.querySelector('[name=start_time]');var topic=f.querySelector('[name=topic]');" +
          "var kind='',when=null,label='';" +
          "if(title&&due){kind='task';}" +
          "else if(examDate){kind='exam';}" +
          "else if(dueDate&&title){kind='assignment';}" +
          "else if(dueDate&&subject){kind='assignment';}" +
          "else if(studyDate&&start&&topic){kind='timetable';}" +
          "if(!kind)return;f.dataset.edutrackHooked='1';" +
          "f.addEventListener('submit',function(){" +
          "var now=new Date();var name=(title&&title.value)||(topic&&topic.value)||(subject&&subject.value)||'Study reminder';" +
          "if(kind==='task'){var ms=new Date(due.value).getTime();if(Number.isFinite(ms)&&ms>Date.now())NativeAlarm.schedule(name,ms);return;}" +
          "if(kind==='exam'||kind==='assignment'){" +
          "var raw=(kind==='exam'?examDate.value:dueDate.value);if(!raw)return;" +
          "var d=new Date(raw+'T09:00:00');d.setDate(d.getDate()-1);" +
          "var ms=d.getTime();if(ms>Date.now())NativeAlarm.scheduleNotification((kind==='exam'?'Exam tomorrow: ':'Assignment due tomorrow: ')+name,ms,kind);return;}" +
          "if(kind==='timetable'){var d=new Date(studyDate.value+'T'+start.value+':00');var ms=d.getTime();" +
          "if(ms>Date.now())NativeAlarm.scheduleNotification('Study time: '+name+' — '+(topic?topic.value:''),ms,'timetable');}" +
          "},true);});}" +
          "hook();new MutationObserver(hook).observe(document.documentElement,{childList:true,subtree:true});})();";
        view.evaluateJavascript(js, null);
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Uri sound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);
            AudioAttributes audio = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build();
            NotificationChannel channel = new NotificationChannel(
                "edutrack_reminders_v1", "Edutrack Reminders", NotificationManager.IMPORTANCE_HIGH);
            channel.setDescription("Exam, assignment and timetable reminders");
            channel.enableVibration(true);
            channel.setSound(sound, audio);
            channel.setLockscreenVisibility(android.app.Notification.VISIBILITY_PUBLIC);
            getSystemService(NotificationManager.class).createNotificationChannel(channel);

            Uri alarmSound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
            AudioAttributes alarmAudio = new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build();
            NotificationChannel alarmChannel = new NotificationChannel(
                "edutrack_alarm_v1", "Edutrack Task Alarms", NotificationManager.IMPORTANCE_HIGH);
            alarmChannel.setDescription("Task alarms that continue until stopped");
            alarmChannel.enableVibration(true);
            alarmChannel.setVibrationPattern(new long[]{0,500,250,500});
            alarmChannel.setSound(alarmSound, alarmAudio);
            alarmChannel.setLockscreenVisibility(android.app.Notification.VISIBILITY_PUBLIC);
            getSystemService(NotificationManager.class).createNotificationChannel(alarmChannel);
        }
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 101);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            AlarmManager am = (AlarmManager) getSystemService(ALARM_SERVICE);
            if (!am.canScheduleExactAlarms()) {
                try { startActivity(new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                    Uri.parse("package:" + getPackageName()))); } catch (Exception ignored) { }
            }
        }
    }

    public static class NativeAlarmBridge {
        private final Context context;
        NativeAlarmBridge(Context context) { this.context = context.getApplicationContext(); }

        @JavascriptInterface public void schedule(String title, long triggerAtMillis) {
            scheduleInternal(title, triggerAtMillis, "alarm", title.hashCode());
        }

        @JavascriptInterface public void scheduleNotification(String title, long triggerAtMillis, String category) {
            int id = (category + ":" + title).hashCode();
            scheduleInternal(title, triggerAtMillis, "notification", id);
        }

        private void scheduleInternal(String title, long triggerAtMillis, String mode, int id) {
            if (triggerAtMillis <= System.currentTimeMillis()) return;
            Intent intent = new Intent(context, AlarmReceiver.class);
            intent.putExtra("title", title);
            intent.putExtra("alarm_id", id);
            intent.putExtra("reminder_mode", mode);
            PendingIntent pi = PendingIntent.getBroadcast(context, id, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            AlarmManager am = (AlarmManager) context.getSystemService(ALARM_SERVICE);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !am.canScheduleExactAlarms()) {
                am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pi);
            } else {
                am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pi);
            }
            android.os.Handler handler = new android.os.Handler(context.getMainLooper());
            handler.post(() -> Toast.makeText(context, "Edutrack reminder scheduled", Toast.LENGTH_SHORT).show());
        }

        @JavascriptInterface public void cancel(String title) {
            int id = title.hashCode();
            Intent intent = new Intent(context, AlarmReceiver.class);
            PendingIntent pi = PendingIntent.getBroadcast(context, id, intent,
                PendingIntent.FLAG_NO_CREATE | PendingIntent.FLAG_IMMUTABLE);
            if (pi != null) {
                ((AlarmManager) context.getSystemService(ALARM_SERVICE)).cancel(pi);
                pi.cancel();
            }
        }
    }

    @Override public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }
}