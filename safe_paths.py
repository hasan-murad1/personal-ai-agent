import os


def resolve_inside(base_dir: str, relative_path: str) -> str:
    """Return the absolute path of relative_path inside base_dir, or raise ValueError if it would escape base_dir.

    Uses os.path.commonpath instead of a string prefix check, so a sibling folder such as
    'agent_workspace_evil' is not mistaken for 'agent_workspace'. realpath also resolves '..'
    and symbolic links, and normcase handles Windows' case-insensitive paths.
    """
    base = os.path.realpath(base_dir)
    full = os.path.realpath(os.path.join(base, relative_path))
    try:
        common = os.path.commonpath([os.path.normcase(base), os.path.normcase(full)])
    except ValueError:
        # Raised on Windows when the two paths are on different drives (e.g. C: and D:).
        raise ValueError("Access outside the allowed folder is not allowed.")
    if common != os.path.normcase(base):
        raise ValueError("Access outside the allowed folder is not allowed.")
    return full