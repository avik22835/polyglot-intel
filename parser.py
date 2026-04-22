import os
from tree_sitter import Parser
from tree_sitter_languages import get_language, get_parser
from registry_writer import RegistryWriter

LANGUAGE_TO_LOADER = {
    "python": "py", "javascript": "node", "typescript": "ts",
    "rust": "rs", "ruby": "rb", "go": "go", "c": "c", "cpp": "cpp"
}

EXT_TO_LANGUAGE = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".rs": "rust", ".rb": "ruby", ".go": "go", ".c": "c", ".cpp": "cpp"
}

METHOD_NODES = {
    "python": {"function_definition", "class_definition"},
    "javascript": {"function_declaration", "method_definition", "arrow_function"},
    "typescript": {"function_declaration", "method_definition", "arrow_function"},
    "rust": {"function_item"},
    "ruby": {"method"},
    "go": {"function_declaration", "method_declaration"},
    "c": {"function_definition"},
    "cpp": {"function_definition"}
}

METACALL_BOOL = 0; METACALL_CHAR = 1; METACALL_SHORT = 2; METACALL_INT = 3
METACALL_LONG = 4; METACALL_FLOAT = 5; METACALL_DOUBLE = 6; METACALL_STRING = 7
METACALL_BUFFER = 8; METACALL_ARRAY = 9; METACALL_MAP = 10; METACALL_PTR = 11
METACALL_FUTURE = 12; METACALL_FUNCTION = 13; METACALL_NULL = 14; METACALL_CLASS = 15
METACALL_OBJECT = 16; METACALL_EXCEPTION = 17; METACALL_THROWABLE = 18

TYPE_MAPPING = {
    "python": {
        "bool": {"name": "Bool", "id": METACALL_BOOL}, "int": {"name": "Int", "id": METACALL_INT},
        "float": {"name": "Double", "id": METACALL_DOUBLE}, "str": {"name": "String", "id": METACALL_STRING},
        "bytes": {"name": "Buffer", "id": METACALL_BUFFER}, "list": {"name": "Array", "id": METACALL_ARRAY},
        "tuple": {"name": "Array", "id": METACALL_ARRAY}, "dict": {"name": "Map", "id": METACALL_MAP},
        "None": {"name": "Null", "id": METACALL_NULL}, "Callable": {"name": "Function", "id": METACALL_FUNCTION}
    },
    "typescript": {
        "boolean": {"name": "Bool", "id": METACALL_BOOL}, "number": {"name": "Double", "id": METACALL_DOUBLE},
        "string": {"name": "String", "id": METACALL_STRING}, "any": {"name": "Ptr", "id": METACALL_PTR},
        "Array": {"name": "Array", "id": METACALL_ARRAY}
    },
    "rust": {
        "bool": {"name": "Bool", "id": METACALL_BOOL}, "i32": {"name": "Int", "id": METACALL_INT},
        "i64": {"name": "Long", "id": METACALL_LONG}, "f32": {"name": "Float", "id": METACALL_FLOAT},
        "f64": {"name": "Double", "id": METACALL_DOUBLE}, "String": {"name": "String", "id": METACALL_STRING},
        "str": {"name": "String", "id": METACALL_STRING}, "Vec": {"name": "Array", "id": METACALL_ARRAY}
    },
    "ruby": {
        "TrueClass": {"name": "Bool", "id": METACALL_BOOL}, "FalseClass": {"name": "Bool", "id": METACALL_BOOL},
        "Integer": {"name": "Int", "id": METACALL_INT}, "Float": {"name": "Double", "id": METACALL_DOUBLE},
        "String": {"name": "String", "id": METACALL_STRING}, "Array": {"name": "Array", "id": METACALL_ARRAY},
        "Hash": {"name": "Map", "id": METACALL_MAP}, "Proc": {"name": "Function", "id": METACALL_FUNCTION},
        "Lambda": {"name": "Function", "id": METACALL_FUNCTION}, "nil": {"name": "Null", "id": METACALL_NULL}
    },
    "c": {
        "_Bool": {"name": "Bool", "id": METACALL_BOOL}, "int": {"name": "Int", "id": METACALL_INT},
        "long": {"name": "Long", "id": METACALL_LONG}, "float": {"name": "Float", "id": METACALL_FLOAT},
        "double": {"name": "Double", "id": METACALL_DOUBLE}, "char*": {"name": "String", "id": METACALL_STRING},
        "void*": {"name": "Ptr", "id": METACALL_PTR}, "NULL": {"name": "Null", "id": METACALL_NULL}
    }
}
TYPE_MAPPING["cpp"] = TYPE_MAPPING["c"]


class MetaCallParser:
    def __init__(self):
        self.parsers = {}
        self.queries = {}
        for lang in LANGUAGE_TO_LOADER.keys():
            try:
                lang_obj = get_language(lang)
                self.parsers[lang] = get_parser(lang)

                if lang == "python":
                    self.queries[lang] = lang_obj.query("(function_definition parameters: (parameters [ (typed_parameter (identifier) @param.name type: (type) @param.type) (identifier) @param.name ] ) return_type: (type)? @ret.type)")
                elif lang == "javascript":
                    self.queries[lang] = lang_obj.query("(function_declaration parameters: (formal_parameters (identifier) @param.name)? )")
                elif lang == "typescript":
                    self.queries[lang] = lang_obj.query("(function_declaration parameters: (formal_parameters (required_parameter name: (identifier) @param.name type: (type_annotation) @param.type)? ))")
                elif lang == "rust":
                    self.queries[lang] = lang_obj.query("(function_item name: (identifier) @name parameters: (parameters (parameter pattern: (identifier) @param.name type: (type_identifier) @param.type)? ) return_type: (type_identifier)? @ret.type)")
                elif lang == "go":
                    self.queries[lang] = lang_obj.query("(function_declaration name: (identifier) @name parameters: (parameter_list (parameter_declaration name: (identifier) @param.name type: (type_identifier) @param.type)) )")
                elif lang == "ruby":
                    self.queries[lang] = lang_obj.query("(method name: (identifier) @name parameters: (method_parameters (identifier) @param.name)? )")
                elif lang in ["c", "cpp"]:
                    self.queries[lang] = lang_obj.query("(function_definition declarator: (function_declarator declarator: (identifier) @name parameters: (parameter_list (parameter_declaration type: (type_identifier) @param.type declarator: (identifier) @param.name)? )))")

                print(f"Loaded parser and queries for {lang}")
            except Exception as e:
                print(f"Could not load parser for {lang}: {e}")

    def _clean_c_type(self, type_str: str) -> str:
        return type_str.replace("const", "").replace(" ", "").strip()

    def _map_type(self, type_str: str, language: str) -> dict:
        if not type_str or language not in TYPE_MAPPING:
            return {"name": "Ptr", "id": METACALL_PTR, "inferred": True}
        cleaned = self._clean_c_type(type_str) if language in ["c", "cpp"] else type_str
        base_type = cleaned.split('[')[0].split('<')[0].strip()
        mapping = TYPE_MAPPING[language].get(base_type)
        return {**(mapping or {"name": "Ptr", "id": METACALL_PTR}), "inferred": not bool(mapping)}

    def _walk_for_metacalls(self, node, language, calls, start_line):
        is_metacall = False
        args_node = None
        if language in ["python", "ruby"] and node.type == "call":
            f = node.child_by_field_name("function") or node.child_by_field_name("method")
            if f and f.text.decode('utf-8') == "metacall":
                is_metacall = True
                args_node = node.child_by_field_name("arguments")
        elif language in ["javascript", "typescript", "go", "c", "cpp"] and node.type == "call_expression":
            f = node.child_by_field_name("function")
            if f and f.text.decode('utf-8') == "metacall":
                is_metacall = True
                args_node = node.child_by_field_name("arguments")
        elif language == "rust" and node.type == "macro_invocation":
            m = node.child_by_field_name("macro")
            if m and m.text.decode('utf-8') == "metacall":
                is_metacall = True
                args_node = node.child_by_field_name("token_tree")

        if is_metacall and args_node:
            first_arg = None
            for i in range(args_node.named_child_count):
                first_arg = args_node.named_child(i)
                break
            callee = "DYNAMIC"
            dynamic = True
            if first_arg and first_arg.type in ["string", "string_literal"]:
                callee = first_arg.text.decode('utf-8').strip('"\'')
                dynamic = False
            calls.append({
                "callee": callee,
                "call_line": start_line + node.start_point[0],
                "dynamic": dynamic,
                "resolved": False
            })
        for child in node.children:
            self._walk_for_metacalls(child, language, calls, start_line)

    def _detect_metacall_calls(self, code: str, language: str, start_line: int) -> list:
        if language not in self.parsers:
            return []
        tree = self.parsers[language].parse(bytes(code, "utf-8"))
        calls = []
        self._walk_for_metacalls(tree.root_node, language, calls, start_line)
        return calls

    def _extract_signature(self, node, language):
        signature = {"args": [], "ret": {"name": "Ptr", "id": METACALL_PTR, "inferred": True}}
        if language not in self.queries:
            return signature
        query = self.queries[language]
        captures = query.captures(node)
        for capture_node, tag in captures:
            if tag == "param.name":
                signature["args"].append({
                    "name": capture_node.text.decode('utf-8'),
                    "metacall_type": {"name": "Ptr", "id": METACALL_PTR, "inferred": True}
                })
            elif tag == "param.type":
                if signature["args"]:
                    t = capture_node.text.decode('utf-8')
                    signature["args"][-1]["metacall_type"] = self._map_type(t, language)
            elif tag == "ret.type":
                t = capture_node.text.decode('utf-8')
                signature["ret"] = self._map_type(t, language)
        return signature

    def _get_node_name(self, node, language) -> str:
        name_node = node.child_by_field_name("name")
        if name_node:
            return name_node.text.decode('utf-8', errors='ignore')
        # arrow functions assigned to variables: const fn = () => {}
        if language in ["javascript", "typescript"] and node.type == "arrow_function":
            parent = node.parent
            if parent and parent.type == "variable_declarator":
                name_node = parent.child_by_field_name("name")
                if name_node:
                    return name_node.text.decode('utf-8', errors='ignore')
        return "anonymous"

    def _make_chunk(self, node, file_path, language):
        code = node.text.decode('utf-8', errors='ignore')
        start_line = node.start_point[0] + 1
        return {
            'file_path': file_path,
            'file_name': os.path.basename(file_path),
            'language': language,
            'loader_tag': LANGUAGE_TO_LOADER.get(language, "unknown"),
            'chunk_type': node.type,
            'chunk_name': self._get_node_name(node, language),
            'start_line': start_line,
            'end_line': node.end_point[0] + 1,
            'code': code,
            'signature': self._extract_signature(node, language),
            'cross_language_calls': self._detect_metacall_calls(code, language, start_line)
        }

    def parse_file(self, file_path):
        ext = os.path.splitext(file_path)[1]
        lang = EXT_TO_LANGUAGE.get(ext)
        if not lang or lang not in self.parsers:
            return []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            tree = self.parsers[lang].parse(bytes(content, "utf-8"))
            root = tree.root_node
            chunks = []
            for node in root.children:
                if lang == "rust" and node.type == "function_item":
                    # only export functions marked #[no_mangle]
                    prev = node.prev_sibling
                    is_exported = False
                    if prev and "attribute_item" in prev.type:
                        if "no_mangle" in prev.text.decode('utf-8'):
                            is_exported = True
                    if not is_exported and "#[no_mangle]" in node.text.decode('utf-8'):
                        is_exported = True
                    if is_exported:
                        chunks.append(self._make_chunk(node, file_path, lang))
                    continue
                if node.type in METHOD_NODES.get(lang, set()):
                    chunks.append(self._make_chunk(node, file_path, lang))
                elif lang in ["javascript", "typescript"] and node.type == "lexical_declaration":
                    for decl in node.named_children:
                        if decl.type == "variable_declarator":
                            value = decl.child_by_field_name("value")
                            if value and value.type == "arrow_function":
                                chunks.append(self._make_chunk(value, file_path, lang))
            return chunks
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return []

    def parse_directory(self, directory_path: str) -> list:
        all_chunks = []
        ignored_dirs = {".git", "node_modules", "__pycache__", "venv", "build", "dist"}
        for root, dirs, files in os.walk(directory_path):
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            for file in files:
                file_path = os.path.join(root, file)
                ext = os.path.splitext(file)[1]
                if ext in EXT_TO_LANGUAGE:
                    chunks = self.parse_file(file_path)
                    all_chunks.extend(chunks)
        return all_chunks


if __name__ == "__main__":
    import sys

    project_dir = sys.argv[1] if len(sys.argv) > 1 else "./simulation"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "metacall-registry.json"

    intel = MetaCallParser()
    print(f"\nScanning {project_dir}/")

    all_chunks = intel.parse_directory(project_dir)

    writer = RegistryWriter(all_chunks)
    registry = writer.build_registry(output_path)

    if registry:
        print(f"Files:     {registry['summary']['total_files']}")
        print(f"Functions: {registry['summary']['total_functions']}")
        print(f"Languages: {', '.join(registry['summary']['languages'])}")
        print(f"Registry:  {output_path}")
