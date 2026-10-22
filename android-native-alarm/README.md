# Student Smart Study Planner — Android native alarm wrapper

This is a native Android WebView wrapper for the existing hosted Flask website. It requests notification permission and exact-alarm access, and schedules an Android AlarmManager alarm when a user submits the To-Do form with a future `due_datetime`.

## Open in Android Studio
1. Open the `android-native-alarm` folder as a project.
2. Use JDK 17 and allow Gradle sync.
3. Build and run on an Android phone.
4. Allow notifications and exact-alarm access when prompted.

## Important limitations
- This is source code; it does not publish or install an APK automatically.
- The alarm is scheduled when the To-Do form is submitted from this Android wrapper. Existing reminders created earlier in the website are not automatically imported yet.
- Editing/deleting a To-Do in the website does not yet reschedule/cancel the Android alarm.
- Android battery optimization, notification permission, and exact-alarm settings can affect delivery.
- The website must remain online for login and task management; the alarm already scheduled on the phone is local.
