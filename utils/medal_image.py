from PIL import Image, ImageDraw, ImageFont, ImageColor


class MedalImage:
    ft_38 = ImageFont.truetype("utils/d.ttf", 38)
    ft_28 = ImageFont.truetype("utils/d.ttf", 28)
    ft_18 = ImageFont.truetype("utils/d.ttf", 18)
    ft_22 = ImageFont.truetype("utils/d.ttf", 22)

    def __init__(
        self,
        uid: int,
        user_name: str,
        sign: str,
        medals,
    ):
        self.uid = uid
        self.user_name = user_name
        self.sign = sign

        medals = [m for m in medals if not m["receive_time"].startswith("0001-01-01")]
        self.medals = sorted(medals, key=lambda x: (x["is_lighted"], x["score"]), reverse=True)
        self.path = f"/home/wwwroot/qq/images/medal_{self.uid}.png"

        self.width = 600
        self.y_offset = 95
        self.height = 30 * len(self.medals) + self.y_offset + 10

        self.img = Image.new('RGB', (self.width, self.height), 0xffffff)
        self.draw_obj = draw_obj = ImageDraw.Draw(self.img)

        draw_obj.text((1, 1, 400, 40), f"{user_name}({uid})", align="center", font=self.ft_38, fill=0)
        draw_obj.line((0, 40 + 3, self.width, 40 + 3), fill=0, width=1)
        draw_obj.text((0, 40 + 5), sign, align="left", font=self.ft_22, fill=0)
        for i, medal in enumerate(self.medals):
            medal_color = medal["medal_color"]
            text = medal["medal_name"]
            level = medal["level"]
            receive_time = medal["receive_time"].split(" ")[0]
            intimacy = medal["intimacy"]
            next_intimacy = medal["next_intimacy"]
            master = medal["target_name"]
            extra = f"{receive_time} {master}"
            is_lighted = medal["is_lighted"] != 0
            self.draw_one_medal(
                x=2,
                y=30 * i + 2 + self.y_offset,
                color=medal_color,
                text=text,
                level=level,
                extra=extra,
                intimacy=intimacy,
                next_intimacy=next_intimacy,
                is_lighted=is_lighted,
            )

    def draw_one_medal(self, x, y, color, text, level, extra, intimacy, next_intimacy, is_lighted: bool):
        draw_obj = self.draw_obj
        w = 120
        h = 26
        r = 5
        color = ImageColor.getrgb(f"#{color:0>6x}")

        '''Rounds'''
        draw_obj.ellipse((x, y, x + r, y + r), fill=color)
        draw_obj.ellipse((x + w - r, y, x + w, y + r), fill=color)
        draw_obj.ellipse((x, y + h - r, x + r, y + h), fill=color)
        draw_obj.ellipse((x + w - r, y + h - r, x + w, y + h), fill=color)

        '''rec.s'''
        draw_obj.rectangle((x + r / 2, y, x + w - (r / 2), y + h), fill=color)
        draw_obj.rectangle((x, y + r / 2, x + w, y + h - (r / 2)), fill=color)

        # (width, height)
        draw_obj.rectangle((x + 90, y + 2, x + w - 2, y + h - 2), fill=0xffffff)

        draw_obj.text((x + 1, y, x + 90, y + 30), text, align="center", font=self.ft_28, fill=0xffffff)
        x_delta = 7 if level < 10 else 0
        draw_obj.text((x + 90 + 1 + x_delta, y), str(level), align="center", font=self.ft_28, fill=color)

        # progress bar
        x_offset = 120 + 10
        width = 140
        progress_text = f"{intimacy:>6}/{next_intimacy:<6}"
        percent = int(intimacy / next_intimacy * width)

        draw_obj.text((x_offset, y + 2), progress_text, font=self.ft_18, fill=0)

        draw_obj.rectangle((x_offset, y + 22, x_offset + width, y + 25), fill=0xdddddd)
        draw_obj.rectangle((x_offset, y + 22, x_offset + percent, y + 25), fill=color)

        # fetched time
        x_offset = x_offset + width + 10
        draw_obj.text((x_offset, y + 4), str(extra), align="center", font=self.ft_22, fill=0)

    def show(self):
        self.img.show()

    @property
    def file_loc(self) -> str:
        return self.path

    def save(self):
        self.img.save(self.path)
