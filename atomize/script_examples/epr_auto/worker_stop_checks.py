"""Offline checks for bounded worker cleanup and a second stop interrupt."""
import sys
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')

from atomize.epr_auto.engine import executor


def process_stub():
    process = Mock()
    process.is_alive.return_value = True
    process.terminate.side_effect = lambda: setattr(process.is_alive, 'return_value', False)
    return process


process, conn = process_stub(), Mock()
conn.poll.return_value = False
with patch.object(executor.time, 'monotonic', side_effect=[0, 0, 61]):
    executor._wind_down(conn, process, 'dummy.csv', .2)
conn.send.assert_called_once_with('exit')
assert conn.poll.call_count == 1
process.terminate.assert_called_once()
assert process.join.call_args_list == [call(timeout=10), call()]
print('PASS: stalled worker reaches the drain deadline and terminates')

process, conn = process_stub(), Mock()
conn.poll.side_effect = KeyboardInterrupt
executor._wind_down(conn, process, None, .2)
process.terminate.assert_called_once()
process.join.assert_called_once_with()
print('PASS: second interrupt skips the grace and timed join')

process, conn = process_stub(), Mock()
conn.poll.side_effect = EOFError
process.join.side_effect = [KeyboardInterrupt, None]
executor._wind_down(conn, process, None, .2)
process.terminate.assert_called_once()
print('PASS: interrupt during final timed join still terminates the worker')

process, conn = process_stub(), Mock()
conn.poll.side_effect = [True, False]
conn.recv.return_value = ('Open', '')
with patch.object(executor.time, 'monotonic', side_effect=[0, 0, 0, 61]):
    executor._wind_down(conn, process, 'dummy.csv', .2)
assert conn.send.call_args_list == [call('exit'), call('FLdummy.csv')]
print('PASS: graceful drain preserves the save handshake')

process, conn = process_stub(), Mock()
conn.poll.side_effect = KeyboardInterrupt
args = SimpleNamespace(build=lambda: ())
with patch.dict(executor.SWEEP_METHOD, {'dummy': ('exp', 'build')}), \
        patch.object(executor, 'Worker'), patch.object(executor, '_hand_attrs'), \
        patch.object(executor, 'Pipe', return_value=(conn, Mock())), \
        patch.object(executor, 'Process', return_value=process), \
        patch.object(executor, '_wind_down') as drain:
    try:
        executor.run_worker(args, 'dummy', script_test=True)
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError('worker interrupt was swallowed')
    drain.assert_called_once_with(conn, process, None, .2)
    assert conn.poll.call_count == 1, 'runner entered a second, unbounded drain'
print('PASS: first worker interrupt uses only the shared bounded drain and propagates')
print('ALL PASS')
