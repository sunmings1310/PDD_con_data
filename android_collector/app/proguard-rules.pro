-keep class com.collector.pdd.** { *; }
-keep class * extends android.accessibilityservice.AccessibilityService { *; }
-keep class * extends android.app.Service { *; }
-keep class * extends android.app.Activity { *; }
-keep class * extends android.content.ContentProvider { *; }
-keepclassmembers class * {
    @androidx.room.* <methods>;
}
-keep class * extends androidx.room.RoomDatabase { *; }
-dontwarn okhttp3.**
-dontwarn okio.**
