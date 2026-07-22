# GROMI 桌面宠物

GROMI 是一个 Windows 桌面宠物小应用，使用 Python、Tkinter、Pillow 和 pystray 制作。

“GROMI / 格洛米”是许嵩宠物狗的名字。项目中使用了 GROMI 的卡通图像，仅用于个人娱乐、学习和功能测试，不代表已获得相关素材的使用授权。

## 功能

- 任务栏巡逻模式：自动适配任务栏高度，保持小尺寸活动
- 普通桌面模式：可调整宠物显示大小
- 守护模式：固定不动，禁止自动巡逻
- 开机自启动：可在设置中开启或关闭
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
dist\GROMI.exe
```

## GitHub 自动构建

项目包含 GitHub Actions 配置：

```text
.github\workflows\build-windows.yml
```

上传到 GitHub 后，push 到 `main` 分支或手动运行 workflow 时，会自动在 Windows 环境中打包 EXE。

构建成功后，可以在对应 Actions 运行记录的 Artifacts 区域下载：

```text
GROMI-Desktop-Pet-Windows
```

如果推送 `v*` 格式的 tag，例如 `v0.1.1`，workflow 会自动创建 GitHub Release，并上传 `GROMI.exe`。

## 设置位置

应用设置保存在：

```text
%APPDATA%\GROMI Desktop Pet\settings.json
```

如果启动后没有看到窗口，可能是已有 GROMI 正在运行。可以先检查系统托盘，或退出旧进程后再打开。
