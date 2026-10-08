"""Timing rules of the background job queue: retry backoff and the lease on a running job."""

from datetime import timedelta

# A failed job waits before its next attempt, longer each time: a network blip, a locked
# backup repository or an unplugged disk gets time to recover instead of using up every
# attempt within seconds. Entry n is the wait after the n-th failed attempt.
RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=25))
# One first run plus one retry after each wait, so every entry above is used: an outage of
# up to 31 minutes passes before a job fails for good. The crash-loop guard counts the same.
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1

# The process running a job renews its claim this often, however long the job takes …
HEARTBEAT_INTERVAL = timedelta(seconds=30)
# … and a claim nobody renewed for this long belongs to a process that died: the job is
# queued again. Ten missed heartbeats, so a busy database never looks like a dead process.
CLAIM_STALE_AFTER = timedelta(minutes=5)
# How often the server looks for stale claims. Longer than a heartbeat on purpose: after the
# machine wakes from sleep every live process renews its claims before the next look.
STALE_SWEEP_INTERVAL = timedelta(minutes=1)


def retry_delay(failed_attempts: int) -> timedelta:
    """How long a job waits after its ``failed_attempts``-th failed attempt (1 = the first)."""
    if failed_attempts < 1:
        raise ValueError(f"attempt numbers start at 1, got {failed_attempts}")
    return RETRY_DELAYS[min(failed_attempts, len(RETRY_DELAYS)) - 1]
