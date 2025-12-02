"""Spider discovery and validation for Scrapy projects."""

import os
from typing import Dict, List, Optional

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings


class SpiderLoader:
    """Loads and validates Scrapy spiders from a project."""

    def __init__(self, project_path: Optional[str] = None):
        """Initialize spider loader.

        Args:
            project_path: Path to Scrapy project. If None, auto-discovers from CWD.
        """
        self.project_path = project_path or os.getcwd()
        self._spiders: Optional[Dict[str, type]] = None
        self._settings = None

    def _discover_spiders(self) -> Dict[str, type]:
        """Discover all available spiders in the project.

        Returns:
            Dictionary mapping spider names to spider classes.
        """
        if self._spiders is not None:
            return self._spiders

        # Change to project directory to ensure Scrapy can find the project
        original_cwd = os.getcwd()
        try:
            os.chdir(self.project_path)
            settings = get_project_settings()
            self._settings = settings

            # Use CrawlerProcess to discover spiders
            process = CrawlerProcess(settings)
            spiders = {}
            # spider_loader.list() returns spider names (strings), not tuples
            for spider_name in process.spider_loader.list():
                spider_class = process.spider_loader.load(spider_name)
                spiders[spider_name] = spider_class

            self._spiders = spiders
            return spiders
        finally:
            os.chdir(original_cwd)

    def list_spiders(self) -> List[str]:
        """List all available spider names.

        Returns:
            List of spider names.
        """
        spiders = self._discover_spiders()
        return list(spiders.keys())

    def validate_spider(self, spider_name: str) -> bool:
        """Validate that a spider exists.

        Args:
            spider_name: Name of the spider to validate.

        Returns:
            True if spider exists, False otherwise.
        """
        spiders = self._discover_spiders()
        return spider_name in spiders

    def get_spider_class(self, spider_name: str):
        """Get the spider class for a given spider name.

        Args:
            spider_name: Name of the spider.

        Returns:
            Spider class.

        Raises:
            ValueError: If spider does not exist.
        """
        spiders = self._discover_spiders()
        if spider_name not in spiders:
            available = ", ".join(sorted(spiders.keys()))
            raise ValueError(
                f"Spider '{spider_name}' not found. Available spiders: {available}"
            )
        return spiders[spider_name]

    def get_settings(self):
        """Get Scrapy project settings.

        Returns:
            Scrapy settings dict.
        """
        if self._settings is None:
            self._discover_spiders()
        return self._settings
