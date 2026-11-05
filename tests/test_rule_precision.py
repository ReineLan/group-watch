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


def test_repeat_ignores_media_only_messages_and_placeholders():
    image = [{'type': 'image', 'data': {'file': 'a.jpg', 'url': 'https://gchat.qpic.cn/a'}}]

    def message(mid, segments, text=''):
        return dict(text=text, mentions=[], user_id=1, message_id=mid, time=1000.0,
                    media=['image'], segments=segments)

    def detected(segments, text=''):
        # Ingest inserts the current message into the window before detection runs.
        recent = [message(f'i{n}', segments, text) for n in range(3)] + [message('now', segments, text)]
        return detect(CFG, recent[-1], recent)

    assert 'repeat' not in detected(image)

    placeholder = [{'type': 'text', 'data': {'text': '[图片]'}}, *image]
    assert 'repeat' not in detected(placeholder, '[图片]')

    caption = [{'type': 'text', 'data': {'text': '哈哈'}}, *image]
    assert 'repeat' in detected(caption, '哈哈')


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
    assert 'abuse' in hits('你真是傻逼')
    assert 'abuse' in hits('妈的，幸亏我跑得快')
    assert 'abuse' in hits('他妈的')
    assert 'abuse' in hits('你妈的')
    assert 'abuse' in hits('滚出去', mentions=['123456'])


def test_meta_discussion_does_not_match_context_rules():
    assert 'scam' not in hits('暂时没有到借钱吃饭的地步')
    assert 'scam' not in hits('群友集资买COS服 我包穿的')
    assert 'scam' in hits('集资买挂，私聊我')
    assert 'vulgar' not in hits('生成失败：生成的图片可能违反关于裸露、色情或情色内容的防护限制。')
    assert 'vulgar' in hits('发色情资源')
    assert 'privacy' not in hits('所以，开盒有门槛')
    assert 'privacy' in hits('开盒他')
    assert 'privacy' in hits('身份证')
    assert 'conflict' not in hits('引战的？那不惯着他，不过也不能随便冲别人')
    assert 'conflict' in hits('粉丝滚')
    assert 'sarcasm' not in hits('就这？')
    assert 'sarcasm' in hits('急了急了')


def test_snowluma_status_is_flagged_as_a_bot_and_image_notices_are_ignored():
    status = 'SnowLuma 状态\n版本: 2.0.3\n平台: win32-x64\n运行时长: 16小时 34分钟'
    assert hits(status) == {'snowluma': ['m']}
    assert 'snowluma' not in hits('SnowLuma 状态怎么查')
    assert hits('生成失败：非常抱歉，生成的图片可能违反了关于裸露、色情或情色内容的防护限制。') == {}
