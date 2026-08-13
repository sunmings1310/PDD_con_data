pluginManagement {
    repositories {
        maven { url = uri("https://maven.aliyun.com/repository/google") }
        maven { url = uri("https://maven.aliyun.com/repository/public") }
        maven { url = uri("https://maven.aliyun.com/repository/gradle-plugin") }
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

val releaseTaskRequested = gradle.startParameter.taskNames.any {
    it.lowercase().contains("release")
}

if (releaseTaskRequested) {
    fun releaseSetting(propertyName: String, environmentName: String): String? =
        providers.gradleProperty(propertyName)
            .orElse(providers.environmentVariable(environmentName))
            .orNull
            ?.trim()
            ?.takeIf { it.isNotEmpty() }

    val releaseStoreFile = releaseSetting("RELEASE_STORE_FILE", "ANDROID_RELEASE_STORE_FILE")
    val missing = listOfNotNull(
        "RELEASE_STORE_FILE".takeIf { releaseStoreFile == null },
        "RELEASE_STORE_PASSWORD".takeIf {
            releaseSetting("RELEASE_STORE_PASSWORD", "ANDROID_RELEASE_STORE_PASSWORD") == null
        },
        "RELEASE_KEY_ALIAS".takeIf {
            releaseSetting("RELEASE_KEY_ALIAS", "ANDROID_RELEASE_KEY_ALIAS") == null
        },
        "RELEASE_KEY_PASSWORD".takeIf {
            releaseSetting("RELEASE_KEY_PASSWORD", "ANDROID_RELEASE_KEY_PASSWORD") == null
        },
    )
    require(missing.isEmpty()) {
        "Release signing configuration is missing: ${missing.joinToString(", ")}"
    }
    require(file(releaseStoreFile!!).isFile) {
        "Release signing keystore file does not exist (RELEASE_STORE_FILE)."
    }
}
dependencyResolutionManagement {
    // PREFER_PROJECT：兼容全局 ~/.gradle/init.gradle 注入镜像仓库（与 pda-picking 一致）
    repositoriesMode.set(RepositoriesMode.PREFER_PROJECT)
    repositories {
        maven { url = uri("https://maven.aliyun.com/repository/google") }
        maven { url = uri("https://maven.aliyun.com/repository/public") }
        google()
        mavenCentral()
    }
}
rootProject.name = "PddCollector"
include(":app")
