import fileinput, os, re, sys

config = {}

StringElements = {
"PLUG_VERSION_HEX",
"PLUG_NAME",
"PLUG_MFR",
"BUNDLE_MFR",
"BUNDLE_NAME",
"BUNDLE_DOMAIN",
"PLUG_CHANNEL_IO",
"PLUG_COPYRIGHT_STR",
"PLUG_UNIQUE_ID",
"PLUG_MFR_ID",
"PLUG_CLASS_NAME",
"AUV2_ENTRY",
"AUV2_ENTRY_STR",
"AUV2_FACTORY",
"AUV2_VIEW_CLASS",
"AUV2_VIEW_CLASS_STR",
"AAX_TYPE_IDS",
"AAX_TYPE_IDS_AUDIOSUITE",
"AAX_PLUG_MFR_STR",
"AAX_PLUG_NAME_STR",
"AAX_PLUG_CATEGORY_STR",
"VST3_SUBCATEGORY",
"SHARED_RESOURCES_SUBPATH"
}

IntElements = {
"PLUG_TYPE",
"PLUG_DOES_MIDI_IN",
"PLUG_DOES_MIDI_OUT",
"PLUG_HAS_UI",
"PLUG_SHARED_RESOURCES",
"PLUG_WIDTH",
"PLUG_HEIGHT",
"PLUG_FPS",
"APP_COPY_AUV3",
"AAX_DOES_AUDIOSUITE",
}

for stringElement in StringElements:
  config[stringElement] = ""

for intElement in IntElements:
  config[intElement] = 0

def extractInt(line, macro):
  lineText = "#define " + macro + " "
  if lineText in line:
    config[macro] = int(line[len(lineText):].strip())
    return True
  return False

def extractStringElement(line, macro):
  lineText = "#define " + macro + " "
  if lineText in line:
    rhs = line[len(lineText):].strip()
    if rhs.endswith('\\'):
      rhs = rhs[:-1].strip()
    if '\"' in rhs:
      config[macro] = rhs.strip('\"')
    elif "\'" in rhs:
      config[macro] = rhs.strip('\'')
    else:
      config[macro] = rhs
    return True
  else:
    return False

def set_uniqueid(projectpath, id):
  for line in fileinput.input(projectpath + "/config.h", inplace=1):
    found = extractStringElement(line, "PLUG_UNIQUE_ID")
    if(found):
      sys.stdout.write(line.replace(config["PLUG_UNIQUE_ID"], id))
    else:
      sys.stdout.write(line)

  fileinput.close()

def _strip_comment(line):
  # Remove // comments outside quotes
  out = []
  in_str = False
  quote = ''
  i = 0
  while i < len(line):
    c = line[i]
    if not in_str and i + 1 < len(line) and line[i:i+2] == '//':
      break
    if c in ('"', "'"):
      if not in_str:
        in_str = True
        quote = c
      elif quote == c:
        in_str = False
    out.append(c)
    i += 1
  return ''.join(out).rstrip()

def _parse_define_line(line, macros):
  m = re.match(r'^\s*#define\s+(\w+)\s+(.+)$', line)
  if not m:
    return
  name, rhs = m.group(1), m.group(2).strip()
  if rhs.endswith('\\'):
    rhs = rhs[:-1].strip()
  if len(rhs) >= 2 and rhs[0] == '"' and rhs[-1] == '"':
    macros[name] = rhs[1:-1]
  elif len(rhs) >= 2 and rhs[0] == "'" and rhs[-1] == "'":
    macros[name] = rhs[1:-1]
  else:
    macros[name] = rhs

def _resolve_token(token, macros, depth=0):
  if depth > 20 or token is None:
    return token
  if not isinstance(token, str):
    return token
  # Already a literal-ish value with spaces / path chars kept as-is
  if token in macros:
    return _resolve_token(macros[token], macros, depth + 1)
  return token

def _gather_macros(projectpath):
  """Parse config.h plus quoted #includes (e.g. MingusBrand.h) into a macro map."""
  macros = {}
  search_dirs = [
    projectpath,
    os.path.join(projectpath, '..', '..', 'shared', 'include'),
    os.path.join(projectpath, '..', '..', '..', 'shared', 'include'),
  ]
  search_dirs = [os.path.abspath(d) for d in search_dirs if os.path.isdir(d)]

  visited = set()

  def read_file(path):
    path = os.path.abspath(path)
    if path in visited or not os.path.isfile(path):
      return
    visited.add(path)
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
      for raw in f:
        line = _strip_comment(raw).strip()
        if not line:
          continue
        inc = re.match(r'^\s*#include\s+"([^"]+)"', line)
        if inc:
          rel = inc.group(1)
          candidates = [os.path.join(os.path.dirname(path), rel)]
          for d in search_dirs:
            candidates.append(os.path.join(d, os.path.basename(rel)))
            candidates.append(os.path.join(d, rel))
          for c in candidates:
            if os.path.isfile(c):
              read_file(c)
              break
          continue
        _parse_define_line(line, macros)

  read_file(os.path.join(projectpath, 'config.h'))
  return macros

def parse_config(projectpath):
  # Reset module-level config for repeated calls
  for stringElement in StringElements:
    config[stringElement] = ""
  for intElement in IntElements:
    config[intElement] = 0

  macros = _gather_macros(projectpath)

  # extract values from config.h (legacy path) then overlay resolved macros
  for line in fileinput.input(projectpath + "/config.h", inplace=0):
    found = False
    for stringElement in StringElements:
      if extractStringElement(line, stringElement):
        found = True
        break
    if not found:
      for intElement in IntElements:
        if extractInt(line, intElement):
          break
  fileinput.close()

  # Prefer fully resolved macros from includes (MINGUS_* -> real values)
  for key in list(StringElements):
    if key in macros:
      config[key] = _resolve_token(macros[key], macros)
    else:
      config[key] = _resolve_token(config[key], macros)

  for key in list(IntElements):
    if key in macros:
      try:
        config[key] = int(str(macros[key]).strip(), 0)
      except ValueError:
        pass

  # add some derived vals
  config["PLUG_VERSION_INT"] = int(config["PLUG_VERSION_HEX"], 16)
  MAJOR_INT = config["PLUG_VERSION_INT"] & 0xFFFF0000
  config["MAJOR_STR"] = str(MAJOR_INT >> 16)
  MINOR_INT = config["PLUG_VERSION_INT"] & 0x0000FF00
  config["MINOR_STR"] = str(MINOR_INT >> 8)
  config["BUGFIX_STR"] = str(config["PLUG_VERSION_INT"] & 0x000000FF)
  config["FULL_VER_STR"] = config["MAJOR_STR"] + "." + config["MINOR_STR"] + "." + config["BUGFIX_STR"]

  return config

def parse_xcconfig(configFile):

  def extractXCInt(line, setting):
    lineText = setting + " = "
    if lineText in line:
      xcconfig[setting] = int(line[len(lineText):], 16)

  def extractXCStringElement(line, setting):
    lineText = setting + " = "
    if lineText in line:
      xcconfig[setting] = line[len(lineText):-1].strip('\"')

  xcconfig = {}

  xcconfig['BASE_SDK_MAC'] = "macosx"
  xcconfig['MACOSX_DEPLOYMENT_TARGET'] = "10.9"

  for line in fileinput.input(configFile, inplace=0):
    if not "//" in line:
      extractXCStringElement(line, 'BASE_SDK_MAC')
      extractXCStringElement(line, 'IPLUG2_ROOT')

      if "MACOSX_DEPLOYMENT_TARGET = " in line:
        xcconfig['DEPLOYMENT_TARGET'] = line[len("MACOSX_DEPLOYMENT_TARGET = "):-1].strip('\"') + ".0"

      if "IPHONEOS_DEPLOYMENT_TARGET = " in line:
        xcconfig['DEPLOYMENT_TARGET'] = line[len("IPHONEOS_DEPLOYMENT_TARGET = "):-1].strip('\"') + ".0"

  fileinput.close()

  return xcconfig

if __name__ == '__main__':
  parse_config(sys.argv[1])
  for k in ("PLUG_MFR", "PLUG_MFR_ID", "BUNDLE_MFR", "BUNDLE_DOMAIN", "PLUG_COPYRIGHT_STR"):
    print(f"{k}={config[k]!r}")
