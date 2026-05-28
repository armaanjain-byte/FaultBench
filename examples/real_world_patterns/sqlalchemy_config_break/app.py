import json
from pathlib import Path

def connect_db(work_dir: Path):
    """Simulate app startup connecting to a database."""
    config_path = work_dir / "config.json"
    if not config_path.exists():
        raise RuntimeError("Missing config.json")
        
    config = json.loads(config_path.read_text())
    
    # Strict validation: DATABASE_URL must exist
    if "DATABASE_URL" not in config:
        raise ValueError("App startup failed: DATABASE_URL missing from configuration")
        
    db_url = config["DATABASE_URL"]
    return f"Engine connected to {db_url}"
