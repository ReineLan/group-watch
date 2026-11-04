from group_watch.evidence.domain import risk_members


def test_risk_matching_preserves_aliases_group_identity_and_rule_edits():
    rules = [{'id':'alias', 'reason':'提及无关主播/up主', 'steps':['警告','移出群聊']},
             {'id':'multi', 'reason':'刷屏、重复内容', 'steps':['警告','禁言','移出群聊']}]
    def record(identity, category, group='甲群', account='００１２３４５'):
        return dict(id=identity, reason=category, nickname='成员', member_id=account,
                    group_id={'甲群':100000001,'乙群':100000002}[group], punishment='警告', event_date='2026-10-29')
    records = [record('a','提及无关up主'), record('b','提及无关UP主', account='12345'),
               record('c','重复内容', group='乙群'), record('d','刷屏', group='乙群'),
               record('e','未匹配'), record('f','未匹配')]
    result = risk_members(records, rules)
    assert [(r['group_id'],r['status'],r['total']) for r in result] == [
        (100000001,'达到移出规则',4), (100000002,'再犯预警',2)]
    assert result[0]['record_ids'] == ['a','b','e','f']
    rules[0]['steps'] = ['警告','禁言','禁言','移出群聊']
    assert [(r['group_id'],r['status']) for r in risk_members(records,rules)] == [(100000002,'再犯预警')]
    records[0]['punishment'] = '移出群聊'
    assert risk_members(records,rules)[0]['status'] == '已记录移出'
