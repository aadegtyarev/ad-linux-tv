plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
android {
    namespace = "io.github.aadegtyarev.adlinuxtv.remote"
    compileSdk = 35
    defaultConfig {
        applicationId = "io.github.aadegtyarev.adlinuxtv.remote"
        minSdk = 28
        targetSdk = 35
        versionCode = 6
        versionName = "0.2.5"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildTypes { release { isMinifyEnabled = false } }
    lint { abortOnError = true; checkReleaseBuilds = true }
    testOptions.unitTests.isIncludeAndroidResources = true
    testOptions.unitTests.all {
        // Robolectric downloads/caches remain in the approved private dev tree.
        it.systemProperty("user.home", System.getenv("HOME") ?: System.getProperty("user.home"))
    }
}
dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.webkit:webkit:1.12.1")
    implementation("androidx.media:media:1.7.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")
    implementation("com.google.zxing:core:3.5.3")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.14.1")
    testImplementation("org.mockito.kotlin:mockito-kotlin:5.4.0")
    testImplementation("org.mockito:mockito-core:5.14.2")
}
