import os
import json
import datetime
import traceback
from aiohttp import web
from utils.cq import async_qq, bot
from config.log4 import cqbot_logger as logging
from utils.dao import HansyQQGroupUserInfo, RaffleToCQPushList
from website.handlers.cq_zy import handler as zy_handler


class BotHandler:
    NOTICE_GROUP_ID_LIST = [
        159855203,  # test
        883237694,  # guard
        436496941,
        591691708,  # 禁言群
    ]

    @classmethod
    async def handle_group_message(cls, context):
        logging.info(f"group_message: {context}")
        sender = context["sender"]
        user_id = sender["user_id"]
        user_nickname = sender["nickname"]
        title = sender.get("title", "--")
        card = sender.get("card", "--")
        group_id = context["group_id"]
        msg = context["message"]

        logging.info(f"群消息: ({group_id}) [{title}][{card}]{user_nickname}({user_id}) -> {msg}")

        if msg.strip() in ("#help", "#h", "#帮助", "#指令"):
            await async_qq.send_group_msg(group_id=group_id, message="除直播通知外，所有功能都已下线。")

    @classmethod
    async def handle_private_message(cls, context):
        user_id = context["sender"]["user_id"]
        user_nickname = context["sender"]["nickname"]
        msg = context["raw_message"]
        logging.info("初号机收到私聊: %s(qq: %s) -> %s" % (user_nickname, user_id, msg))

        if msg.startswith("ML"):
            if msg.startswith("ML_BIND_BILI_"):
                # ML_BIND_BILI_123_TO_QQ_456
                try:
                    *_, bili_uid, a, b, qq_uid = msg.split("_")
                    qq_uid = int(qq_uid)
                    bili_uid = int(bili_uid)
                except Exception as e:
                    return bot.send_private_msg(
                        user_id=user_id,
                        message=f"命令错误。",
                        auto_escape=True,
                    )
                r = await RaffleToCQPushList.add(bili_uid=bili_uid, qq_uid=qq_uid)
                return bot.send_private_msg(user_id=user_id, message=f"{r}")

            elif msg.startswith("ML_GET"):
                result = await RaffleToCQPushList.get_all()
                message = "\n".join(str(item) for item in result)
                return bot.send_private_msg(
                    user_id=user_id,
                    message=f"已绑定如下：\n\n(bili_uid, qq_uid)\n{message}",
                    auto_escape=True,
                )

            elif msg.startswith("ML_DEL_BY_QQ_"):
                try:
                    qq_uid = int(msg.split("_")[-1])
                except Exception:
                    return bot.send_private_msg(user_id=user_id, message=f"命令错误")

                result = await RaffleToCQPushList.del_by_qq_uid(qq_uid)
                return bot.send_private_msg(user_id=user_id, message=f"{msg} -> {result}")

            elif msg.startswith("ML_DEL_BY_BILI_"):
                try:
                    bili_uid = int(msg.split("_")[-1])
                except Exception:
                    return bot.send_private_msg(user_id=user_id, message=f"命令错误")

                result = await RaffleToCQPushList.del_by_bili_uid(bili_uid)
                return bot.send_private_msg(user_id=user_id, message=f"{msg} -> {result}")

            return bot.send_private_msg(
                user_id=user_id,
                message=f"ML_BIND_BILI_123_TO_QQ_456\nML_GET\nML_DEL_BY_BILI_123\nML_DEL_BY_QQ_456"
            )

        elif msg == "test":
            return bot.send_private_msg(user_id=user_id, message=f"OK: {datetime.datetime.now()}")

    @classmethod
    async def handle_message(cls, context):
        if context["message_type"] == "group":
            return await cls.handle_group_message(context)

        elif context["message_type"] == "private":
            try:
                return await cls.handle_private_message(context)
            except Exception as e:
                message = f"Error happened in handle_message: {e}\n{traceback.format_exc()}"
                bot.send_private_msg(user_id=80873436, message=message)
                return None

    @classmethod
    async def handle_notice(cls, context):
        now = str(datetime.datetime.now())[:19]

        if context["notice_type"] == 'group_increase':
            group_id = context["group_id"]
            if group_id not in (436496941, 159855203, 1007807100):
                return

            user_id = context["user_id"]
            member = bot.get_group_member_info(group_id=group_id, user_id=user_id)
            nickname = member["nickname"]
            operator_id = context["operator_id"]

            sub_type = context["sub_type"]
            if sub_type == "approve":
                sub_type = "主动加群"
            elif sub_type == "invite":
                sub_type = "管理员邀请"

            info = f"{now} QQ: {nickname}({user_id})通过{sub_type}方式加入到本群，审核者QQ({operator_id})"
            await HansyQQGroupUserInfo.add_info(group_id=group_id, user_id=user_id, info=info)

            bot.set_group_card(group_id=group_id, user_id=user_id, card="✿泡泡┊" + nickname)
            message = (
                f"欢迎[CQ:at,qq={user_id}] 进入泡泡小黄鸡养殖场！\n\n"
                "群名片格式：✿泡泡┊ + 你的昵称，初号机已经自动为你修改~ \n\n"
                "进群记得发个言哦，否则有可能会被当机器人清理掉，很可怕的哦~ "
                "从今天开始一起跟泡泡守护小黄鸡呀！叽叽叽~"
            )
            bot.send_group_msg(group_id=group_id, message=message)

        elif context["notice_type"] == 'group_decrease':
            group_id = context["group_id"]
            if group_id not in (436496941, 159855203):
                return

            operator_id = context["operator_id"]
            user_id = context["user_id"]

            sub_type = context["sub_type"]
            if sub_type == "leave":
                sub_type = "主动退群"
            elif sub_type == "kick":
                sub_type = "被管理员移出"
            elif sub_type == "kick_me":
                sub_type = "登录号被踢"

            info = f"{now} QQ: ({user_id})通过{sub_type}方式离开本群，操作者QQ({operator_id})"
            await HansyQQGroupUserInfo.add_info(group_id=group_id, user_id=user_id, info=info)

    @classmethod
    async def handle_request(cls, context):
        logging.info(f"Request context: {context}")
        if context["request_type"] != "group":
            return

        user_id = context["user_id"]
        comment = context["comment"]
        group_id = context["group_id"]

        sub_type = context["sub_type"]
        if sub_type == "add":
            sub_type = "主动添加"
        elif sub_type == "invite":
            sub_type = "群内成员邀请"

        logging.info(f"Add group request: user_id: {user_id}, comment: {comment}, group_id: {group_id}")
        if group_id == 591691708:
            return {'approve': True}

        elif group_id in (436496941, 159855203):
            now = str(datetime.datetime.now())[:19]
            user_info = await HansyQQGroupUserInfo.get_info(group_id=group_id, user_id=user_id)

            if user_info:
                info = f"{now} QQ({user_id})通过{sub_type}方式尝试加入本群，初号机未处理。验证信息: {comment}"
                await HansyQQGroupUserInfo.add_info(group_id=group_id, user_id=user_id, info=info)

                split = "\n" + "-" * 30 + "\n"
                user_info_str = split.join([info] + user_info)
                message = f"发现已退出本群成员的重新加群请求！相关记录如下：\n\n{user_info_str}"
                logging.info(message)

                if len(message) > 700:
                    message = message[:700] + "..."
                bot.send_group_msg(group_id=group_id, message=message)

            else:
                info = f"{now} QQ({user_id})通过{sub_type}方式加入本群，由初号机审核通过。验证信息: {comment}"
                await HansyQQGroupUserInfo.add_info(group_id=group_id, user_id=user_id, info=info)
                return {'approve': True}


async def handler(request):
    x_self_id = int(request.headers['X-Self-ID'])
    if x_self_id == 250666570:
        return await zy_handler(request)

    context = await request.json()

    if context["post_type"] == "message":
        response = await BotHandler.handle_message(context)

    elif context["post_type"] == "notice":
        response = await BotHandler.handle_notice(context)

    elif context["post_type"] == "request":
        response = await BotHandler.handle_request(context)

    else:
        response = None

    if isinstance(response, dict) and response:
        return web.Response(text=json.dumps(response), content_type="application/json")
    else:
        return web.Response(text="", status=204)
