import os
import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple, Optional
from backend.services.analysis_service import analysis_manager
from backend.services.search_service import search_service

logger = logging.getLogger(__name__)

# Critical paths or modules that raise risk levels
CRITICAL_KEYWORDS = {"auth", "payment", "security", "login", "db", "config", "core", "billing", "checkout"}

class ImpactService:
    """
    Impact Analysis Engine. Builds and maintains a dependency graph of files, classes,
    functions, modules, and APIs using the knowledge model and search indexes.
    Traces propagation paths of proposed changes and assesses risk.
    """

    def __init__(self):
        self.project_path = ""
        self._graph_cache = {}
        self._last_analyzed_at = ""
        
        # Dependency mappings: key is the callee/dependency, value is a set of callers/dependents
        self.file_dependents: Dict[str, Set[str]] = {}  # file -> files that import it
        self.class_dependents: Dict[str, Set[str]] = {} # class_name -> classes that inherit/reference it
        self.class_parents: Dict[str, Set[str]] = {}    # class_name -> base classes in project
        self.class_children: Dict[str, Set[str]] = {}   # class_name -> direct subclasses
        self.func_dependents: Dict[str, Set[str]] = {}  # func/method -> funcs that call it
        
        # Outward mappings for finding callee/outward dependencies
        self.file_dependencies: Dict[str, Set[str]] = {}
        self.class_dependencies: Dict[str, Set[str]] = {}
        self.func_dependencies: Dict[str, Set[str]] = {}
        
        # Meta lists for fast lookup
        self.defined_classes: Dict[str, Dict[str, Any]] = {}  # class_name -> {file, line}
        self.defined_funcs: Dict[str, Dict[str, Any]] = {}    # func_signature -> {file, line, name}
        self.circular_paths: List[List[str]] = []

    def ensure_graph_ready(self, project_root: str, force: bool = False) -> None:
        """Ensure the dependency graph is built and matches the current analysis."""
        resolved = str(Path(project_root).resolve())
        if not force and self.project_path == resolved and self.file_dependents:
            return

        self.project_path = resolved
        search_service.ensure_indexed(self.project_path)

        # Check if analysis_manager has active data
        if not analysis_manager.files:
            cache_path = analysis_manager._get_cache_path(self.project_path)
            cache_data = analysis_manager._load_cache(cache_path)
            if cache_data:
                analysis_manager.project_path = cache_data.get("project_path", "")
                analysis_manager.files = cache_data.get("files", {})
                analysis_manager.modules = cache_data.get("modules", {})
                analysis_manager.relationships = cache_data.get("relationships", {})
                analysis_manager.stats = cache_data.get("stats", {})
                analysis_manager.analyzed_at = cache_data.get("analyzed_at", "")
            else:
                logger.warning("No analysis cache found. Graph will be empty until analysis completes.")

        # Rebuild graph if needed
        current_analyzed_at = analysis_manager.analyzed_at
        if force or current_analyzed_at != self._last_analyzed_at or not self.file_dependents:
            logger.info("Building dependency graph from analysis knowledge model...")
            self._build_dependency_graph()
            self._last_analyzed_at = current_analyzed_at

    def _build_dependency_graph(self) -> None:
        """Construct the call, import, inheritance, and module dependency maps."""
        # Reset structures
        self.file_dependents.clear()
        self.class_dependents.clear()
        self.class_parents.clear()
        self.class_children.clear()
        self.func_dependents.clear()
        
        self.file_dependencies.clear()
        self.class_dependencies.clear()
        self.func_dependencies.clear()
        
        self.defined_classes.clear()
        self.defined_funcs.clear()
        self.circular_paths.clear()

        all_files = list(analysis_manager.files.keys())
        
        # 1. Map all files in the depend maps
        for f in all_files:
            self.file_dependents[f] = set()
            self.file_dependencies[f] = set()

        # 2. Populate file-level imports mapping
        for file_path, file_data in analysis_manager.files.items():
            imports = analysis_manager.relationships.get("imports", {}).get(file_path, [])
            for imp in imports:
                if imp in self.file_dependents:
                    self.file_dependents[imp].add(file_path)
                    self.file_dependencies[file_path].add(imp)

        # 3. Populate defined classes & class relationships (Inheritance)
        for file_path, file_data in analysis_manager.files.items():
            for cls in file_data.get("classes", []):
                cls_name = cls["name"]
                self.defined_classes[cls_name] = {
                    "file": file_path,
                    "line": cls["line_start"],
                    "bases": cls.get("bases", [])
                }
                self.class_dependents[cls_name] = set()
                self.class_dependencies[cls_name] = set()
                self.class_parents[cls_name] = set()
                self.class_children[cls_name] = set()

        # Establish inheritance links
        for cls_name, cls_meta in self.defined_classes.items():
            for base in cls_meta["bases"]:
                # If the base class is defined in the project, map it
                if base in self.defined_classes:
                    self.class_children[base].add(cls_name)
                    self.class_parents[cls_name].add(base)
                    self.class_dependents[base].add(cls_name)
                    self.class_dependencies[cls_name].add(base)

        # 4. Populate defined functions index
        for file_path, file_data in analysis_manager.files.items():
            # Module-level functions
            for func in file_data.get("functions", []):
                func_name = func["name"]
                # Signature: file_path::func_name
                sig = f"{file_path}::{func_name}"
                self.defined_funcs[sig] = {
                    "file": file_path,
                    "line": func["line_start"],
                    "line_end": func["line_end"],
                    "name": func_name,
                    "class": None
                }
                self.func_dependents[sig] = set()
                self.func_dependencies[sig] = set()

            # Class methods
            for cls in file_data.get("classes", []):
                cls_name = cls["name"]
                for method in cls.get("methods", []):
                    m_name = method["name"]
                    # Signature: file_path::class_name::method_name
                    sig = f"{file_path}::{cls_name}::{m_name}"
                    self.defined_funcs[sig] = {
                        "file": file_path,
                        "line": method["line_start"],
                        "line_end": method["line_end"],
                        "name": m_name,
                        "class": cls_name
                    }
                    self.func_dependents[sig] = set()
                    self.func_dependencies[sig] = set()

        # Index function names → signatures so call detection is O(tokens) per
        # body instead of O(all functions) regex scans per body.
        name_to_sigs: Dict[str, List[str]] = {}
        for sig, meta in self.defined_funcs.items():
            name_to_sigs.setdefault(meta["name"], []).append(sig)

        # Group function signatures by their defining file (avoids re-scanning
        # the full defined_funcs map once per file).
        funcs_by_file: Dict[str, List[str]] = {}
        for sig, meta in self.defined_funcs.items():
            funcs_by_file.setdefault(meta["file"], []).append(sig)

        # 5 & 6. Single read per file: extract function-call and class-reference edges.
        for file_path, file_data in analysis_manager.files.items():
            full_path = Path(self.project_path) / file_path
            if not full_path.exists():
                continue
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
            except Exception as e:
                logger.error(f"Failed to read file {file_path} for graph: {e}")
                continue

            lines = content.splitlines(keepends=True)

            # 5. Function calls — tokenize each function body once, then look up
            #    matching callee signatures by name.
            for caller_sig in funcs_by_file.get(file_path, []):
                caller_meta = self.defined_funcs[caller_sig]
                start = max(0, caller_meta["line"] - 1)
                end = caller_meta["line_end"]
                body_content = "".join(lines[start:end])
                for token in set(re.findall(r"\b\w+\b", body_content)):
                    for callee_sig in name_to_sigs.get(token, ()):
                        if callee_sig == caller_sig:
                            continue
                        self.func_dependents[callee_sig].add(caller_sig)
                        self.func_dependencies[caller_sig].add(callee_sig)

            # 6. Class references/instantiations — tokenize the whole file once.
            file_tokens = set(re.findall(r"\b\w+\b", content))
            referencing_classes = [c["name"] for c in file_data.get("classes", [])]
            for target_cls, target_meta in self.defined_classes.items():
                if target_meta["file"] != file_path and target_cls in file_tokens:
                    for ref_cls in referencing_classes:
                        self.class_dependents[target_cls].add(ref_cls)
                        self.class_dependencies[ref_cls].add(target_cls)

        # 7. Check for circular dependencies at file level
        self._detect_circular_dependencies()

    def _detect_circular_dependencies(self) -> None:
        """Detect file-level circular import cycles using Tarjan's or DFS backtracking."""
        visited = set()
        stack = []
        path = []

        def dfs(node: str):
            if node in stack:
                cycle_start = stack.index(node)
                cycle = stack[cycle_start:] + [node]
                self.circular_paths.append(cycle)
                return
            if node in visited:
                return

            visited.add(node)
            stack.append(node)
            for neighbor in self.file_dependencies.get(node, []):
                dfs(neighbor)
            stack.pop()

        for f in self.file_dependents.keys():
            if f not in visited:
                dfs(f)

    # ---------------------------------------------------------------------------
    # Tracing core logic
    # ---------------------------------------------------------------------------

    def analyze_file_impact(self, target_file: str) -> Dict[str, Any]:
        """Compute files directly and indirectly affected by changes to target_file."""
        # Standardize target_file path
        target_file = target_file.replace("\\", "/").strip()
        
        # Verify file exists in analysis records
        if target_file not in self.file_dependents:
            # Fallback search if path is partial
            matched = [f for f in self.file_dependents.keys() if target_file in f]
            if matched:
                target_file = matched[0]
            else:
                return {"direct": [], "indirect": [], "chains": []}

        direct = list(self.file_dependents[target_file])
        indirect = []
        chains = []

        # BFS for transitive propagation
        visited = {target_file}
        # Keep track of paths/chains for explanation: element -> path list
        paths = {target_file: [target_file]}
        queue = [(target_file, 0)]

        while queue:
            curr, depth = queue.pop(0)
            
            for dep in self.file_dependents.get(curr, []):
                if dep not in visited:
                    visited.add(dep)
                    paths[dep] = paths[curr] + [dep]
                    if dep not in direct:
                        indirect.append(dep)
                    chains.append(" -> ".join(paths[dep]))
                    queue.append((dep, depth + 1))

        return {
            "target": target_file,
            "direct": direct,
            "indirect": indirect,
            "chains": chains
        }

    def analyze_class_impact(self, class_name: str) -> Dict[str, Any]:
        """Compute impact of changes to a class."""
        class_name = class_name.strip()
        if class_name not in self.class_dependents:
            return {"calling": [], "referencing": [], "child": [], "parent": [], "chains": []}

        # Parent/Super classes
        parents = list(self.class_parents.get(class_name, []))
        
        # Direct child classes (inheritance)
        children = []
        # Calling/referencing classes
        referencing = []

        # Transitively affected classes
        visited = {class_name}
        paths = {class_name: [class_name]}
        queue = [class_name]
        chains = []

        while queue:
            curr = queue.pop(0)
            for dep in self.class_dependents.get(curr, []):
                if dep not in visited:
                    visited.add(dep)
                    paths[dep] = paths[curr] + [dep]
                    chains.append(" -> ".join(paths[dep]))
                    
                    # Distinguish between subclass and simple reference
                    is_subclass = dep in self.class_children.get(curr, [])
                    if is_subclass and (curr == class_name or curr in children):
                        children.append(dep)
                    else:
                        referencing.append(dep)
                        
                    queue.append(dep)

        return {
            "target": class_name,
            "parent": parents,
            "child": children,
            "calling": referencing,
            "chains": chains
        }

    def analyze_function_impact(self, func_name: str) -> Dict[str, Any]:
        """Compute impact of changing validateUser() or module-level functions."""
        func_name = func_name.strip()
        
        # Match function signature in global defined functions
        matched_sigs = [sig for sig in self.defined_funcs.keys() if func_name == sig or sig.split("::")[-1] == func_name]
        
        if not matched_sigs:
            return {"calling": [], "dependent": [], "hierarchy": [], "target": func_name}

        # Trace callers (incoming) and dependent callees (outgoing)
        primary_sig = matched_sigs[0]
        
        # BFS for callers (who call this function -> incoming dependents)
        callers = []
        visited_callers = {primary_sig}
        caller_paths = {primary_sig: [primary_sig]}
        queue = [primary_sig]
        hierarchy = []

        while queue:
            curr = queue.pop(0)
            for caller in self.func_dependents.get(curr, []):
                if caller not in visited_callers:
                    visited_callers.add(caller)
                    caller_paths[caller] = caller_paths[curr] + [caller]
                    callers.append(caller)
                    
                    # Convert signatures to readable format for hierarchy display
                    readable_path = " <- ".join([sig.split("::")[-1] for sig in reversed(caller_paths[caller])])
                    hierarchy.append(readable_path)
                    queue.append(caller)

        # BFS for dependent functions (functions called by this function -> outgoing dependencies)
        callees = []
        visited_callees = {primary_sig}
        queue = [primary_sig]

        while queue:
            curr = queue.pop(0)
            for callee in self.func_dependencies.get(curr, []):
                if callee not in visited_callees:
                    visited_callees.add(callee)
                    callees.append(callee)
                    queue.append(callee)

        return {
            "target": primary_sig,
            "calling": callers,
            "dependent": callees,
            "hierarchy": hierarchy
        }

    def analyze_module_impact(self, module_name: str) -> Dict[str, Any]:
        """Compute dependent modules that will be affected if module_name changes."""
        module_name = module_name.strip()
        if module_name not in analysis_manager.modules:
            # Fallback checking
            matched = [m for m in analysis_manager.modules.keys() if module_name.lower() in m.lower()]
            if matched:
                module_name = matched[0]
            else:
                return {"dependents": [], "dependencies": [], "chains": []}

        # A module is affected if its files import files of our target module
        target_files = set(analysis_manager.modules[module_name])
        
        # Direct dependent modules
        direct_modules = set()
        for f in target_files:
            # Find files that import files of target module
            importing_files = self.file_dependents.get(f, set())
            for imp_file in importing_files:
                # Find importing file's module
                imp_mod = self._get_module_of_file(imp_file)
                if imp_mod and imp_mod != module_name:
                    direct_modules.add(imp_mod)

        # Tracing transitive module dependents (BFS)
        visited = {module_name}
        queue = list(direct_modules)
        visited.update(direct_modules)
        indirect_modules = []
        
        while queue:
            curr_mod = queue.pop(0)
            curr_files = set(analysis_manager.modules.get(curr_mod, []))
            
            for f in curr_files:
                importing_files = self.file_dependents.get(f, set())
                for imp_file in importing_files:
                    imp_mod = self._get_module_of_file(imp_file)
                    if imp_mod and imp_mod not in visited:
                        visited.add(imp_mod)
                        indirect_modules.append(imp_mod)
                        queue.append(imp_mod)

        # What modules does target_module depend on? (outgoing dependencies)
        outgoing_modules = set()
        for f in target_files:
            deps = self.file_dependencies.get(f, set())
            for dep_file in deps:
                dep_mod = self._get_module_of_file(dep_file)
                if dep_mod and dep_mod != module_name:
                    outgoing_modules.add(dep_mod)

        return {
            "target": module_name,
            "dependents": list(direct_modules) + indirect_modules,
            "dependencies": list(outgoing_modules),
            "chains": [f"{module_name} -> {d}" for d in direct_modules]
        }

    def analyze_api_impact(self, api_endpoint: str) -> Dict[str, Any]:
        """Trace what is affected if an API changes (controllers, services, clients)."""
        api_endpoint = api_endpoint.strip()
        
        # 1. Locate API route matching endpoint
        matched_apis = []
        for api in search_service.apis:
            route = api.get("endpoint", "")
            if api_endpoint in route or route in api_endpoint:
                matched_apis.append(api)
                
        if not matched_apis:
            return {"controllers": [], "services": [], "clients": [], "middleware": [], "target": api_endpoint}

        # Take first match
        api = matched_apis[0]
        api_file = api["file"]
        api_line = api["line"]
        
        # 2. Controllers: find controller function handling the API in the routers
        controllers = []
        # Find which function in the router file spans across the api line
        for sig, meta in self.defined_funcs.items():
            if meta["file"] == api_file and (meta["line"] - 3 <= api_line <= meta["line_end"]):
                controllers.append(sig)

        # 3. Services: Find functions called by the controller (outgoing services)
        services = []
        for ctrl in controllers:
            callees = self.func_dependencies.get(ctrl, set())
            for c in callees:
                services.append(c)

        # 4. Clients: Find files in frontend or other assets referencing this route URL string
        clients = []
        for f, file_data in analysis_manager.files.items():
            # Check javascript / html / frontend files
            if f.startswith("frontend/") or file_data.get("language") in ("js", "ts", "html"):
                full_path = Path(self.project_path) / f
                if full_path.exists():
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
                            content = fh.read()
                        # Search for route string e.g. "/api/auth/login" or similar
                        clean_endpoint = api["endpoint"].rstrip("/")
                        if clean_endpoint in content:
                            clients.append(f)
                    except Exception:
                        pass

        # 5. Middleware: Find if files containing middleware or auth are in the call path
        middleware = []
        for s in services:
            if "middleware" in s.lower() or "auth" in s.lower():
                middleware.append(s)

        return {
            "target": api["endpoint"],
            "method": api["method"],
            "controllers": controllers,
            "services": services,
            "clients": clients,
            "middleware": middleware
        }

    # ---------------------------------------------------------------------------
    # Risk and full summary logic
    # ---------------------------------------------------------------------------

    def assess_risk(self, affected_files: List[str], target_path: str) -> Dict[str, Any]:
        """Estimate the change risk level (Low, Medium, High) and provide explanation."""
        num_files = len(affected_files)
        
        # Check critical modules in paths
        critical_triggered = []
        for path in affected_files + [target_path]:
            for keyword in CRITICAL_KEYWORDS:
                if keyword in path.lower():
                    critical_triggered.append(keyword)
        critical_triggered = list(set(critical_triggered))

        # Check circular dependencies in this affected set
        has_cycles = False
        impacted_cycles = []
        for cycle in self.circular_paths:
            # If any element in the cycle is in the affected set
            if any(c_file in affected_files for c_file in cycle):
                has_cycles = True
                impacted_cycles.append(" -> ".join(cycle))

        # Compute risk
        if num_files > 7 or len(critical_triggered) >= 3 or (has_cycles and num_files >= 3):
            level = "High"
            explanation = (
                f"Modifying this component incurs High Risk. It propagates to {num_files} files "
                f"across the system. It impacts core modules ({', '.join(critical_triggered)}) "
                f"and crosses circular dependency pathways:\n"
                f"- {impacted_cycles[0] if impacted_cycles else 'Circular loops detected.'}"
            )
        elif num_files >= 3 or len(critical_triggered) > 0 or has_cycles:
            level = "Medium"
            explanation = (
                f"Modifying this component incurs Medium Risk. It affects {num_files} files. "
                + (f"It touches critical system pathways related to {', '.join(critical_triggered)}. " if critical_triggered else "")
                + ("Circular references exist in the impacted path." if has_cycles else "")
            )
        else:
            level = "Low"
            explanation = (
                f"Modifying this component is Low Risk. It has a localized impact restricted "
                f"to only {num_files} file(s) and doesn't cross critical auth or payment nodes."
            )

        return {
            "level": level,
            "explanation": explanation,
            "metrics": {
                "affected_files_count": num_files,
                "critical_modules_hit": len(critical_triggered),
                "circular_dependencies_involved": len(impacted_cycles)
            }
        }

    def get_change_summary(self, target: str, project_root: str) -> Dict[str, Any]:
        """Resolve target type, trace impacts, calculate risk, and construct overall summary."""
        self.ensure_graph_ready(project_root)
        
        # Determine the target type heuristically
        target_clean = target.strip()
        
        # 1. Is it a file path?
        all_files = list(analysis_manager.files.keys())
        matched_file = None
        for f in all_files:
            if target_clean == f or f.endswith("/" + target_clean) or f.endswith("\\" + target_clean):
                matched_file = f
                break
        if not matched_file:
            # check substring
            for f in all_files:
                if target_clean.lower() in f.lower():
                    matched_file = f
                    break

        if matched_file:
            impact = self.analyze_file_impact(matched_file)
            risk = self.assess_risk(impact["direct"] + impact["indirect"], matched_file)
            return {
                "type": "file",
                "target": matched_file,
                "summary": {
                    "files": [matched_file] + impact["direct"] + impact["indirect"],
                    "classes": self._get_classes_in_files([matched_file] + impact["direct"] + impact["indirect"]),
                    "functions": self._get_funcs_in_files([matched_file] + impact["direct"] + impact["indirect"]),
                    "modules": list({self._get_module_of_file(f) for f in [matched_file] + impact["direct"] + impact["indirect"] if self._get_module_of_file(f)}),
                    "chains": impact["chains"],
                    "risk": risk
                }
            }

        # 2. Is it a class name?
        if target_clean in self.defined_classes:
            impact = self.analyze_class_impact(target_clean)
            affected_classes = [target_clean] + impact["parent"] + impact["child"] + impact["calling"]
            affected_files = list({self.defined_classes[c]["file"] for c in affected_classes if c in self.defined_classes})
            risk = self.assess_risk(affected_files, target_clean)
            return {
                "type": "class",
                "target": target_clean,
                "summary": {
                    "files": affected_files,
                    "classes": affected_classes,
                    "functions": self._get_funcs_in_classes(affected_classes),
                    "modules": list({self._get_module_of_file(f) for f in affected_files if self._get_module_of_file(f)}),
                    "chains": impact["chains"],
                    "risk": risk
                }
            }

        # 3. Is it a function name?
        # Match signatures
        matched_sigs = [sig for sig in self.defined_funcs.keys() if target_clean == sig or sig.split("::")[-1] == target_clean]
        if matched_sigs:
            primary_sig = matched_sigs[0]
            impact = self.analyze_function_impact(primary_sig)
            affected_funcs = [primary_sig] + impact["calling"] + impact["dependent"]
            affected_files = list({self.defined_funcs[f]["file"] for f in affected_funcs if f in self.defined_funcs})
            risk = self.assess_risk(affected_files, primary_sig)
            return {
                "type": "function",
                "target": primary_sig,
                "summary": {
                    "files": affected_files,
                    "classes": list({self.defined_funcs[f]["class"] for f in affected_funcs if f in self.defined_funcs and self.defined_funcs[f]["class"]}),
                    "functions": affected_funcs,
                    "modules": list({self._get_module_of_file(f) for f in affected_files if self._get_module_of_file(f)}),
                    "chains": impact["hierarchy"],
                    "risk": risk
                }
            }

        # 4. Is it a module name?
        if target_clean in analysis_manager.modules:
            impact = self.analyze_module_impact(target_clean)
            affected_modules = [target_clean] + impact["dependents"]
            affected_files = []
            for m in affected_modules:
                affected_files.extend(analysis_manager.modules.get(m, []))
            risk = self.assess_risk(affected_files, target_clean)
            return {
                "type": "module",
                "target": target_clean,
                "summary": {
                    "files": affected_files,
                    "classes": self._get_classes_in_files(affected_files),
                    "functions": self._get_funcs_in_files(affected_files),
                    "modules": affected_modules,
                    "chains": impact["chains"],
                    "risk": risk
                }
            }

        # 5. Is it an API endpoint route?
        # Check API routers
        for api in search_service.apis:
            if target_clean in api.get("endpoint", "") or api.get("endpoint", "") in target_clean:
                impact = self.analyze_api_impact(api.get("endpoint"))
                affected_files = list(set([api["file"]] + impact["clients"]))
                affected_classes = []
                for ctrl in impact["controllers"]:
                    cls = self.defined_funcs.get(ctrl, {}).get("class")
                    if cls:
                        affected_classes.append(cls)
                risk = self.assess_risk(affected_files, api.get("endpoint"))
                return {
                    "type": "api",
                    "target": api.get("endpoint"),
                    "summary": {
                        "files": affected_files,
                        "classes": affected_classes,
                        "functions": impact["controllers"] + impact["services"],
                        "modules": list({self._get_module_of_file(f) for f in affected_files if self._get_module_of_file(f)}),
                        "chains": [f"{ctrl} -> {svc}" for ctrl in impact["controllers"] for svc in impact["services"]],
                        "risk": risk
                    }
                }

        # Return basic response if target could not be resolved
        return {
            "type": "unknown",
            "target": target_clean,
            "summary": {
                "files": [],
                "classes": [],
                "functions": [],
                "modules": [],
                "chains": [],
                "risk": {
                    "level": "Low",
                    "explanation": "No matching project component could be resolved to analyze.",
                    "metrics": {"affected_files_count": 0, "critical_modules_hit": 0, "circular_dependencies_involved": 0}
                }
            }
        }

    # ---------------------------------------------------------------------------
    # Helper utilities
    # ---------------------------------------------------------------------------

    def _get_module_of_file(self, file_path: str) -> Optional[str]:
        parts = file_path.split("/")
        return parts[0] if len(parts) > 1 else None

    def _get_classes_in_files(self, file_list: List[str]) -> List[str]:
        classes = []
        for f in file_list:
            file_data = analysis_manager.files.get(f, {})
            for c in file_data.get("classes", []):
                classes.append(c["name"])
        return classes

    def _get_funcs_in_files(self, file_list: List[str]) -> List[str]:
        funcs = []
        for f in file_list:
            file_data = analysis_manager.files.get(f, {})
            for func in file_data.get("functions", []):
                funcs.append(f"{f}::{func['name']}")
            for cls in file_data.get("classes", []):
                for method in cls.get("methods", []):
                    funcs.append(f"{f}::{cls['name']}::{method['name']}")
        return funcs

    def _get_funcs_in_classes(self, class_list: List[str]) -> List[str]:
        funcs = []
        for sig, meta in self.defined_funcs.items():
            if meta["class"] in class_list:
                funcs.append(sig)
        return funcs

# Singleton instance
impact_service = ImpactService()
