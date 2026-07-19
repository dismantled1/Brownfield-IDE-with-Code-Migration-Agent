import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from backend.services.analysis_service import analysis_manager
from backend.services.llm import get_active_provider

logger = logging.getLogger(__name__)

class AIService:
    """
    AI Assistant Service. Generates code element explanations using
    either an LLM API (via the unified Provider Layer) or a detailed local structural template.
    """

    def __init__(self):
        pass

    def explain(
        self,
        scope: str,
        target: str,
        active_file: Optional[str] = None,
        cursor_line: Optional[int] = None
    ) -> str:
        """
        Main entry point to explain a project component.
        
        Args:
            scope (str): project, module, file, class, or function
            target (str): target symbol or file name
            active_file (str): active editor relative path
            cursor_line (int): active line number in editor
            
        Returns:
            str: Markdown explanation
        """
        # Ensure analysis has run
        if not analysis_manager.files:
            return (
                "### No Project Analyzed Yet\n\n"
                "Please open a project or wait for the initial project analysis to complete "
                "before requesting explanations."
            )

        # 1. Resolve target details using context if parameters are empty
        resolved_scope, resolved_target, context_data = self._resolve_context(
            scope, target, active_file, cursor_line
        )

        if not resolved_target and resolved_scope != "project":
            return (
                f"### Explanation Failed\n\n"
                f"Could not determine the target {resolved_scope} to explain. "
                f"Please open a relevant file or place your cursor on a class/function."
            )

        # 2. Check for active provider and fetch explanation
        explanation = None
        provider = get_active_provider()
        if provider:
            prompt = self._build_prompt_text(resolved_scope, resolved_target, context_data)
            system = (
                "You are Antigravity, an AI assistant integrated into a development environment. "
                "Write clear, technical, developer-oriented Markdown explanations of codebase elements "
                "based on the parsed metadata context provided."
            )
            result = provider.generate(prompt, system=system)
            if result.ok:
                explanation = result.text

        # 3. Fallback to Local Explanation Engine
        if not explanation:
            explanation = self._generate_local_explanation(resolved_scope, resolved_target, context_data)

        return explanation

    def _resolve_context(
        self,
        scope: str,
        target: str,
        active_file: Optional[str],
        cursor_line: Optional[int]
    ) -> Tuple[str, str, Dict[str, Any]]:
        """Identify which file/class/function to explain and fetch its structure."""
        scope = scope.lower().strip()
        target = target.strip()
        context = {}

        # Default fallback
        if not active_file and analysis_manager.files:
            active_file = list(analysis_manager.files.keys())[0]

        # Case 1: Project Scope
        if scope == "project":
            context = {
                "stats": analysis_manager.stats,
                "modules": list(analysis_manager.modules.keys()),
                "files_summary": {path: f.get("summary") for path, f in analysis_manager.files.items()}
            }
            return "project", analysis_manager.project_path, context

        # Case 2: File Scope
        if scope == "file":
            file_path = target if target else (active_file or "")
            # Canonicalize relative path
            file_path = file_path.replace("\\", "/")
            
            # Look up file_path
            file_data = analysis_manager.files.get(file_path)
            if not file_data:
                # Try finding file name matches
                for path in analysis_manager.files.keys():
                    if path.endswith(file_path) or file_path in path:
                        file_path = path
                        file_data = analysis_manager.files[path]
                        break

            if file_data:
                context = {
                    "file_data": file_data,
                    "dependencies": analysis_manager.relationships["imports"].get(file_path, []),
                    "referenced_by": [k for k, v in analysis_manager.relationships["imports"].items() if file_path in v]
                }
                return "file", file_path, context
            return "file", target, {}

        # Case 3: Module Scope
        if scope == "module":
            module_name = target
            if not module_name and active_file:
                parts = active_file.replace("\\", "/").split("/")
                module_name = parts[0] if len(parts) > 1 else "root"
            
            if module_name in analysis_manager.modules:
                files_in_module = analysis_manager.modules[module_name]
                context = {
                    "module_name": module_name,
                    "files": files_in_module,
                    "summaries": {f: analysis_manager.files[f].get("summary") for f in files_in_module}
                }
                return "module", module_name, context
            return "module", target, {}

        # Case 4: Class Scope
        if scope == "class":
            class_name = target
            file_path = active_file
            
            # If class_name not specified, look for cursor or active file classes
            if not class_name and file_path:
                file_data = analysis_manager.files.get(file_path)
                if file_data:
                    # Check cursor positioning
                    if cursor_line:
                        for cls in file_data.get("classes", []):
                            if cls["line_start"] <= cursor_line <= cls["line_end"]:
                                class_name = cls["name"]
                                break
                    # Fallback to first class in active file
                    if not class_name and file_data.get("classes"):
                        class_name = file_data["classes"][0]["name"]

            # Look up class in all files
            for path, f_data in analysis_manager.files.items():
                for cls in f_data.get("classes", []):
                    if cls["name"] == class_name or class_name.lower() in cls["name"].lower():
                        class_name = cls["name"]
                        context = {
                            "class": cls,
                            "file": path,
                            "inherits_from": analysis_manager.relationships["inherits"].get(class_name, []),
                            "inherited_by": [k for k, v in analysis_manager.relationships["inherits"].items() if class_name in v]
                        }
                        return "class", class_name, context
            return "class", target, {}

        # Case 5: Function Scope
        if scope == "function":
            func_name = target
            file_path = active_file
            
            # Cursor position lookup
            if not func_name and file_path:
                file_data = analysis_manager.files.get(file_path)
                if file_data:
                    if cursor_line:
                        # Check class methods first
                        for cls in file_data.get("classes", []):
                            for m in cls.get("methods", []):
                                if m["line_start"] <= cursor_line <= m["line_end"]:
                                    func_name = f"{cls['name']}.{m['name']}"
                                    break
                            if func_name:
                                break
                        # Check module functions
                        if not func_name:
                            for func in file_data.get("functions", []):
                                if func["line_start"] <= cursor_line <= func["line_end"]:
                                    func_name = func["name"]
                                    break
                    # Fallback to first module-level function
                    if not func_name and file_data.get("functions"):
                        func_name = file_data["functions"][0]["name"]

            # Search in project database
            if func_name:
                parts = func_name.split(".")
                if len(parts) == 2:
                    cls_name, met_name = parts
                    for path, f_data in analysis_manager.files.items():
                        for cls in f_data.get("classes", []):
                            if cls["name"] == cls_name:
                                for m in cls.get("methods", []):
                                    if m["name"] == met_name:
                                        context = {
                                            "function": m,
                                            "class_name": cls_name,
                                            "file": path
                                        }
                                        return "function", func_name, context
                else:
                    for path, f_data in analysis_manager.files.items():
                        for func in f_data.get("functions", []):
                            if func["name"] == func_name:
                                context = {
                                    "function": func,
                                    "file": path
                                }
                                return "function", func_name, context
            return "function", target, {}

        return scope, target, context



    def _build_prompt_text(self, scope: str, target: str, context: Dict[str, Any]) -> str:
        return (
            f"Please explain this codebase target: '{target}' (Scope: '{scope}').\n\n"
            f"Below is the exact parsed structural metadata extracted from the project analysis engine:\n\n"
            f"```json\n{json.dumps(context, indent=2)}\n```\n\n"
            f"Provide a clear description of its purpose, inputs/outputs (if applicable), relationships, "
            f"and usage. Format your response beautifully in Markdown."
        )

    def _generate_local_explanation(self, scope: str, target: str, context: Dict[str, Any]) -> str:
        """Local explanation generator fallback in case of no internet or missing keys."""
        if scope == "project":
            stats = context.get("stats", {})
            modules_list = context.get("modules", [])
            files_summary = context.get("files_summary", {})
            
            # Formatting language lists
            languages = "\n".join([f"- **{lang}**: {pct}%" for lang, pct in stats.get("languages", {}).items()])
            modules = "\n".join([f"- **{m}** ({len(analysis_manager.modules[m])} files)" for m in modules_list])
            
            summary = (
                f"# Project Overview\n\n"
                f"Project root directory: `{target}`\n\n"
                f"### Detected Technology Stack\n"
                f"{languages}\n\n"
                f"### Codebase Statistics\n"
                f"- **Total Files**: {stats.get('files', 0)}\n"
                f"- **Total Folders**: {stats.get('folders', 0)}\n"
                f"- **Total Modules**: {stats.get('modules', 0)}\n"
                f"- **Total Classes**: {stats.get('classes', 0)}\n"
                f"- **Total Functions/Methods**: {stats.get('functions', 0)}\n\n"
                f"### Main Modules\n"
                f"{modules}\n\n"
                f"### Key Entry Points & Structure\n"
                f"The project structure contains first-level directories as module boundaries. "
                f"To inspect further, expand the modules in the sidebar or ask to explain a specific file."
            )
            return summary

        if scope == "module":
            files = context.get("files", [])
            summaries = context.get("summaries", {})
            file_rows = "\n".join([f"- [`{f}`](file:///{analysis_manager.project_path}/{f}): {summaries.get(f, 'Source file.')}" for f in files])
            
            # Module imports
            imports = set()
            for f in files:
                for imp in analysis_manager.relationships["imports"].get(f, []):
                    # check if importing outside the module
                    if not imp.startswith(target + "/"):
                        imports.add(imp)
            
            imports_str = "\n".join([f"- `{imp}`" for imp in sorted(list(imports))]) or "*None*"
            
            return (
                f"# Module: {target}\n\n"
                f"This directory houses module services and structural components.\n\n"
                f"### Files List\n"
                f"{file_rows}\n\n"
                f"### External & cross-module dependencies\n"
                f"{imports_str}"
            )

        if scope == "file":
            fd = context.get("file_data", {})
            classes = fd.get("classes", [])
            functions = fd.get("functions", [])
            deps = context.get("dependencies", [])
            ref_by = context.get("referenced_by", [])
            
            classes_str = "\n".join([f"- **Class `{c['name']}`** (lines {c['line_start']}-{c['line_end']}): {c.get('docstring') or '*No docstring*'}" for c in classes]) or "*None*"
            funcs_str = "\n".join([f"- **Function `{f['name']}`** (lines {f['line_start']}-{f['line_end']}): {f.get('docstring') or '*No docstring*'}" for f in functions]) or "*None*"
            deps_str = "\n".join([f"- `{d}`" for d in deps]) or "*None*"
            ref_by_str = "\n".join([f"- `{r}`" for r in ref_by]) or "*None*"
            
            return (
                f"# File: {target}\n\n"
                f"**Path**: [`{target}`](file:///{analysis_manager.project_path}/{target})\n"
                f"**Language**: `{fd.get('language', '').upper()}` | **Size**: {fd.get('size', 0)} bytes\n\n"
                f"### Purpose / Overview\n"
                f"{fd.get('summary', 'Source file.')}\n\n"
                f"### Defined Classes\n"
                f"{classes_str}\n\n"
                f"### Defined Functions\n"
                f"{funcs_str}\n\n"
                f"### Dependencies (Imports)\n"
                f"{deps_str}\n\n"
                f"### Imported by\n"
                f"{ref_by_str}"
            )

        if scope == "class":
            cls = context.get("class", {})
            file_path = context.get("file", "")
            methods = cls.get("methods", [])
            bases = context.get("inherits_from", [])
            inherited_by = context.get("inherited_by", [])
            
            bases_str = ", ".join([f"`{b}`" for b in bases]) if bases else "*None (Base Object)*"
            inherited_str = ", ".join([f"`{i}`" for i in inherited_by]) if inherited_by else "*None*"
            
            methods_rows = []
            for m in methods:
                args = ", ".join(m.get("args", []))
                methods_rows.append(
                    f"- **`{m['name']}({args})`** (lines {m['line_start']}-{m['line_end']})\n"
                    f"  {m.get('docstring') or '*No description available*'}"
                )
            methods_str = "\n".join(methods_rows) or "*None*"
            
            return (
                f"# Class: {target}\n\n"
                f"Defined in: [`{file_path}`](file:///{analysis_manager.project_path}/{file_path}) (lines {cls.get('line_start')}-{cls.get('line_end')})\n\n"
                f"### Description\n"
                f"{cls.get('docstring') or '*No class-level docstring available.*'}\n\n"
                f"### Inheritance\n"
                f"- **Extends**: {bases_str}\n"
                f"- **Extended by**: {inherited_str}\n\n"
                f"### Methods / Interfaces\n"
                f"{methods_str}\n\n"
                f"### Usage Blueprint\n"
                f"```python\n"
                f"# Initialisation template\n"
                f"instance = {target}()\n"
                f"```"
            )

        if scope == "function":
            fn = context.get("function", {})
            cls_name = context.get("class_name")
            file_path = context.get("file", "")
            args = ", ".join(fn.get("args", []))
            
            prefix = f"{cls_name}." if cls_name else ""
            
            args_list = fn.get("args", [])
            args_str = "\n".join([f"- `{a}`" for a in args_list]) if args_list else "*No parameters*"
            return (
                f"# Function: {prefix}{target}\n\n"
                f"Defined in: [`{file_path}`](file:///{analysis_manager.project_path}/{file_path}) (lines {fn.get('line_start')}-{fn.get('line_end')})\n\n"
                f"### Signature\n"
                f"`{fn['name']}({args})`\n\n"
                f"### Description / Purpose\n"
                f"{fn.get('docstring') or '*No docstring available for this block.*'}\n\n"
                f"### Arguments\n"
                f"{args_str}\n\n"
                f"### Reference Analysis\n"
                f"This function is part of the file namespace. You can call it locally inside the module."
            )

        return f"Explanation for target '{target}' of type '{scope}' not found."

# Singleton instance
ai_service = AIService()
