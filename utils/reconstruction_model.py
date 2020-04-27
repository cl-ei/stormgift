import time
import datetime
from config import g
from random import randint
from utils.cq import async_zy
from utils.dao import redis_cache
from utils.biliapi import BiliApi
from config.log4 import lt_login_logger as logging
from utils.email import send_cookie_invalid_notice
from utils.dao import BiliToQQBindInfo, UserRaffleRecord, LTLastAcceptTime, LTTempBlack, XNodeRedis


BLOCK_FRESH_TIME = 1


def random_datetime():
    return datetime.datetime.now() - datetime.timedelta(days=randint(3600, 4000))


def gen_time_prompt(interval):
    if interval > 3600 * 24 * 365:
        return f"很久以前"
    elif interval > 3600 * 24:
        return f"约{int(interval // (3600 * 24))}天前"
    elif interval > 3600:
        return f"约{int(interval // 3600)}小时前"
    elif interval > 60:
        return f"约{int(interval // 60)}分钟前"
    return f"{int(interval)}秒前"


class LTUserCookie:
    key_prefix = "LT:U"
    key_white_list = "LT:whitelist"
    key_account_to_uid = "LT:ac_to_uid"
    """
    key: LT:U:uid:account
        uid: num or 0

    name = peewee.CharField(index=True, null=True)

    * DedeUserID = peewee.IntegerField(unique=True, index=True, null=True)
    SESSDATA = peewee.CharField(null=True)
    bili_jct = peewee.CharField(null=True)
    sid = peewee.CharField(null=True)
    DedeUserID__ckMd5 = peewee.CharField(null=True)

    access_token = peewee.CharField(null=True)
    refresh_token = peewee.CharField(null=True)

    cookie_expire_time = peewee.DateTimeField(default=datetime.datetime.now)

    notice_email = peewee.CharField(null=True)
    is_vip = peewee.BooleanField(default=False)
    blocked_time = peewee.DateTimeField(default=random_datetime)

    * account = peewee.CharField(null=True)
    password = peewee.CharField(null=True)

    available = peewee.BooleanField(default=False)
    """

    IMPORTANT_UID_LIST = (
        20932326,  # DD
        39748080,  # LP
        312186483,  # TZ
        87301592,  # 村长
    )

    FIELDS = (
        "name",
        "DedeUserID",
        "SESSDATA",
        "bili_jct",
        "sid",
        "DedeUserID__ckMd5",
        "access_token",
        "refresh_token",
        "cookie_expire_time",
        "notice_email",
        "is_vip",
        "blocked_time",
        "account",
        "password",
        "available",
    )

    def __init__(self, **kwargs):
        for k in self.FIELDS:
            value = kwargs.get(k, None)
            if k in ("name", "access_token", "refresh_token", ) and not value:
                value = ""
            if k in ("cookie_expire_time", "blocked_time", ) and not value:
                value = random_datetime()
            setattr(self, k, value)

    @classmethod
    async def create(cls, **kwargs):
        account = kwargs.get("account")
        if not account:
            return None

        obj = cls(**kwargs)
        save_values = {}
        for k in cls.FIELDS:
            save_values[k] = getattr(obj, k)

        uid = kwargs.get("DedeUserID")
        if isinstance(uid, int) and uid > 0:
            await redis_cache.set(key=f"{cls.key_account_to_uid}:{account}", value=uid)
        await redis_cache.set(key=f"{cls.key_prefix}:{uid}", value=save_values)
        return obj

    @classmethod
    async def add_uid_or_account_to_white_list(cls, uid=None, account=None):
        r1, r2 = None, None
        if account:
            r1 = await redis_cache.set(key=f"{cls.key_account_to_uid}:{account}", value=int(uid or -1))
        if uid:
            r2 = await redis_cache.set_add(cls.key_white_list, uid)
        return f"{r1}_{r2}"

    @classmethod
    async def del_uid_or_account_from_white_list(cls, uid=None, account=None):
        r1, r2 = None, None
        if account:
            r1 = await redis_cache.delete(key=f"{cls.key_account_to_uid}:{account}")
        if uid:
            r2 = await redis_cache.set_remove(cls.key_white_list, uid)
        return f"{r1}_{r2}"

    @classmethod
    async def get_uid(cls, account=None, uid=None):
        if not uid:
            uid = await redis_cache.get(key=f"{cls.key_account_to_uid}:{account}")

        if uid is None:
            return uid

        if isinstance(uid, int) and uid <= 0:
            return uid

        if await redis_cache.set_is_member(cls.key_white_list, uid):
            return uid
        logging.error(f"Not in white list: {uid}, {type(uid)}")
        return None

    @classmethod
    async def get_by_uid(cls, user_id, available=None):
        if user_id == "*":
            all_keys = await redis_cache.keys(f"{cls.key_prefix}:*")
            all_values = await redis_cache.mget(*all_keys)
            for value in all_values:
                obj = cls(**value)
                if not available:
                    return obj

                if obj.available is True:
                    return obj

            return None

        if user_id == "DD":
            user_id = 20932326
        elif user_id == "LP":
            user_id = 39748080
        elif user_id == "TZ":
            user_id = 312186483
        elif user_id == "CZ":
            user_id = 87301592

        key = f"{cls.key_prefix}:{user_id}"
        value = await redis_cache.get(key=key)
        if not isinstance(value, dict):
            return None
        obj = cls(**value)
        if not available:
            return obj
        return obj if obj.available is True else None

    @classmethod
    async def get_objs(cls, available=None, is_vip=None, non_blocked=None, separate=False):
        all_keys = await redis_cache.keys(f"{cls.key_prefix}:*")
        all_values = await redis_cache.mget(*all_keys)

        important_objs = []
        objs = []
        x_hour_ago = datetime.datetime.now() - datetime.timedelta(hours=BLOCK_FRESH_TIME)
        for value in all_values:
            obj = cls(**value)
            if available and not obj.available:
                continue
            if is_vip and not obj.is_vip:
                continue

            if non_blocked and obj.blocked_time and obj.blocked_time > x_hour_ago:
                continue

            if obj.DedeUserID in cls.IMPORTANT_UID_LIST:
                important_objs.append(obj)
            else:
                objs.append(obj)

        if separate:
            return important_objs, objs
        else:
            return important_objs + objs

    @classmethod
    async def update(cls, obj, kv):
        values = {}
        need_write = False
        for k in cls.FIELDS:
            if k in kv:
                need_write = True
                values[k] = kv[k]
                setattr(obj, k, kv[k])
            else:
                values[k] = getattr(obj, k, None)

        if need_write:
            key = f"{cls.key_prefix}:{obj.uid}"
            await redis_cache.set(key=key, value=values)
        return need_write

    @property
    def cookie(self):
        return (
            f"bili_jct={self.bili_jct}; "
            f"DedeUserID={self.DedeUserID}; "
            f"DedeUserID__ckMd5={self.DedeUserID__ckMd5}; "
            f"sid={self.sid}; "
            f"SESSDATA={self.SESSDATA};"
        )

    @property
    def uid(self):
        return self.DedeUserID

    @property
    def user_id(self):
        return self.DedeUserID

    @classmethod
    async def _update_cookie(cls, lt_user):
        if lt_user.available:
            return True, lt_user

        if not lt_user.account or not lt_user.password:
            return False, "No account or password."

        flag, r = await BiliApi.login(
            lt_user.account,
            lt_user.password,
            lt_user.cookie,
            lt_user.access_token,
            lt_user.refresh_token
        )
        if not flag:
            return False, r

        update_fields = {"available": True}
        for k, v in r.items():
            setattr(update_fields, k, v)

        await cls.update(lt_user, update_fields)
        await redis_cache.set(key=f"{cls.key_account_to_uid}:{lt_user.account}", value=lt_user.uid)

        return True, lt_user

    @classmethod
    async def add_user_by_account(cls, account, password, notice_email=None):
        uid = await cls.get_uid(account=account)
        if uid is None:
            return False, "你不在白名单里。提前联系站长经过允许才可以使用哦。"
        if uid > 0:
            lt_user = await cls.get_by_uid(uid)
        else:
            flag, r = await BiliApi.login(account, password)
            if flag:
                r.update({
                    "account": account,
                    "password": password,
                    "available": True,
                })
                lt_user = await cls.create(**r)
                return True, lt_user
            else:
                return False, f"登录失败。{r}"

        diff = {}
        if lt_user.account != account:
            diff["account"] = account

        if lt_user.password != password:
            diff["password"] = password

        if lt_user.notice_email != notice_email:
            diff["notice_email"] = notice_email
        await cls.update(lt_user, diff)

        if lt_user.available:
            return True, lt_user

        return await cls._update_cookie(lt_user)

    @classmethod
    async def add_cookie_by_qrcode(cls, DedeUserID, SESSDATA, bili_jct, sid, DedeUserID__ckMd5):
        uid = await cls.get_uid(uid=int(DedeUserID))
        if not uid:
            return False, "你不在白名单里。提前联系站长经过允许才可以使用哦。"

        lt_user = await cls.get_by_uid(DedeUserID)
        update_kw = {
            "available": True,
            "DedeUserID": DedeUserID,
            "SESSDATA": SESSDATA,
            "bili_jct": bili_jct,
            "sid": sid,
            "DedeUserID__ckMd5": DedeUserID__ckMd5,
            "access_token": "",
            "refresh_token": "",
        }

        await cls.update(lt_user, update_kw)
        return True, lt_user

    @classmethod
    async def set_invalid(cls, obj_or_user_id):
        if isinstance(obj_or_user_id, LTUserCookie):
            user = obj_or_user_id
        else:
            user = await cls.get_by_uid(uid=obj_or_user_id)

        await cls.update(user, {"available": False})

        flag, result = await cls._update_cookie(user)
        if flag:
            if user.uid in (g.BILI_UID_TZ, g.BILI_UID_CZ):
                # await ReqFreLimitApi.set_available_cookie_for_xnode()
                pass
            return True, ""

        # email & qq notice
        send_cookie_invalid_notice(user)
        qq_num = await BiliToQQBindInfo.get_by_bili(bili=user.DedeUserID)
        if qq_num:
            await async_zy.send_private_msg(user_id=qq_num, message=f"你的登录已过期，请重新登录。")
        return False, result

    @classmethod
    async def set_vip(cls, obj_or_user_id, is_vip):
        if isinstance(obj_or_user_id, LTUserCookie):
            cookie_obj = obj_or_user_id
        else:
            cookie_obj = await cls.get_by_uid(obj_or_user_id)
        await cls.update(cookie_obj, {"is_vip": bool(is_vip)})
        return True, cookie_obj

    @classmethod
    async def set_blocked(cls, obj_or_user_id):
        if isinstance(obj_or_user_id, LTUserCookie):
            cookie_obj = obj_or_user_id
        else:
            cookie_obj = await cls.get_by_uid(obj_or_user_id)

        await cls.update(cookie_obj, {"blocked_time": datetime.datetime.now()})
        return True, cookie_obj

    @classmethod
    async def get_lt_status(cls, uid):
        obj = await cls.get_by_uid(uid)
        if obj is None:
            return False, f"{uid}未登录宝藏站点。"

        user_prompt_title = f"{obj.name}（uid: {uid}）"
        if not obj.available:
            return False, f"{user_prompt_title}登录已过期，请重新登录。"

        start_time = time.time()
        rows = await UserRaffleRecord.get_by_user_id(user_id=uid)
        most_recently = await LTLastAcceptTime.get_by_uid(uid=uid)
        most_recently = gen_time_prompt(time.time() - most_recently)
        user_prompt = f"{user_prompt_title}\n最后一次抽奖时间：{most_recently}"

        if (datetime.datetime.now() - obj.blocked_time).total_seconds() < 3600 * BLOCK_FRESH_TIME:
            interval_seconds = (datetime.datetime.now() - obj.blocked_time).total_seconds()
            return False, f"{user_prompt}\n{gen_time_prompt(interval_seconds)}发现你被关进了小黑屋。"

        ttl = await LTTempBlack.get_blocking_time(uid=uid)
        if ttl > 0:
            message = (
                f"{user_prompt}\n"
                f"系统发现你在手动领取高能，或者你在别处也参与了抢辣条,所以机器人现在冷却中。\n"
                f"剩余冷却时间：{ttl//60}分钟"
            )
            return False, message

        process_time = time.time() - start_time
        calc = {}
        total_intimacy = 0
        raffle_count = len(rows)
        for row in rows:
            gift_name, raffle_id, intimacy = row.split("$")
            intimacy = int(intimacy)
            if gift_name not in calc:
                calc[gift_name] = 1
            else:
                calc[gift_name] += 1

            if gift_name != "宝箱":
                total_intimacy += intimacy

        def sort_func(r):
            priority_map = {
                "宝箱": 0,
                "总督": 1,
                "提督": 2,
                "舰长": 3,
            }
            return priority_map.get(r[0], 4)

        postfix = []
        for gift_name, times in sorted([(gift_name, times) for gift_name, times in calc.items()], key=sort_func):
            postfix.append(f"{gift_name}: {times}次")
        if postfix:
            postfix = f"{'-'*20}\n" + "、".join(postfix) + "。"
        else:
            postfix = ""

        prompt = [
            f"{user_prompt}，现在正常领取辣条中。\n",
            f"24小时内累计抽奖{raffle_count}次，共获得{total_intimacy}辣条。\n",
            postfix,
            f"\n处理时间：{process_time:.3f}"
        ]
        return True, "".join(prompt)

    @classmethod
    async def set_available_cookie_for_xnode(cls):
        key = "LT_AVAILABLE_COOKIES"
        cookies = []
        for uid in ("CZ", "TZ"):
            user = await cls.get_by_uid(uid, available=True)
            if user:
                cookies.append(user.cookie)

        async with XNodeRedis() as redis:
            await redis.set(key=key, value=cookies)
        await redis_cache.set(key=key, value=cookies)
        logging.info("DATASYNC: available cookies uploaded.")
