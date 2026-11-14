"""Generate the profile cards (assets/stats.svg, assets/languages.svg) from the GitHub API.

Runs daily in GitHub Actions (see .github/workflows/profile-assets.yml) so the README never depends on
third-party card services. Standard library only. Uses GITHUB_TOKEN (or GH_TOKEN) when available.
"""
import json
import math
import os
import sys
import urllib.request
from xml.sax.saxutils import escape

USER = os.environ.get("PROFILE_USER", "arielDirema")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

# Palette inspired by Dynamic Island (black, Windows 11 accent blue)
BG, BORDER, TEXT, MUTED, ACCENT = "#000000", "#30363d", "#ffffff", "#8b949e", "#4cc2ff"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"
LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "Kotlin": "#A97BFF", "Java": "#b07219",
    "PHP": "#4F5D95", "Blade": "#f7523f", "HTML": "#e34c26", "CSS": "#663399", "C": "#555555", "C++": "#f34b7d",
    "Dart": "#00B4AB", "Shell": "#89e051", "Jupyter Notebook": "#DA5B0B", "Vue": "#41b883", "SCSS": "#c6538c",
}


def request(url, data=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-cards"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, headers=headers,
                                 method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def collect():
    user = request(f"https://api.github.com/users/{USER}")
    repos = [r for r in request(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner")
             if not r["fork"] and r["name"].lower() != USER.lower()]
    langs = {}
    for r in repos:
        for lang, size in request(r["languages_url"]).items():
            langs[lang] = langs.get(lang, 0) + size
    stats = {
        "repos": len(repos),
        "stars": sum(r["stargazers_count"] for r in repos),
        "followers": user["followers"],
        "commits": None, "prs": None, "contributions": None,
    }
    if TOKEN:  # contributions over the last 12 months (GraphQL needs a token)
        q = """query($login: String!) { user(login: $login) { contributionsCollection {
                 totalCommitContributions totalPullRequestContributions
                 contributionCalendar { totalContributions } } } }"""
        try:
            c = request("https://api.github.com/graphql", {"query": q, "variables": {"login": USER}})
            cc = c["data"]["user"]["contributionsCollection"]
            stats.update(commits=cc["totalCommitContributions"], prs=cc["totalPullRequestContributions"],
                         contributions=cc["contributionCalendar"]["totalContributions"])
        except Exception as e:  # keep the public numbers if GraphQL is unavailable
            print("GraphQL indisponible :", e, file=sys.stderr)
    return stats, langs


def card(width, height, title, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
  <title>{escape(title)}</title>
  <style>
    .t {{ font: 600 16px {FONT}; fill: {TEXT}; }}
    .l {{ font: 400 13px {FONT}; fill: {MUTED}; }}
    .v {{ font: 700 13px {FONT}; fill: {TEXT}; }}
    .s {{ font: 400 11px {FONT}; fill: {MUTED}; }}
    .fade {{ animation: fade .6s ease both; }}
    @keyframes fade {{ from {{ opacity: 0; }} }}
    @keyframes grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
  </style>
  <rect x="0.5" y="0.5" rx="12" width="{width - 1}" height="{height - 1}" fill="{BG}" stroke="{BORDER}"/>
  <rect x="24" y="22" width="34" height="10" rx="5" fill="#000" stroke="#3d444d"/>
  <circle cx="51" cy="27" r="2.6" fill="{ACCENT}"/>
  <text x="68" y="32" class="t">{escape(title)}</text>
{body}
</svg>
"""


def icon(kind, x, y):
    """Small line icons (16 px), drawn in the accent colour."""
    s = f'fill="none" stroke="{ACCENT}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'
    paths = {
        "repo": f'<path {s} d="M{x+3} {y+2}h8a2 2 0 0 1 2 2v10H{x+5}a2 2 0 0 1-2-2z M{x+3} {y+12}a2 2 0 0 1 2-2h8"/>',
        "star": '<polygon ' + s + ' points="' + " ".join(
            f"{x + 8 + (7 if i % 2 == 0 else 3) * math.sin(i * math.pi / 5):.1f},"
            f"{y + 8.5 - (7 if i % 2 == 0 else 3) * math.cos(i * math.pi / 5):.1f}"
            for i in range(10)) + '"/>',
        "people": f'<circle {s} cx="{x+6}" cy="{y+5}" r="3"/><path {s} d="M{x+1} {y+14}c0-3 2.2-5 5-5s5 2 5 5 M{x+11} {y+2.5}a3 3 0 0 1 0 5.5 M{x+13} {y+9.5}c1.4.8 2.2 2.4 2.2 4.5"/>',
        "commit": f'<circle {s} cx="{x+8}" cy="{y+8}" r="3"/><path {s} d="M{x+1} {y+8}h4 M{x+11} {y+8}h4"/>',
        "pr": f'<circle {s} cx="{x+4}" cy="{y+3}" r="2"/><circle {s} cx="{x+4}" cy="{y+13}" r="2"/><circle {s} cx="{x+12}" cy="{y+13}" r="2"/><path {s} d="M{x+4} {y+5}v6 M{x+12} {y+11}V{y+7}a3 3 0 0 0-3-3H{x+7}"/>',
        "flame": f'<path {s} d="M{x+8} {y+15}c-3.3 0-5-2.2-5-4.8 0-3.4 3.2-4.6 3.2-8.2 2.8 1.6 4.3 4.1 3.8 6.6.9-.6 1.5-1.6 1.6-2.6 1.5 1.3 2.4 3 2.4 4.6 0 2.4-2 4.4-5 4.4z"/>',
    }
    return paths[kind]


def stats_card(stats):
    rows = [("repo", "Public repositories", stats["repos"]), ("star", "Stars earned", stats["stars"]),
            ("people", "Followers", stats["followers"])]
    if stats["contributions"] is not None:
        rows += [("flame", "Contributions (last year)", stats["contributions"]),
                 ("commit", "Commits (last year)", stats["commits"]), ("pr", "Pull requests (last year)", stats["prs"])]
    rows = [r for r in rows if r[2]]  # pas de ligne « 0 » sur la carte
    body = []
    for i, (kind, label, value) in enumerate(rows):
        y = 62 + i * 28
        body.append(f'  <g class="fade" style="animation-delay:{i * 120}ms">{icon(kind, 26, y - 12)}'
                    f'<text x="52" y="{y}" class="l">{escape(label)}</text>'
                    f'<text x="370" y="{y}" class="v" text-anchor="end">{value:,}</text></g>'.replace(",", " "))
    height = 62 + len(rows) * 28
    return card(400, height, "GitHub stats", "\n".join(body))


def languages_card(langs):
    total = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1])[:6]
    shown = sum(v for _, v in top)
    if total - shown > 0:
        top.append(("Other", total - shown))
    body, x = [], 24.0
    width = 352
    body.append(f'  <clipPath id="bar"><rect x="24" y="52" width="{width}" height="10" rx="5"/></clipPath>')
    body.append('  <g clip-path="url(#bar)" style="transform-origin:24px 0;animation:grow .9s ease">')
    for lang, size in top:
        w = width * size / total
        body.append(f'    <rect x="{x:.2f}" y="52" width="{w + 0.5:.2f}" height="10" fill="{LANG_COLORS.get(lang, "#6e7681")}"/>')
        x += w
    body.append("  </g>")
    for i, (lang, size) in enumerate(top):
        cx = 24 + (i % 2) * 180
        cy = 88 + (i // 2) * 24
        body.append(f'  <g class="fade" style="animation-delay:{300 + i * 90}ms">'
                    f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{LANG_COLORS.get(lang, "#6e7681")}"/>'
                    f'<text x="{cx + 16}" y="{cy}" class="l">{escape(lang)}</text>'
                    f'<text x="{cx + 168}" y="{cy}" class="v" text-anchor="end">{100 * size / total:.1f}%</text></g>')
    height = 88 + ((len(top) + 1) // 2) * 24 - 4
    return card(400, height, "Most used languages", "\n".join(body))


def main():
    os.makedirs(OUT, exist_ok=True)
    stats, langs = collect()
    with open(os.path.join(OUT, "stats.svg"), "w", encoding="utf-8") as f:
        f.write(stats_card(stats))
    with open(os.path.join(OUT, "languages.svg"), "w", encoding="utf-8") as f:
        f.write(languages_card(langs))
    print("stats :", stats)
    print("langages :", sorted(langs.items(), key=lambda kv: -kv[1])[:6])


if __name__ == "__main__":
    main()
