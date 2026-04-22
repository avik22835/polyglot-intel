from metacall import metacall_load_from_file, metacall
import os

sim = os.path.dirname(os.path.abspath(__file__))

print("Loading Ruby...")
metacall_load_from_file("rb", [os.path.join(sim, "styler.rb")])
print("Ruby loaded")

print("Calling style_text('hello')...")
result = metacall("style_text", "hello")
print("Result:", result)
