import json
from collections import Counter, defaultdict
from github import Github
from typing import Dict, Set

# Load config once
with open("config.json", "r") as f:
    config = json.load(f)


def get_repos(g: Github):
    """Return public repos for the authenticated user, optionally excluding org-owned repos."""
    exclude_organizations = config.get("exclude_organizations", True)

    # Get only public repos for the authenticated user
    repos = [
        repo
        for repo in g.get_user().get_repos(type="public")
        if repo.visibility == "public"
    ]

    if exclude_organizations:
        repos = [repo for repo in repos if repo.owner.type != "Organization"]

    return repos


def get_bytes_of_code_from_repos(repos) -> int:
    """Sum total bytes of code across given repositories based on language stats."""
    total_bytes = 0
    for repo in repos:
        try:
            languages = repo.get_languages()
            total_bytes += sum(languages.values())
        except Exception:
            # In real usage, consider logging this
            continue
    return total_bytes


def get_languages_from_repos(repos) -> Dict[str, int]:
    """Aggregate language usage (in bytes) across given repositories."""
    languages: Counter[str] = Counter()
    for repo in repos:
        if repo.fork or repo.visibility != "public":
            continue
        try:
            for lang, bytes_count in repo.get_languages().items():
                languages[lang] += bytes_count
        except Exception:
            continue
    return dict(languages)


def format_languages(languages: Dict[str, int]) -> str:
    """Return a human-readable summary of language usage (still in bytes)."""
    sorted_lang = sorted(languages.items(), key=lambda x: x[1], reverse=True)
    max_languages = config.get("max_languages", -1)
    if max_languages != -1:
        sorted_lang = sorted_lang[:max_languages]

    if not sorted_lang:
        return ""

    lines = [f"- {lang}: {bytes_count} bytes of code" for lang, bytes_count in sorted_lang]
    return "\n" + "\n".join(lines)


def get_pr_contributions(g: Github, user_login: str, owned_repo_names: Set[str]) -> Dict:
    """Return PR contributions for a user across all public repos, grouped by repo.

    Output shape:
    {
        "total_prs": int,
        "by_repo": { "owner/repo": count, ... },
        "own_repos": { "owner/repo": count, ... },
        "external_repos": { "owner/repo": count, ... },
    }
    """
    query = f"author:{user_login} is:pr"
    pr_search_results = g.search_issues(query)

    by_repo: Dict[str, int] = defaultdict(int)

    for pr in pr_search_results:
        repo_full_name = pr.repository.full_name  # e.g. "owner/repo"
        by_repo[repo_full_name] += 1

    own_repos = {name: count for name, count in by_repo.items() if name in owned_repo_names}
    external_repos = {name: count for name, count in by_repo.items() if name not in owned_repo_names}

    return {
        "total_prs": sum(by_repo.values()),
        "by_repo": dict(by_repo),
        "own_repos": own_repos,
        "external_repos": external_repos,
    }


def get_issue_contributions(g: Github, user_login: str, owned_repo_names: Set[str]) -> Dict:
    """Return issue contributions for a user across all public repos, grouped by repo.

    Output shape:
    {
        "total_issues": int,
        "by_repo": { "owner/repo": count, ... },
        "own_repos": { "owner/repo": count, ... },
        "external_repos": { "owner/repo": count, ... },
    }
    """
    query = f"author:{user_login} is:issue"
    issue_search_results = g.search_issues(query)

    by_repo: Dict[str, int] = defaultdict(int)

    for issue in issue_search_results:
        # search_issues can return PRs as issues; skip those
        if getattr(issue, "pull_request", None) is not None:
            continue
        repo_full_name = issue.repository.full_name
        by_repo[repo_full_name] += 1

    own_repos = {name: count for name, count in by_repo.items() if name in owned_repo_names}
    external_repos = {name: count for name, count in by_repo.items() if name not in owned_repo_names}

    return {
        "total_issues": sum(by_repo.values()),
        "by_repo": dict(by_repo),
        "own_repos": own_repos,
        "external_repos": external_repos,
    }


def fetch_stats(g: Github) -> Dict:
    """Fetch aggregated stats for the authenticated user using PyGithub only."""
    user = g.get_user()
    repos = get_repos(g)
    owned_repo_names: Set[str] = {repo.full_name for repo in repos}

    total_commits_in_own_repos = 0
    total_issues_in_own_repos = 0
    total_prs_in_own_repos = 0

    for repo in repos:
        if repo.fork or repo.visibility != "public":
            continue
        try:
            # Commits and issues filtered by this user in own repos
            total_commits_in_own_repos += repo.get_commits(author=user).totalCount
            total_issues_in_own_repos += repo.get_issues(creator=user.login).totalCount

            # PRs per repo (all authors) - keep if you still want repo-level PR counts
            total_prs_in_own_repos += repo.get_pulls(state="all").totalCount
        except Exception:
            # In real usage, consider logging this
            continue

    # Global contribution stats via search (PRs & issues across all public repos)
    pr_contribs = get_pr_contributions(g, user.login, owned_repo_names)
    issue_contribs = get_issue_contributions(g, user.login, owned_repo_names)

    # Language and code size stats from own repos
    languages = get_languages_from_repos(repos)

    return {
        "username": user.login,
        "followers": user.followers,
        "following": user.following,
        "public_repos": user.public_repos,
        "public_gists": user.public_gists,
        "total_stars": sum(repo.stargazers_count for repo in repos),
        "bytes_of_code": get_bytes_of_code_from_repos(repos),
        "bio": user.bio,
        "location": user.location,
        "company": user.company,
        "email": user.email,
        "website": user.blog,
        "hireable": user.hireable,
        "created_at": user.created_at.strftime("%d-%m-%Y"),
        "updated_at": user.updated_at.strftime("%d-%m-%Y"),
        "languages": languages,                  # raw dict
        "languages_pretty": format_languages(languages),  # formatted string
        # Aggregated numbers in own repos (user-specific where possible)
        "total_commits_in_own_repos": total_commits_in_own_repos,
        "total_issues_in_own_repos": total_issues_in_own_repos,
        "total_prs_in_own_repos": total_prs_in_own_repos,
        # Global contribution stats using search (includes external repos)
        "pr_contributions": pr_contribs,
        "issue_contributions": issue_contribs,
    }
