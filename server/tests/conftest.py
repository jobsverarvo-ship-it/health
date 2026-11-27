import os
import tempfile
from pathlib import Path

# server.main 을 불러올 때 만들어지는 기본 앱이 실제 데이터 파일을 건드리지 않게 한다
os.environ.setdefault("APP_ENV", "development")
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "import.db")
