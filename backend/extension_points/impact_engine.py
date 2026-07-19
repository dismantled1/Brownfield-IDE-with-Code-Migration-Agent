"""
Extension Point: Impact Analysis Engine
=========================================
Phase 4 Integration Point.

This module will analyze the ripple effects of proposed code changes,
identifying all files, tests, and systems that would be affected.

Future capabilities:
- Change impact graph computation
- Dependency chain traversal
- Risk assessment for modifications
- Test coverage mapping
- Breaking change detection
"""

from typing import List, Dict, Any


class ImpactEngine:
    """
    Phase 4: Impact Analysis Engine.
    Coordinates ripple effects analysis and dependency queries.
    """

    def __init__(self):
        pass

    async def analyze_impact(
        self,
        project_root: str,
        changed_files: List[str]
    ) -> Dict[str, Any]:
        """
        Analyze the impact of changes to the given files.
        
        Returns affected files, risk level, and explanations.
        """
        from backend.services.impact_service import impact_service
        impact_service.ensure_graph_ready(project_root)
        
        all_affected = set()
        chains = []
        for f in changed_files:
            res = impact_service.analyze_file_impact(f)
            all_affected.update(res.get("direct", []))
            all_affected.update(res.get("indirect", []))
            chains.extend(res.get("chains", []))
            
        risk = impact_service.assess_risk(list(all_affected), changed_files[0] if changed_files else "")
        return {
            "affected_files": list(all_affected),
            "risk_level": risk["level"],
            "explanation": risk["explanation"],
            "chains": chains,
            "recommended_tests": []  # Stub for Phase 6
        }

    async def get_dependency_chain(
        self,
        project_root: str,
        file_path: str
    ) -> Dict[str, Any]:
        """Get the full dependency chain for a file."""
        from backend.services.impact_service import impact_service
        impact_service.ensure_graph_ready(project_root)
        res = impact_service.analyze_file_impact(file_path)
        return {
            "file": file_path,
            "direct": res.get("direct", []),
            "indirect": res.get("indirect", []),
            "chains": res.get("chains", [])
        }


# Singleton instance
impact_engine = ImpactEngine()
