# Web Crawler

一个用于下载文件的网络爬虫程序。

## 设置

1. 克隆仓库
2. 复制 `config.example.json` 为 `config.json`
3. 在 `config.json` 中填入你的配置信息：
   - base_url: 目标网站URL
   - auth.password: 认证密码
   - headers: 请求头信息
   - base_path: 基础路径
   - save_dir: 保存目录

## 使用方法

```bash
python Web_Crawler.py
```

## 功能

- 支持递归下载整个目录结构
- 自动跳过已下载的文件
- 显示下载进度
- 支持断点续传
- 完善的错误处理机制

## 注意事项

- 请确保在使用前正确配置 `config.json` 文件
- 敏感信息（如密码、URL等）都存储在 `config.json` 中，该文件已被添加到 `.gitignore`
- 可以参考 `config.example.json` 来了解配置文件的结构
