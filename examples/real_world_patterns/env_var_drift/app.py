import os

def start_app():
    """Simulate app startup using environment variables."""
    # Strict validation: Environment must provide DATABASE_URL
    if "DATABASE_URL" not in os.environ:
        raise RuntimeError("Missing required environment variable: DATABASE_URL")
        
    db_url = os.environ["DATABASE_URL"]
    return f"Running app with DB: {db_url}"
