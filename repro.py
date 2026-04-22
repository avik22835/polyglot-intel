from metacall import metacall_load_from_file, metacall

SIM = "C:/Users/KIIT0001/GSOC/polyglot-intel/simulation"

# STEP 1: Load Ruby
# styler.rb exports: style_text(text: String) -> String
# Internally it calls metacall('compute_hash', text) into Rust
print("Loading Ruby (styler.rb)...")
metacall_load_from_file("rb", [SIM + "/styler.rb"])
print("Ruby loaded OK")

# STEP 2: Call Ruby from Python WITHOUT loading Rust first
# style_text will try metacall('compute_hash', text) inside Ruby
# compute_hash is NOT loaded yet -- this is where it explodes
print("\n[TEST 1] Calling style_text WITHOUT Rust loaded:")
print("  Passing type: String ('hello')")
result = metacall("style_text", "hello")
print("  Result: " + str(result))

# STEP 3: Now load Rust and retry
# core.rs exports: compute_hash(data: *const u8) -> i32
# Type crossing the boundary: Python str -> Ruby String -> Rust *const u8
print("\nLoading Rust (core.rs compiled to .so)...")
metacall_load_from_file("rs", [SIM + "/core.so"])
print("Rust loaded OK")

print("\n[TEST 2] Calling style_text WITH Rust loaded:")
print("  Chain: Python str -> Ruby String -> Rust *const u8")
result = metacall("style_text", "hello")
print("  Result: " + str(result))
