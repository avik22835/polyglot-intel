import os
from metacall import metacall_load_from_file, metacall

d = os.path.dirname(os.path.abspath(__file__))

# CASE 1: Python -> Ruby (no require 'metacall' inside .rb)
# Expected: works fine
print("=== CASE 1: Python -> Ruby (plain function, no require metacall) ===")
metacall_load_from_file("rb", [os.path.join(d, "works.rb")])
result = metacall("rb_plain", "hello")
print("Result:", result)

# CASE 2: Ruby -> Python (requires metacall gem inside .rb)
# Expected: LoadError - cannot load such file -- metacall
print("\n=== CASE 2: Ruby -> Python (require metacall inside .rb) ===")
metacall_load_from_file("py", [os.path.join(d, "target.py")])
metacall_load_from_file("rb", [os.path.join(d, "fails.rb")])
result = metacall("rb_caller", "hello")
print("Result:", result)
