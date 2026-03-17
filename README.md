# astrbot-plugin-browser

基于 [Crawl4AI](https://github.com/unclecode/crawl4ai) 无头浏览器的增强网页搜索与全文抓取插件。

## 功能

为 AstrBot 的 LLM 提供两个自动调用的工具（Function Tool）：

| 工具名 | 功能 | 场景 |
|--------|------|------|
| `web_search_enhanced` | 通过无头浏览器执行搜索引擎检索 | 用户提问需要搜索时自动触发 |
| `web_browse` | 打开指定 URL，渲染 JS，提取全文 Markdown | 需要精读某个网页时触发 |

LLM 可以组合使用：**先搜索 → 挑选有价值的链接 → 打开精读 → 综合回答**，类似 Claude/Perplexity 的深度搜索体验。

## 前置依赖

⚠️ 本插件需要 **Playwright + Chromium 浏览器**，AstrBot 的 `pip install` 只能装 Python 包，浏览器需要手动安装。

### 源码部署

```bash
pip install crawl4ai
crawl4ai-setup
playwright install chromium
playwright install-deps chromium  # 安装 Chromium 的系统依赖
```

### Docker 部署

进入 AstrBot 容器后执行同样的命令，或自定义 Dockerfile：

```dockerfile
FROM soulter/astrbot:latest
RUN pip install crawl4ai \
    && crawl4ai-setup \
    && playwright install chromium \
    && playwright install-deps chromium
```

## 安装插件

1. 将本文件夹放入 `<AstrBot>/data/plugins/astrbot-plugin-browser/`
2. 重启 AstrBot 或在 WebUI 插件管理中热重载
3. 确保插件状态为"已启用"

## 验证

在任意接入的聊天平台对 AstrBot 说：

> 帮我搜索一下最近 AI 编程工具的发展趋势

如果一切正常，LLM 会自动调用 `web_search_enhanced` 工具，返回搜索结果后可能进一步调用 `web_browse` 精读某些页面，最后给出综合回答。

## 注意事项

- Chromium 大约占用 200-500MB 内存，建议 VPS 至少 2GB
- 每次抓取都会启动一个无头浏览器实例，如果并发量大需注意资源
- 网页内容会被截断到 8000 字符以避免撑爆 LLM 上下文窗口
- 搜索优先使用 Google，失败时 fallback 到 Bing
