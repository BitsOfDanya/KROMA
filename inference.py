import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "ml" / "src"))

from kroma_ml.competition import main

if __name__ == "__main__":
    main()
