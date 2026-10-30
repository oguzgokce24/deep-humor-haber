@echo off
setlocal
cd /d "%~dp0"
title Deep Humor Haber - Kurulum
echo.
echo  ==============================================
echo    Deep Humor Haber - Kurulum
echo  ==============================================
echo.

REM 1) Python var mi?
py -3 --version >nul 2>&1
if errorlevel 1 (
  echo  [1/4] Python bulunamadi, yukleniyor... ^(birkac dakika surebilir^)
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo.
    echo  Python otomatik yuklenemedi. https://www.python.org/downloads/ adresinden
    echo  Python'u yukleyip ^("Add python.exe to PATH" kutusunu isaretle^) bu dosyayi tekrar calistir.
    pause
    exit /b 1
  )
  echo  Python yuklendi. Lutfen bu pencereyi kapatip KUR.bat dosyasini TEKRAR calistir.
  pause
  exit /b 0
) else (
  echo  [1/4] Python hazir.
)

REM 2) Gerekli paketler
echo  [2/4] Gerekli paketler yukleniyor...
py -3 -m pip install --user --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo  Paketler yuklenemedi. Internet baglantini kontrol edip tekrar dene.
  pause
  exit /b 1
)

REM 3) Anahtar dosyasi
if not exist anahtarlar.txt copy /y anahtarlar_ornek.txt anahtarlar.txt >nul
findstr /r /c:"^FB_PAGE_TOKEN=..*" anahtarlar.txt >nul
if errorlevel 1 (
  echo  [3/4] Simdi Not Defteri acilacak. FB_PAGE_TOKEN= satirinin sonuna Facebook anahtarini
  echo        yapistir, istersen ANTHROPIC_API_KEY= satirina da Claude anahtarini. Kaydet ve kapat.
  notepad anahtarlar.txt
)
findstr /r /c:"^FB_PAGE_TOKEN=..*" anahtarlar.txt >nul
if errorlevel 1 (
  echo  Facebook anahtari girilmedi. Anahtari ekledikten sonra KUR.bat'i tekrar calistir.
  pause
  exit /b 1
)
echo  [3/4] Anahtarlar hazir.

REM 4) Gorev Zamanlayici: her 3 dakikada bir, pencere acmadan
for /f "delims=" %%P in ('py -3 -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set "PYW=%%P"
schtasks /Create /F /SC MINUTE /MO 3 /TN "DeepHumorHaber" /TR "\"%PYW%\" \"%~dp0run.pyw\"" >nul
if errorlevel 1 (
  echo  Zamanlanmis gorev olusturulamadi.
  pause
  exit /b 1
)
schtasks /Run /TN "DeepHumorHaber" >nul
echo  [4/4] Otomasyon kuruldu: her 3 dakikada bir arka planda calisacak.
echo.
echo  Kayitlar: logs\calisma.log
echo  Durdurmak icin: KALDIR.bat
echo.
pause
