
# fix gift name;
update raffle set gift_name = "小电视飞船抽奖" where gift_name = "-" and gift_type = "small_tv";
update raffle set gift_name = "任意门抽奖" where gift_name = "-" and gift_type = "GIFT_30035";
update raffle set gift_name = "幻乐之声抽奖" where gift_name = "-" and gift_type = "GIFT_30207";
update raffle set gift_name = "摩天大楼抽奖" where gift_name = "-" and gift_type = "GIFT_20003";

