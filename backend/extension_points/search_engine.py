"""
Extension Point: Search Engine
================================
Phase 3 Integration Point.

This module will host the Intelligent Code Search & Navigation engine
that allows semantic and structural code search across the project.

Future capabilities:
- Symbol search (classes, functions, variables)
- Full-text code search with ranking
- Semantic similarity search
- Go-to-definition
- Find all references
- Call graph navigation
"""

from typing import List, Optional, Dict, Any
from backend.services.search_service import search_service


class SearchEngine:
    """
    Phase 3 integration: Intelligent Search Engine.
    Maps extension functions directly to search_service implementation.
    """

    def __init__(self):
        pass

    async def build_index(self, project_root: str) -> None:
        """Build search index for a project."""
        search_service.build_index(project_root)

    async def search_symbols(self, query: str, project_root: str) -> List[Dict[str, Any]]:
        """Search for code symbols (classes, functions, etc.)."""
        res = search_service.search(query, project_root)
        # return flat results list
        return res.get("results", [])

    async def search_text(self, query: str, project_root: str, 
                          file_pattern: Optional[str] = None) -> List[Dict[str, Any]]:
        """Full-text code search."""
        res = search_service.search(query, project_root)
        return res.get("results", [])

    async def find_references(self, symbol: str, project_root: str) -> List[Dict[str, Any]]:
        """Find all references to a symbol."""
        res = search_service.find_references(symbol, project_root)
        # Return combined list for references api contract
        return res.get("incoming", []) + res.get("outgoing", [])


# Singleton instance — wire up in Phase 3
search_engine = SearchEngine()
