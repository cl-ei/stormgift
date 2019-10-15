import time
import json
import asyncio
import aiohttp
import datetime
from utils.biliapi import BiliApi, CookieFetcher
from config import cloud_get_uid
from config.log4 import bili_api_logger as logging
from utils.db_raw_query import AsyncMySQL
from utils.reconstruction_model import LTUserCookie
from utils.email import send_cookie_invalid_notice
from utils.dao import LtUserLoginPeriodOfValidity


BLOCK_FRESH_TIME = 1


class ReqFreLimitApi(object):
    __req_time = {}

    @classmethod
    async def _wait(cls, f, wait_time):
        last_req_time = cls.__req_time.get(f)
        if last_req_time is None:
            cls.__req_time[f] = time.time()
        else:
            interval = time.time() - last_req_time
            if interval < wait_time:
                sleep_time = wait_time - interval
                logging.warn(f"High level api request frequency control: f: {f}, sleep_time: {sleep_time:.3f}")
                await asyncio.sleep(sleep_time)
            cls.__req_time[f] = time.time()

    @classmethod
    async def _update_time(cls, f):
        cls.__req_time[f] = time.time()

    @classmethod
    async def get_uid_by_name(cls, user_name, wait_time=2):
        r = await DBCookieOperator.get_by_uid("DD")
        cookie = r.cookie if r else ""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
                async with session.post(cloud_get_uid, json={"cookie": cookie, "name": user_name}) as resp:
                    status_code = resp.status
                    content = await resp.text()
        except Exception as e:
            status_code = 5000
            content = f"Error: {e}"

        if status_code != 200:
            logging.error(f"Error happened when get_uid_by_name({user_name}): {content}.")
            return None

        try:
            r = json.loads(content)
            assert r[0] is True
        except (json.JSONDecodeError, AssertionError) as e:
            logging.error(f"Error happened when get_uid_by_name({user_name}): {e}")
            return None

        return r[1]

    @classmethod
    async def get_raffle_record(cls, uid):
        raffles = await AsyncMySQL.execute(
            "select r.winner_name, r.room_id, r.prize_gift_name, r.expire_time "
            "from raffle r, biliuser u "
            "where r.winner_obj_id = u.id and u.uid = %s and r.expire_time >= %s "
            "order by r.expire_time desc;",
            (uid, datetime.datetime.now() - datetime.timedelta(days=7))
        )

        results = []
        for r in raffles:
            name, room_id, gift_name, created_time = r
            results.append([name, room_id, gift_name, created_time])

        if not results:
            return results

        room_id_map = await AsyncMySQL.execute(
            "select real_room_id, short_room_id from biliuser where real_room_id in %s;",
            ([row[1] for row in results], )
        )
        room_id_map = {r[0]: r[1] for r in room_id_map}
        for r in results:
            r[1] = room_id_map.get(r[1], r[1])
        return results

    @classmethod
    async def get_guard_record(cls, uid):
        user_obj = await AsyncMySQL.execute("select u.id, u.name from biliuser u where u.uid = %s", (uid, ))
        if not user_obj:
            return f"未能查询到用户?(uid: {uid})"

        user_obj_id, user_name = user_obj[0]

        guards = await AsyncMySQL.execute(
            "select g.room_id, g.gift_name, g.created_time "
            "from guard g "
            "where g.sender_obj_id = %s and g.created_time >= %s "
            "order by g.room_id, g.created_time desc;",
            (user_obj_id, datetime.datetime.now() - datetime.timedelta(days=45))
        )
        if not guards:
            return f"{user_name}(uid: {uid})在45天内没有开通过1条船。"

        room_id_map = await AsyncMySQL.execute(
            "select real_room_id, short_room_id from biliuser where real_room_id in %s;",
            ([r[0] for r in guards],)
        )
        room_id_map = {r[0]: r[1] for r in room_id_map}

        def gen_time_prompt(interval):
            if interval > 3600*24:
                return f"约{int(interval // (3600*24))}天前"
            elif interval > 3600:
                return f"约{int(interval // 3600)}小时前"
            elif interval > 60:
                return f"约{int(interval // 60)}分钟前"
            return f"{int(interval)}秒前"

        prompt = []
        now = datetime.datetime.now()
        for r in guards:
            room_id, gift_name, created_time = r
            time_interval = (now - created_time).total_seconds()
            interval_prompt = gen_time_prompt(time_interval)

            short_room_id = room_id_map.get(room_id, room_id)
            prompt.append(f"{interval_prompt}在{short_room_id}直播间开通{gift_name}*1")

        prompt = f"\n{'-'*80}".join(prompt)

        return f"{user_name}(uid: {uid})在45天内开通{len(guards)}条船：\n\n{prompt}"

    @classmethod
    async def get_raffle_count(cls, day_range=0):
        now = datetime.datetime.today()
        start_datetime = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if day_range > 0:
            start_datetime -= datetime.timedelta(days=day_range)
        end_date_time = start_datetime + datetime.timedelta(days=1)

        result = await AsyncMySQL.execute(
            "select max(id), min(id) "
            "from raffle where created_time >= %s and created_time < %s;",
            (start_datetime, end_date_time)
        )
        max_raffle_id, min_raffle_id = result[0]

        result = await AsyncMySQL.execute(
            "select id, winner_obj_id, gift_type from raffle where id >= %s and id <= %s order by id desc;",
            (min_raffle_id, max_raffle_id)
        )
        miss_raffle_count = 0
        total_gift_count = 0
        miss_gift_record = max_raffle_id - min_raffle_id - len(result) + 1
        gift_list = {}
        for raffle_id, winner_obj_id, gift_type in result:
            if gift_type == "GIFT_20003":
                gift_name = "大楼"
            elif gift_type == "GIFT_30035":
                gift_name = "任意门"
            elif gift_type == "GIFT_30207":
                gift_name = "幻月之声"
            elif gift_type == "small_tv":
                gift_name = "小电视"
            else:
                gift_name = "其他高能"

            if gift_name not in gift_list:
                gift_list[gift_name] = 1
            else:
                gift_list[gift_name] += 1

            total_gift_count += 1
            if winner_obj_id is None:
                miss_raffle_count += 1

        return_data = {
            "miss": miss_gift_record,
            "miss_raffle": miss_raffle_count,
            "total": total_gift_count,
            "gift_list": gift_list
        }
        return return_data

    @classmethod
    async def get_guard_count(cls):
        max_id_yesterday = (await AsyncMySQL.execute(
            "select id from guard where created_time < %s order by id desc limit 1;",
            (datetime.date.today(),)
        ))[0][0]
        print("max_id_yesterday: %s" % max_id_yesterday)

        result = await AsyncMySQL.execute(
            "select id from guard where id > %s and created_time >= %s order by id desc;",
            (max_id_yesterday, datetime.date.today(), )
        )
        total_id_list = [r[0] for r in result]

        target_count = total_id_list[0] - max_id_yesterday
        miss = target_count - len(total_id_list)

        result = await AsyncMySQL.execute(
            "select gift_name, count(id) from guard where id > %s group by 1;", (max_id_yesterday, )
        )

        gift_list = {}
        total_gift_count = 0
        for row in result:
            gift_list[row[0]] = row[1]
            total_gift_count += row[1]

        return_data = {
            "miss": miss,
            "total": total_gift_count,
            "gift_list": gift_list
        }
        return return_data


class DBCookieOperator:

    _objects = None

    IMPORTANT_UID_LIST = (
        20932326,  # DD
        39748080,  # LP
        312186483,  # TZ
        87301592,  # 村长
    )

    @classmethod
    async def execute(cls, *args, **kwargs):
        if cls._objects is None:
            from utils.reconstruction_model import objects
            await objects.connect()
            cls._objects = objects
        if args or kwargs:
            return await cls._objects.execute(*args, **kwargs)
        else:
            return None

    @classmethod
    async def add_uid_or_account_to_white_list(cls, uid=None, account=None):
        await cls.execute()

        if uid is not None:
            obj, is_new = await cls._objects.get_or_create(LTUserCookie, DedeUserID=uid)
        else:
            obj, is_new = await cls._objects.get_or_create(LTUserCookie, account=account)

        return obj

    @classmethod
    async def del_uid_or_account_from_white_list(cls, uid=None, account=None):
        count = 0
        if uid:
            objs = await cls._objects.execute(LTUserCookie.select().where(LTUserCookie.DedeUserID == uid))
            for obj in objs:
                count += 1
                await cls._objects.delete(obj)

        if account:
            objs = await cls._objects.execute(LTUserCookie.select().where(LTUserCookie.account == account))
            for obj in objs:
                count += 1
                await cls._objects.delete(obj)

        return count

    @classmethod
    async def add_cookie_by_account(cls, account, password, notice_email=None):
        objs = await cls.execute(LTUserCookie.select().where(LTUserCookie.account == account))
        if not objs:
            return False, "你不在白名单里。提前联系站长经过允许才可以使用哦。"

        lt_user = objs[0]
        if lt_user.available and (lt_user.cookie_expire_time - datetime.datetime.now()).total_seconds() > 3600*24*10:
            return True, lt_user

        flag, data = await CookieFetcher.login(account, password)
        if not flag:
            return False, data

        lt_user.password = password
        lt_user.cookie_expire_time = datetime.datetime.now() + datetime.timedelta(days=30)
        lt_user.available = True
        attrs = ["password", "cookie_expire_time", "available"]

        for k, v in data.items():
            setattr(lt_user, k, v)
            attrs.append(k)

        flag, data, uname = await BiliApi.get_if_user_is_live_vip(
            cookie=lt_user.cookie,
            user_id=lt_user.uid,
            return_uname=True
        )
        if not flag:
            return False, "无法获取你的个人信息，请稍后再试。"

        lt_user.is_vip = data
        lt_user.name = uname
        attrs.extend(["is_vip", "name"])

        if notice_email is not None:
            lt_user.notice_email = notice_email
            attrs.append("notice_email")

        for obj in await cls._objects.execute(LTUserCookie.select().where(
            (LTUserCookie.DedeUserID == lt_user.DedeUserID) & (LTUserCookie.id != lt_user.id)
        )):
            await cls._objects.delete(obj)

        await cls._objects.update(lt_user, only=attrs)

        return True, lt_user

    @classmethod
    async def set_invalid(cls, obj_or_user_id):
        if isinstance(obj_or_user_id, LTUserCookie):
            cookie_obj = obj_or_user_id
        else:
            objs = await cls.execute(LTUserCookie.select().where(LTUserCookie.DedeUserID == obj_or_user_id))
            if not objs:
                return False, "Cannot get LTUserCookie obj."
            cookie_obj = objs[0]

        cookie_obj.available = False
        await cls._objects.update(cookie_obj, only=("available",))

        user_in_period = await LtUserLoginPeriodOfValidity.in_period(user_id=cookie_obj.DedeUserID)
        user_in_iptt_list = cookie_obj.DedeUserID in cls.IMPORTANT_UID_LIST

        if (user_in_iptt_list or user_in_period) and cookie_obj.account and cookie_obj.password:
            for try_times in range(3):
                flag, data = await cls.add_cookie_by_account(
                    account=cookie_obj.account,
                    password=cookie_obj.password
                )
                if flag:
                    # send_cookie_relogin_notice(cookie_obj)
                    return True, ""
                else:
                    logging.error(
                        f"Failed to login user: {cookie_obj.name}(uid: {cookie_obj.user_id}), "
                        f"try times: {try_times}, error msg: {data}"
                    )
                    await asyncio.sleep(1)

        send_cookie_invalid_notice(cookie_obj)
        return True, ""

    @classmethod
    async def refresh_token(cls, obj_or_user_id):
        if isinstance(obj_or_user_id, LTUserCookie):
            cookie_obj = obj_or_user_id
        else:
            objs = await cls.execute(LTUserCookie.select().where(LTUserCookie.DedeUserID == obj_or_user_id))
            if not objs:
                return False, "Cannot get LTUserCookie obj."
            cookie_obj = objs[0]

        if not cookie_obj.available:
            return False, "User not available!"

        if not cookie_obj.account or not cookie_obj.password:
            return False, "No account or password."

        user_in_period = await LtUserLoginPeriodOfValidity.in_period(user_id=cookie_obj.DedeUserID)
        user_in_iptt_list = cookie_obj.DedeUserID in cls.IMPORTANT_UID_LIST
        if not user_in_period and not user_in_iptt_list:
            return False, "User not in period."

        if not cookie_obj.refresh_token or not cookie_obj.access_token:
            # 重新登录
            return await cls.set_invalid(cookie_obj)

        flag, r = await CookieFetcher.fresh_token(cookie_obj.cookie, cookie_obj.access_token, cookie_obj.refresh_token)
        if not flag:
            return False, f"User {cookie_obj.name}(uid: {cookie_obj.uid}) cannot fresh_token: {r}"

        attrs = []
        for k, v in r.items():
            setattr(cookie_obj, k, v)
            attrs.append(k)
        await cls._objects.update(cookie_obj, only=attrs)
        logging.info(f"User {cookie_obj.name}(uid: {cookie_obj.uid}) access token refresh success!")
        return True, ""

    @classmethod
    async def set_vip(cls, obj_or_user_id, is_vip):
        if isinstance(obj_or_user_id, LTUserCookie):
            cookie_obj = obj_or_user_id
        else:
            objs = await cls.execute(LTUserCookie.select().where(LTUserCookie.DedeUserID == obj_or_user_id))
            if not objs:
                return False, "Cannot get LTUserCookie obj."
            cookie_obj = objs[0]

        cookie_obj.is_vip = bool(is_vip)
        await cls._objects.update(cookie_obj, only=("is_vip",))

        return True, cookie_obj

    @classmethod
    async def set_blocked(cls, obj_or_user_id):
        if isinstance(obj_or_user_id, LTUserCookie):
            cookie_obj = obj_or_user_id
        else:
            objs = await cls.execute(LTUserCookie.select().where(LTUserCookie.DedeUserID == obj_or_user_id))
            if not objs:
                return False, "Cannot get LTUserCookie obj."
            cookie_obj = objs[0]

        cookie_obj.blocked_time = datetime.datetime.now()
        await cls._objects.update(cookie_obj, only=("blocked_time",))
        return True, cookie_obj

    @classmethod
    async def get_by_uid(cls, user_id, available=None):
        if user_id == "*":
            objs = await cls.execute(LTUserCookie.select().where(LTUserCookie.available == True))
            return objs[0]

        if user_id == "DD":
            user_id = 20932326
        elif user_id == "LP":
            user_id = 39748080

        if available is None:
            query = LTUserCookie.select().where(LTUserCookie.DedeUserID == user_id)
        else:
            query = LTUserCookie.select().where(
                (LTUserCookie.DedeUserID == user_id) & (LTUserCookie.available == available)
            )
        objs = await cls.execute(query)
        if objs:
            return objs[0]
        return None

    @classmethod
    async def get_objs(cls, available=None, is_vip=None, non_blocked=None, separate=False):
        query = LTUserCookie.select()
        if available is not None:
            query = query.where(LTUserCookie.available == available)
        if is_vip is not None:
            query = query.where(LTUserCookie.is_vip == is_vip)

        if non_blocked is not None:
            three_hour_ago = datetime.datetime.now() - datetime.timedelta(hours=BLOCK_FRESH_TIME)
            query = query.where(LTUserCookie.blocked_time < three_hour_ago)

        important_objs = []
        objs = []
        for o in await cls.execute(query):
            if o.DedeUserID in cls.IMPORTANT_UID_LIST:
                important_objs.append(o)
            else:
                objs.append(o)

        if separate:
            return important_objs, objs
        else:
            return important_objs + objs

    @classmethod
    async def get_lt_status(cls, uid):
        cookie_obj = await cls.get_by_uid(uid)
        if cookie_obj is None:
            return False, f"{uid}未登录宝藏站点。"

        def gen_time_prompt(interval):
            if interval > 3600*24:
                return f"约{int(interval // (3600*24))}天前"
            elif interval > 3600:
                return f"约{int(interval // 3600)}小时前"
            elif interval > 60:
                return f"约{int(interval // 60)}分钟前"
            return f"{int(interval)}秒前"

        if not cookie_obj.available:
            return False, f"用户{cookie_obj.name}（uid: {uid}）的登录已过期，请重新登录。"

        start_time = time.time()

        most_recently = await AsyncMySQL.execute(
            "select created_time from userrafflerecord "
            "where user_id = %s order by created_time desc limit 1;",
            (uid,)
        )
        if most_recently:
            interval = (datetime.datetime.now() - most_recently[0][0]).total_seconds()
            most_recently = gen_time_prompt(interval)
        else:
            most_recently = "约100年前"

        if (datetime.datetime.now() - cookie_obj.blocked_time).total_seconds() < 3600 * BLOCK_FRESH_TIME:
            interval = (datetime.datetime.now() - cookie_obj.blocked_time).total_seconds()
            return False, (
                f"{cookie_obj.name}(uid: {cookie_obj.uid}):\n"
                f"{gen_time_prompt(interval)}发现你被关进了小黑屋，最后一次抽奖时间：{most_recently}。"
            )

        rows = await AsyncMySQL.execute(
            (
                "select gift_name, count(raffle_id), sum(intimacy) "
                "from userrafflerecord "
                "where user_id = %s and created_time >= %s "
                "group by gift_name;"
            ), (uid, datetime.datetime.now() - datetime.timedelta(hours=24))
        )
        process_time = time.time() - start_time

        raffle_result = [(r[0], r[1], r[2]) for r in rows]

        def sort_func(row):
            priority_map = {
                "宝箱": 0,
                "总督": 1,
                "提督": 2,
                "舰长": 3,
            }
            return priority_map.get(row[0], 4)

        total_intimacy = sum([r[2] for r in raffle_result if r[0] != "宝箱"])
        postfix = []
        for r in sorted(raffle_result, key=sort_func):
            gift_name = r[0]
            award_name = "银瓜子" if gift_name == "宝箱" else "辣条"
            postfix.append(f"{gift_name}: {r[1]}次({r[2]}{award_name})")
        if postfix:
            postfix = f"{'-'*20}\n" + "、".join(postfix) + "。"
        else:
            postfix = ""

        prompt = [
            f"{cookie_obj.name}(uid: {cookie_obj.uid})正常领取辣条中:\n",
            f"最后一次抽奖在{str(most_recently)}，24小时内共获得{total_intimacy}辣条。\n",
            postfix,
            f"\n处理时间：{process_time:.3f}"
        ]
        return True, "".join(prompt)
