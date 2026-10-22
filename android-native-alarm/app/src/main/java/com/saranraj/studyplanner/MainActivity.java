package com.saranraj.studyplanner;

import android.Manifest;
import android.app.Activity;
import android.app.AlarmManager;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

public class MainActivity extends Activity {
    private static final String SITE_URL = "https://student-smart-study-planner-2.onrender.com";
    private WebView webView;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        createChannel();
        requestNotificationPermission();

        webView = new WebView(this);
        setContentView(webView);
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.setWebChromeClient(new WebChromeClient());
        webView.addJavascriptInterface(new NativeAlarmBridge(this), "NativeAlarm");
        webView.setWebViewClient(new WebViewClient() {
            @Override public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                injectTodoAlarmHook(view);
            }
        });
        webView.loadUrl(SITE_URL);
    }

    private void injectTodoAlarmHook(WebView view) {
        String js = "(function(){if(window.__nativeAlarmHooked)return;window.__nativeAlarmHooked=true;" +
            "function hook(){document.querySelectorAll('form').forEach(function(f){" +
            "if(f.dataset.nativeAlarmHooked)return;" +
            "var title=f.querySelector('[name=title]');var due=f.querySelector('[name=due_datetime]');" +
            "if(!title||!due)return;f.dataset.nativeAlarmHooked='1';" +
            "f.addEventListener('submit',function(){" +
            "var t=title.value;var d=due.value;if(t&&d&&window.NativeAlarm){" +
            "var ms=new Date(d).getTime();if(Number.isFinite(ms)&&ms>Date.now())NativeAlarm.schedule(t,ms);" +
            "}},true);});}" +
            "hook();new MutationObserver(hook).observe(document.documentElement,{childList:true,subtree:true});})();";
        view.evaluateJavascript(js, null);
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                "study_planner_alarms", "Study Planner Alarms", NotificationManager.IMPORTANCE_HIGH);
            channel.setDescription("To-do due-time alarms");
            channel.enableVibration(true);
            channel.setLockscreenVisibility(android.app.Notification.VISIBILITY_PUBLIC);
            getSystemService(NotificationManager.class).createNotificationChannel(channel);
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
                try {
                    startActivity(new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                        Uri.parse("package:" + getPackageName())));
                } catch (Exception ignored) { }
            }
        }
    }

    public static class NativeAlarmBridge {
        private final Context context;
        NativeAlarmBridge(Context context) { this.context = context.getApplicationContext(); }

        @JavascriptInterface public void schedule(String title, long triggerAtMillis) {
            if (triggerAtMillis <= System.currentTimeMillis()) return;
            int id = title.hashCode();
            Intent intent = new Intent(context, AlarmReceiver.class);
            intent.putExtra("title", title);
            intent.putExtra("alarm_id", id);
            PendingIntent pi = PendingIntent.getBroadcast(context, id, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            AlarmManager am = (AlarmManager) context.getSystemService(ALARM_SERVICE);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !am.canScheduleExactAlarms()) {
                am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pi);
            } else {
                am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pi);
            }
            android.os.Handler handler = new android.os.Handler(context.getMainLooper());
            handler.post(() -> Toast.makeText(context, "Native alarm scheduled", Toast.LENGTH_SHORT).show());
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
