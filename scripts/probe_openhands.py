import httpx, json, time

base = 'http://localhost:3000'
start_task_id = '0c717a2e801f48d09565bc2c31f9c88f'

print('Polling start task for agent_server_url...')
for i in range(30):
    resp = httpx.get(
        f'{base}/api/v1/app-conversations/start-tasks',
        params={'ids': [start_task_id]},
        timeout=10
    )
    data = resp.json()
    if data and data[0]:
        task = data[0]
        status = task.get('status', 'UNKNOWN')
        agent_url = task.get('agent_server_url')
        conv_id = task.get('app_conversation_id')
        print(f'  [{i}] status={status} agent_server_url={agent_url} conv_id={conv_id}')

        if status in ('READY', 'ERROR'):
            print()
            print('=== START TASK ===')
            print(json.dumps(task, indent=2))

            if conv_id:
                conv_resp = httpx.get(
                    f'{base}/api/v1/app-conversations',
                    params={'ids': [conv_id]},
                    timeout=10
                )
                print('=== CONVERSATION ===')
                print(json.dumps(conv_resp.json(), indent=2))

                # Try to read conversation file from workspace
                file_resp = httpx.get(
                    f'{base}/api/v1/app-conversations/{conv_id}/file',
                    params={'file_path': '/workspace/project/PLAN.md'},
                    timeout=10
                )
                print(f'=== FILE /workspace/project/PLAN.md ===')
                print(f'HTTP {file_resp.status_code}: {file_resp.text[:500]}')

                # Also try root listing
                for p in ['/workspace', '/workspace/project', '/root', '/home']:
                    fr = httpx.get(
                        f'{base}/api/v1/app-conversations/{conv_id}/file',
                        params={'file_path': p},
                        timeout=10
                    )
                    print(f'  {p}: HTTP {fr.status_code} len={len(fr.text)} preview={fr.text[:100]}')

            # Clean up probe conversation
            if conv_id:
                httpx.delete(f'{base}/api/v1/app-conversations/{conv_id}', timeout=10)
                print('Deleted probe conversation')
            break
    time.sleep(4)
