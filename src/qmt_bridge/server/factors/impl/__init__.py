"""因子实现模块包。

所有具体的因子计算实现放在此包中，按因子名分文件。
新增因子只需在此包中创建新文件并继承 ``Factor`` 基类即可。
"""

from .adjustment import AdjustmentFactor
from .chip import ChipDistributionFactor

__all__ = ["AdjustmentFactor", "ChipDistributionFactor"]
