import json
from collections import deque


class RegistryManager:
    def __init__(self, registry_path: str):
        try:
            with open(registry_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        except Exception as e:
            print(f"Failed to load registry: {e}")
            self.data = {"files": {}}

        self.nodes = []
        self.edges = []
        self.adj_forward = {}   # caller -> [callees]
        self.adj_backward = {}  # callee -> [callers]

        self._build_graph()

    def _build_graph(self):
        for f_name, f_data in self.data.get("files", {}).items():
            for func in f_data.get("functions", []):
                func_id = f"{f_name}:{func['name']}"
                self.nodes.append({
                    "id": func_id,
                    "name": func["name"],
                    "file": f_name,
                    "language": f_data["language"],
                    "loader": f_data["loader"],
                    "signature": func["signature"]
                })
                self.adj_forward[func_id] = []
                self.adj_backward[func_id] = []

        for f_name, f_data in self.data.get("files", {}).items():
            for func in f_data.get("functions", []):
                caller_id = f"{f_name}:{func['name']}"
                for call in func.get("calls", []):
                    if call.get("resolved"):
                        callee_id = f"{call['target_file']}:{call['callee']}"
                        self.edges.append({
                            "from": caller_id,
                            "to": callee_id,
                            "line": call["call_line"]
                        })
                        if callee_id in self.adj_backward:
                            self.adj_forward[caller_id].append(callee_id)
                            self.adj_backward[callee_id].append(caller_id)

    def find_entry_points(self) -> list:
        # Functions with no incoming edges are candidates for entry points
        roots = [n for n in self.nodes if not self.adj_backward.get(n['id'])]
        priority_names = {"main", "start", "run", "index", "init"}
        roots.sort(key=lambda x: x['name'].lower() in priority_names, reverse=True)
        return roots

    def get_graph(self):
        return {"nodes": self.nodes, "edges": self.edges}

    def trace_execution(self, start_id: str) -> list:
        """DFS forward — returns the full call chain from start_id."""
        stack = [(start_id, 0)]
        visited = []
        path = []
        while stack:
            node_id, depth = stack.pop()
            if node_id not in visited:
                visited.append(node_id)
                path.append({"id": node_id, "depth": depth})
                for child in reversed(self.adj_forward.get(node_id, [])):
                    stack.append((child, depth + 1))
        return path

    def analyze_impact(self, target_id: str, direction="backward") -> list:
        """BFS — returns everything that would be affected if target_id changes."""
        queue = deque([(target_id, 0)])
        visited = {target_id}
        impact_map = []
        adj = self.adj_backward if direction == "backward" else self.adj_forward
        while queue:
            node_id, level = queue.popleft()
            if level > 0:
                impact_map.append({"id": node_id, "distance": level})
            for neighbor in adj.get(node_id, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, level + 1))
        return impact_map
