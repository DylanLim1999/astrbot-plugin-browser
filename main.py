"""
AstrBot 增强搜索插件 - 基于 Crawl4AI 的无头浏览器搜索与网页抓取
为 AstrBot 提供两个 LLM Tool：
  1. web_search_enhanced - 搜索引擎检索，返回结构化结果列表
  2. web_browse - 打开指定 URL，提取完整网页内容（Markdown）
"""

import asyncio
import re
import traceback

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

# ============================================================
# Tool 1: 增强网页搜索
# ============================================================

@dataclass
class WebSearchEnhancedTool(FunctionTool[AstrAgentContext]):
    """通过无头浏览器执行搜索引擎检索，返回搜索结果列表。"""

    name: str = "web_search_enhanced"
    description: str = (
        "Search the web using a headless browser. "
        "Returns a list of search results with titles, URLs, and snippets. "
        "Use this when you need to find information on the internet."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string.",
                },
                "max_results": {
                    "type": "number",
                    "description": "Maximum number of results to return (default 5, max 10).",
                },
            },
            "required": ["query"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        query = kwargs.get("query", "")
        max_results = min(int(kwargs.get("max_results", 5)), 10)

        if not query.strip():
            return "Error: search query cannot be empty."

        logger.info(f"[BrowserPlugin] Searching: {query}")

        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

            browser_config = BrowserConfig(
                headless=True,
                text_mode=True,
                verbose=False,
            )

            # 使用 Google 搜索
            import urllib.parse
            search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}&num={max_results + 5}&hl=en"

            crawler_config = CrawlerRunConfig(
                wait_for="css:div#search",
                page_timeout=30000,
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=search_url, config=crawler_config)

                if not result.success:
                    # Fallback: 尝试 Bing
                    logger.warning("[BrowserPlugin] Google search failed, trying Bing...")
                    search_url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(query)}&count={max_results + 5}"
                    crawler_config = CrawlerRunConfig(
                        wait_for="css:ol#b_results",
                        page_timeout=30000,
                    )
                    result = await crawler.arun(url=search_url, config=crawler_config)

                if not result.success:
                    return f"Search failed: {result.error_message}"

                # 从 markdown 中提取搜索结果
                markdown = result.markdown or ""
                parsed = _parse_search_results(markdown, max_results)

                if not parsed:
                    # 如果解析失败，返回原始 markdown 的前 3000 字符
                    return f"Search results for '{query}':\n\n{markdown[:3000]}"

                output_parts = [f"Search results for '{query}':\n"]
                for i, item in enumerate(parsed, 1):
                    output_parts.append(
                        f"{i}. **{item['title']}**\n"
                        f"   URL: {item['url']}\n"
                        f"   {item['snippet']}\n"
                    )

                return "\n".join(output_parts)

        except ImportError:
            return (
                "Error: crawl4ai is not installed. "
                "Please run: pip install crawl4ai && crawl4ai-setup && playwright install chromium"
            )
        except Exception as e:
            logger.error(f"[BrowserPlugin] Search error: {traceback.format_exc()}")
            return f"Search error: {str(e)}"


# ============================================================
# Tool 2: 网页全文抓取
# ============================================================

@dataclass
class WebBrowseTool(FunctionTool[AstrAgentContext]):
    """通过无头浏览器打开 URL，渲染页面后提取干净的 Markdown 内容。"""

    name: str = "web_browse"
    description: str = (
        "Open a URL with a headless browser, render JavaScript, and extract "
        "the full page content as clean Markdown text. "
        "Use this when you need to read the detailed content of a specific web page."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL of the web page to open and read.",
                },
                "extract_only_main": {
                    "type": "boolean",
                    "description": "If true, try to extract only the main content (remove nav/footer/ads). Default true.",
                },
            },
            "required": ["url"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        url = kwargs.get("url", "")
        extract_only_main = kwargs.get("extract_only_main", True)

        if not url.strip():
            return "Error: URL cannot be empty."

        # 基础 URL 验证
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        logger.info(f"[BrowserPlugin] Browsing: {url}")

        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
            from crawl4ai import DefaultMarkdownGenerator, PruningContentFilter

            browser_config = BrowserConfig(
                headless=True,
                text_mode=True,
                verbose=False,
            )

            # 配置 Markdown 生成器
            md_generator_kwargs = {}
            if extract_only_main:
                md_generator_kwargs["content_filter"] = PruningContentFilter()

            crawler_config = CrawlerRunConfig(
                markdown_generator=DefaultMarkdownGenerator(**md_generator_kwargs),
                page_timeout=30000,
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=url, config=crawler_config)

                if not result.success:
                    return f"Failed to load page: {result.error_message}"

                # 优先使用过滤后的 markdown
                content = ""
                if hasattr(result, "markdown"):
                    md = result.markdown
                    if hasattr(md, "fit_markdown") and md.fit_markdown:
                        content = md.fit_markdown
                    elif hasattr(md, "raw_markdown") and md.raw_markdown:
                        content = md.raw_markdown
                    elif isinstance(md, str):
                        content = md

                if not content:
                    content = result.html[:5000] if result.html else "No content extracted."

                # 截断过长内容，避免塞爆 LLM 上下文
                max_len = 8000
                if len(content) > max_len:
                    content = content[:max_len] + f"\n\n... [Content truncated, total {len(content)} characters]"

                title = ""
                if hasattr(result, "metadata") and result.metadata:
                    title = result.metadata.get("title", "")

                header = f"## Page: {title or url}\n\n" if title else f"## Page: {url}\n\n"
                return header + content

        except ImportError:
            return (
                "Error: crawl4ai is not installed. "
                "Please run: pip install crawl4ai && crawl4ai-setup && playwright install chromium"
            )
        except Exception as e:
            logger.error(f"[BrowserPlugin] Browse error: {traceback.format_exc()}")
            return f"Browse error: {str(e)}"


# ============================================================
# 搜索结果解析辅助函数
# ============================================================

def _parse_search_results(markdown: str, max_results: int = 5) -> list[dict]:
    """从搜索引擎返回的 Markdown 中解析结构化结果。"""
    results = []

    # 模式1: Markdown 链接格式 [title](url)
    link_pattern = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')
    seen_urls = set()

    for match in link_pattern.finditer(markdown):
        title = match.group(1).strip()
        url = match.group(2).strip()

        # 过滤掉搜索引擎自身的链接和无意义的链接
        if any(skip in url.lower() for skip in [
            "google.com/search", "google.com/advanced",
            "bing.com/search", "bing.com/aclick",
            "accounts.google", "support.google",
            "maps.google", "translate.google",
            "#", "javascript:",
        ]):
            continue

        if url in seen_urls:
            continue
        if len(title) < 5:
            continue

        seen_urls.add(url)

        # 尝试提取 snippet (链接后面的文本)
        pos = match.end()
        remaining = markdown[pos:pos + 500]
        snippet_lines = remaining.strip().split("\n")
        snippet = ""
        for line in snippet_lines[:3]:
            line = line.strip()
            if line and not line.startswith("[") and not line.startswith("#"):
                snippet = line[:200]
                break

        results.append({
            "title": title,
            "url": url,
            "snippet": snippet or "(no snippet)",
        })

        if len(results) >= max_results:
            break

    return results


# ============================================================
# 插件主类
# ============================================================

@register(
    "astrbot-plugin-browser",
    "Dylan",
    "Enhanced web search & browsing via headless browser (Crawl4AI)",
    "1.0.0",
    "https://github.com/your-repo/astrbot-plugin-browser",
)
class BrowserPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

        # 注册 Tool 到 AstrBot，LLM 在对话中会自动发现和调用
        self.context.add_llm_tools(
            WebSearchEnhancedTool(),
            WebBrowseTool(),
        )
        logger.info("[BrowserPlugin] Registered web_search_enhanced and web_browse tools.")

    async def terminate(self):
        """插件卸载时清理"""
        logger.info("[BrowserPlugin] Plugin terminated.")
