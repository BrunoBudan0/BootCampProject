import sys
from pathlib import Path

# testes de unidade importam o código da API direto, sem HTTP
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "events-api" / "src"))