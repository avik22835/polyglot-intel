require 'metacall'

def rb_caller(text)
  result = metacall('py_target', text)
  "Ruby got back: " + result.to_s
end
