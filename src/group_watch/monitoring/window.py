"""Bounded messages, candidates and rollback for incoming batches."""
from collections import OrderedDict, deque
from copy import deepcopy
from contextlib import contextmanager
import uuid


class MessageWindow:
    def __init__(self):
        self.messages = OrderedDict()
        self.candidates = OrderedDict()
        self.cooldowns = OrderedDict()
        self.activity = {}

    @contextmanager
    def atomic_batch(self):
        saved=deepcopy((self.messages,self.candidates,self.cooldowns,self.activity))
        try:
            yield
        except Exception:
            self.messages,self.candidates,self.cooldowns,self.activity=saved
            raise


    def insert_message(self, msg, now):
        self._prune_memory(now)
        key=(msg['group_id'],msg['message_id'])
        if key in self.messages:
            return False
        self.messages[key]=(now,msg)
        self.activity.setdefault(msg['group_id'],deque(maxlen=50000)).append((now,msg['time']))
        while len(self.messages)>20000:
            self.messages.popitem(last=False)
        return True


    def window(self, group, start, end, limit=500):
        return sorted((msg for _,msg in self.messages.values() if msg['group_id']==group and start<=msg['time']<=end),
                      key=lambda m:m['time'])[-limit:]


    def candidate(self, msg, rule, evidence, context, cooldown, now):
        key=(msg['group_id'],msg['user_id'],rule)
        if self.cooldowns.get(key,float('-inf'))>now-cooldown:
            return False
        self.cooldowns[key]=now
        selected=[x for x in context if x['message_id'] in evidence][-30:]
        neighbors=[x for x in context[-12:] if x['message_id'] not in evidence]
        ident=uuid.uuid4().hex
        self.candidates[ident]=dict(id=ident,group_id=msg['group_id'],user_id=msg['user_id'],rule=rule,created=now,
            evidence=evidence,context=sorted(selected+neighbors,key=lambda x:x['time']),state='pending',reason='',attempts=0,next_try=0,error='')
        while len(self.candidates)>1000:
            self.candidates.popitem(last=False)
        return ident


    def _prune_memory(self, now):
        while self.messages and next(iter(self.messages.values()))[0]<now-300:
            self.messages.popitem(last=False)
        for key,case in list(self.candidates.items()):
            if case['created']<now-3600 or case['attempts']>=3:
                self.candidates.pop(key,None)
        for key,at in list(self.cooldowns.items()):
            if at<now-300:
                self.cooldowns.pop(key,None)
        for rows in self.activity.values():
            while rows and rows[0][0]<now-86400:
                rows.popleft()
