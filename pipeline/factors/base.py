"""
因子系统基类

Factor 是原子计算单元，只关心自己的计算逻辑，不感知自己属于哪个组合。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import pandas as pd
import os


@dataclass
class FactorResult:
    """因子计算结果"""
    
    passed: bool  # 是否通过
    value: Optional[float] = None  # 计算出的值（用于展示/调试）
    detail: Optional[str] = None  # 详细说明


@dataclass
class Factor(ABC):
    """因子抽象基类"""
    
    id: str  # 因子 ID，如 "ma60_monotonic"
    label: str  # 因子名称，如 "MA60 单调不减"
    params: Dict[str, Any] = field(default_factory=dict)  # 默认参数
    
    def __post_init__(self):
        """从环境变量加载参数覆盖"""
        self._load_params_from_env()
    
    def _load_params_from_env(self):
        """
        从环境变量加载参数覆盖
        格式：FACTOR_<ID>_<PARAM>，如 FACTOR_MA60_MONOTONIC_MIN_CHANGE=2
        """
        prefix = f"FACTOR_{self.id.upper()}_"
        for key, default_value in self.params.items():
            env_key = prefix + key.upper()
            env_value = os.environ.get(env_key)
            if env_value is not None:
                # 根据默认值类型转换
                if isinstance(default_value, int):
                    self.params[key] = int(env_value)
                elif isinstance(default_value, float):
                    self.params[key] = float(env_value)
                elif isinstance(default_value, bool):
                    self.params[key] = env_value.lower() in ("true", "1", "yes")
                else:
                    self.params[key] = env_value
    
    def get_param(self, key: str, default: Any = None) -> Any:
        """获取参数值"""
        return self.params.get(key, default)
    
    @abstractmethod
    def compute(self, df: pd.DataFrame) -> FactorResult:
        """
        计算单只股票的因子结果
        
        Args:
            df: 单只股票的历史数据 DataFrame，按日期升序排列
                必须包含 date, close 列，可能包含 turn, pct_chg 等
        
        Returns:
            FactorResult: 因子计算结果
        """
        pass
    
    def compute_batch(self, all_data: pd.DataFrame) -> Dict[str, FactorResult]:
        """
        批量计算所有股票的因子结果（向量化）
        
        默认实现是逐股票计算，子类可以覆盖实现向量化版本以提高性能。
        
        Args:
            all_data: 所有股票数据 DataFrame，包含 code 列
        
        Returns:
            Dict[code, FactorResult]: 每只股票的因子结果
        """
        results = {}
        for code, group in all_data.groupby("code"):
            # 按日期升序
            stock_df = group.sort_values("date").reset_index(drop=True)
            results[code] = self.compute(stock_df)
        return results


def calculate_ma(df: pd.DataFrame, window: int, column: str = "close") -> pd.Series:
    """
    计算移动平均线
    
    Args:
        df: 数据 DataFrame
        window: 窗口大小
        column: 计算列名
    
    Returns:
        MA 序列
    """
    return df[column].rolling(window=window, min_periods=window).mean()


def calculate_ema(df: pd.DataFrame, span: int, column: str = "close") -> pd.Series:
    """
    计算指数移动平均线
    
    Args:
        df: 数据 DataFrame
        span: 跨度
        column: 计算列名
    
    Returns:
        EMA 序列
    """
    return df[column].ewm(span=span, adjust=False).mean()

