import os
import json
from collections import Counter

from dotenv import load_dotenv
from github import Github, GithubException


# Load configuration once
with open("config.json", "r") as f:
    config = json.load(f)


def get_github_client() -> Github:
    """Create an authenticated Github client using GITHUB_TOKEN from .env or environment."""
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set in environment or .env file")
    return Github(token)


def get_repos(g: Github):
    """Return public user repos, optionally excluding organization-owned ones."""
    exclude_organizations = config.get("exclude_organizations", True)

    repos = [
        repo
        for repo in g.get_user().get_repos(type="public")
        if repo.visibility == "public"
    ]

    if exclude_organizations:
        repos = [repo for repo in repos if repo.owner.type != "Organization"]

    return repos


def get_bytes_of_code(g: Github) -> int:
    """Return total bytes of code across all selected repos."""
    total_bytes = 0
    for repo in get_repos(g):
        try:
            languages = repo.get_languages()
            total_bytes += sum(languages.values())
        except GithubException:
            continue
    return total_bytes


def get_languages(g: Github) -> dict:
    """Return a dict of language -> total bytes across all selected repos."""
    languages = Counter()
    for repo in get_repos(g):
        try:
            for lang, bytes_count in repo.get_languages().items():
                languages[lang] += bytes_count
        except GithubException:
            continue
    return dict(languages)


def format_languages(languages: dict) -> str:
    """Format the languages dict into a markdown bullet list string."""
    sorted_lang = sorted(languages.items(), key=lambda x: x[1], reverse=True)
    max_languages = config.get("max_languages", -1)
    if max_languages != -1:
        sorted_lang = sorted_lang[:max_languages]

    return "\n" + "\n".join(
        [f"- {lang}: {bytes_count} bytes of code" for lang, bytes_count in sorted_lang]
    )


def fetch_stats(g: Github) -> dict:
    """Fetch user-focused GitHub statistics.

    - total_commits: commits authored by the user in their public repos
    - total_issues: issues created by the user (open + closed) in their public repos
    - total_prs: pull requests authored by the user across GitHub (open + closed + merged)
    """

    user = g.get_user()
    username = user.login

    repos = get_repos(g)

    total_commits = 0
    total_issues = 0
    total_prs = 0

    for repo in repos:
        if repo.fork or repo.visibility != "public":
            continue

        try:
            # Commits authored by this user in this repo
            total_commits += repo.get_commits(author=username).totalCount
        except GithubException:
            pass

        try:
            # Issues created by this user in this repo (open + closed)
            total_issues += repo.get_issues(creator=username, state="all").totalCount
        except GithubException:
            pass

    try:
        # All PRs authored by this user across GitHub (open + closed + merged)
        # If you only want PRs in your own repos, add `user:<username>` to the query.
        total_prs = g.search_issues(f"author:{username} is:pr state:all").totalCount
    except GithubException:
        total_prs = 0

    return {
        "username": user.login,
        "followers": user.followers,
        "following": user.following,
        "public_repos": user.public_repos,
        "public_gists": user.public_gists,
        "total_stars": sum(repo.stargazers_count for repo in repos),
        "bytes_of_code": get_bytes_of_code(g),
        "bio": user.bio,
        "location": user.location,
        "company": user.company,
        "email": user.email,
        "website": user.blog,
        "hireable": user.hireable,
        "created_at": user.created_at.strftime("%d-%m-%Y"),
        "updated_at": user.updated_at.strftime("%d-%m-%Y"),
        "languages": format_languages(get_languages(g)),
        "total_commits": total_commits,
        "total_issues": total_issues,
        "total_prs": total_prs,
    }


if __name__ == "__main__":
    g = get_github_client()
    stats = fetch_stats(g)
