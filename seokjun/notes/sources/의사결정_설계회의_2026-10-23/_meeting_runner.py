"""Task-local adapter for the installed ai-meeting runner; globals are unchanged."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path('~/ai-collab')))
import meeting

original_command_for = meeting.c.command_for
original_invoke = meeting.c.invoke


def isolated_command_for(agent, state, attempt):
    if agent != 'claude':
        return original_command_for(agent, state, attempt)
    model = state['models'].get(agent)
    if model != 'claude-opus-5-5':
        raise ValueError('This meeting requires exactly claude-opus-5-5; no fallback.')
    return meeting.c.cli(agent) + [
        '-p', '--output-format', 'stream-json', '--verbose',
        '--json-schema', json.dumps(meeting.c.SCHEMA),
        '--model', model, '--effort', 'max',
        '--safe-mode', '--setting-sources', '',
        '--permission-mode', 'dontAsk', '--tools', '',
        '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
        '--no-session-persistence', '--disable-slash-commands', '--no-chrome',
        '--max-turns', '20',
        '--system-prompt',
        'You are Claude, providing an independent research opinion and then peer review. '
        'Use only the supplied problem and explicit attachments. Do not infer unseen files or '
        'claim external verification you have not performed. Follow the requested Korean format.'
    ]


meeting.c.command_for = isolated_command_for


def invoke_with_stream_result(state, item, prompt, attempt):
    try:
        return original_invoke(state, item, prompt, attempt)
    except json.JSONDecodeError:
        events = []
        for line in meeting.c.read(attempt / 'stdout.log').splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        results = [event for event in events if event.get('type') == 'result']
        if not results:
            raise RuntimeError('Claude stream ended without a result event.')
        envelope = results[-1]
        meeting.c.save(attempt / 'result-envelope.json', envelope)
        if envelope.get('is_error') or envelope.get('subtype', 'success') != 'success':
            raise RuntimeError('Claude stream result failed: ' + str(envelope.get('subtype')))
        data = envelope.get('structured_output')
        if data is None:
            data = json.loads(envelope.get('result', ''))
        return meeting.c.validate_result(data, item['kind'])


meeting.c.invoke = invoke_with_stream_result

if __name__ == '__main__':
    raise SystemExit(meeting.main())
