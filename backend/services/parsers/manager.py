from pathlib import Path
from typing import Optional
from backend.services.parsers.base import LanguageParser
from backend.services.parsers.python import PythonParser
from backend.services.parsers.javascript import JavaScriptParser
from backend.services.parsers.java import JavaParser

class ParserManager:
    """
    Registry for all language-specific parsers.
    Maps file extensions to parser instances and exposes check utilities.
    """

    _parsers = {
        ".py": PythonParser(),
        ".js": JavaScriptParser(),
        ".jsx": JavaScriptParser(),
        ".ts": JavaScriptParser(),
        ".tsx": JavaScriptParser(),
        ".java": JavaParser(),
    }

    @classmethod
    def get_parser(cls, filepath: str) -> Optional[LanguageParser]:
        """
        Get the parser instance registered for the file extension.
        
        Args:
            filepath (str): The filename or path.
            
        Returns:
            Optional[LanguageParser]: The matching parser, or None if not supported.
        """
        suffix = Path(filepath).suffix.lower()
        return cls._parsers.get(suffix)

    @classmethod
    def supports(cls, filepath: str) -> bool:
        """Check if the file suffix is supported by any registered parser."""
        return Path(filepath).suffix.lower() in cls._parsers
