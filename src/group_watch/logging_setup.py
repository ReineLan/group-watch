"""Loguru configuration shared by the supervisor and application worker."""
import json
import logging
import socket
import sys
from loguru import logger

FORMAT = '<green>[{time:MM-DD HH:mm:ss} <level>{level:<5}</level>]</green> {message}'


class Intercept(logging.Handler):
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.opt(exception=record.exc_info).log(level, record.getMessage())


def configure(folder, *, managed=False):
    logger.remove()
    if managed:
        # Only the supervisor owns file rotation. Child streams are pipes, never empty files.
        def pipe(message):
            sys.stdout.write(json.dumps({'level':message.record['level'].name, 'message':str(message)}, ensure_ascii=True)+'\n')
            sys.stdout.flush()
        logger.add(pipe, format='{message}', level='INFO', diagnose=False, backtrace=False)
    else:
        logger.add(sys.stdout, format=FORMAT, level='INFO', diagnose=False, backtrace=False)
        folder.mkdir(parents=True, exist_ok=True)
        logger.add(folder / ('info_{time:YYYY-MM-DD}_'+socket.gethostname()+'.log'),
                   format=FORMAT, level='INFO', rotation='7 days', retention='30 days',
                   encoding='utf-8', delay=True, diagnose=False, backtrace=False)
    logging.basicConfig(handlers=[Intercept()], level=logging.INFO, force=True)
    for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access'):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    for name in ('httpx', 'httpcore', 'websockets'):
        logging.getLogger(name).setLevel(logging.WARNING)
