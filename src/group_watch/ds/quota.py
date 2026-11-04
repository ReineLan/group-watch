"""Process-local rolling quota. Restarting starts with an empty budget."""
from collections import deque


class AutomaticQuota:
    def __init__(self):
        self.attempts = deque()

    def record(self, now, *, scope='automatic'):
        if scope == 'automatic':
            self.attempts.append(now)

    def calls_hour(self, now):
        while self.attempts and self.attempts[0] <= now - 3600:
            self.attempts.popleft()
        return len(self.attempts)
