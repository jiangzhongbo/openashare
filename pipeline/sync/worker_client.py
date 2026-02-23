"""
Worker 客户端

HTTP 客户端，用于将筛选结果 POST 到 Cloudflare Worker。
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

import requests

from pipeline.screening.screener import ScreeningReport


logger = logging.getLogger(__name__)


# 默认配置
DEFAULT_WORKER_URL = "http://localhost:8787"
DEFAULT_TIMEOUT = 30


@dataclass
class WorkerResponse:
    """Worker 响应"""
    success: bool
    status_code: int
    message: str
    data: Optional[Dict[str, Any]] = None


class WorkerClient:
    """Worker HTTP 客户端"""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """
        初始化客户端
        
        Args:
            base_url: Worker URL，默认从 WORKER_URL 环境变量获取
            token: 认证 token，默认从 WORKER_WRITE_TOKEN 环境变量获取
            timeout: 请求超时秒数
        """
        self.base_url = base_url or os.getenv("WORKER_URL", DEFAULT_WORKER_URL)
        self.token = token or os.getenv("WORKER_WRITE_TOKEN", "")
        self.timeout = timeout
        
        # 移除末尾斜杠
        self.base_url = self.base_url.rstrip("/")
    
    def _make_headers(self) -> Dict[str, str]:
        """构建请求头"""
        headers = {
            "Content-Type": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    def ingest(self, report: ScreeningReport) -> WorkerResponse:
        """
        发送筛选结果到 Worker
        
        Args:
            report: 筛选报告
        
        Returns:
            WorkerResponse
        """
        url = f"{self.base_url}/api/ingest"
        payload = report.to_ingest_payload()
        
        logger.info(
            f"Sending {len(report.results)} results to {url} "
            f"(combinations: {report.combination_counts})"
        )
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._make_headers(),
                timeout=self.timeout,
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Ingest successful: {data}")
                return WorkerResponse(
                    success=True,
                    status_code=200,
                    message="OK",
                    data=data,
                )
            elif response.status_code == 403:
                logger.error("Ingest failed: unauthorized (403)")
                return WorkerResponse(
                    success=False,
                    status_code=403,
                    message="Unauthorized: invalid or missing token",
                )
            else:
                logger.error(f"Ingest failed: {response.status_code} - {response.text}")
                return WorkerResponse(
                    success=False,
                    status_code=response.status_code,
                    message=response.text,
                )
                
        except requests.exceptions.Timeout:
            logger.error(f"Ingest timeout after {self.timeout}s")
            return WorkerResponse(
                success=False,
                status_code=0,
                message=f"Timeout after {self.timeout}s",
            )
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Ingest connection error: {e}")
            return WorkerResponse(
                success=False,
                status_code=0,
                message=f"Connection error: {e}",
            )
        except Exception as e:
            logger.error(f"Ingest error: {e}")
            return WorkerResponse(
                success=False,
                status_code=0,
                message=str(e),
            )
    
    def health_check(self) -> bool:
        """
        检查 Worker 是否可用
        
        Returns:
            是否可用
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/screening/latest",
                timeout=5,
            )
            return response.status_code == 200
        except Exception:
            return False

