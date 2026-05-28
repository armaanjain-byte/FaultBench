import json
from pathlib import Path

def fetch_user_data(work_dir: Path):
    """
    Simulate fetching data from a downstream microservice API.
    In reality, this would be `requests.get("https://api.mycorp.com/v1/user/123").json()`.
    We mock the network request by reading `config.json` from the workspace.
    """
    mock_api_response_file = work_dir / "config.json"
    if not mock_api_response_file.exists():
        raise RuntimeError("Mock API response not found")
        
    try:
        return json.loads(mock_api_response_file.read_text())
    except json.JSONDecodeError:
        raise ValueError("API returned malformed JSON instead of the expected contract")


def process_user(work_dir: Path):
    """Business logic that relies on a strict API contract."""
    payload = fetch_user_data(work_dir)
    
    # Strict contract validation: The API must return 'user_id'
    if "user_id" not in payload:
        raise KeyError("API Contract Violation: missing 'user_id' in response payload")
        
    user_id = payload["user_id"]
    name = payload.get("name", "Unknown")
    return f"Processed user {user_id} ({name})"
