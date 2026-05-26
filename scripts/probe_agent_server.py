"""
Probe the agent server directly (via localhost port redirect) to understand
the conversation initialization API and workspace mounting contract.
"""
import httpx, json, time

# The agent server URL from the start-task response uses host.docker.internal
# but from the host machine, the port is forwarded to localhost
# Extract the port from: http://host.docker.internal:38063
AGENT_SERVER_PORT = 38063
AGENT_BASE = f"http://localhost:{AGENT_SERVER_PORT}"

print(f"Probing agent server at {AGENT_BASE}")

# 1. Check if we can reach it
try:
    r = httpx.get(f"{AGENT_BASE}/", timeout=5)
    print(f"Root: HTTP {r.status_code} - {r.text[:200]}")
except Exception as e:
    print(f"Root unreachable: {e}")

# 2. Check health
try:
    r = httpx.get(f"{AGENT_BASE}/health", timeout=5)
    print(f"Health: HTTP {r.status_code} - {r.text[:200]}")
except Exception as e:
    print(f"Health unreachable: {e}")

# 3. Try to get the OpenAPI spec from the agent server
try:
    r = httpx.get(f"{AGENT_BASE}/openapi.json", timeout=5)
    if r.status_code == 200:
        spec = r.json()
        print(f"Agent server OpenAPI paths: {list(spec.get('paths', {}).keys())[:30]}")
        schemas = spec.get('components', {}).get('schemas', {})
        for name in ['ConversationRequest', 'ConversationInitData', 'InitAction']:
            if name in schemas:
                print(f"  Schema {name}: {json.dumps(schemas[name], indent=2)[:500]}")
    else:
        print(f"OpenAPI: HTTP {r.status_code} - {r.text[:200]}")
except Exception as e:
    print(f"OpenAPI unreachable: {e}")

# 4. List all conversations on the agent server
try:
    r = httpx.get(f"{AGENT_BASE}/api/conversations", timeout=5)
    print(f"Agent conversations: HTTP {r.status_code} - {r.text[:1000]}")
except Exception as e:
    print(f"Agent conversations: {e}")
