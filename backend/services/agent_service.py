"""
Development Agent Engine (Phase 5).

Turns a natural-language request ("Add forgot password", "Fix login bug",
"Refactor payment module") into a *proposed* change set — a modification plan,
generated code, unified-diff patches, and a validation report.

It NEVER writes to project files. Results are cached by plan_id so later phases
(Phase 6 validation/approval, Phase 7 source update) can act on them.

Context is built intelligently from the existing engines (analysis, search,
impact) rather than sending the whole project to the model. When an LLM provider
is configured it generates real code; otherwise a deterministic offline
generator produces coherent scaffolding + patches so the workflow always runs.
"""

from __future__ import annotations
import ast
import json
import time
import uuid
import difflib
import logging
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from backend.services.analysis_service import analysis_manager
from backend.services.search_service import search_service
from backend.services.impact_service import impact_service
from backend.services.llm import get_active_provider, list_providers

logger = logging.getLogger(__name__)

# How much context we are willing to gather (keeps prompts bounded).
MAX_CONTEXT_FILES = 6
MAX_SNIPPET_CHARS = 1800
MAX_RESULT_CACHE = 25

# Intent keyword cues.
_BUG_CUES = ("fix", "bug", "issue", "error", "exception", "broken", "fail",
             "crash", "not working", "regression", "npe", "null pointer")
_REFACTOR_CUES = ("refactor", "optimize", "improve", "clean", "restructure",
                  "rename", "extract", "simplify", "modularize", "tidy")
_FEATURE_CUES = ("add", "implement", "create", "support", "enable", "introduce",
                 "build", "new feature")

# Comment syntax per language for safe scaffold insertions.
_LINE_COMMENT = {
    "py": "#", "js": "//", "jsx": "//", "ts": "//", "tsx": "//",
    "java": "//", "go": "//", "rs": "//", "c": "//", "cpp": "//",
    "cs": "//", "php": "//", "rb": "#", "css": "/*", "html": "<!--",
}


class DevelopmentAgent:
    """Coordinates requirement understanding → plan → code → patch → validation."""

    def __init__(self):
        self.project_path = ""
        self._results: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def develop(self, request: str, project_root: str) -> Dict[str, Any]:
        """Produce a full proposed-change bundle for *request*."""
        started = time.time()
        self.project_path = str(Path(project_root).resolve())
        self._ensure_context_ready()

        request = (request or "").strip()
        intent = self.classify_intent(request)
        topic = self._extract_topic(request, intent)

        context = self.build_context(topic, intent)

        provider = get_active_provider()
        used_provider = "offline"
        plan: Dict[str, Any] = {}
        changes: List[Dict[str, Any]] = []

        if provider:
            llm_bundle = self._generate_with_llm(provider, request, intent, topic, context)
            if llm_bundle:
                plan, changes = llm_bundle
                used_provider = provider.key

        if not plan:
            plan = self._offline_plan(request, intent, topic, context)
            changes = self._offline_changes(intent, topic, context, plan)
            used_provider = "offline"

        patches = self._build_patches(changes)
        validation = self._validate(patches)
        risk = self._assess_risk(patches, context)

        plan_id = uuid.uuid4().hex[:12]
        bundle = {
            "plan_id": plan_id,
            "request": request,
            "intent": intent,
            "topic": topic,
            "provider": used_provider,
            "understanding": plan.get("understanding", ""),
            "plan": {
                "steps": plan.get("steps", []),
                "files_to_modify": sorted({p["path"] for p in patches if p["change_type"] == "modify"}),
                "files_to_create": sorted({p["path"] for p in patches if p["change_type"] == "create"}),
                "files_to_delete": sorted({p["path"] for p in patches if p["change_type"] == "delete"}),
                "files_to_rename": [
                    {"from": p["path"], "to": p.get("new_path")} for p in patches if p["change_type"] == "rename"
                ],
                "tests_to_update": plan.get("tests_to_update", []),
            },
            "patches": patches,
            "validation": validation,
            "risk": risk,
            "context_files": [c["path"] for c in context.get("files", [])],
            "stats": self._patch_stats(patches),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_ms": round((time.time() - started) * 1000, 1),
            # Hand-off envelope for Phase 6 (validation/approval) & Phase 7 (apply).
            "next_phase": {
                "ready_for_validation": validation["summary"]["failed"] == 0,
                "approval_required": True,
                "applied": False,
            },
        }

        self._cache_result(plan_id, bundle)
        return bundle

    def get_result(self, plan_id: str) -> Optional[Dict[str, Any]]:
        return self._results.get(plan_id)

    def providers(self) -> List[Dict[str, Any]]:
        return list_providers()

    # ------------------------------------------------------------------
    # Step 1 — requirement understanding
    # ------------------------------------------------------------------

    def classify_intent(self, request: str) -> str:
        text = request.lower()

        def hits(cues):
            return sum(1 for c in cues if c in text)

        bug, refac, feat = hits(_BUG_CUES), hits(_REFACTOR_CUES), hits(_FEATURE_CUES)
        # Bug/refactor cues are more specific than the broad "add/create" feature cues.
        if bug and bug >= refac:
            return "bug"
        if refac and refac >= feat:
            return "refactor"
        if feat:
            return "feature"
        if bug:
            return "bug"
        if refac:
            return "refactor"
        return "feature"

    def _extract_topic(self, request: str, intent: str) -> str:
        """Strip intent verbs/filler to get the subject of the request."""
        text = request.lower().strip().rstrip(".!?")
        drop = set(_BUG_CUES) | set(_REFACTOR_CUES) | set(_FEATURE_CUES) | {
            "the", "a", "an", "to", "for", "of", "in", "please", "can", "you",
            "module", "functionality", "feature", "function", "service", "this",
            "my", "our", "with", "into", "on", "and", "code", "quality",
        }
        words = re.split(r"\W+", text)
        kept = [w for w in words if w and w not in drop]
        topic = " ".join(kept).strip()
        return topic or text

    # ------------------------------------------------------------------
    # Step 2 — context building (reuse analysis / search / impact)
    # ------------------------------------------------------------------

    def _ensure_context_ready(self) -> None:
        """Make sure analysis + search indexes are populated for this project."""
        try:
            impact_service.ensure_graph_ready(self.project_path)
        except Exception as exc:
            logger.warning(f"Agent: impact graph check warning: {exc}")
        try:
            search_service.ensure_indexed(self.project_path)
        except Exception as exc:
            logger.warning(f"Agent: search index check warning: {exc}")

    def build_context(self, topic: str, intent: str) -> Dict[str, Any]:
        """Select the most relevant files (and their structure) for the request."""
        relevant: List[str] = []
        try:
            search_data = search_service.search(topic, self.project_path)
            for res in search_data.get("results", []):
                if res.get("file") and res["file"] not in relevant:
                    relevant.append(res["file"])
                if len(relevant) >= MAX_CONTEXT_FILES:
                    break
        except Exception as exc:
            logger.warning(f"Agent: search for context failed: {exc}")

        # Enrich with import-dependencies of the primary file (impact engine).
        if relevant:
            deps = impact_service.file_dependencies.get(relevant[0], set())
            for dep in list(deps)[:3]:
                if dep not in relevant and len(relevant) < MAX_CONTEXT_FILES:
                    relevant.append(dep)

        files: List[Dict[str, Any]] = []
        for rel in relevant:
            meta = analysis_manager.files.get(rel, {})
            files.append({
                "path": rel,
                "language": meta.get("language", Path(rel).suffix.lstrip(".")),
                "summary": meta.get("summary", ""),
                "classes": [c.get("name") for c in meta.get("classes", [])],
                "functions": [f.get("name") for f in meta.get("functions", [])],
                "snippet": self._read_snippet(rel),
            })

        apis = [
            {"method": a["method"], "endpoint": a["endpoint"], "file": a["file"]}
            for a in search_service.apis[:10]
        ]

        return {
            "topic": topic,
            "intent": intent,
            "files": files,
            "apis": apis,
            "languages": list(analysis_manager.stats.get("languages", {}).keys()),
            "modules": list(analysis_manager.modules.keys()),
        }

    def _read_snippet(self, rel_path: str, max_chars: int = MAX_SNIPPET_CHARS) -> str:
        full = Path(self.project_path) / rel_path
        try:
            if full.exists() and full.is_file():
                text = full.read_text(encoding="utf-8", errors="replace")
                return text[:max_chars]
        except Exception:
            pass
        return ""

    def _read_full(self, rel_path: str) -> str:
        full = Path(self.project_path) / rel_path
        try:
            if full.exists() and full.is_file():
                return full.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass
        return ""

    # ------------------------------------------------------------------
    # Step 3/4 — plan + code generation (LLM path)
    # ------------------------------------------------------------------

    def _generate_with_llm(self, provider, request, intent, topic, context):
        """Returns (plan, changes) or None on failure."""
        system = (
            "You are a senior software engineer working inside an existing "
            "(brownfield) codebase. Propose precise, minimal changes. You MUST "
            "return ONLY a JSON object — no markdown fences, no prose."
        )
        ctx_json = json.dumps({
            "request": request,
            "intent": intent,
            "topic": topic,
            "languages": context.get("languages"),
            "modules": context.get("modules"),
            "apis": context.get("apis"),
            "files": context.get("files"),
        }, indent=2)[:12000]

        prompt = (
            f"Codebase context:\n```json\n{ctx_json}\n```\n\n"
            f"Task ({intent}): {request}\n\n"
            "Return a JSON object with this exact shape:\n"
            "{\n"
            '  "understanding": "one-paragraph restatement of the request",\n'
            '  "steps": ["ordered implementation steps"],\n'
            '  "tests_to_update": ["relative/test/paths"],\n'
            '  "changes": [\n'
            '    {"path": "relative/path", "change_type": "modify|create|delete",\n'
            '     "content": "FULL new file content (omit for delete)"}\n'
            "  ]\n"
            "}\n"
            "Only include files you actually change. Keep existing code intact "
            "except where the task requires edits. Paths are relative to the project root."
        )

        result = provider.generate(prompt, system=system, temperature=0.2)
        if not result.ok or not result.text:
            logger.warning(f"Agent: LLM provider '{provider.key}' failed: {result.error}")
            return None

        data = self._parse_json(result.text)
        if not isinstance(data, dict):
            logger.warning("Agent: LLM did not return a JSON object; using offline fallback.")
            return None

        raw_changes = data.get("changes", []) or []
        changes: List[Dict[str, Any]] = []
        for ch in raw_changes:
            if not isinstance(ch, dict) or not ch.get("path"):
                continue
            path = ch["path"].replace("\\", "/").lstrip("/")
            ctype = ch.get("change_type", "modify")
            before = self._read_full(path)
            if ctype == "create" and before:
                ctype = "modify"
            if ctype == "modify" and not before:
                ctype = "create"
            after = "" if ctype == "delete" else (ch.get("content") or "")
            changes.append({
                "path": path,
                "change_type": ctype,
                "before": before,
                "after": after,
            })

        plan = {
            "understanding": data.get("understanding", ""),
            "steps": data.get("steps", []),
            "tests_to_update": data.get("tests_to_update", []),
        }
        if not changes:
            return None
        return plan, changes

    @staticmethod
    def _parse_json(text: str) -> Any:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except Exception:
            # Best effort: grab the outermost JSON object.
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    return None
            return None

    # ------------------------------------------------------------------
    # Step 3/4 — plan + code generation (offline deterministic path)
    # ------------------------------------------------------------------

    def _primary_language(self, context: Dict[str, Any]) -> str:
        for f in context.get("files", []):
            lang = (f.get("language") or "").lower()
            if lang in ("py", "js", "ts", "tsx", "jsx", "java"):
                return lang
        langs = [l.lower() for l in context.get("languages", [])]
        if "py" in langs:
            return "py"
        if "js" in langs:
            return "js"
        return "py"

    def _slug(self, topic: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")
        return slug or "feature"

    def _pascal(self, topic: str) -> str:
        parts = re.split(r"[^a-zA-Z0-9]+", topic)
        return "".join(p.capitalize() for p in parts if p) or "Feature"

    def _offline_plan(self, request, intent, topic, context) -> Dict[str, Any]:
        primary = context["files"][0]["path"] if context.get("files") else None
        if intent == "feature":
            steps = [
                f"Understand the '{topic}' feature requirement and acceptance criteria.",
                "Identify integration points in the existing modules and APIs.",
                f"Create a dedicated service/module to encapsulate '{topic}' logic.",
                "Wire the new module into the relevant entry point / router.",
                "Add or update tests covering the new behaviour.",
            ]
            understanding = (
                f"You requested a new feature: \"{request}\". The agent will scaffold a "
                f"'{topic}' service and wire it into the most relevant existing file"
                + (f" ({primary})." if primary else ".")
            )
        elif intent == "bug":
            steps = [
                f"Reproduce and localize the '{topic}' defect.",
                "Inspect the most relevant file(s) and surrounding call sites.",
                "Add guards / corrected logic at the fault location.",
                "Add a regression test that fails before and passes after the fix.",
            ]
            understanding = (
                f"You reported a bug: \"{request}\". The agent located the most relevant "
                f"file{(' (' + primary + ')') if primary else ''} and proposes a guarded fix."
            )
        else:  # refactor
            steps = [
                f"Assess the current structure of the '{topic}' area.",
                "Identify duplication, long functions, and unclear naming.",
                "Propose extraction / documentation / simplification edits.",
                "Keep behaviour identical; rely on tests to confirm parity.",
            ]
            understanding = (
                f"You requested a refactor: \"{request}\". The agent proposes structural "
                f"improvements to {primary or 'the relevant module'} without changing behaviour."
            )
        return {"understanding": understanding, "steps": steps, "tests_to_update": []}

    def _fallback_primary(self) -> Optional[str]:
        """When the request topic matches no file, target the most-central file
        (most imported), so bug/refactor proposals always have an anchor."""
        deps = impact_service.file_dependents
        if deps:
            ranked = sorted(deps.items(), key=lambda kv: len(kv[1]), reverse=True)
            for path, dependents in ranked:
                if dependents:
                    return path
        files = list(analysis_manager.files.keys())
        return files[0] if files else None

    def _offline_changes(self, intent, topic, context, plan) -> List[Dict[str, Any]]:
        changes: List[Dict[str, Any]] = []
        lang = self._primary_language(context)
        files = context.get("files", [])
        primary = files[0]["path"] if files else self._fallback_primary()

        if intent == "feature":
            new_path, new_content = self._scaffold_feature_file(topic, lang, primary)
            changes.append({"path": new_path, "change_type": "create", "before": "", "after": new_content})
            if primary:
                before = self._read_full(primary)
                note = [
                    f"Phase 5 proposal: wire in the new '{topic}' module.",
                    f"See generated scaffold: {new_path}",
                    "TODO: import and register the new module here.",
                ]
                after = self._insert_comment_block(before, primary, note)
                changes.append({"path": primary, "change_type": "modify", "before": before, "after": after})

        elif intent == "bug":
            if primary:
                before = self._read_full(primary)
                note = [
                    f"Phase 5 proposed fix for: {topic}",
                    "TODO: add the guard/null-check/error-handling described in the plan",
                    "below at the identified fault location, then add a regression test.",
                ]
                after = self._insert_comment_block(before, primary, note)
                changes.append({"path": primary, "change_type": "modify", "before": before, "after": after})

        else:  # refactor
            if primary:
                before = self._read_full(primary)
                note = [
                    f"Phase 5 refactor plan for: {topic}",
                    "TODO: extract long functions, remove duplication, add docstrings.",
                    "Behaviour must remain identical; rely on tests for parity.",
                ]
                after = self._insert_comment_block(before, primary, note)
                changes.append({"path": primary, "change_type": "modify", "before": before, "after": after})

        return changes

    def _scaffold_feature_file(self, topic, lang, primary) -> Tuple[str, str]:
        slug = self._slug(topic)
        name = self._pascal(topic)
        base_dir = str(Path(primary).parent) if primary and "/" in primary.replace("\\", "/") else ""
        base = (base_dir + "/") if base_dir else ""

        if lang == "py":
            path = f"{base}{slug}_service.py"
            content = (
                f'"""\n{name} Service — generated scaffold (Phase 5 Development Agent).\n\n'
                f'Proposed implementation for: {topic}.\nThis is a non-applied proposal; '
                f'review before approval.\n"""\n\n\n'
                f"class {name}Service:\n"
                f'    """Encapsulates the {topic} feature."""\n\n'
                f"    def __init__(self):\n"
                f"        pass\n\n"
                f"    def handle(self, *args, **kwargs):\n"
                f'        raise NotImplementedError("TODO: implement {topic}")\n'
            )
        elif lang in ("js", "jsx", "ts", "tsx"):
            ext = lang
            path = f"{base}{slug}.{ext}"
            content = (
                f"// {name} — generated scaffold (Phase 5 Development Agent)\n"
                f"// Proposed implementation for: {topic}\n\n"
                f"export function {slug}() {{\n"
                f"  // TODO: implement {topic}\n"
                f"  throw new Error('TODO: implement {topic}');\n"
                f"}}\n"
            )
        elif lang == "java":
            path = f"{base}{name}Service.java"
            content = (
                f"// {name}Service — generated scaffold (Phase 5 Development Agent)\n"
                f"// Proposed implementation for: {topic}\n\n"
                f"public class {name}Service {{\n"
                f"    // TODO: implement {topic}\n"
                f"}}\n"
            )
        else:
            path = f"{base}{slug}.txt"
            content = f"{name} scaffold — proposed implementation for: {topic}\nTODO: implement.\n"
        return path, content

    def _insert_comment_block(self, content: str, rel_path: str, lines: List[str]) -> str:
        ext = Path(rel_path).suffix.lstrip(".").lower()
        marker = _LINE_COMMENT.get(ext, "#")
        if marker == "/*":
            block = "/*\n" + "\n".join(f" * {ln}" for ln in lines) + "\n */\n"
        elif marker == "<!--":
            block = "<!--\n" + "\n".join(f"  {ln}" for ln in lines) + "\n-->\n"
        else:
            block = "\n".join(f"{marker} {ln}" for ln in lines) + "\n"
        sep = "" if content.startswith("\n") else "\n"
        return block + sep + content

    # ------------------------------------------------------------------
    # Step 5 — patch / diff generation
    # ------------------------------------------------------------------

    def _build_patches(self, changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        patches = []
        for ch in changes:
            path = ch["path"]
            ctype = ch["change_type"]
            before = ch.get("before", "")
            after = ch.get("after", "")
            diff_text = self._unified_diff(path, ctype, before, after)
            additions, removals = self._count_diff(diff_text)
            patches.append({
                "path": path,
                "new_path": ch.get("new_path"),
                "change_type": ctype,
                "language": self._lang_id(path),
                "before": before,
                "after": after,
                "diff": diff_text,
                "additions": additions,
                "removals": removals,
            })
        return patches

    def _unified_diff(self, path, ctype, before, after) -> str:
        from_label = f"a/{path}" if ctype != "create" else "/dev/null"
        to_label = f"b/{path}" if ctype != "delete" else "/dev/null"
        before_lines = before.splitlines(keepends=True) if before else []
        after_lines = after.splitlines(keepends=True) if after else []
        diff = difflib.unified_diff(
            before_lines, after_lines, fromfile=from_label, tofile=to_label, lineterm=""
        )
        return "".join(line if line.endswith("\n") else line + "\n" for line in diff)

    @staticmethod
    def _count_diff(diff_text: str) -> Tuple[int, int]:
        additions = removals = 0
        for line in diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                removals += 1
        return additions, removals

    @staticmethod
    def _lang_id(path: str) -> str:
        ext = Path(path).suffix.lstrip(".").lower()
        return {
            "py": "python", "js": "javascript", "jsx": "javascript",
            "ts": "typescript", "tsx": "typescript", "java": "java",
            "html": "html", "css": "css", "json": "json", "md": "markdown",
        }.get(ext, "plaintext")

    def _patch_stats(self, patches) -> Dict[str, int]:
        return {
            "modified": sum(1 for p in patches if p["change_type"] == "modify"),
            "created": sum(1 for p in patches if p["change_type"] == "create"),
            "deleted": sum(1 for p in patches if p["change_type"] == "delete"),
            "renamed": sum(1 for p in patches if p["change_type"] == "rename"),
            "additions": sum(p["additions"] for p in patches),
            "removals": sum(p["removals"] for p in patches),
        }

    # ------------------------------------------------------------------
    # Step 6 — validation
    # ------------------------------------------------------------------

    def _validate(self, patches: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = []
        for p in patches:
            path = p["path"]
            ctype = p["change_type"]
            after = p.get("after", "")

            if ctype == "delete":
                results.append({"file": path, "type": "delete", "status": "pass",
                                "message": "File marked for deletion."})
                continue

            # Path safety — must stay within the project.
            try:
                (Path(self.project_path) / path).resolve().relative_to(Path(self.project_path).resolve())
            except ValueError:
                results.append({"file": path, "type": "path", "status": "fail",
                                "message": "Path escapes the project root."})
                continue

            if not after.strip():
                results.append({"file": path, "type": "content", "status": "warn",
                                "message": "Proposed content is empty."})
                continue

            ext = Path(path).suffix.lstrip(".").lower()
            if ext == "py":
                results.append(self._validate_python(path, after))
            elif ext in ("js", "jsx", "ts", "tsx", "java", "json", "css"):
                results.append(self._validate_braces(path, after, ext))
            else:
                results.append({"file": path, "type": "syntax", "status": "pass",
                                "message": "No validator for this file type; skipped."})

        summary = {
            "passed": sum(1 for r in results if r["status"] == "pass"),
            "warnings": sum(1 for r in results if r["status"] == "warn"),
            "failed": sum(1 for r in results if r["status"] == "fail"),
            "total": len(results),
        }
        return {"results": results, "summary": summary}

    @staticmethod
    def _validate_python(path: str, content: str) -> Dict[str, Any]:
        try:
            ast.parse(content)
            return {"file": path, "type": "syntax", "status": "pass",
                    "message": "Python syntax valid (ast.parse)."}
        except SyntaxError as exc:
            return {"file": path, "type": "syntax", "status": "fail",
                    "message": f"Python syntax error: line {exc.lineno}: {exc.msg}"}

    @staticmethod
    def _validate_braces(path: str, content: str, ext: str) -> Dict[str, Any]:
        pairs = {")": "(", "]": "[", "}": "{"}
        opens = set(pairs.values())
        stack = []
        in_str = None
        prev = ""
        for ch in content:
            if in_str:
                if ch == in_str and prev != "\\":
                    in_str = None
            elif ch in ("'", '"', "`"):
                in_str = ch
            elif ch in opens:
                stack.append(ch)
            elif ch in pairs:
                if not stack or stack[-1] != pairs[ch]:
                    return {"file": path, "type": "syntax", "status": "warn",
                            "message": f"Unbalanced '{ch}' detected (heuristic)."}
                stack.pop()
            prev = ch
        if stack:
            return {"file": path, "type": "syntax", "status": "warn",
                    "message": "Unbalanced brackets detected (heuristic)."}
        return {"file": path, "type": "syntax", "status": "pass",
                "message": f"{ext.upper()} bracket balance OK (heuristic)."}

    # ------------------------------------------------------------------
    # Risk (reuse impact engine where possible)
    # ------------------------------------------------------------------

    def _assess_risk(self, patches, context) -> Dict[str, Any]:
        affected = [p["path"] for p in patches]
        primary = context["files"][0]["path"] if context.get("files") else (affected[0] if affected else "")
        try:
            risk = impact_service.assess_risk(affected, primary)
            if risk and risk.get("level"):
                return risk
        except Exception as exc:
            logger.warning(f"Agent: impact risk assessment failed: {exc}")
        # Fallback heuristic.
        n = len(affected)
        level = "High" if n > 5 else ("Medium" if n >= 3 else "Low")
        return {
            "level": level,
            "explanation": f"Proposed change touches {n} file(s).",
            "metrics": {"affected_files_count": n, "critical_modules_hit": 0,
                        "circular_dependencies_involved": 0},
        }

    # ------------------------------------------------------------------
    # Result cache
    # ------------------------------------------------------------------

    def _cache_result(self, plan_id: str, bundle: Dict[str, Any]) -> None:
        self._results[plan_id] = bundle
        if len(self._results) > MAX_RESULT_CACHE:
            oldest = next(iter(self._results))
            self._results.pop(oldest, None)


# Singleton instance
agent_service = DevelopmentAgent()
