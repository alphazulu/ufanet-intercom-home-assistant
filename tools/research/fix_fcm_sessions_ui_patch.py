from pathlib import Path

path = Path(__file__).with_name("apply_fcm_sessions_ui_patch.py")
source = path.read_text(encoding="utf-8")
old = '''source = replace_once(
    source,
    '    this._renderArchiveExports();\\n    this._renderRuntimeStatus();',
    '    this._renderArchiveExports();\\n    this._renderFcmSessions();\\n    this._renderRuntimeStatus();',
    "initial sessions render",
)
'''
new = '''needle = '    this._renderArchiveExports();\\n    this._renderRuntimeStatus();'
replacement = '    this._renderArchiveExports();\\n    this._renderFcmSessions();\\n    this._renderRuntimeStatus();'
render_count = source.count(needle)
if render_count != 2:
    raise RuntimeError(f"initial sessions render: expected exactly two matches, got {render_count}")
source = source.replace(needle, replacement)
'''
if source.count(old) != 1:
    raise RuntimeError("unable to locate temporary render patch block")
source = source.replace(old, new, 1)
source = source.replace("незaщищённых", "незащищённых")
path.write_text(source, encoding="utf-8")
