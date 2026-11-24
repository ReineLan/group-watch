import json
from types import SimpleNamespace

from group_watch.monitoring.rules import detect

CFG = SimpleNamespace(flood_seconds=60, flood_count=12, repeat_count=4,
                      protected_qq=100000003, protected_groups=[123456],
                      blocked_words=[], unrelated_streamers=[], sensitive_topics=[])


def hits(text, mentions=(), recent=(), user=1, media=()):
    return detect(CFG, dict(text=text, mentions=list(mentions), user_id=user,
                            message_id='m', time=1000.0, media=list(media)), list(recent))


def prior(text, user=2):
    return dict(text=text, mentions=[], user_id=user, message_id=f'p{user}', time=999.0, media=[])


def test_normal_links_and_vocabulary_are_not_ads():
    assert 'ad' not in hits('投票入口：https://www.bilibili.com/blackboard/era/x')
    assert 'ad' not in hits('https://v.douyin.com/OUyNeviHVPQ/')
    assert 'ad' not in hits('这个我从进群就开始听了')
    assert 'ad' not in hits('话说我好友，进群后一句话还没说呢')
    assert 'ad' not in hits('京东有时候的优惠券好大啊')
    assert 'ad' not in hits('饥荒怎么被藤子代理了？')
    assert 'ad' not in hits('我擅长推广别人的表情')
    assert 'ad' not in hits('兰兰的想法是将外边的用户引流过来')
    assert 'ad' not in hits('淦已经入群一坤年了')


def test_ad_needs_action_or_mass_forwarding():
    assert 'ad' not in hits('https://example.com/article')
    assert 'ad' in hits('https://example.com/article 加群领福利')
    assert 'ad' in hits('https://example.com/article', recent=[prior('https://example.com/article')])
    assert 'ad' in hits('加群领福利')
    assert 'ad' in hits('加微信')
    assert 'ad' in hits('扫码进群')
    assert 'ad' in hits('群号 123456789')


def test_trade_needs_action_near_service_name():
    for text in ('有人用过代充吗', '我想聊聊代购。不相关的建议：加我', '代购不接单'):
        assert 'ad' not in hits(text)
    for text in ('代购接单，私聊我报价', '代充，扫码付款', '私聊我代充', '代充？进群领福利'):
        assert 'ad' in hits(text)


def test_privacy_fields_need_a_disclosure_or_request():
    benign = ('办身份证要带照片吗', '手机号码可以换吗', '真实姓名是必填项吗', '真实姓名：待确认', '他住在一个小区',
              '群友说开盒不合适', '人肉搜索违法吗', '我能公开问一下怎么改自己的手机号吗', '我喜欢住在带花园的小区')
    candidates = ('把楼上那位的住址发出来', '谁有楼上那位的手机号，发一下', '把他身份证号发出来',
                  '这是他的手机号：１３８-００００-００００', '身份证号：00000000000000000X',
                  '真实姓名：某小明', '她住在某某路1号', '他的家庭住址：某市某区幸福花园3栋',
                  '她住址是某某公寓三栋', '我要人肉他', '我们一起开盒')
    for text in benign:
        assert 'privacy' not in hits(text), text
    for text in candidates:
        assert 'privacy' in hits(text), text
    assert 'privacy' in hits('我要开盒', mentions=['987654'])
    assert 'privacy' not in hits('开盒是什么意思', mentions=['987654'])


def test_repeat_counts_identical_media_and_keeps_others_apart():
    def image(fid):
        return [{'type': 'image', 'data': {'file': fid, 'url': 'https://gchat.qpic.cn/' + fid}}]

    def message(mid, segments, text=''):
        return dict(text=text, mentions=[], user_id=1, message_id=mid, time=1000.0,
                    media=['image'], segments=segments)

    def detected(history):
        # Ingest inserts the current message into the window before detection runs.
        return detect(CFG, history[-1], history)

    # The same sticker or image shares a stable file id, so it counts as a repeat.
    same = [message(f'i{n}', image('a.jpg')) for n in range(3)] + [message('now', image('a.jpg'))]
    assert 'repeat' in detected(same)

    # Different file ids never look identical.
    mixed = [message(f'i{n}', image(f'{n}.jpg')) for n in range(3)] + [message('now', image('a.jpg'))]
    assert 'repeat' not in detected(mixed)

    # Media without an id stays invisible to repeat detection.
    noid = [{'type': 'image', 'data': {'url': 'https://gchat.qpic.cn/x'}}]
    unmarked = [message(f'i{n}', noid) for n in range(3)] + [message('now', noid)]
    assert 'repeat' not in detected(unmarked)

    # A text-only media placeholder still carries no comparable content.
    label = [{'type': 'text', 'data': {'text': '[图片]'}}]
    labeled = [message(f'i{n}', label, '[图片]') for n in range(3)] + [message('now', label, '[图片]')]
    assert 'repeat' not in detected(labeled)

    caption = [{'type': 'text', 'data': {'text': '哈哈'}}, *image('a.jpg')]
    captioned = [message(f'i{n}', caption, '哈哈') for n in range(3)] + [message('now', caption, '哈哈')]
    assert 'repeat' in detected(captioned)


def test_card_urls_are_readable_text_not_ads():
    card = json.dumps({'prompt': '群相册《兰图》',
                       'meta': {'feed': {'cover': 'http://qungz.photo.store.qq.com/x'}}})
    assert 'ad' not in hits(card, media=['json'])


def test_abuse_ignores_family_words_and_untargeted_profanity():
    assert 'abuse' not in hits('兰兰可是能当我妈妈的存在啊')
    assert 'abuse' not in hits('我曾经当着我妈的面儿买谷给朋友送礼物')
    assert 'abuse' not in hits('也是把老妈的手机还回去了')
    assert 'abuse' not in hits('也没必要浪费你爸妈的供你读书的钱')
    assert 'abuse' not in hits('总不能一棒子打死全部的')
    assert 'abuse' not in hits('傻逼开屏广告')
    assert 'abuse' not in hits('奶龙去死😡😡')
    assert 'abuse' not in hits('这死妈射手还给我举报了')
    assert 'abuse' in hits('你真是傻逼', mentions=['123456'])
    assert 'abuse' not in hits('你真是傻逼')
    for text in ('妈的，幸亏我跑得快', '他妈的', '你妈的', '滚出去', '你可真是个天才'):
        assert 'abuse' not in hits(text, mentions=['123456'])
    for text in ('兰兰这场直播的音质很垃圾', '给兰兰分享一个垃圾分类视频', '兰兰，你的耳机好漂亮'):
        assert 'lanyin_attack' not in hits(text, mentions=['100000003'])
    assert 'lanyin_attack' in hits('兰兰，你是废物。')
    assert 'abuse' in hits('你是废物', recent=[dict(prior('说说你的想法'), mentions=['1'])])


def test_meta_discussion_does_not_match_context_rules():
    assert 'scam' not in hits('暂时没有到借钱吃饭的地步')
    assert 'scam' not in hits('群友集资买COS服 我包穿的')
    assert 'scam' in hits('集资买挂，私聊我')
    assert 'vulgar' not in hits('生成失败：生成的图片可能违反关于裸露、色情或情色内容的防护限制。')
    assert 'vulgar' in hits('发色情资源')
    assert 'privacy' not in hits('所以，开盒有门槛')
    assert 'privacy' in hits('开盒他')
    assert 'privacy' not in hits('身份证')
    assert 'conflict' not in hits('引战的？那不惯着他，不过也不能随便冲别人')
    assert 'conflict' in hits('粉丝滚')
    assert 'sarcasm' not in hits('就这？')
    assert 'sarcasm' not in hits('急了急了')
    assert 'sarcasm' not in hits('懂的都懂，有些人出现以后这个群就没好过')


def test_snowluma_status_is_flagged_as_a_bot_and_image_notices_are_ignored():
    status = 'SnowLuma 状态\n版本: 2.0.3\n平台: win32-x64\n运行时长: 16小时 34分钟'
    assert hits(status) == {'snowluma': ['m']}
    assert 'snowluma' not in hits('SnowLuma 状态怎么查')
    assert hits('生成失败：非常抱歉，生成的图片可能违反了关于裸露、色情或情色内容的防护限制。') == {}
