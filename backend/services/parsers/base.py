from abc import ABC, abstractmethod
from typing import Dict, Any

class LanguageParser(ABC):
    """
    Abstract base class for all language-specific parsers.
    Parsers are responsible for extracting classes, methods, module-level functions,
    imports, and comments from source code.
    """

    @abstractmethod
    def parse(self, code: str, filepath: str) -> Dict[str, Any]:
        """
        Parse source code and return its structural details.
        
        Args:
            code (str): The raw source code of the file.
            filepath (str): The absolute path or relative path of the file.
            
        Returns:
            Dict[str, Any]: A dictionary containing:
                - classes (list): Extracted classes and their methods.
                - functions (list): Extracted module-level functions.
                - imports (list): Extracted dependencies and imports.
        """
        pass
