# GROMI 桌面宠物

GROMI 是一个 Windows 桌面宠物小应用，使用 Python、Tkinter、Pillow 和 pystray 制作。它可以在普通桌面模式下陪你待着，也可以切换到任务栏巡逻模式，在任务栏附近以更小尺寸活动。

## 功能

- 任务栏巡逻模式：自动适配任务栏高度，保持小尺寸活动
- 普通桌面模式：可调整宠物显示大小
- 守护模式：固定不动，禁止自动巡逻
- 普通桌面置顶开关：任务栏模式会始终保持在任务栏前方
- 系统托盘图标：可隐藏、显示、切换模式和退出
- 天气气泡：鼠标悬停 3 秒后显示天气
- 单实例保护：如果 GROMI 已经在运行，会弹窗提示

## 预览

![GROMI 图标预览](gromi-icon-preview.png)

## 环境要求

- Windows 10/11
- Python 3.10 或更新版本

安装依赖：

```bat
python -m pip install -r requirements.txt
```

## 从源码运行

```bat
python gromi_desktop_pet.py
```

## 打包为 EXE

```bat
build.bat
```

打包完成后，生成文件位于：

```text
dist\GROMI桌面宠物.exe
```

## GitHub 自动构建

项目已经包含 GitHub Actions 配置：

```text
.github\workflows\build-windows.yml
```

上传到 GitHub 后，以下情况会自动在 Windows 环境中打包 EXE：

- push 到 `main` 分支
- 提交 Pull Request
- 在 Actions 页面手动运行 workflow

构建成功后，可以在对应 Actions 运行记录的 Artifacts 区域下载：

```text
GROMI-Desktop-Pet-Windows
```

## 文件说明

- `gromi_desktop_pet.py`：主程序
- `gromi_spritesheet.webp`：宠物动画精灵图
- `gromi.ico`：EXE 图标
- `gromi-icon-preview.png`：图标预览
- `build.bat`：本地 Windows 打包脚本
- `requirements.txt`：Python 依赖
- `.github/workflows/build-windows.yml`：GitHub Actions 自动构建配置

## 设置位置

应用设置保存在：

```text
%APPDATA%\GROMI Desktop Pet\settings.json
```

如果启动后没有看到窗口，可能是已有 GROMI 正在运行。可以先检查系统托盘，或退出旧进程后再打开。

## 命名说明

“GROMI / 格洛米”这个名字和许嵩有关：公开歌词资料显示，许嵩的歌曲《有何不可》中出现了“格洛米”；多篇公开资料也将“格洛米”解释为许嵩宠物狗的名字。

本项目只是个人桌面宠物实验项目，不是许嵩或其团队的官方项目，也不包含许嵩的音乐、歌词全文、肖像或其他官方素材。

参考资料：

- [《有何不可》歌词资料](https://lyrics.net.cn/lyrics/26661)
- [搜狐：许嵩《有何不可》中，格洛米到底是何方神圣？](https://www.sohu.com/a/147943062_581277)
- [DailyView：歌词“格洛米”到底是什么意思？](https://dailyview.tw/popular/detail/2442)
- [iQIYI：许嵩 格洛米GROMI](https://www.iq.com/wiki/zh_tw/album/%E8%A8%B1%E5%B5%A9-%E6%A0%BC%E6%B4%9B%E7%B1%B3gromi-2025-1xf38h69gj4)
