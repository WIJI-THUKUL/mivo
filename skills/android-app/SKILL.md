---
name: android-app
description: Create Android apps that build in AIDE or Gradle (Java/XML project layout, manifest, activity, layout).
triggers: android, aide, apk, kotlin, manifest, activity
---
# Android apps (AIDE-friendly)
Follow the layout that already exists in the folder. For a NEW simple app use the classic layout (opens directly in AIDE), plain Java and only the Android SDK (no AppCompat or external libs):

```
MyApp/
  AndroidManifest.xml
  src/com/example/myapp/MainActivity.java
  res/layout/main.xml
  res/values/strings.xml
```
Gradle layout (only if asked, or if build.gradle exists): settings.gradle, build.gradle, app/build.gradle, app/src/main/{AndroidManifest.xml, java/..., res/...}.

**AndroidManifest.xml**
```
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.example.myapp" android:versionCode="1" android:versionName="1.0">
  <uses-sdk android:minSdkVersion="21" android:targetSdkVersion="30"/>
  <application android:label="@string/app_name" android:theme="@android:style/Theme.Holo.Light">
    <activity android:name=".MainActivity" android:exported="true">
      <intent-filter>
        <action android:name="android.intent.action.MAIN"/>
        <category android:name="android.intent.category.LAUNCHER"/>
      </intent-filter>
    </activity>
  </application>
</manifest>
```
**MainActivity.java**: `package com.example.myapp; import android.app.Activity; import android.os.Bundle; import android.widget.*; public class MainActivity extends Activity { @Override protected void onCreate(Bundle b){ super.onCreate(b); setContentView(R.layout.main); } }` (put each statement on its own line in the real file).
**res/layout/main.xml**: a LinearLayout (vertical, match_parent) containing a TextView and a Button with ids `@+id/...`.
**res/values/strings.xml**: `<resources><string name="app_name">MyApp</string></resources>`.

Rules: the package in the manifest must equal the folder path under src/ (or java/); every id used in Java exists in the layout; every @string exists in strings.xml; add `<uses-permission .../>` for each permission used (e.g. INTERNET). You cannot compile or run an APK inside Termux: finish by telling the user to open the folder in AIDE (or run ./gradlew assembleDebug if Gradle is set up) and press build.
