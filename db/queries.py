import random
import datetime
from typing import Union, List, Iterable
from db.tables import LTUser
from utils.dao import redis_cache


class LTUserQueryMixin:
    key_prefix = LTUser.__key__

    async def delete_lt_user(self, user_id: int) -> None:
        key = f"{self.key_prefix}:{user_id}"
        await redis_cache.hash_map_del_all(key)
        await redis_cache.set_remove(self.key_prefix, user_id)

    async def update_lt_user(self, lt_user: LTUser, fields: Iterable[str]) -> None:
        key = f"{self.key_prefix}:{lt_user.user_id}"
        update_params = {}
        for k, v in lt_user.dict().items():
            if k in fields:
                update_params[k] = v

        from config.log4 import lt_login_logger as logging
        logging.info(f".hash_map_set(key, update_params): {key} -> {update_params}")

        await redis_cache.hash_map_set(key, update_params)
        r = await redis_cache.hash_map_get_all(key)
        logging.info(f"hash_map_get_all r: {r}")

    async def upsert_lt_user(
            self,
            DedeUserID: int,
            SESSDATA: str,
            bili_jct: str,
            sid: str,
            DedeUserID__ckMd5: str,
            access_token: str,
            refresh_token: str,
            account: str = None,
            password: str = None,
            notice_email: str = None,
            bind_qq: int = None,
            available: bool = True,
    ) -> LTUser:

        params = dict(
            DedeUserID=int(DedeUserID),
            SESSDATA=SESSDATA,
            bili_jct=bili_jct,
            sid=sid,
            DedeUserID__ckMd5=DedeUserID__ckMd5,
            access_token=access_token,
            refresh_token=refresh_token,
            available=available,
        )
        fields = list(params.keys())
        if account is not None:
            params["account"] = account
            fields.append("account")
        if password is not None:
            params["password"] = password
            fields.append("password")
        if notice_email is not None:
            params["notice_email"] = notice_email
            fields.append("notice_email")
        if bind_qq is not None:
            params["bind_qq"] = bind_qq
            fields.append("bind_qq")

        lt_user = LTUser(**params)
        await self.update_lt_user(lt_user, fields=fields)

        lt_user = await self.get_lt_user_by_uid(lt_user.user_id)
        await redis_cache.set_add(self.key_prefix, lt_user.user_id)
        return lt_user

    async def set_lt_user_invalid(self, lt_user: LTUser) -> LTUser:
        lt_user.available = False
        await self.update_lt_user(lt_user, fields=("available", ))

        if lt_user.bind_qq:
            from utils.cq import async_zy
            await async_zy.send_private_msg(
                user_id=lt_user.bind_qq,
                message=f"你挂的辣条机已经掉线，请重新登录。{lt_user}"
            )
        if lt_user.notice_email:
            from utils.email import send_cookie_invalid_notice
            send_cookie_invalid_notice(lt_user)
        return lt_user

    async def set_lt_user_if_is_vip(self, lt_user: LTUser, is_vip: bool) -> LTUser:
        lt_user.is_vip = is_vip
        await self.update_lt_user(lt_user, fields=("is_vip", ))
        return lt_user

    async def set_lt_user_blocked(self, lt_user: LTUser) -> LTUser:
        lt_user.blocked_time = datetime.datetime.now()
        await self.update_lt_user(lt_user, fields=("blocked_time", ))
        return lt_user

    async def get_lt_user_by_uid(self, user_id: Union[str, int]) -> Union[LTUser, None]:
        user_id = LTUser.__UID_STR_TO_INT_MAP__.get(user_id, user_id)
        if not isinstance(user_id, int):
            return None

        key = f"{self.key_prefix}:{user_id}"
        result = await redis_cache.hash_map_get_all(key)
        if not result:
            return
        return LTUser(**result)

    async def get_lt_user_by_account(self, account: str) -> Union[LTUser, None]:
        all_users = await self.get_all_lt_user()
        for user in all_users:
            if user.account == account:
                return user

    async def get_all_lt_user(self) -> List[LTUser]:
        user_id_list = await redis_cache.set_get_all(self.key_prefix)
        if not user_id_list:
            return []
        key_list = [f"{self.key_prefix}:{user_id}" for user_id in user_id_list]
        user_dict_list = await redis_cache.hash_map_multi_get(*key_list)
        return [LTUser(**d) for d in user_dict_list]

    async def get_lt_user_by(
            self,
            available: bool = None,
            is_vip: bool = None,
            is_blocked: bool = None,
            filter_k: str = None,
            bind_qq: int = None,
    ) -> List[LTUser]:

        all_users = await self.get_all_lt_user()
        result = []
        for u in all_users:
            if available is not None and u.available != available:
                continue
            if is_vip is not None and u.is_vip != is_vip:
                continue
            if is_blocked is not None and u.is_blocked != is_blocked:
                continue

            if bind_qq is not None and u.bind_qq != bind_qq:
                continue

            if filter_k is not None:
                percent = getattr(u, filter_k, 0)

                # randint 可以取值到1和100
                # 如果 percent 设置为0，则任意随即值都比 percent 大，故100%跳过
                if random.randint(1, 100) > percent:
                    continue

            result.append(u)

        return result

    async def get_an_available_lt_user(self) -> Union[LTUser, None]:
        all_users = await self.get_all_lt_user()
        for u in all_users:
            if u.available:
                return u

    async def set_lt_user_last_accept(self, user: LTUser) -> None:
        user.last_accept_time = datetime.datetime.now()
        await self.update_lt_user(user, fields=("last_accept_time", ))


class Queries(LTUserQueryMixin):
    ...


queries = Queries()
