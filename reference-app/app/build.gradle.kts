plugins {
    id("com.android.application")
    id("com.google.devtools.ksp")
}

android {
    namespace = "dev.jidan.reference"
    compileSdk = 37

    defaultConfig {
        applicationId = "dev.jidan.reference"
        minSdk = 37
        targetSdk = 37
        versionCode = 2
        versionName = "0.2.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("androidx.appfunctions:appfunctions:1.0.0-alpha10")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")
    ksp("androidx.appfunctions:appfunctions-compiler:1.0.0-alpha10")
}

ksp {
    arg("appfunctions:aggregateAppFunctions", "true")
}
