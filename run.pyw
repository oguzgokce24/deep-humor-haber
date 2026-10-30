"""Windows'ta Görev Zamanlayıcı'nın çalıştırdığı dosya (pencere açmadan).
Çıktıyı logs/calisma.log dosyasına yazar ve aynı anda iki kopyanın çalışmasını engeller."""
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
LOG = ROOT / "logs" / "calisma.log"
LOCK = ROOT / "logs" / "calisiyor.kilit"
LOG.parent.mkdir(exist_ok=True)

# Önceki çalışma hâlâ sürüyorsa (10 dk'dan yeni kilit) bu turu atla
if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 600:
    sys.exit(0)
LOCK.write_text(str(os.getpid()))

# Log 2 MB'ı geçerse son kısmı tut
if LOG.exists() and LOG.stat().st_size > 2_000_000:
    LOG.write_bytes(LOG.read_bytes()[-500_000:])

with open(LOG, "a", encoding="utf-8") as f:
    sys.stdout = sys.stderr = f
    print(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====", flush=True)
    try:
        import main
        sys.argv = ["main.py"]
        main.main()
    except SystemExit as e:
        if e.code not in (0, None):
            print(f"Durdu: {e.code}")
    except Exception:
        traceback.print_exc()
    finally:
        try:
            LOCK.unlink()
        except OSError:
            pass
