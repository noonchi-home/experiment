"""Use installed ai-meeting through a task-local adapter, with explicit XHigh."""
import importlib.util
from pathlib import Path

source = Path('~/Desktop/소웨공/의사결정_설계회의_2026-10-23/_meeting_runner.py')
spec = importlib.util.spec_from_file_location('meeting_adapter_source', source)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
previous_command = adapter.meeting.c.command_for


def command_xhigh(agent, state, attempt):
    command = previous_command(agent, state, attempt)
    if agent == 'claude':
        command[command.index('--effort') + 1] = 'xhigh'
    return command


adapter.meeting.c.command_for = command_xhigh

if __name__ == '__main__':
    raise SystemExit(adapter.meeting.main())
