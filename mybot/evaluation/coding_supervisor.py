"""Fresh interpreter per live slot, inherited real terminal, no approval injection."""
import signal
import subprocess


def supervise(argv, *, timeout=930, grace=10):
    # Inherit stdin/stdout/stderr unchanged. Native worker TTY/cost checks still run.
    child=subprocess.Popen(argv)
    try:
        return child.wait(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        child.send_signal(signal.SIGINT)
        try:child.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            child.kill();child.wait()
        # A timeout/signal is never a successful run or authorization to replay.
        return 124
