@echo off
setlocal
cd /d "%~dp0"
set "FX=C:\Windows\Microsoft.NET\Framework64\v4.0.30319"
set "WPF=%FX%\WPF"
if not exist "%FX%\csc.exe" (
  echo Native C# compiler was not found.
  exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is required only to generate the clean-room sample packages.
  exit /b 1
)
node tools\build-samples.mjs
if errorlevel 1 exit /b 1
call tools\build-android-sample.cmd
if errorlevel 1 exit /b 1
"%FX%\csc.exe" /nologo /target:winexe /platform:x64 /optimize+ /debug- /out:"JidanOS.exe" /win32manifest:"src\app.manifest" /resource:"src\MainWindow.xaml",JidanOS.MainWindow.xaml /reference:"%WPF%\PresentationCore.dll" /reference:"%WPF%\PresentationFramework.dll" /reference:"%WPF%\WindowsBase.dll" /reference:"%FX%\System.Xaml.dll" /reference:"%FX%\System.dll" /reference:"%FX%\System.Core.dll" /reference:"%FX%\System.Xml.dll" /reference:"%FX%\System.Xml.Linq.dll" /reference:"%FX%\System.IO.Compression.dll" /reference:"%FX%\System.IO.Compression.FileSystem.dll" src\*.cs
if errorlevel 1 exit /b 1
echo Built JidanOS.exe
