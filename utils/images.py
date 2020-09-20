import os
import time
from PIL import Image
from typing import *


class DynamicPicturesProcessor:

    def __init__(self, path, target_path=None, target_size=None):
        self.path = path

        if target_path is None:
            target_path = "/home/wwwroot/qq/images"
        self.target_path = target_path

        self.target = None
        self.target_size = target_size or (1920, 1440)
        self.target_file_name = None

    @staticmethod
    def join_pic_horizontal(*images):
        if len(images) == 1:
            return images

        target_height = min([img.size[1] for img in images])
        sources = []
        target_width = 0
        for img in images:
            w, h = img.size
            width = int(w * (target_height / h))
            target_width += width
            img = img.resize((width, target_height))
            sources.append(img)

        target = Image.new('RGB', (target_width, target_height), 0x333333)

        target_offset_x = 0
        for img in sources:
            w, h = img.size
            target.paste(im=img, box=(target_offset_x, 0, target_offset_x + w, h))
            target_offset_x += w

        return target

    @staticmethod
    def join_pic_vertical(*images):
        if len(images) == 1:
            return images

        target_width = min([img.size[0] for img in images])
        sources = []
        target_height = 0
        for img in images:
            w, h = img.size
            height = int(h * (target_width / w))
            target_height += height
            img = img.resize((target_width, height))
            sources.append(img)

        target = Image.new('RGB', (target_width, target_height), 0x333333)

        target_offset_y = 0
        for img in sources:
            w, h = img.size
            target.paste(im=img, box=(0, target_offset_y, w, target_offset_y + h))
            target_offset_y += h

        return target

    def draw_type_lte_3(self, files):
        sources = []
        for f in files:
            img = Image.open(os.path.join(self.path, f), mode="r")
            img = img.convert('RGB')
            sources.append(img)

        self.target = self.join_pic_horizontal(*sources)

    def draw_type_eq_4(self, files):
        sources = []
        for f in files:
            img = Image.open(os.path.join(self.path, f), mode="r")
            img = img.convert('RGB')
            sources.append(img)
        img = self.join_pic_horizontal(*sources[:2])
        img2 = self.join_pic_horizontal(*sources[2:])
        self.target = self.join_pic_vertical(img, img2)

    def draw_type_gt_4(self, files):
        images = []
        sizes = {}
        for f in files:
            img = Image.open(os.path.join(self.path, f), mode="r")
            img = img.convert('RGB')

            if img.size not in sizes:
                sizes[img.size] = 1
            else:
                sizes[img.size] += 1
            images.append(img)

        if len(files) == 9 and len(sizes.keys()) == 2:
            temp = [(size, count) for size, count in sizes.items()]
            temp.sort(key=lambda x: x[1], reverse=True)
            target_re_size = temp[0][0]
        else:
            target_re_size = None

        sources = []
        temp_sources = []
        for img in images:
            if target_re_size:
                w, h = img.size
                if w >= target_re_size[0]:
                    offset_height = int((abs(target_re_size[1] - h)) / 2)
                    img = img.crop(box=(0, offset_height, w, offset_height + target_re_size[1]))

            temp_sources.append(img)
            if len(temp_sources) == 3:
                sources.append(temp_sources)
                temp_sources = []
        if temp_sources:
            sources.append(temp_sources)

        images = []
        for s in sources:
            images.append(self.join_pic_horizontal(*s))
        self.target = self.join_pic_vertical(*images)

    def save(self):
        if not os.path.exists(self.target_path):
            os.mkdir(self.target_path)

        if self.target.size[0] > self.target_size[0]:
            height = int(self.target.size[1] * (self.target_size[0] / self.target.size[0]))
            self.target = self.target.resize((self.target_size[0], height))
        elif self.target.size[1] > self.target_size[1]:
            width = int(self.target.size[0] * (self.target_size[1] / self.target.size[1]))
            self.target = self.target.resize((width, self.target_size[1]))

        file_name = f"b_{int(time.time()*1000):0x}.jpg"
        self.target.save(os.path.join(self.target_path, file_name), quality=90)
        self.target_file_name = file_name
        # self.target.show()

    def join(self) -> Tuple[bool, str]:
        """

        Returns
        -------
        flag:
        path: str, 目标文件的绝对路径
        """
        files = sorted(os.listdir(self.path))
        target = []
        for f in files:
            if not os.path.isfile(os.path.join(self.path, f)):
                continue

            if f.startswith("."):
                continue

            target.append(f)
        try:
            if len(target) <= 3:
                self.draw_type_lte_3(files=target)
            elif len(target) == 4:
                self.draw_type_eq_4(files=target)
            else:
                self.draw_type_gt_4(files=target)
            self.save()
        except Exception as e:
            return False, f"Error happened: {e}"

        return True, os.path.join(self.target_path, self.target_file_name)
