"""
字体配置工具模块

支持通过环境变量配置中文字体路径，支持多个备选路径。

环境变量:
    CHINESE_FONT_PATHS: 逗号分隔的字体文件路径列表，按优先级排序
        例如: /root/font/SiYuanHeiTi-Regular/SourceHanSansSC-Regular-2.otf,/root/font/QingNiaoHuaGuangJianMeiHei/QingNiaoHuaGuangJianMeiHei-2.ttf

    CHINESE_FONT_PATH: (兼容旧配置) 单个字体文件路径
"""

import os
from pathlib import Path
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class FontConfig:
    """字体配置管理类"""

    # 默认字体搜索路径
    DEFAULT_FONT_PATHS = [
        "/home/ubuntu/font/SiYuanHeiTi-Regular/SourceHanSansSC-Regular-2.otf",
        "/root/font/SiYuanHeiTi-Regular/SourceHanSansSC-Regular-2.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    ]

    _cached_font_path: Optional[Path] = None

    @classmethod
    def get_configured_paths(cls) -> List[str]:
        """
        获取配置的字体路径列表

        优先级:
        1. CHINESE_FONT_PATHS 环境变量（逗号分隔）
        2. CHINESE_FONT_PATH 环境变量（单个路径，兼容旧配置）
        3. 默认路径列表

        Returns:
            字体路径列表
        """
        # 优先使用 CHINESE_FONT_PATHS（支持多路径）
        paths_env = os.getenv("CHINESE_FONT_PATHS", "").strip()
        if paths_env:
            paths = [p.strip() for p in paths_env.split(",") if p.strip()]
            if paths:
                return paths

        # 兼容旧的 CHINESE_FONT_PATH 配置
        single_path = os.getenv("CHINESE_FONT_PATH", "").strip()
        if single_path:
            return [single_path]

        # 使用默认路径
        return cls.DEFAULT_FONT_PATHS

    @classmethod
    def find_font(cls, use_cache: bool = True) -> Optional[Path]:
        """
        查找可用的中文字体文件

        Args:
            use_cache: 是否使用缓存的结果

        Returns:
            找到的字体文件路径，如果都不存在则返回 None
        """
        if use_cache and cls._cached_font_path is not None:
            if cls._cached_font_path.exists():
                return cls._cached_font_path
            # 缓存的路径不存在了，清除缓存
            cls._cached_font_path = None

        configured_paths = cls.get_configured_paths()

        for path_str in configured_paths:
            path = Path(path_str)
            if path.exists() and path.is_file():
                logger.info(f"找到可用字体: {path}")
                cls._cached_font_path = path
                return path
            else:
                logger.debug(f"字体文件不存在: {path}")

        logger.warning(f"所有配置的字体路径都不存在: {configured_paths}")
        return None

    @classmethod
    def get_font_format(cls, font_path: Path) -> str:
        """
        根据字体文件后缀获取 CSS font-format

        Args:
            font_path: 字体文件路径

        Returns:
            CSS font-format 字符串
        """
        return {
            '.ttf': 'truetype',
            '.otf': 'opentype',
            '.woff': 'woff',
            '.woff2': 'woff2',
            '.ttc': 'truetype',
        }.get(font_path.suffix.lower(), 'truetype')

    @classmethod
    def clear_cache(cls) -> None:
        """清除缓存的字体路径"""
        cls._cached_font_path = None
