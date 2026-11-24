# Coloring Pixels Mouse Assistant

Windows 下的 Coloring Pixels 鼠标填色助手。它从本机已安装游戏的关卡元数据读取目标颜色，再发送键鼠操作。支持自动平移、按颜色填充、蛇形逐格填充以及按已保存进度续填。

## 新电脑安装

1. 通过 Steam 安装 Coloring Pixels，并至少启动一次。
2. 安装 [Python 3.14 64 位](https://www.python.org/downloads/windows/)，安装时勾选 Add Python to PATH。
3. 下载 Release 里的 ZIP 并解压，双击 `Launch.bat`。首次运行联网安装锁定版本的依赖到项目自己的 `.venv`。
4. 如果 Steam 库没被找到，在 PowerShell 设置本机安装目录再启动：

   ```powershell
   $env:COLORING_PIXELS_GAME_DIR = 'E:\SteamLibrary\steamapps\common\Coloring Pixels'
   .\Launch.bat
   ```

## 填色流程

1. 在游戏里重新进入关卡，保留初始缩放和位置。辅助器中选中同一关卡。
2. 点「已重新进图 · 重置视角」，先「试填一格」。整图开始后工具会接管鼠标。如果游戏选色受到「隐藏已完成颜色」影响，可以在退出游戏后用工具内的开关切换，再启动游戏。
3. 选择按颜色或蛇形填充，点「开始整图」。Esc 或「停止」可中止。程序会读取游戏已经保存的颜色，跳过填对的格子。
4. 整图动作结束后等待游戏自动保存，并逐格核对。默认结束任务并保留窗口。可选复查通过后关机，60 秒内可取消。保持关卡打开直到复查结束。

游戏更新后如果关卡数据格式变化，需要重新验证。New Game+ 的特殊存档当前不支持。辅助器通过当前选定的关卡和初始视角计算坐标，启动前需确认游戏里打开的是同一张图。

## 历史版本

| 路径 | 功能 |
| --- | --- |
| `history/slow-manual` | 双角手动标定，保守逐格点击 |
| `history/auto-pan` | 自动平移、手动标定备选、按已保存进度跳格 |
| `history/serpentine` | 蛇形遍历、自动定位、复查和可选关机 |
| 仓库根目录 | 复查默认开启，复查后的动作独立选择 |

历史版本分别从所在目录的 `Launch.bat` 启动。发布副本统一改用 Steam 自动发现、独立 Python 环境和锁定依赖。
