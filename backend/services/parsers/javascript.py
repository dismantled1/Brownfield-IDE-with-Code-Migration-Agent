import re
from typing import Dict, Any, List, Optional
from backend.services.parsers.base import LanguageParser

class JavaScriptParser(LanguageParser):
    """
    Regex and line-by-line structural parser for JavaScript and TypeScript.
    """

    def parse(self, code: str, filepath: str) -> Dict[str, Any]:
        lines = code.splitlines()
        classes = []
        functions = []
        imports = []
        
        # Accumulators for comments
        current_comment = []
        in_comment = False
        last_comment = None
        
        # Scope and brace depth tracking
        in_class = None
        class_brace_depth = 0
        brace_depth = 0

        def clean_args(args_str: str) -> List[str]:
            """Helper to extract parameter names and strip TS type annotations."""
            params = []
            for arg in args_str.split(","):
                arg = arg.strip()
                if not arg:
                    continue
                # Strip TS types, e.g. "param: string" -> "param"
                name = arg.split(":")[0].strip()
                # Strip default values, e.g. "param = default" -> "param"
                name = name.split("=")[0].strip()
                # Clean rest parameter, e.g. "...param" -> "param"
                if name.startswith("..."):
                    name = name[3:]
                if name:
                    params.append(name)
            return params

        for idx, line in enumerate(lines):
            line_num = idx + 1
            stripped = line.strip()

            # Per-iteration match state. These are referenced by the docstring-reset
            # check at the end of the loop, so they must always be defined even when
            # the corresponding branch below isn't taken.
            method_match = None
            func_match = None
            arrow_match = None

            # 1. Parse comments (Block comments /* ... */ and Single-line //)
            if in_comment:
                if "*/" in stripped:
                    in_comment = False
                    end_idx = stripped.find("*/")
                    comment_part = stripped[:end_idx]
                    if comment_part:
                        current_comment.append(comment_part.replace("*", "").strip())
                    last_comment = "\n".join(current_comment).strip()
                    current_comment = []
                else:
                    comment_content = stripped.lstrip("*").strip()
                    current_comment.append(comment_content)
                continue
                
            if stripped.startswith("/*") or stripped.startswith("/**"):
                in_comment = True
                start_idx = stripped.find("/*") + 2
                if "*/" in stripped:
                    in_comment = False
                    end_idx = stripped.find("*/")
                    comment_part = stripped[start_idx:end_idx]
                    last_comment = comment_part.replace("*", "").strip()
                else:
                    comment_part = stripped[start_idx:]
                    current_comment.append(comment_part.lstrip("*").strip())
                continue
                
            if stripped.startswith("//"):
                comment_content = stripped[2:].strip()
                if last_comment:
                    last_comment += "\n" + comment_content
                else:
                    last_comment = comment_content
                continue
            
            # Check braces in current line
            opening_braces = stripped.count("{")
            closing_braces = stripped.count("}")

            # 2. Parse imports
            # ESM: import { x } from 'y'; import * as z from 'y'; import 'y';
            esm_match = re.match(r"^import\s+(?:([\s\S]*?)\s+from\s+)?['\"]([^'\"]+)['\"]", stripped)
            if esm_match:
                imported, source = esm_match.groups()
                names = []
                if imported:
                    imported_clean = imported.replace("{", "").replace("}", "").strip()
                    names = [n.strip() for n in imported_clean.split(",") if n.strip()]
                imports.append({
                    "source": source,
                    "is_internal": source.startswith(".") or source.startswith("/"),
                    "imported_names": names
                })
                last_comment = None
                continue
                
            # CommonJS: const x = require('y')
            cjs_match = re.match(r"^(?:const|let|var)\s+([\s\S]*?)\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", stripped)
            if cjs_match:
                imported, source = cjs_match.groups()
                imported_clean = imported.replace("{", "").replace("}", "").strip()
                names = [n.strip() for n in imported_clean.split(",") if n.strip()]
                imports.append({
                    "source": source,
                    "is_internal": source.startswith(".") or source.startswith("/"),
                    "imported_names": names
                })
                last_comment = None
                continue

            # 3. Class declarations
            class_match = re.match(r"^(?:export\s+(?:default\s+)?)?class\s+([a-zA-Z0-9_]+)(?:\s+extends\s+([a-zA-Z0-9_\.]+))?", stripped)
            if class_match:
                class_name, parent_name = class_match.groups()
                in_class = {
                    "name": class_name,
                    "line_start": line_num,
                    "line_end": line_num,
                    "docstring": last_comment,
                    "bases": [parent_name] if parent_name else [],
                    "methods": []
                }
                classes.append(in_class)
                class_brace_depth = brace_depth
                brace_depth += opening_braces - closing_braces
                last_comment = None
                continue
            
            # 4. Class Methods vs. Module Functions
            if in_class and brace_depth > class_brace_depth:
                # Class method: async method(args) { or method(args) {
                method_match = re.match(r"^(?:public|private|protected|async|static|\*)*\s*([a-zA-Z0-9_]+)\s*\(([^)]*)\)\s*[^\{]*\{?", stripped)
                if method_match:
                    method_name, args_str = method_match.groups()
                    if method_name not in ["if", "for", "while", "switch", "catch", "return", "super", "this"]:
                        in_class["methods"].append({
                            "name": method_name,
                            "args": clean_args(args_str),
                            "line_start": line_num,
                            "line_end": line_num,  # updated when block closes
                            "docstring": last_comment
                        })
                        last_comment = None
            else:
                # Module function: function f(x) {
                func_match = re.match(r"^(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+([a-zA-Z0-9_]+)\s*\(([^)]*)\)", stripped)
                if func_match:
                    func_name, args_str = func_match.groups()
                    functions.append({
                        "name": func_name,
                        "args": clean_args(args_str),
                        "line_start": line_num,
                        "line_end": line_num,
                        "docstring": last_comment
                    })
                    last_comment = None
                else:
                    # Arrow function: const f = (x) => {
                    arrow_match = re.match(r"^(?:export\s+(?:default\s+)?)?(?:const|let|var)\s+([a-zA-Z0-9_]+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>", stripped)
                    if arrow_match:
                        func_name, args_str = arrow_match.groups()
                        functions.append({
                            "name": func_name,
                            "args": clean_args(args_str),
                            "line_start": line_num,
                            "line_end": line_num,
                            "docstring": last_comment
                        })
                        last_comment = None
            
            # Maintain brace depth
            brace_depth += opening_braces - closing_braces
            
            # Class boundaries
            if in_class and brace_depth <= class_brace_depth:
                in_class["line_end"] = line_num
                for m in in_class["methods"]:
                    if m["line_end"] == m["line_start"]:
                        m["line_end"] = line_num
                in_class = None

            # Reset docstring after encountering a non-comment non-empty line
            if stripped and not (stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*")):
                if not (class_match or esm_match or cjs_match or (in_class and method_match) or func_match or arrow_match):
                    last_comment = None

        return {
            "classes": classes,
            "functions": functions,
            "imports": imports
        }
