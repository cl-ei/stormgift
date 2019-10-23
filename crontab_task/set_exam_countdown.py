from utils.cq import bot_zy
import datetime


def main():
    end_date = datetime.datetime.strptime("2019-12-20 00:00:00", "%Y-%m-%d %H:%M:%S")
    count_down = (end_date - datetime.datetime.now()).total_seconds()
    days = int(count_down / 3600 / 24)
    card = f"梓亞.考研倒计时{days}天"
    r = bot_zy.set_group_card(group_id=159855203, user_id=250666570, card=card)
    print(f"Execute result: {r}, card: {card}")


if __name__ == "__main__":
    main()
