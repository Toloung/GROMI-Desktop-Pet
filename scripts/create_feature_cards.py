from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1200, 675
BG = "#FFF8EE"
INK = "#3F354A"
MUTED = "#786A7B"
PURPLE = "#D6C2F3"
PURPLE_DARK = "#55436F"
PINK = "#FF9DB1"
GREEN = "#91B684"
BLUE = "#A8C9E8"
CARD = "#FFFFFF"


def font(size, bold=False):
    path = "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"
    return ImageFont.truetype(path, size)


F_TITLE = font(64, True)
F_SUB = font(30)
F_BODY = font(27)
F_SMALL = font(22)
F_LABEL = font(24, True)


def rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def text(draw, xy, value, fnt, fill=INK, anchor="la", **kwargs):
    draw.text(xy, value, font=fnt, fill=fill, anchor=anchor, **kwargs)


def wrap(draw, value, fnt, max_width):
    lines = []
    current = ""
    for char in value:
        test = current + char
        if draw.textlength(test, font=fnt) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def multiline(draw, xy, value, fnt, max_width, line_gap=10, fill=MUTED):
    x, y = xy
    for paragraph in value.splitlines():
        for line in wrap(draw, paragraph, fnt, max_width):
            text(draw, (x, y), line, fnt, fill)
            y += fnt.size + line_gap


def load_pet(size=260):
    pet = Image.open(ROOT / "gromi-icon-preview.png").convert("RGBA")
    pet.thumbnail((size, size), Image.Resampling.LANCZOS)
    return pet


def paste_pet(canvas, xy, size=260):
    pet = load_pet(size)
    canvas.alpha_composite(pet, xy)


def header(draw, title, subtitle):
    text(draw, (72, 72), title, F_TITLE, PURPLE_DARK)
    multiline(draw, (78, 158), subtitle, F_SUB, 430, 8, MUTED)


def badge(draw, xy, label, fill=PURPLE):
    x, y = xy
    w = int(draw.textlength(label, font=F_SMALL)) + 34
    rounded(draw, (x, y, x + w, y + 44), 22, fill)
    text(draw, (x + 17, y + 9), label, F_SMALL, PURPLE_DARK)


def save(card, name):
    card.convert("RGB").save(OUT / name, quality=96)


def card_taskbar():
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    header(d, "任务栏巡逻", "贴近任务栏小尺寸巡逻，自动避开开始菜单和系统托盘。")
    badge(d, (78, 248), "任务栏模式")
    badge(d, (245, 248), "自动缩小")
    badge(d, (390, 248), "避开托盘")

    rounded(d, (130, 485, 1070, 610), 24, "#EAF0F7", "#C8D1DD", 2)
    rounded(d, (170, 525, 285, 573), 18, CARD, "#D1D7E0", 2)
    text(d, (205, 538), "开始", F_SMALL, "#4B5968")
    rounded(d, (790, 523, 1030, 575), 18, CARD, "#D1D7E0", 2)
    text(d, (822, 537), "系统托盘", F_SMALL, "#4B5968")
    d.line((320, 550, 760, 550), fill=PURPLE_DARK, width=6)
    d.ellipse((316, 546, 324, 554), fill=PURPLE_DARK)
    d.ellipse((756, 546, 764, 554), fill=PURPLE_DARK)
    paste_pet(img, (505, 360), 180)
    save(img, "feature-01-taskbar-patrol.png")


def card_weather():
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    header(d, "天气气泡", "悬停 3 秒显示城市天气、体感温度和小提示。")
    badge(d, (78, 248), "悬停显示")
    badge(d, (225, 248), "自动刷新")
    badge(d, (372, 248), "奶油气泡")

    rounded(d, (520, 160, 1035, 410), 34, CARD, INK, 4)
    d.polygon([(690, 407), (742, 407), (713, 465)], fill=CARD, outline=INK)
    rounded(d, (565, 205, 990, 254), 0, PURPLE)
    text(d, (595, 217), "GROMI 天气", F_LABEL, PURPLE_DARK)
    d.ellipse((930, 215, 960, 245), fill=PINK)
    text(d, (565, 282), "株洲 · 阴天 · 08:44", F_BODY, INK)
    text(d, (565, 330), "28.2°C · 体感 32.4°C", F_BODY, MUTED)
    text(d, (565, 376), "提示：今天适合补水和少晒太阳。", F_SMALL, "#7C6A82")
    paste_pet(img, (250, 345), 220)
    save(img, "feature-02-weather-bubble.png")


def card_interaction():
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    header(d, "互动设置", "桌面模式、任务栏巡逻、守护模式和动作频率，都可以在设置里调整。")
    badge(d, (78, 278), "开机启动")
    badge(d, (238, 278), "守护模式")
    badge(d, (398, 278), "动作频率")

    rounded(d, (610, 90, 1045, 585), 28, CARD, "#E4D6C8", 3)
    text(d, (650, 132), "GROMI 设置", font(34, True), PURPLE_DARK)
    sections = [
        ("模式", "任务栏巡逻 / 普通桌面"),
        ("行为", "守护、只露头、开机启动"),
        ("显示", "普通大小、置顶"),
        ("天气", "城市、刷新间隔"),
    ]
    y = 205
    for label, body in sections:
        text(d, (650, y), label, F_LABEL, PURPLE_DARK)
        rounded(d, (650, y + 36, 995, y + 76), 10, "#FFF8EE", "#EADFCC", 1)
        text(d, (670, y + 43), body, F_SMALL, MUTED)
        y += 86
    paste_pet(img, (240, 355), 230)
    save(img, "feature-03-settings.png")


def card_release():
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    header(d, "开源与发布", "上传 GitHub 后，打 tag 自动编译，并发布 Windows EXE。")
    badge(d, (78, 248), "GitHub Actions")
    badge(d, (292, 248), "自动 Release")
    badge(d, (78, 306), "下载 EXE")

    rounded(d, (560, 150, 1030, 480), 30, CARD, "#E4D6C8", 3)
    text(d, (600, 205), "v0.3.2", font(44, True), PURPLE_DARK)
    text(d, (600, 270), "Build Windows EXE", F_BODY, INK)
    d.line((600, 330, 970, 330), fill="#EADFCC", width=3)
    rounded(d, (600, 365, 950, 430), 18, PURPLE, None)
    text(d, (675, 382), "下载 GROMI.exe", F_BODY, PURPLE_DARK)
    paste_pet(img, (235, 340), 240)
    save(img, "feature-04-github-release.png")


def main():
    card_taskbar()
    card_weather()
    card_interaction()
    card_release()
    print(f"Wrote feature cards to {OUT}")


if __name__ == "__main__":
    main()
