plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.devtools.ksp")
}

val releaseTaskRequested = gradle.startParameter.taskNames.any {
    it.lowercase().contains("release")
}

fun releaseSetting(propertyName: String, environmentName: String): String? =
    providers.gradleProperty(propertyName)
        .orElse(providers.environmentVariable(environmentName))
        .orNull
        ?.trim()
        ?.takeIf { it.isNotEmpty() }

val releaseStoreFile = releaseSetting("RELEASE_STORE_FILE", "ANDROID_RELEASE_STORE_FILE")
val releaseStorePassword = releaseSetting("RELEASE_STORE_PASSWORD", "ANDROID_RELEASE_STORE_PASSWORD")
val releaseKeyAlias = releaseSetting("RELEASE_KEY_ALIAS", "ANDROID_RELEASE_KEY_ALIAS")
val releaseKeyPassword = releaseSetting("RELEASE_KEY_PASSWORD", "ANDROID_RELEASE_KEY_PASSWORD")

android {
    namespace = "com.collector.pdd"
    compileSdk = 34

    defaultConfig {
        // 独立包名 + 自有证书，降低华为云端「诈骗应用」指纹命中
        applicationId = "com.linkdesk.tool"
        minSdk = 26
        targetSdk = 33
        versionCode = 70
        versionName = "1.0.69"
    }

    buildFeatures {
        buildConfig = true
    }

    signingConfigs {
        create("release") {
            if (releaseTaskRequested) {
                storeFile = file(releaseStoreFile!!)
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }
    buildTypes {
        release {
            // 混淆改变 DEX 指纹，降低云端哈希命中（功能类全 keep）
            isMinifyEnabled = true
            isShrinkResources = true
            signingConfig = signingConfigs.getByName("release")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            isDebuggable = true
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.9.0")
    implementation("androidx.activity:activity-ktx:1.7.2")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.6.2")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.6.2")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")

    implementation("androidx.room:room-runtime:2.5.2")
    implementation("androidx.room:room-ktx:2.5.2")
    ksp("androidx.room:room-compiler:2.5.2")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    testImplementation("junit:junit:4.13.2")
}
