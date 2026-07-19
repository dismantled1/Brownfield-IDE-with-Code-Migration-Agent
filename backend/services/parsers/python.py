import ast
from typing import Dict, Any, List, Optional
from backend.services.parsers.base import LanguageParser

class PythonParser(LanguageParser):
    """
    AST-based parser for Python source code files.
    """

    def parse(self, code: str, filepath: str) -> Dict[str, Any]:
        try:
            tree = ast.parse(code)
        except Exception:
            # Return basic empty structure if syntax is invalid or parse fails
            return {"classes": [], "functions": [], "imports": []}

        classes = []
        functions = []
        imports = []

        for node in tree.body:
            # 1. Imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({
                        "source": alias.name,
                        "is_internal": False,
                        "imported_names": [alias.asname or alias.name]
                    })
            elif isinstance(node, ast.ImportFrom):
                source = ""
                if node.level > 0:
                    source += "." * node.level
                if node.module:
                    source += node.module
                names = [alias.name for alias in node.names]
                imports.append({
                    "source": source,
                    "is_internal": node.level > 0 or source.startswith('.'),
                    "imported_names": names
                })

            # 2. Classes
            elif isinstance(node, ast.ClassDef):
                methods = []
                for subnode in node.body:
                    if isinstance(subnode, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        args = [arg.arg for arg in subnode.args.args]
                        methods.append({
                            "name": subnode.name,
                            "args": args,
                            "line_start": subnode.lineno,
                            "line_end": getattr(subnode, "end_lineno", subnode.lineno),
                            "docstring": ast.get_docstring(subnode)
                        })
                
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        bases.append(f"{base.attr}")
                    else:
                        try:
                            bases.append(ast.unparse(base))
                        except Exception:
                            bases.append(str(base))

                classes.append({
                    "name": node.name,
                    "line_start": node.lineno,
                    "line_end": getattr(node, "end_lineno", node.lineno),
                    "docstring": ast.get_docstring(node),
                    "bases": bases,
                    "methods": methods
                })

            # 3. Module-level Functions
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [arg.arg for arg in node.args.args]
                functions.append({
                    "name": node.name,
                    "args": args,
                    "line_start": node.lineno,
                    "line_end": getattr(node, "end_lineno", node.lineno),
                    "docstring": ast.get_docstring(node)
                })

        return {
            "classes": classes,
            "functions": functions,
            "imports": imports
        }
