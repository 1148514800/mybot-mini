"""Fresh interpreter per live slot, inherited real terminal, no approval injection."""
import signal
import subprocess


def supervise(argv, *, timeout=930, grace=10):
    # Inherit stdin/stdout/stderr unchanged. Native worker TTY/cost checks still run.
    child=subprocess.Popen(argv)
    try:
        return child.wait(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        try:child.send_signal(signal.SIGINT)
        except ProcessLookupError:pass
        try:child.wait(timeout=grace)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            try:child.kill()
            except ProcessLookupError:pass
            try:child.wait(timeout=grace)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                return 125  # no trustworthy exit receipt; never replay
        # A timeout/signal is never a successful run or authorization to replay.
        return 124
