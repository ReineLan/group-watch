"""Import a Numbers evidence folder. Preview by default; --apply writes a copy."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
LEGACY_IMPORT_NOTE = '历史导入：昵称、群名和处理人未记载；处理日期由证据编号推定。'


def image_date(images):
    """Use a single unambiguous source filename date, never a hashed disk name."""
    from datetime import datetime
    dates = set()
    for image in images:
        name = str(image.get('original_name') or image.get('name') or '')
        match = re.match(r'^(\d{8}|\d{6})(?=[^\d]|$)', name)
        if not match:
            continue
        try:
            dates.add(datetime.strptime(match[1], '%Y%m%d' if len(match[1]) == 8 else '%y%m%d').strftime('%Y-%m-%d'))
        except ValueError:
            continue
    return next(iter(dates)) if len(dates) == 1 else ''


def read_tables(folder):
    sys.path.insert(0, str(ROOT / '.import-deps'))
    try:
        from numbers_parser import Document
    except ImportError as error:
        raise SystemExit('读取 Numbers 需安装：python -m pip install --target .import-deps numbers-parser；或提供 --snapshot JSON') from error
    tables = []
    for name in ('记录', '处理办法'):
        document = Document(str(folder / (name + '.numbers')))
        for sheet in document.sheets:
            for table in sheet.tables:
                tables.append({'file': name, 'sheet': sheet.name, 'table': table.name,
                               'rows': [[cell.value for cell in row] for row in table.rows()]})
    return tables


def clean(value):
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value or '').strip()


def build(folder, tables, group):
    from group_watch.evidence.domain import normalize_account
    from group_watch.evidence.domain import punishment_type
    from group_watch.evidence.domain import rule_for
    rules, records, missing, referenced = [], [], [], set()
    image_files = sorted((p for p in folder.iterdir() if p.suffix.lower() in ('.png','.jpg','.jpeg','.webp')), key=lambda p: [int(x) if x.isdigit() else x for x in re.split(r'(\d+)', p.name)])
    for table in tables:
        if table['file'] != '处理办法':
            continue
        header = [clean(x) for x in table['rows'][0]]
        if not header or header[0] != '违规行为':
            raise ValueError('处理办法表头不匹配')
        levels = [i for i,x in enumerate(header) if '违反' in x]
        for row in table['rows'][1:]:
            if not clean(row[0]):
                continue
            reason = clean(row[0])
            empty = ('——','—','--','-','无')
            steps = [clean(row[i]) if i<len(row) and clean(row[i]) not in empty else '' for i in levels]
            notes = clean(row[header.index('备注')]) if '备注' in header else ''
            rules.append({'id': hashlib.sha256(reason.encode()).hexdigest()[:32], 'reason':reason, 'steps':steps, 'notes':'' if notes in empty else notes})
    for table in tables:
        if table['file'] != '记录':
            continue
        header = [clean(x) for x in table['rows'][0]]
        if header[:5] != ['QQ号','缘由','次数','处罚','证据']:
            raise ValueError('记录表头不匹配，未写入任何记录')
        for index,row in enumerate(table['rows'][1:], 2):
            if not any(clean(x) for x in row[:5]):
                continue
            account, reason, count, penalty, incident = [clean(x) for x in row[:5]]
            if not account or not reason or not penalty or not re.fullmatch(r'\d{6}(?:-\d+)?', incident):
                raise ValueError(f'第 {index} 行缺少账号、缘由、处罚或合法证据编号')
            from datetime import datetime
            date = datetime.strptime('20'+incident[:6], '%Y%m%d').strftime('%Y-%m-%d')
            images = []
            for path in image_files:
                if path.stem == incident or path.stem.startswith(incident+'-'):
                    raw = path.read_bytes()
                    digest = hashlib.sha256(raw).hexdigest()
                    target = digest + path.suffix.lower()
                    images.append({'url': '/uploads/'+target, 'name':path.name, 'source_path':str(path), 'sha256':digest})
                    referenced.add(path.name)
            if not images:
                missing.append({'row':index,'member_id':account,'incident':incident})
            filename_date = image_date(images)
            date = filename_date or date
            rule = rule_for(reason, rules)
            source_key = json.dumps([group,table['sheet'],table['table'],index,row[:5]],ensure_ascii=False)
            records.append({'id':'ref-'+hashlib.sha256(source_key.encode()).hexdigest()[:28],
                            'member_id':normalize_account(account), 'group_id':int(group),
                            'nickname':None,'card':None,'event_date':date,'reason':reason,
                            'punishment':punishment_type(penalty),'penalty_text':penalty,
                            'occurrence':count,'operator':'','notes':'','images':images})
    if not records or not rules:
        raise ValueError('未解析到有效的记录或规则')
    report = {'source':str(folder),'records':len(records),'rules':len(rules),'source_images':len(image_files),
              'matched_images':len(referenced),'records_with_images':sum(bool(r['images']) for r in records),
              'missing_evidence':missing,'unreferenced_images':[p.name for p in image_files if p.name not in referenced],
              'notes':'原表次数原样保留；累计次数按实际历史记录条数计算。日期由证据编号推定；缺图保留编号。'}
    return records, rules, report


def apply(records, rules, report, store):
    import base64
    existing={r['id'] for r in store.get_records()}
    pending=[]
    for row in records:
        if row['id'] in existing: continue
        item=dict(row)
        item['images']=[dict(data=base64.b64encode(Path(i['source_path']).read_bytes()).decode(),name=i['name']) for i in row['images']]
        # save_records creates IDs for new rows; retain the deterministic import ID
        # by inserting a validated current-schema row in the same transaction below.
        pending.append(item)
    written=[]
    try:
        with store.lock:
            # One snapshot covers the entire import, including new rules.
            names={r['reason'] for r in store.get_rules()}
            archive=store.backup('before-import') if pending or any(r['reason'] not in names for r in rules) else None
            return _apply_pending(pending,rules,report,store,written,archive)
    except Exception:
        for path in written: path.unlink(missing_ok=True)
        raise


def _apply_pending(pending,rules,report,store,written,archive):
    from group_watch.evidence.domain import now
    with store.connect() as db:
        for row in pending:
            values=store.validate_record(row)
            at=now().isoformat()
            item=dict(id=row['id'],**values,images=store.store_images(row['images'],[],written,row['id']),
                      created_at=at,updated_at=at,nickname_status=0,nickname_at=None,avatar_status=0,avatar_at=None,avatar_url=None)
            columns=list(item)
            db.execute(f'INSERT INTO records({",".join(columns)}) VALUES({",".join("?" for _ in columns)})',
                       [json.dumps(item[k],ensure_ascii=False) if k=='images' else item[k] for k in columns])
        before=db.total_changes
        db.executemany('INSERT OR IGNORE INTO rules VALUES(?,?,?,?)',[(r['id'],r['reason'],json.dumps(r['steps'],ensure_ascii=False),r['notes']) for r in rules])
        added_rules=db.total_changes-before
        if pending or added_rules: store.audit(db,'导入资料',detail=dict(records=len(pending),rules=added_rules,backup=archive.name))
    store.queue_profiles([r for r in store.get_records() if r['id'] in {x['id'] for x in pending}])
    return {**report,'already_imported':not pending,'added_records':len(pending),'added_rules':added_rules}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    parser.add_argument('--group',type=int,required=True,help='已经登记的群号或负数直播间号')
    parser.add_argument('--snapshot',type=Path,help='由 Numbers 只读解析得到的 JSON；不改原表')
    parser.add_argument('--apply',action='store_true',help='确认预览后写入；重复导入自动跳过')
    args = parser.parse_args()
    folder = args.folder.resolve(strict=True)
    tables = json.loads(args.snapshot.read_text(encoding='utf-8-sig')) if args.snapshot else read_tables(folder)
    records,rules,report = build(folder,tables,args.group)
    if args.apply:
        from group_watch.evidence.store import RecordStore
        from group_watch.settings import load_settings
        from group_watch.settings import ROOT
        cfg = load_settings(ROOT/'config/config.json')
        store = RecordStore(cfg.evidence_data or Path(cfg.db_path).parent/'group-evidence')
        allowed={*cfg.groups,*(-x for x in cfg.live_rooms)}
        store.groups=lambda:allowed
        if args.group not in allowed: raise ValueError("群聊或直播间尚未登记")
        store.initialize(store.data)
        try:
            report = apply(records,rules,report,store)
        finally:
            store.close()
    print(json.dumps(report,ensure_ascii=False,indent=2))
