# 打包与分发（Windows）

1. 在项目目录双击 `build_package.bat`
2. 等待打包结束
3. 输出目录：`dist\OTC-Risk-App`
4. 把整个 `OTC-Risk-App` 文件夹发给别人
5. 对方双击 `OTC-Risk-App.exe` 即可运行

## 数据库

- `otc_gui.db` 会被复制到输出目录（如果存在）
- 想带上你的历史数据，就确保打包前项目目录里有 `otc_gui.db`

## 常见问题

- 首次运行较慢：属于正常现象
- 端口占用：关闭已有 Streamlit 实例后重试
- 杀软误报：可将输出目录加入信任列表

