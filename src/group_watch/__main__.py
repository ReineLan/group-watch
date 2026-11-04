from group_watch.paths import resolve_path
from group_watch.settings import ROOT, load_settings
import argparse
import os
from pathlib import Path
import sys


def worker(config, port):
    import uvicorn
    from group_watch.app import create_app
    from group_watch.launcher import process_lock
    from group_watch.launcher import LOGS
    from group_watch.logging_setup import configure
    configure(LOGS, managed=os.environ.get('GROUP_WATCH_MANAGED') == '1')
    cfg = load_settings(config)
    with process_lock(Path(cfg.db_path).with_suffix('.lock')):
        application = create_app(cfg)
        server = uvicorn.Server(uvicorn.Config(application, host='127.0.0.1', port=port,
            log_config=None, log_level='info', access_log=False,
            proxy_headers=True, forwarded_allow_ips='127.0.0.1,::1'))
        application.state.shutdown = lambda: setattr(server, 'should_exit', True)
        try:
            server.run()
        except KeyboardInterrupt:
            return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Compatibility for an already-running old supervisor, until its next stop.
    if argv and argv[0].startswith('--') and argv[0] not in ('--help', '-h'):
        argv.insert(0, '_worker')
    parser = argparse.ArgumentParser(description='Lan 群管理工作台：统一 Web 与 SnowLuma')
    commands = parser.add_subparsers(dest='command', required=True, metavar='{serve,web,stop}')
    for command, help_text in [('serve','启动统一服务'),('web','仅启动 Web，连接外部 SnowLuma'),('_worker',argparse.SUPPRESS)]:
        sub = commands.add_parser(command, help=help_text)
        sub.add_argument('--config', type=Path, default=ROOT/'config/config.json')
        sub.add_argument('--port', type=int, default=8066)
        if command=='serve': sub.add_argument('--background', '-b', action='store_true', help='在后台运行')
    commands.add_parser('stop', help='安全停止本项目拥有的服务进程')
    commands._choices_actions = [choice for choice in commands._choices_actions if choice.dest != '_worker']
    args = parser.parse_args(argv)
    from group_watch import launcher
    try:
        if args.command=='stop': return launcher.stop()
        config = resolve_path(args.config, base=Path.cwd())
        if args.command in ('_worker', 'web'): return worker(config,args.port)
        return launcher.background(config,args.port) if args.background else launcher.serve(config,args.port)
    except (RuntimeError, OSError, ValueError) as exc:
        parser.exit(1, str(exc)+'\n')


if __name__=='__main__':
    main()
