@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

set "SDK=%ANDROID_SDK_ROOT%"
if not defined SDK set "SDK=%ANDROID_HOME%"
if not defined SDK set "SDK=%LOCALAPPDATA%\Android\Sdk"
if not exist "%SDK%\build-tools" exit /b 0
if not exist "%SDK%\platforms" exit /b 0

set "BUILD_TOOLS="
for /f "delims=" %%D in ('dir /b /ad /o-n "%SDK%\build-tools" 2^>nul') do if not defined BUILD_TOOLS set "BUILD_TOOLS=%SDK%\build-tools\%%D"
set "PLATFORM="
set "PLATFORM_DIR="
for /f "delims=" %%D in ('dir /b /ad /o-n "%SDK%\platforms\android-*" 2^>nul') do if not defined PLATFORM set "PLATFORM=%SDK%\platforms\%%D\android.jar"& set "PLATFORM_DIR=%%D"
if not defined BUILD_TOOLS exit /b 0
if not exist "%PLATFORM%" exit /b 0
set "TARGET_API=%PLATFORM_DIR:android-=%"

set "JAVAC="
set "KEYTOOL="
if defined JAVA_HOME if exist "%JAVA_HOME%\bin\javac.exe" set "JAVAC=%JAVA_HOME%\bin\javac.exe"
if defined JAVA_HOME if exist "%JAVA_HOME%\bin\keytool.exe" set "KEYTOOL=%JAVA_HOME%\bin\keytool.exe"
if not defined JAVAC if exist "C:\Program Files\Android\Android Studio\jbr\bin\javac.exe" set "JAVAC=C:\Program Files\Android\Android Studio\jbr\bin\javac.exe"
if not defined KEYTOOL if exist "C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe" set "KEYTOOL=C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe"
if not defined JAVA_HOME if exist "C:\Program Files\Android\Android Studio\jbr\bin\java.exe" set "JAVA_HOME=C:\Program Files\Android\Android Studio\jbr"
for /f "delims=" %%J in ('where javac.exe 2^>nul') do if not defined JAVAC set "JAVAC=%%J"
for /f "delims=" %%J in ('where keytool.exe 2^>nul') do if not defined KEYTOOL set "KEYTOOL=%%J"
if not defined JAVAC exit /b 0

if exist "android-sample\build" rmdir /s /q "android-sample\build"
mkdir "android-sample\build\classes"
mkdir "android-sample\build\dex"
"%JAVAC%" -source 8 -target 8 -bootclasspath "%PLATFORM%" -d "android-sample\build\classes" "android-sample\src\org\jidan\demo\MainActivity.java"
if errorlevel 1 exit /b 1
call "%BUILD_TOOLS%\d8.bat" --lib "%PLATFORM%" --output "android-sample\build\dex" "android-sample\build\classes\org\jidan\demo\MainActivity.class" "android-sample\build\classes\org\jidan\demo\MainActivity$1.class"
if errorlevel 1 exit /b 1
"%BUILD_TOOLS%\aapt2.exe" link -o "android-sample\build\base.apk" -I "%PLATFORM%" --manifest "android-sample\AndroidManifest.xml" --min-sdk-version 26 --target-sdk-version "%TARGET_API%" --version-code 1 --version-name 1.0
if errorlevel 1 exit /b 1
copy /y "android-sample\build\base.apk" "android-sample\build\unaligned.apk" >nul
pushd "android-sample\build\dex"
"%BUILD_TOOLS%\aapt.exe" add "..\unaligned.apk" classes.dex >nul
popd
if errorlevel 1 exit /b 1
"%BUILD_TOOLS%\zipalign.exe" -f 4 "android-sample\build\unaligned.apk" "android-sample\build\aligned.apk"
if errorlevel 1 exit /b 1

set "KEYSTORE=%USERPROFILE%\.android\debug.keystore"
if not exist "%KEYSTORE%" (
  if not defined KEYTOOL exit /b 0
  set "KEYSTORE=android-sample\build\debug.keystore"
  "%KEYTOOL%" -genkeypair -keystore "android-sample\build\debug.keystore" -storepass android -alias androiddebugkey -keypass android -dname "CN=Jidan Debug,O=Jidan,C=CN" -keyalg RSA -keysize 2048 -validity 3650 -noprompt >nul 2>nul
  if errorlevel 1 exit /b 1
)
call "%BUILD_TOOLS%\apksigner.bat" sign --ks "%KEYSTORE%" --ks-key-alias androiddebugkey --ks-pass pass:android --key-pass pass:android --out "samples\JidanDemo.apk" "android-sample\build\aligned.apk"
if errorlevel 1 exit /b 1
echo Built signed samples\JidanDemo.apk with Android API %TARGET_API%
