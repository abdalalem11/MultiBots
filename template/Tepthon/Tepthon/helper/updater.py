from .git import repo

def get_origin_upstream() -> tuple:
    branch = "main"
    for remote in repo.remotes():
        repo.fetch_remote(remote)
    origin = repo.rev_parse(f"origin/{branch}")
    upstream = repo.rev_parse(branch)
    return (origin, upstream)


def check_update() -> bool:
    origin, upstream = get_origin_upstream()
    return origin != upstream
