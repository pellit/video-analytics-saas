from abc import ABC, abstractmethod
from typing import Dict, Any
from ..domain.models import FrameData

class ISkillEvaluator(ABC):
    @abstractmethod
    def process_frame(self, data: FrameData): pass
    
    @abstractmethod
    def get_metrics(self) -> Dict[str, Any]: pass
