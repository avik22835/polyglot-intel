import json
import os


class RegistryWriter:
    def __init__(self, chunks: list):
        self.chunks = chunks
        self.symbol_table = {}
        self.registry = {
            "summary": {},
            "files": {},
            "metacall_inspect_compatible": []
        }

    def _build_symbol_table(self):
        for chunk in self.chunks:
            name = chunk["chunk_name"]
            if name not in self.symbol_table:
                self.symbol_table[name] = {
                    "file_path": chunk["file_path"],
                    "file_name": chunk["file_name"],
                    "loader_tag": chunk["loader_tag"],
                    "language": chunk["language"]
                }

    def _resolve_calls(self):
        for chunk in self.chunks:
            for call in chunk["cross_language_calls"]:
                callee = call["callee"]
                if callee in self.symbol_table:
                    target = self.symbol_table[callee]
                    call["resolved"] = True
                    call["target_file"] = target["file_name"]
                    call["target_loader"] = target["loader_tag"]
                    call["target_language"] = target["language"]
                else:
                    call["resolved"] = False

    def build_registry(self, output_path: str):
        self._build_symbol_table()
        self._resolve_calls()

        for chunk in self.chunks:
            f_name = chunk["file_name"]
            if f_name not in self.registry["files"]:
                self.registry["files"][f_name] = {
                    "language": chunk["language"],
                    "loader": chunk["loader_tag"],
                    "functions": []
                }
            self.registry["files"][f_name]["functions"].append({
                "name": chunk["chunk_name"],
                "signature": chunk["signature"],
                "calls": chunk["cross_language_calls"],
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"]
            })

        self.registry["summary"] = {
            "total_files": len(self.registry["files"]),
            "total_functions": len(self.chunks),
            "languages": list(set(c["language"] for c in self.chunks))
        }

        for chunk in self.chunks:
            self.registry["metacall_inspect_compatible"].append({
                "name": chunk["chunk_name"],
                "loader": chunk["loader_tag"],
                "signature": chunk["signature"]
            })

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(self.registry, f, indent=4)
            print(f"Registry written to {output_path}")
            return self.registry
        except Exception as e:
            print(f"Error writing registry: {e}")
            return None
