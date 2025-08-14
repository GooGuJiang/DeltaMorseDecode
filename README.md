# DeltaMorseDecode - 三角洲行动摩斯电码数字解码器

三角洲行动摩斯电码数字解码器

![示例图](https://raw.githubusercontent.com/GooGuJiang/DeltaMorseDecode/refs/heads/main/image/img.webp)

## GitHub Actions 自动构建

仓库内置 GitHub Actions 工作流，会在每次提交或 Pull Request 时自动安装依赖并使用 PyInstaller 将 `morse_decoder_optimized.py` 编译为 Windows 可执行文件。构建完成后，可执行文件会作为工作流产物提供下载。
