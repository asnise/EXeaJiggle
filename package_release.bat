@echo off
echo Preparing EXea Jiggle Release...
set WORK_DIR=%TEMP%\EXeaJiggle_Release
set TARGET_DIR=%WORK_DIR%\exea_jiggle
set OUT_ZIP=%~dp0EXeaJiggle_Release.zip

if exist "%OUT_ZIP%" del "%OUT_ZIP%"
if exist "%WORK_DIR%" rmdir /s /q "%WORK_DIR%"

mkdir "%TARGET_DIR%"
xcopy "%~dp0*" "%TARGET_DIR%\" /E /I /H /Y /Q

echo Cleaning up unnecessary files...
for /d /r "%TARGET_DIR%" %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
for /d /r "%TARGET_DIR%" %%d in (.git) do @if exist "%%d" rd /s /q "%%d"
del /s /q "%TARGET_DIR%\*.bat"
del /s /q "%TARGET_DIR%\*.zip"
del /s /q "%TARGET_DIR%\.gitignore" 2>nul
del /s /q "%TARGET_DIR%\user_presets.json" 2>nul

echo Compressing Addon...
powershell -Command "Compress-Archive -Path '%TARGET_DIR%\*' -DestinationPath '%OUT_ZIP%' -Force"

echo Cleanup...
rmdir /s /q "%WORK_DIR%"

echo Done! Release zip created at: %OUT_ZIP%
