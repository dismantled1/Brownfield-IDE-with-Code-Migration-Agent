import os
import re
import json
import hashlib
import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Optional
from backend.services.analysis_service import analysis_manager

logger = logging.getLogger(__name__)

STOPWORDS = {
    "where", "is", "the", "find", "show", "related", "to", "implemented", 
    "handled", "code", "in", "referenced", "user", "get", "post", "jwt",
    "auth", "all", "what", "how", "create", "validate", "files", "class", 
    "function", "api", "endpoint", "method", "service", "controller"
}

class SearchService:
    """
    Search & Navigation Engine. Handles semantic queries, full-text symbol searches,
    regex-based API discovery, and codebase dependency routing.
    """

    def __init__(self):
        self.apis: List[Dict[str, Any]] = []
        self.project_path = ""
        self._indexed = False

    def ensure_indexed(self, project_root: str, force: bool = False) -> None:
        """Build search index if not already indexed for this project path."""
        resolved = str(Path(project_root).resolve())
        if not force and self._indexed and self.project_path == resolved:
            return
        self.build_index(resolved)

    def build_index(self, project_root: str) -> None:
        """Trigger API discovery and load metadata from analysis manager."""
        resolved = str(Path(project_root).resolve())
        self.project_path = resolved
        self.apis = []
        
        # Ensure files are loaded in analysis manager
        if not analysis_manager.files:
            cache_path = analysis_manager._get_cache_path(self.project_path)
            cache_data = analysis_manager._load_cache(cache_path)
            if cache_data:
                analysis_manager.project_path = cache_data.get("project_path", "")
                analysis_manager.files = cache_data.get("files", {})
                analysis_manager.modules = cache_data.get("modules", {})
                analysis_manager.relationships = cache_data.get("relationships", {})
                analysis_manager.stats = cache_data.get("stats", {})
        
        # Extract endpoints from project files
        self._extract_endpoints(self.project_path)
        self._indexed = True
        logger.info(f"Search index built successfully for {self.project_path}. Extracted {len(self.apis)} APIs.")

    def search(self, query: str, project_root: str) -> Dict[str, Any]:
        """Perform search query and return ranked results by type."""
        self.ensure_indexed(project_root)

        # 1. Execute Local Scorer to fetch candidate hits
        candidates = self._run_local_search(query)

        # 2. Check for active provider to perform semantic candidate ranking
        from backend.services.llm import get_active_provider
        provider = get_active_provider()
        
        if provider and candidates:
            # Re-rank using LLM
            llm_results = self._call_llm_rerank(query, candidates[:20])
            if llm_results:
                return self._assemble_results(llm_results)

        # 3. Fallback/Standard returns using local scores
        return self._assemble_results(candidates)

    def find_references(self, symbol: str, project_root: str) -> Dict[str, Any]:
        """Find incoming references and outgoing dependencies for a given symbol."""
        self.ensure_indexed(project_root)

        incoming = []
        outgoing = []

        symbol_clean = symbol.strip().lower()

        # Check if symbol matches a file path
        all_rel_paths = list(analysis_manager.files.keys())
        matched_file = None
        for path in all_rel_paths:
            if symbol_clean in path.lower():
                matched_file = path
                break

        if matched_file:
            # Outgoing references (files this file imports)
            deps = analysis_manager.relationships.get("imports", {}).get(matched_file, [])
            for dep in deps:
                outgoing.append({
                    "name": dep,
                    "type": "file",
                    "file": dep,
                    "line": 1,
                    "reason": f"Imported by {matched_file}"
                })
            
            # Incoming references (files importing this file)
            for path, imports in analysis_manager.relationships.get("imports", {}).items():
                if matched_file in imports:
                    incoming.append({
                        "name": path,
                        "type": "file",
                        "file": path,
                        "line": 1,
                        "reason": f"Imports {matched_file}"
                    })
        else:
            # Symbol is a Class or Function name
            # Incoming references: scan occurrences in file contents
            for path, file_data in analysis_manager.files.items():
                # Read file contents and search symbol
                full_path = Path(self.project_path) / path
                if full_path.exists():
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
                            for idx, line in enumerate(fh):
                                if symbol in line:
                                    # Ensure it's not the declaration itself
                                    line_num = idx + 1
                                    # Check if it matches class or function decl
                                    is_decl = False
                                    for cls in file_data.get("classes", []):
                                        if cls["name"] == symbol and cls["line_start"] == line_num:
                                            is_decl = True
                                        for m in cls.get("methods", []):
                                            if m["name"] == symbol and m["line_start"] == line_num:
                                                is_decl = True
                                    for func in file_data.get("functions", []):
                                        if func["name"] == symbol and func["line_start"] == line_num:
                                            is_decl = True
                                            
                                    if not is_decl:
                                        incoming.append({
                                            "name": f"Line {line_num}: {line.strip()[:40]}...",
                                            "type": "reference",
                                            "file": path,
                                            "line": line_num,
                                            "reason": f"References {symbol}"
                                        })
                    except Exception:
                        pass

            # Outgoing references (e.g. if symbol is a class, bases classes)
            for path, file_data in analysis_manager.files.items():
                for cls in file_data.get("classes", []):
                    if cls["name"] == symbol:
                        for base in cls.get("bases", []):
                            outgoing.append({
                                "name": base,
                                "type": "class",
                                "file": path,
                                "line": cls["line_start"],
                                "reason": f"Superclass of {symbol}"
                            })

        return {
            "symbol": symbol,
            "incoming": incoming,
            "outgoing": outgoing,
            "stats": {
                "incoming_count": len(incoming),
                "outgoing_count": len(outgoing)
            }
        }

    def _extract_endpoints(self, project_root: str) -> None:
        """Scan file contents of all code assets for API endpoint patterns."""
        for path, file_data in analysis_manager.files.items():
            full_path = Path(project_root) / path
            if not full_path.exists():
                continue

            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
                
                lines = content.splitlines()
                ext = full_path.suffix.lower()

                # Case A: Python Router/Endpoints
                if ext == ".py":
                    # matches: @app.get("/login") or @router.post('/checkout')
                    py_matches = re.finditer(
                        r"@(?:app|router|blueprint)\.(get|post|put|delete|patch|options|head)\s*\(\s*['\"]([^'\"]+)['\"]", 
                        content
                    )
                    for m in py_matches:
                        method = m.group(1).upper()
                        route = m.group(2)
                        line_no = content[:m.start()].count("\n") + 1
                        purpose = self._get_preceding_comments(lines, line_no)
                        self.apis.append({
                            "endpoint": route,
                            "method": method,
                            "file": path,
                            "line": line_no,
                            "purpose": purpose or f"Python {method} API Endpoint"
                        })

                # Case B: JS/TS Express Routers
                elif ext in (".js", ".ts", ".jsx", ".tsx"):
                    # matches: router.post('/login', ...) or app.get("/api/v1", ...)
                    js_matches = re.finditer(
                        r"\b(?:app|router|route)\.(get|post|put|delete|patch|options|head)\s*\(\s*['\"]([^'\"]+)['\"]", 
                        content
                    )
                    for m in js_matches:
                        method = m.group(1).upper()
                        route = m.group(2)
                        line_no = content[:m.start()].count("\n") + 1
                        purpose = self._get_preceding_comments(lines, line_no)
                        self.apis.append({
                            "endpoint": route,
                            "method": method,
                            "file": path,
                            "line": line_no,
                            "purpose": purpose or f"Express {method} API Endpoint"
                        })

                # Case C: Spring Boot endpoints
                elif ext == ".java":
                    # matches: @GetMapping("/users") or @PostMapping(value = "/checkout")
                    java_matches = re.finditer(
                        r"@(?:GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\s*\(\s*(?:value\s*=\s*)?['\"]([^'\"]+)['\"]", 
                        content
                    )
                    for m in java_matches:
                        # Infer method type
                        match_str = m.group(0)
                        method = "GET"
                        if "PostMapping" in match_str:
                            method = "POST"
                        elif "PutMapping" in match_str:
                            method = "PUT"
                        elif "DeleteMapping" in match_str:
                            method = "DELETE"
                        elif "PatchMapping" in match_str:
                            method = "PATCH"
                        elif "RequestMapping" in match_str:
                            # Default request mapping to GET / ALL
                            method = "GET/ANY"
                            
                        route = m.group(1)
                        line_no = content[:m.start()].count("\n") + 1
                        purpose = self._get_preceding_comments(lines, line_no)
                        self.apis.append({
                            "endpoint": route,
                            "method": method,
                            "file": path,
                            "line": line_no,
                            "purpose": purpose or f"Spring {method} API Endpoint"
                        })
            except Exception as exc:
                logger.error(f"Failed to scan APIs for {path}: {exc}")

    def _get_preceding_comments(self, lines: List[str], line_no: int) -> str:
        """Scan backwards for comment headers directly preceding the API decorators."""
        comment_lines = []
        idx = line_no - 2  # 0-indexed line before decorator
        
        while idx >= 0:
            stripped = lines[idx].strip()
            if stripped.startswith("//") or stripped.startswith("#"):
                comment_lines.insert(0, stripped.lstrip("/# ").strip())
            elif stripped.endswith("*/"):
                # block comments
                while idx >= 0:
                    strp = lines[idx].strip()
                    comment_lines.insert(0, strp.lstrip("/* ").rstrip("*/ ").strip())
                    if strp.startswith("/*"):
                        break
                    idx -= 1
                break
            elif stripped == "":
                # empty spacer
                pass
            else:
                # hit code structure, stop comment parsing
                break
            idx -= 1
            if len(comment_lines) >= 3:
                break
                
        return " ".join([c for c in comment_lines if c]).strip()

    def _run_local_search(self, query: str) -> List[Dict[str, Any]]:
        """Rank code assets by counting match term intersections across indexed headers and files."""
        # Tokenize query
        terms = [t for t in re.split(r"\W+", query.lower()) if t and t not in STOPWORDS]
        if not terms:
            # Fallback to direct string split
            terms = [t for t in query.lower().split() if t]

        hits = []

        # 1. Search APIs
        for api in self.apis:
            score = self._compute_score(terms, api["endpoint"] + " " + api["method"], api["purpose"], "")
            if score > 0:
                hits.append({
                    "type": "api",
                    "name": f"{api['method']} {api['endpoint']}",
                    "file": api["file"],
                    "line": api["line"],
                    "score": score,
                    "reason": api["purpose"]
                })

        # 2. Search Files
        for path, file_data in analysis_manager.files.items():
            filename = path.split("/")[-1]
            score = self._compute_score(terms, filename, file_data.get("summary", ""), path)
            if score > 0:
                hits.append({
                    "type": "file",
                    "name": filename,
                    "file": path,
                    "line": 1,
                    "score": score,
                    "reason": file_data.get("summary", "Source code asset.")
                })

            # 3. Search Classes inside File
            for cls in file_data.get("classes", []):
                score = self._compute_score(terms, cls["name"], cls.get("docstring", ""), "")
                if score > 0:
                    hits.append({
                        "type": "class",
                        "name": cls["name"],
                        "file": path,
                        "line": cls["line_start"],
                        "score": score,
                        "reason": cls.get("docstring") or f"Class structure in {filename}"
                    })

                # 4. Search Methods inside Class
                for m in cls.get("methods", []):
                    score = self._compute_score(terms, m["name"], m.get("docstring", ""), "")
                    if score > 0:
                        hits.append({
                            "type": "function",
                            "name": f"{cls['name']}.{m['name']}",
                            "file": path,
                            "line": m["line_start"],
                            "score": score,
                            "reason": m.get("docstring") or f"Class method in {cls['name']}"
                        })

            # 5. Search Module Functions inside File
            for func in file_data.get("functions", []):
                score = self._compute_score(terms, func["name"], func.get("docstring", ""), "")
                if score > 0:
                    hits.append({
                        "type": "function",
                        "name": func["name"],
                        "file": path,
                        "line": func["line_start"],
                        "score": score,
                        "reason": func.get("docstring") or f"Function defined in {filename}"
                    })

        # Sort descending by score
        hits = sorted(hits, key=lambda x: x["score"], reverse=True)
        return hits

    def _compute_score(self, terms: List[str], header: str, docstring: str, path: str) -> float:
        """Heuristic similarity scorer using word intersection weights."""
        score = 0.0
        header_lower = header.lower()
        doc_lower = docstring.lower() if docstring else ""
        path_lower = path.lower()

        for term in terms:
            # Exact matches in name/endpoint (very high priority)
            if term == header_lower or f"/{term}" in header_lower:
                score += 8.0
            elif term in header_lower:
                score += 4.0

            # Matches in relative file paths
            if path_lower and term in path_lower:
                score += 3.0

            # Matches in code docs/summaries
            if doc_lower and term in doc_lower:
                score += 2.0

        return score

    def _call_llm_rerank(self, query: str, candidates: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """Send candidate hits to active provider to re-rank and augment them semantically."""
        # Prompt construction
        prompt = (
            f"The user wants to find: '{query}'.\n\n"
            f"We have retrieved the following candidate files/symbols from the codebase:\n\n"
            f"```json\n{json.dumps(candidates, indent=2)}\n```\n\n"
            f"Evaluate which candidates match best. Filter out non-matching candidates. "
            f"Augment their confidence score (0.0 to 1.0) and write a short reason explaining "
            f"how they relate to the user query. Your response MUST be a pure JSON array containing objects matching this schema:\n"
            f"[\n"
            f"  {{\n"
            f"    \"type\": \"file|class|function|api\",\n"
            f"    \"name\": \"symbol or file name\",\n"
            f"    \"file\": \"relative file path\",\n"
            f"    \"line\": 123,\n"
            f"    \"score\": 0.95,\n"
            f"    \"reason\": \"reason description\"\n"
            f"  }}\n"
            f"]\n\n"
            f"Output ONLY the raw JSON array without markdown headers or code block surrounds."
        )

        from backend.services.llm import get_active_provider
        provider = get_active_provider()
        if provider:
            system = "You are a code search ranker. Evaluate candidate matches for queries and output a structured JSON array."
            result = provider.generate(prompt, system=system, temperature=0.1)
            if result.ok and result.text:
                try:
                    text = result.text.strip()
                    text = text.replace("```json", "").replace("```", "").strip()
                    return json.loads(text)
                except Exception as exc:
                    logger.error(f"Search re-rank JSON parse failed: {exc}")

        return None

    def _assemble_results(self, hits: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate list hits by type and compute stats summaries."""
        files = 0
        classes = 0
        functions = 0
        apis = 0

        # Normalise scores if they are out of range
        for h in hits:
            # Stats count
            t = h.get("type", "")
            if t == "file":
                files += 1
            elif t == "class":
                classes += 1
            elif t == "function":
                functions += 1
            elif t == "api":
                apis += 1

        return {
            "results": hits,
            "stats": {
                "files": files,
                "classes": classes,
                "functions": functions,
                "apis": apis,
                "total": len(hits)
            }
        }

# Singleton instance
search_service = SearchService()
