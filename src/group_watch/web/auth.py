"""One workspace session store for the entire local application."""
import hashlib
import hmac
import secrets
import threading
import time


class WorkspaceAuth:
    def __init__(self, tokens, session_seconds=12*3600):
        self.configure_tokens(tokens)
        self.ttl = session_seconds
        self.lock = threading.Lock()
        self.sessions = {}
        self.attempts = {}

    def configure_tokens(self, tokens):
        if not tokens or any(not token or len(token) > 512 for token in tokens):
            raise ValueError('请配置非空工作台密码，最多512个字符')
        self.hashes = [hashlib.sha256(token.encode()).digest() for token in tokens]

    def valid(self, token):
        return isinstance(token, str) and any(hmac.compare_digest(hashlib.sha256(token.encode()).digest(), candidate) for candidate in self.hashes)

    def bearer(self, request):
        value = request.headers.get('authorization', '')
        return value.startswith('Bearer ') and self.valid(value[7:])

    def authenticated(self, request):
        if self.bearer(request):
            return True
        with self.lock:
            return self.sessions.get(request.cookies.get('lan_workspace', ''), 0) > time.time()

    def issue(self):
        with self.lock:
            now = time.time()
            self.sessions = {key:until for key,until in self.sessions.items() if until > now}
            if len(self.sessions) >= 4096:
                raise ValueError('会话过多，请稍后重试')
            value = secrets.token_urlsafe(32)
            self.sessions[value] = now + self.ttl
            return value

    def allow_login(self, client):
        with self.lock:
            now = time.time()
            self.attempts = {key:[t for t in values if t > now-300] for key,values in self.attempts.items() if values and values[-1] > now-300}
            attempts = self.attempts.get(client, [])
            if len(attempts) >= 10 or len(self.attempts) >= 4096:
                return False
            self.attempts[client] = [*attempts, now]
            return True

    def revoke(self, request):
        with self.lock:
            self.sessions.pop(request.cookies.get('lan_workspace', ''), None)

    def attach(self, response, *, secure=False):
        response.set_cookie('lan_workspace', self.issue(), max_age=self.ttl, httponly=True, samesite='strict', path='/', secure=secure)
