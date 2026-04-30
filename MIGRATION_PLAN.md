# Tkinter+ttkbootstrap → PyQt6 迁移计划

## 一、项目现状分析

### 1.1 代码规模统计

| 模块 | 文件数 | 代码行数 | 可复用度 |
|------|--------|----------|----------|
| core | 8 | ~800 | **90%** (纯逻辑，无UI依赖) |
| services | 3 | ~400 | **95%** (无UI依赖) |
| gui | 7 | ~2600 | **0%** (需完全重写) |
| i18n | 2 | ~300 | **90%** (字符串资源) |
| **总计** | ~20 | ~4100 | **~60%** |

### 1.2 核心功能清单

1. **主菜单 (Main Menu)**
   - [x] 启动 Blender
   - [x] 创建项目
   - [x] 检查更新
   - [x] 刷新按钮 (刷新所有模块)
   - [x] 设置窗口
   - [x] 帮助窗口
   - [x] Blender 版本显示
   - [x] BM 版本显示

2. **插件管理 (Addon Management)**
   - [x] 添加插件
   - [x] 刷新插件列表
   - [x] 版本选择下拉框
   - [x] 搜索功能
   - [x] 插件树形列表 (显示名称、版本、状态)
   - [x] 右键菜单 (删除、启用、停用、查看信息)
   - [x] 拖拽导入 (移除)

3. **项目管理 (Project Management)**
   - [x] 浏览项目目录
   - [x] 添加项目
   - [x] 刷新项目列表
   - [x] 项目树形结构显示
   - [x] 右键菜单 (重命名、打开、移动、删除、导出)
   - [x] 拖拽排序 (移除)

4. **渲染管理 (Render Management)**
   - [x] 浏览渲染目录
   - [x] 导入渲染文件
   - [x] 刷新渲染列表
   - [x] 渲染文件表格 (文件名、大小、分辨率、日期)
   - [x] 打开/预览渲染
   - [x] 删除渲染
   - [x] 渲染笔记功能
   - [x] 拖拽导入 (移除)

5. **版本管理 (Version Management)**
   - [x] OS/架构选择
   - [x] 获取版本列表
   - [x] 下载安装
   - [x] 进度显示
   - [x] 取消下载
   - [x] 释放说明查看
   - [x] 已安装版本列表
   - [x] 启动/设为主版本/删除

6. **系统集成**
   - [x] 系统托盘 (最小化到托盘)
   - [x] Windows 暗色模式
   - [x] 窗口恢复钩子
   - [x] 国际化 (中/英)
   - [x] 日志显示

---

## 二、技术栈对比

| 对比项 | Tkinter+ttkbootstrap | PyQt6 |
|--------|---------------------|-------|
| 许可证 | BSD | GPL/LGPL |
| 包大小 | ~5MB | ~15MB |
| UI现代化 | 一般 | 好 |
| 布局系统 | pack/grid | QLayout (更强大) |
| 事件系统 | callback | signal/slot |
| 拖拽支持 | tkinterdnd2 | 需自定义实现 |
| 文档生态 | 一般 | 丰富 |

---

## 三、分步迁移计划

### 阶段一：基础设施搭建 (预计 3-5 天)

#### 1.1 环境准备

- [ ] 创建新目录 `source/gui_qt/`
- [ ] 安装依赖: `pip install PyQt6 PyQt6-stubs`
- [ ] 安装可选依赖: `pip install QDarkstyle` (暗色主题)
- [ ] 创建项目入口 `source/main_qt.py`

#### 1.2 主窗口框架

```
source/gui_qt/
├── __init__.py
├── main_window.py       # 主窗口类
├── app.py               # 应用单例
├── base_tab.py          # 标签页基类
├── widgets/             # 自定义组件
│   ├── __init__.py
│   ├── buttons.py       # 按钮组件
│   ├── treeviews.py     # 树形组件
│   └── dialogs.py       # 对话框组件
├── tabs/                # 标签页实现
│   ├── __init__.py
│   ├── main_menu.py
│   ├── addon.py
│   ├── project.py
│   ├── render.py
│   ├── version.py
│   └── logs.py
└── dialogs/             # 弹窗对话框
    ├── __init__.py
    ├── settings.py
    ├── project_create.py
    └── help.py
```

#### 1.3 核心类设计

**MainWindow 骨架** (`source/gui_qt/main_window.py`):
```python
from PyQt6.QtWidgets import QMainWindow, QTabWidget, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal

class MainWindow(QMainWindow):
    # 信号定义
    signal_refresh_all = pyqtSignal()
    signal_update_blender_version = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self.data = DataManager()
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("Blender Manager")
        self.setGeometry(100, 100, 800, 550)
        # 创建标签页
        # 创建系统托盘
```

#### 1.4 日志系统适配

```python
# source/gui_qt/utils/log_redirector.py
class LogRedirector:
    def __init__(self, text_edit: QTextEdit):
        self.text_edit = text_edit

    def write(self, text):
        # 在主线程中更新UI
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText(text)
        self.text_edit.setTextCursor(cursor)
        self.text_edit.ensureCursorVisible()
```

#### 1.5 国际化适配

```python
# source/gui_qt/i18n_qt.py
from PyQt6.QtCore import QObject, pyqtSignal

class Translator(QObject):
    language_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._ = i18n._  # 复用现有翻译函数

    def translate(self, text):
        return self._(text)
```

---

### 阶段二：主菜单标签页迁移 (预计 2-3 天)

#### 2.1 基础布局

**原 Tkinter 布局**:
```
[左侧按钮区]     [右侧信息区]
- Launch       [Blender版本标签]
- Create       [BM版本标签]
- Check Update [最近项目列表]
- Cancel       [最近项目右键菜单]
- Progress     [进度条+标签]
- Refresh      []
- Settings     []
- Help         []
```

**PyQt6 实现**:
```python
# source/gui_qt/tabs/main_menu.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget,
    QProgressBar, QFrame
)
from PyQt6.QtCore import Qt

class MainMenuTab(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._init_ui()

    def _init_ui(self):
        main_layout = QHBoxLayout()
        # 左侧按钮区
        left_widget = self._create_button_panel()
        main_layout.addWidget(left_widget, 1)
        # 右侧信息区
        right_widget = self._create_info_panel()
        main_layout.addWidget(right_widget, 3)
        self.setLayout(main_layout)

    def _create_button_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        # 按钮: Launch, Create, Check Updates, Cancel, Refresh, Settings, Help
        # 进度条
        # 标签
        return widget

    def _create_info_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        # Blender版本标签
        # BM版本标签
        # 最近项目列表
        return widget
```

#### 2.2 功能实现清单

- [ ] 启动 Blender 按钮 (调用 subprocess)
- [ ] 创建项目按钮 (打开 ProjectWindow)
- [ ] 检查更新按钮
- [ ] 取消下载按钮 + 进度条
- [ ] 刷新按钮 (信号触发)
- [ ] 设置按钮 (打开 SettingsDialog)
- [ ] 帮助按钮 (打开 HelpDialog)
- [ ] Blender 版本标签 (点击事件)
- [ ] BM 版本标签
- [ ] 最近项目列表 (QListWidget)
- [ ] 项目右键菜单 (打开、删除、显示时间)

#### 2.3 关键代码映射

| Tkinter | PyQt6 | 备注 |
|---------|-------|------|
| `ttkb.Button` | `QPushButton` | `clicked.connect(callback)` |
| `ttkb.Label` | `QLabel` | 直接替换 |
| `ttkb.Progressbar` | `QProgressBar` | `setValue(int)` |
| `ttkb.Frame` | `QWidget` | 配合 QLayout |
| `tk.StringVar` | `pyqtSignal` + 属性 | 信号机制 |
| `after()` | `QTimer.singleShot()` | 延迟执行 |

---

### 阶段三：插件管理标签页迁移 (预计 3-4 天)

#### 3.1 UI 结构

```
[目录栏] [搜索框] [版本选择] [按钮栏]
[插件树形列表]
  名称 | 版本 | 状态
[状态栏]
```

#### 3.2 功能实现

- [ ] 目录路径显示 (QLineEdit + QLabel)
- [ ] 浏览按钮 (QFileDialog)
- [ ] 添加插件按钮
- [ ] 刷新按钮
- [ ] 搜索框 (QLineEdit + 过滤器)
- [ ] 版本选择下拉框 (QComboBox)
- [ ] 插件树形列表 (QTreeWidget)
  - 列: 插件名、版本、状态
  - 双击打开
  - 右键菜单 (删除、启用、停用、查看信息)
- [ ] 启用/停用插件功能 (调用 Blender --background --python)

#### 3.3 树形组件实现

```python
# source/gui_qt/widgets/addon_tree.py
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
from PyQt6.QtCore import Qt

class AddonTreeWidget(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumns()

    def setColumns(self):
        self.setHeaderLabels(["Plugin Name", "Version", "Status"])
        self.setColumnWidth(0, 250)
        self.setColumnWidth(1, 100)
        self.setColumnWidth(2, 100)

    def add_item(self, name, version, status):
        item = QTreeWidgetItem([name, version, status])
        self.addTopLevelItem(item)
```

---

### 阶段四：项目管理标签页迁移 (预计 3-4 天)

#### 4.1 UI 结构

```
[目录路径] [浏览按钮] [添加按钮] [刷新按钮]
[项目树形列表]
  - 文件夹
    - project.blend
  - 文件夹
[状态栏]
```

#### 4.2 功能实现

- [ ] 项目目录路径显示
- [ ] 浏览按钮 (QFileDialog + 直接打开文件夹)
- [ ] 添加项目按钮
- [ ] 刷新按钮
- [ ] 项目树形列表 (QTreeWidget)
  - 显示文件夹和 .blend 文件
  - 双击打开项目
  - 右键菜单
- [ ] 项目操作
  - 重命名 (QInputDialog)
  - 打开 (subprocess 调用 Blender)
  - 移动 (QFileDialog)
  - 删除 (QMessageBox 确认)
  - 导出 (支持 .blend, .obj, .fbx)

#### 4.3 项目树实现

```python
# source/gui_qt/widgets/project_tree.py
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
from PyQt6.QtGui import QFileSystemModel

class ProjectTreeWidget(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_model = QFileSystemModel()
        self.setModel(self.file_model)
        # 配置显示列
```

---

### 阶段五：渲染管理标签页迁移 (预计 2-3 天)

#### 5.1 UI 结构

```
[目录路径] [浏览按钮] [导入按钮] [刷新按钮]
[渲染表格]
  文件名 | 大小 | 分辨率 | 日期
[预览区]
[笔记区] [保存按钮]
```

#### 5.2 功能实现

- [ ] 渲染目录路径
- [ ] 浏览按钮 (打开文件夹 / 选择目录)
- [ ] 导入渲染文件
- [ ] 刷新按钮
- [ ] 渲染表格 (QTableWidget)
  - 列: 文件名、大小、分辨率、修改日期
  - 双击预览
  - 右键删除
- [ ] 图像预览 (QLabel + QPixmap)
- [ ] 笔记功能 (QTextEdit + 保存按钮)

#### 5.3 图像预览实现

```python
def load_preview(self, file_path):
    pixmap = QPixmap(file_path)
    scaled = pixmap.scaled(
        self.preview_label.size(),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation
    )
    self.preview_label.setPixmap(scaled)
```

---

### 阶段六：版本管理标签页迁移 (预计 3-4 天)

#### 6.1 UI 结构

```
[OS选择] [架构选择] [获取版本按钮]
[版本列表表格]
  版本 | 日期 | 大小 | 类型
[安装按钮] [进度条]
[已安装版本列表]
  [启动] [设为默认] [删除]
```

#### 6.2 功能实现

- [ ] OS 下拉框 (Windows/Mac/Linux)
- [ ] 架构下拉框 (x64/arm64)
- [ ] 获取版本按钮 (requests 爬取 blender.org)
- [ ] 版本列表表格
- [ ] 安装按钮 + 进度条 + 取消按钮
- [ ] 下载功能 (requests + 流式写入 + 进度更新)
- [ ] 解压功能 (zipfile)
- [ ] 已安装版本列表
- [ ] 启动按钮
- [ ] 设为默认版本
- [ ] 删除版本

#### 6.3 进度更新实现

```python
def download_with_progress(url, save_path, progress_callback):
    response = requests.get(url, stream=True)
    total = int(response.headers.get('content-length', 0))
    downloaded = 0
    with open(save_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    progress = int(downloaded / total * 100)
                    progress_callback(progress)
```

---

### 阶段七：对话框迁移 (预计 3-4 天)

#### 7.1 设置窗口

```python
# source/gui_qt/dialogs/settings.py
from PyQt6.QtWidgets import QDialog, QTabWidget, QVBoxLayout
from PyQt6.QtCore import Qt

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(750, 550)
        layout = QVBoxLayout()
        tabs = QTabWidget()
        # 路径设置
        # 外观设置
        # 通用设置
        # Blender设置
        layout.addWidget(tabs)
        self.setLayout(layout)
```

- [ ] 路径设置标签页 (默认路径配置)
- [ ] 外观设置标签页 (主题、字体)
- [ ] 通用设置标签页 (语言、托盘等)
- [ ] Blender设置标签页 (导入/导出配置)

#### 7.2 项目创建窗口

- [ ] 项目名称输入
- [ ] 保存位置选择
- [ ] 参考图像选择
- [ ] 基础网格选择
- [ ] 启动文件设置

#### 7.3 帮助窗口

- [ ] 文档显示 (QTextBrowser)
- [ ] 链接按钮 (QDesktopServices.openUrl)

---

### 阶段八：系统集成 (预计 2-3 天)

#### 8.1 系统托盘

```python
# source/gui_qt/utils/tray.py
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap
from PIL import Image

class TrayManager:
    def __init__(self, parent):
        self.tray = QSystemTrayIcon(parent)
        # 加载图标
        # 创建菜单
        # 连接信号

    def create_menu(self):
        menu = QMenu()
        show_action = menu.addAction("Show Blender Manager")
        exit_action = menu.addAction("Exit")
        return menu
```

- [ ] 托盘图标显示
- [ ] 左键点击显示窗口
- [ ] 右键菜单 (显示/退出)
- [ ] 最小化到托盘

#### 8.2 Windows 暗色模式

- [ ] 检测 Windows 版本
- [ ] 调用 Windows API 设置暗色模式
- [ ] 或使用 QDarkstyle 库

#### 8.3 窗口恢复钩子 (简化版)

```python
def showNormal(self):
    super().showNormal()
    self.raise_()
    self.activateWindow()
```

---

### 阶段九：测试与优化 (预计 3-5 天)

#### 9.1 功能测试

- [ ] 主菜单所有按钮功能
- [ ] 插件管理 CRUD 操作
- [ ] 项目管理 CRUD 操作
- [ ] 渲染管理 CRUD 操作
- [ ] 版本管理安装/删除
- [ ] 设置窗口保存/加载
- [ ] 系统托盘
- [ ] 国际化切换

#### 9.2 兼容性测试

- [ ] Windows 10
- [ ] Windows 11

#### 9.3 性能优化

- [ ] 大列表虚拟滚动 (QAbstractItemView)
- [ ] 延迟加载
- [ ] 后台线程处理耗时操作

#### 9.4 打包测试

- [ ] PyInstaller 打包
- [ ] 生成 .exe 文件
- [ ] 验证运行

---

## 四、代码复用策略

### 4.1 可直接复用的模块

```
source/core/           → 保持不变
source/services/      → 保持不变
source/i18n/          → 轻微修改 (添加 Qt 信号)
source/gui_qt/        → 新建
```

### 4.2 需要适配的模块

```python
# 示例: 适配现有 ConfigManager
from core import ConfigManager

class QtConfigManager:
    def __init__(self):
        self._config = ConfigManager()

    def get(self, key, default=None):
        return self._config.get(key, default)

    def save_setting(self, key, value):
        self._config.save_setting(key, value)
```

---

## 五、验收标准

| 类别 | 标准 |
|------|------|
| 功能完整性 | 所有原有功能可用 |
| UI一致性 | 布局与交互方式一致 |
| 性能 | 启动 < 3秒，响应 < 100ms |
| 兼容性 | Windows 10/11 正常 |
| 打包 | 生成可运行 .exe |

---

## 六、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| 暗色模式兼容性 | 中 | 使用 QDarkstyle |
| 第三方库支持 | 低 | requests/Pillow 完全兼容 |
| 国际化延迟 | 中 | 使用信号同步 UI |
| 打包体积 | 低 | PyQt6 约 15MB 可接受 |

---

## 七、时间估算

| 阶段 | 预计时间 | 累计 |
|------|----------|------|
| 阶段一 | 3-5 天 | 3-5 天 |
| 阶段二 | 2-3 天 | 5-8 天 |
| 阶段三 | 3-4 天 | 8-12 天 |
| 阶段四 | 3-4 天 | 11-16 天 |
| 阶段五 | 2-3 天 | 13-19 天 |
| 阶段六 | 3-4 天 | 16-23 天 |
| 阶段七 | 3-4 天 | 19-27 天 |
| 阶段八 | 2-3 天 | 21-30 天 |
| 阶段九 | 3-5 天 | 24-35 天 |

**总计: 约 4-5 周**