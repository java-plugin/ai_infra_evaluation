"""运行时配置。

从仓库根目录的 ``.env`` 读取（该文件已被 .gitignore 忽略），
不允许把密钥写进任何会被提交的文件。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_base_url: str
    openai_model: str
    data_dir: Path
    report_dir: Path

    @property
    def llm_ready(self) -> bool:
        return bool(self.openai_api_key)


def get_settings() -> Settings:
    data_dir = Path(os.environ.get("AI_INFRA_DATA_DIR", ROOT / "data")).expanduser()
    report_dir = Path(os.environ.get("AI_INFRA_REPORT_DIR", ROOT / "reports")).expanduser()
    return Settings(
        openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
        openai_base_url=os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
        openai_model=os.environ.get("OPENAI_MODEL", "deepseek-chat"),
        data_dir=data_dir,
        report_dir=report_dir,
    )
