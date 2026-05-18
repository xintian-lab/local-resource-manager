# Local Resource Manager

桌面端文件资源浏览器：选一个根文件夹后建立内存索引，用多列视图浏览目录结构，并按名称扩展名搜索；附带文件表格、主题切换与可配置的键盘快捷键。

**仓库：** [github.com/xintian-lab/local-resource-manager](https://github.com/xintian-lab/local-resource-manager)

## 运行环境

- Python 3.10+（建议与当前使用的版本一致）
- Windows（当前开发与测试平台）

## 本地运行

```bash
cd local-resource-manager
python -m venv .venv
.venv\Scripts\activate          # Linux / macOS: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## 依赖

参见 `requirements.txt`（核心是 **PySide6**）。

打包发布可使用 **PyInstaller**（可选安装项已写在 `requirements.txt` 中）。

## 数据与配置

| 用途 | 位置（源码运行） |
|------|------------------|
| SQLite 索引 | `app/data/file_index.db`（由 `.gitignore` 排除） |
| 用户设置（主题、快捷键等） | `app/config/settings.json`（默认不纳入版本库） |

克隆后首次启动会在本地生成上述文件；不要将含个人路径的 `settings.json` 提交进仓库。

## 项目布局（简要）

```
main.py           # 入口
app/ui/           # PySide 界面（主窗口、列视图、文件表）
app/core/         # 扫描、索引、搜索、路径与文件操作
```

## License

未定；后续可在仓库中添加 `LICENSE`。
