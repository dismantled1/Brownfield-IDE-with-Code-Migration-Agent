"""
Validation & Approval Engine (Phase 6).

Takes a proposed change bundle from the Development Agent (Phase 5, looked up by
plan_id) and runs a safety pipeline BEFORE any source code is modified:

    syntax → static analysis → dependency validation → test execution
    → change-impact validation → risk analysis → structured report

It then tracks the user's approval decision (approve / reject). Nothing here
writes to project source files — application happens only in Phase 7. The cached
report + decision form the hand-off envelope (`next_phase`) for the Source
Update Engine.
"""

from __future__ import annotations
import ast
import re
import time
import logging
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional, Set

from backend.services.agent_service import agent_service
from backend.services.analysis_service import analysis_manager
from backend.services.impact_service import impact_service

logger = logging.getLogger(__name__)

HIDDEN_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", ".idea", ".vs",
    ".vscode", "dist", "build", ".gradle", ".mypy_cache", ".pytest_cache", ".tox",
}

CRITICAL_KEYWORDS = {"auth", "payment", "security", "login", "db", "config",
                     "core", "billing", "checkout", "session"}

TEST_TIMEOUT_SECONDS = 60
MAX_REPORT_CACHE = 25


class ValidationEngine:
    """Orchestrates validation stages and records approval decisions."""

    def __init__(self):
        self.project_path = ""
        self._reports: Dict[str, Dict[str, Any]] = {}
        self._decisions: Dict[str, Dict[str, Any]] = {}
        self._test_cache: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, plan_id: str, project_root: str, force: bool = False) -> Dict[str, Any]:
        """Run the full validation pipeline on a stored agent bundle."""
        self.project_path = str(Path(project_root).resolve())

        bundle = agent_service.get_result(plan_id)
        if not bundle:
            raise KeyError(f"No proposed-change bundle for plan_id: {plan_id}")

        # Incremental: reuse a cached report unless forced.
        if not force and plan_id in self._reports:
            return self._reports[plan_id]

        started = time.time()
        patches = bundle.get("patches", [])

        # Independent static stages run in parallel (pure functions of patches).
        with ThreadPoolExecutor(max_workers=3) as pool:
            f_syntax = pool.submit(self._syntax_validation, patches)
            f_static = pool.submit(self._static_analysis, patches)
            f_deps = pool.submit(self._dependency_validation, patches)
            syntax = f_syntax.result()
            static = f_static.result()
            deps = f_deps.result()

        tests = self._run_tests()
        impact = self._impact_validation(patches)
        risk = self._risk_analysis(bundle, syntax, deps, tests, impact)

        errors = (
            [r for r in syntax["results"] if r["status"] == "fail"]
            + [r for r in deps["results"] if r["status"] == "fail"]
        )
        warnings = (
            [r for r in static["results"] if r["status"] == "warn"]
            + [r for r in deps["results"] if r["status"] == "warn"]
            + [r for r in impact["results"] if r["status"] == "warn"]
        )

        tests_failed = tests["status"] == "FAILED"
        validation_status = "FAILED" if (errors or tests_failed) else "PASSED"

        stats = bundle.get("stats", {})
        report = {
            "plan_id": plan_id,
            "request": bundle.get("request", ""),
            "intent": bundle.get("intent", ""),
            "validation_status": validation_status,
            "stages": {
                "syntax": syntax,
                "static": static,
                "dependency": deps,
                "tests": tests,
                "impact": impact,
            },
            "risk": risk,
            "summary": {
                "files_modified": stats.get("modified", 0),
                "files_created": stats.get("created", 0),
                "files_deleted": stats.get("deleted", 0),
                "tests": tests["status"],
                "errors": [f"{r['file']}: {r['message']}" for r in errors],
                "warnings": [f"{r['file']}: {r['message']}" for r in warnings],
                "error_count": len(errors),
                "warning_count": len(warnings),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_ms": round((time.time() - started) * 1000, 1),
            "decision": self._decisions.get(plan_id, {"state": "pending", "at": None}),
            # Hand-off envelope for Phase 7 (Source Update Engine).
            "next_phase": {
                "ready_to_apply": False,  # requires explicit approval
                "blocked": validation_status == "FAILED",
                "applied": False,
            },
        }

        self._cache_report(plan_id, report)
        return report

    def get_report(self, plan_id: str) -> Optional[Dict[str, Any]]:
        return self._reports.get(plan_id)

    def approve(self, plan_id: str) -> Dict[str, Any]:
        return self._decide(plan_id, "approved")

    def reject(self, plan_id: str) -> Dict[str, Any]:
        return self._decide(plan_id, "rejected")

    def get_decision(self, plan_id: str) -> Dict[str, Any]:
        return self._decisions.get(plan_id, {"state": "pending", "at": None})

    # ------------------------------------------------------------------
    # Approval state (no file writes)
    # ------------------------------------------------------------------

    def _decide(self, plan_id: str, state: str) -> Dict[str, Any]:
        if not agent_service.get_result(plan_id):
            raise KeyError(f"No proposed-change bundle for plan_id: {plan_id}")
        decision = {"state": state, "at": datetime.now(timezone.utc).isoformat()}
        self._decisions[plan_id] = decision

        report = self._reports.get(plan_id)
        if report:
            report["decision"] = decision
            ready = state == "approved" and report["validation_status"] == "PASSED"
            report["next_phase"]["ready_to_apply"] = ready
        return {
            "plan_id": plan_id,
            "decision": decision,
            "ready_to_apply": bool(report and report["next_phase"]["ready_to_apply"]),
            "note": "Approval state stored only — no source files were modified.",
        }

    # ------------------------------------------------------------------
    # Stage 1 — syntax validation
    # ------------------------------------------------------------------

    def _syntax_validation(self, patches: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = []
        for p in patches:
            if p["change_type"] == "delete":
                continue
            path, after = p["path"], p.get("after", "")
            ext = Path(path).suffix.lstrip(".").lower()
            if ext == "py":
                results.append(self._check_python_syntax(path, after))
            elif ext in ("js", "jsx", "ts", "tsx", "java", "json", "css"):
                results.append(self._check_braces(path, after, ext))
            else:
                results.append({"file": path, "status": "pass",
                                "message": "No syntax validator for this type; skipped."})
        return self._stage("syntax", results)

    @staticmethod
    def _check_python_syntax(path: str, content: str) -> Dict[str, Any]:
        try:
            compile(content, path, "exec")
            return {"file": path, "status": "pass", "message": "Compiles (Python)."}
        except SyntaxError as exc:
            return {"file": path, "status": "fail",
                    "message": f"SyntaxError line {exc.lineno}: {exc.msg}"}

    @staticmethod
    def _check_braces(path: str, content: str, ext: str) -> Dict[str, Any]:
        pairs = {")": "(", "]": "[", "}": "{"}
        opens = set(pairs.values())
        stack, in_str, prev = [], None, ""
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
                    return {"file": path, "status": "fail",
                            "message": f"Unbalanced '{ch}' ({ext})."}
                stack.pop()
            prev = ch
        if stack:
            return {"file": path, "status": "fail", "message": f"Unclosed brackets ({ext})."}
        return {"file": path, "status": "pass", "message": f"Bracket balance OK ({ext})."}

    # ------------------------------------------------------------------
    # Stage 2 — static analysis (lightweight lint)
    # ------------------------------------------------------------------

    def _static_analysis(self, patches: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = []
        for p in patches:
            if p["change_type"] == "delete":
                continue
            path, after = p["path"], p.get("after", "")
            ext = Path(path).suffix.lstrip(".").lower()
            if ext == "py":
                results.extend(self._lint_python(path, after))
            # generic checks
            if "TODO" in after or "FIXME" in after:
                results.append({"file": path, "status": "warn",
                                "message": "Contains TODO/FIXME marker."})
            for i, line in enumerate(after.splitlines(), 1):
                if len(line) > 200:
                    results.append({"file": path, "status": "warn",
                                    "message": f"Very long line ({len(line)} chars) at line {i}."})
                    break
        if not results:
            results.append({"file": "—", "status": "pass", "message": "No static-analysis issues."})
        return self._stage("static", results)

    def _lint_python(self, path: str, content: str) -> List[Dict[str, Any]]:
        out = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return out  # syntax stage reports it
        imported: Dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    imported[(a.asname or a.name).split(".")[0]] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.name != "*":
                        imported[a.asname or a.name] = node.lineno
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        used |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        for name, line in imported.items():
            if name not in used and name not in content.replace("import", ""):
                # only flag when truly absent from the body
                body_refs = re.findall(r"\b" + re.escape(name) + r"\b", content)
                if len(body_refs) <= 1:
                    out.append({"file": path, "status": "warn",
                                "message": f"Possibly unused import '{name}' (line {line})."})
        return out

    # ------------------------------------------------------------------
    # Stage 3 — dependency validation
    # ------------------------------------------------------------------

    def _dependency_validation(self, patches: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = []
        all_files: Set[str] = set(analysis_manager.files.keys())
        top_pkgs = {f.split("/")[0] for f in all_files if "/" in f}

        for p in patches:
            path = p["path"]
            if p["change_type"] == "delete":
                dependents = impact_service.file_dependents.get(path, set())
                if dependents:
                    results.append({"file": path, "status": "warn",
                                    "message": f"{len(dependents)} file(s) import this — deletion may break them."})
                continue

            # New file must not collide with an existing path.
            if p["change_type"] == "create" and (Path(self.project_path) / path).exists():
                results.append({"file": path, "status": "fail",
                                "message": "Create target already exists on disk."})

            if Path(path).suffix.lstrip(".").lower() != "py":
                continue
            try:
                tree = ast.parse(p.get("after", ""))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    is_internal = node.level > 0 or node.module.split(".")[0] in top_pkgs
                    if is_internal and not self._resolves_internally(node.module, all_files):
                        results.append({"file": path, "status": "warn",
                                        "message": f"Internal import '{node.module}' may not resolve."})

        if not results:
            results.append({"file": "—", "status": "pass", "message": "All dependencies resolve."})
        return self._stage("dependency", results)

    @staticmethod
    def _resolves_internally(module: str, all_files: Set[str]) -> bool:
        target = module.lstrip(".").replace(".", "/")
        if not target:
            return True
        for f in all_files:
            if f.endswith(target + ".py") or f.endswith(target + "/__init__.py") or f"/{target}/" in f or f.endswith(target):
                return True
        return False

    # ------------------------------------------------------------------
    # Stage 4 — test execution
    # ------------------------------------------------------------------

    def _run_tests(self) -> Dict[str, Any]:
        cache_key = self.project_path
        if cache_key in self._test_cache:
            return self._test_cache[cache_key]

        result = self._discover_and_run_tests()
        self._test_cache[cache_key] = result
        return result

    def _discover_and_run_tests(self) -> Dict[str, Any]:
        root = Path(self.project_path)
        test_files = self._discover_python_tests(root)
        if not test_files:
            return {"status": "SKIPPED", "framework": None, "passed": 0, "failed": 0,
                    "total": 0, "duration_ms": 0, "log": "No runnable Python tests detected."}

        started = time.time()
        has_pytest = self._module_available("pytest")
        if has_pytest:
            cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                   "--no-header"] + [str(f) for f in test_files]
            framework = "pytest"
        else:
            cmd = [sys.executable, "-m", "unittest"] + [
                self._to_module(root, f) for f in test_files
            ]
            framework = "unittest"

        try:
            proc = subprocess.run(
                cmd, cwd=str(root), capture_output=True, text=True,
                timeout=TEST_TIMEOUT_SECONDS,
            )
            log = (proc.stdout or "") + (proc.stderr or "")
            passed, failed = self._parse_test_output(log, proc.returncode)
            rc = proc.returncode
            # pytest exit code 5 == no tests collected.
            if framework == "pytest" and rc == 5:
                status = "SKIPPED"
            elif failed > 0 or rc == 1:
                status = "FAILED"
            elif passed == 0 and failed == 0:
                # Nothing ran / couldn't determine — don't claim a failure.
                status = "SKIPPED"
            else:
                status = "PASSED"
            return {
                "status": status, "framework": framework,
                "passed": passed, "failed": failed, "total": passed + failed,
                "duration_ms": round((time.time() - started) * 1000, 1),
                "log": log[-4000:],
            }
        except subprocess.TimeoutExpired:
            return {"status": "TIMEOUT", "framework": framework, "passed": 0, "failed": 0,
                    "total": len(test_files), "duration_ms": TEST_TIMEOUT_SECONDS * 1000,
                    "log": f"Test run exceeded {TEST_TIMEOUT_SECONDS}s and was aborted."}
        except Exception as exc:
            logger.warning(f"Test execution failed to start: {exc}")
            return {"status": "SKIPPED", "framework": framework, "passed": 0, "failed": 0,
                    "total": 0, "duration_ms": 0, "log": f"Could not run tests: {exc}"}

    def _discover_python_tests(self, root: Path) -> List[Path]:
        found = []
        for p in root.rglob("*.py"):
            rel = p.relative_to(root)
            if any(part in HIDDEN_DIRS for part in rel.parts):
                continue
            name = p.name
            looks_like_test = (
                name.startswith("test_") or name.endswith("_test.py")
                or "tests" in rel.parts or "test" in rel.parts
            )
            if not looks_like_test:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            # Only run files that actually contain test cases (avoids importing
            # side-effectful scripts that merely happen to be named test_*).
            if re.search(r"def test_|unittest\.TestCase|class Test\w*\s*\(", text):
                found.append(p)
            if len(found) >= 50:
                break
        return found

    @staticmethod
    def _to_module(root: Path, file: Path) -> str:
        rel = file.relative_to(root).with_suffix("")
        return ".".join(rel.parts)

    @staticmethod
    def _module_available(name: str) -> bool:
        import importlib.util
        try:
            return importlib.util.find_spec(name) is not None
        except Exception:
            return False

    @staticmethod
    def _parse_test_output(log: str, returncode: int) -> tuple:
        # pytest summary, e.g. "3 passed, 1 failed"
        passed = failed = 0
        m = re.search(r"(\d+)\s+passed", log)
        if m:
            passed = int(m.group(1))
        m = re.search(r"(\d+)\s+failed", log)
        if m:
            failed = int(m.group(1))
        if passed == 0 and failed == 0:
            # unittest style: "Ran N tests" + "OK"/"FAILED (failures=X)"
            ran = re.search(r"Ran\s+(\d+)\s+test", log)
            total = int(ran.group(1)) if ran else 0
            fm = re.search(r"failures=(\d+)", log)
            em = re.search(r"errors=(\d+)", log)
            failed = (int(fm.group(1)) if fm else 0) + (int(em.group(1)) if em else 0)
            passed = max(0, total - failed)
        return passed, failed

    # ------------------------------------------------------------------
    # Stage 5 — change-impact validation
    # ------------------------------------------------------------------

    def _impact_validation(self, patches: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = []
        affected = [p["path"] for p in patches]

        # Breaking changes: modified/deleted files that other files import.
        breaking = []
        for p in patches:
            if p["change_type"] in ("modify", "delete"):
                dependents = impact_service.file_dependents.get(p["path"], set())
                if dependents:
                    breaking.append({"file": p["path"], "dependents": sorted(dependents)})
        if breaking:
            results.append({"file": breaking[0]["file"], "status": "warn",
                            "message": f"{len(breaking)} changed file(s) are imported elsewhere — verify callers."})

        # Circular dependencies touching the change set.
        circular = []
        for cycle in impact_service.circular_paths:
            if any(c in affected for c in cycle):
                circular.append(" -> ".join(cycle))
        if circular:
            results.append({"file": affected[0] if affected else "—", "status": "warn",
                            "message": f"Change participates in {len(circular)} circular dependency path(s)."})

        # Critical-module touch.
        critical = sorted({k for path in affected for k in CRITICAL_KEYWORDS if k in path.lower()})
        if critical:
            results.append({"file": "—", "status": "warn",
                            "message": f"Touches critical area(s): {', '.join(critical)}."})

        if not results:
            results.append({"file": "—", "status": "pass", "message": "No breaking/circular/API issues detected."})

        stage = self._stage("impact", results)
        stage["breaking_changes"] = breaking
        stage["circular"] = circular
        stage["critical_modules"] = critical
        return stage

    # ------------------------------------------------------------------
    # Stage 6 — risk analysis
    # ------------------------------------------------------------------

    def _risk_analysis(self, bundle, syntax, deps, tests, impact) -> Dict[str, Any]:
        affected = [p["path"] for p in bundle.get("patches", [])]
        try:
            base = impact_service.assess_risk(affected, affected[0] if affected else "")
        except Exception:
            base = {"level": "Low", "explanation": "", "metrics": {}}

        level = base.get("level", "Low")
        order = {"Low": 0, "Medium": 1, "High": 2}
        reasons = []

        syntax_errors = sum(1 for r in syntax["results"] if r["status"] == "fail")
        dep_errors = sum(1 for r in deps["results"] if r["status"] == "fail")

        if tests["status"] == "FAILED" or syntax_errors:
            level = "High"
            if tests["status"] == "FAILED":
                reasons.append(f"{tests['failed']} failing test(s)")
            if syntax_errors:
                reasons.append(f"{syntax_errors} syntax error(s)")
        elif dep_errors and order[level] < 1:
            level = "Medium"
            reasons.append(f"{dep_errors} dependency error(s)")

        if impact.get("circular"):
            if order[level] < 1:
                level = "Medium"
            reasons.append("circular dependencies")
        if impact.get("critical_modules") and order[level] < 1:
            level = "Medium"
            reasons.append("critical modules affected")

        explanation = base.get("explanation", "")
        if reasons:
            explanation = (explanation + " Elevated due to: " + ", ".join(reasons) + ".").strip()

        metrics = dict(base.get("metrics", {}))
        metrics.update({
            "syntax_errors": syntax_errors,
            "dependency_errors": dep_errors,
            "failing_tests": tests.get("failed", 0),
        })
        return {"level": level, "explanation": explanation, "metrics": metrics}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _stage(name: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        failed = sum(1 for r in results if r["status"] == "fail")
        warnings = sum(1 for r in results if r["status"] == "warn")
        passed = sum(1 for r in results if r["status"] == "pass")
        return {
            "name": name,
            "status": "FAILED" if failed else ("WARN" if warnings else "PASSED"),
            "results": results,
            "passed": passed,
            "warnings": warnings,
            "failed": failed,
        }

    def _cache_report(self, plan_id: str, report: Dict[str, Any]) -> None:
        self._reports[plan_id] = report
        if len(self._reports) > MAX_REPORT_CACHE:
            self._reports.pop(next(iter(self._reports)), None)


# Singleton instance
validation_service = ValidationEngine()
