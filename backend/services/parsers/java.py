import re
from typing import Dict, Any, List, Optional
from backend.services.parsers.base import LanguageParser

class JavaParser(LanguageParser):
    """
    Regex and line-by-line structural parser for Java code.
    """

    def parse(self, code: str, filepath: str) -> Dict[str, Any]:
        lines = code.splitlines()
        classes = []
        functions = []  # Java has no package-level functions
        imports = []
        
        current_comment = []
        in_comment = False
        last_comment = None
        
        in_class = None
        class_brace_depth = 0
        brace_depth = 0

        def clean_args(args_str: str) -> List[str]:
            params = []
            for arg in args_str.split(","):
                arg = arg.strip()
                if not arg:
                    continue
                # Java arguments are formatted as "Type name" or "Type... name"
                parts = arg.split()
                if parts:
                    params.append(parts[-1])
            return params

        for idx, line in enumerate(lines):
            line_num = idx + 1
            stripped = line.strip()
            
            # 1. Parse Comments
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
            
            opening_braces = stripped.count("{")
            closing_braces = stripped.count("}")

            # 2. Parse Imports
            import_match = re.match(r"^import\s+([a-zA-Z0-9_\.\*]+);", stripped)
            if import_match:
                source = import_match.group(1)
                imports.append({
                    "source": source,
                    "is_internal": source.startswith("com.brownfield.") or source.startswith("org.brownfield."),
                    "imported_names": [source.split(".")[-1]]
                })
                last_comment = None
                continue

            # 3. Parse Classes / Interfaces / Enums
            class_match = re.match(
                r"^(?:public|protected|private|abstract|static|final|\s)*\b(class|interface|enum)\b\s+([a-zA-Z0-9_<>]+)(?:\s+extends\s+([a-zA-Z0-9_<>]+))?",
                stripped
            )
            if class_match:
                type_kind, class_name, parent_name = class_match.groups()
                class_name = class_name.split("<")[0]
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

            # 4. Parse Methods (Inside Class)
            if in_class and brace_depth > class_brace_depth:
                method_match = re.match(
                    r"^(?:public|protected|private|static|final|synchronized|abstract|default|native|\s)+(?:[a-zA-Z0-9_<>\[\]\?]+)\s+([a-zA-Z0-9_]+)\s*\(([^)]*)\)\s*(?:throws\s+[a-zA-Z0-9_,\s]+)?\s*\{?",
                    stripped
                )
                if method_match:
                    method_name, args_str = method_match.groups()
                    if method_name not in ["if", "for", "while", "switch", "catch", "return", "new", "throw", "assert", "super", "this"]:
                        in_class["methods"].append({
                            "name": method_name,
                            "args": clean_args(args_str),
                            "line_start": line_num,
                            "line_end": line_num,
                            "docstring": last_comment
                        })
                        last_comment = None

            # Maintain depth
            brace_depth += opening_braces - closing_braces
            
            # Close class boundary
            if in_class and brace_depth <= class_brace_depth:
                in_class["line_end"] = line_num
                for m in in_class["methods"]:
                    if m["line_end"] == m["line_start"]:
                        m["line_end"] = line_num
                in_class = None

            # Reset docstring
            if stripped and not (stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*")):
                if not (class_match or import_match or (in_class and method_match)):
                    last_comment = None

        return {
            "classes": classes,
            "functions": functions,
            "imports": imports
        }
