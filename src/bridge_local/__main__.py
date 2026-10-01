import sys
from pathlib import Path

# Автоматическое добавление каталога src/ в sys.path
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from bridge_local import main  # noqa: E402

if __name__ == "__main__":
    main()
