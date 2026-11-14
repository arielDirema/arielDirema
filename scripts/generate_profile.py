"""Generate the profile images from the GitHub API:

- assets/header.svg   : profile brief (name, role, school) with the avatar rendered as coloured ASCII art
- assets/activity.svg : key figures, contribution heatmap (last 12 months) and language breakdown

Runs daily in GitHub Actions (.github/workflows/profile-assets.yml), so the README does not depend on
third-party card services. Needs Pillow for the ASCII art; uses GITHUB_TOKEN when available.
"""
import datetime as dt
import io
import json
import os
import sys
import urllib.request
from xml.sax.saxutils import escape

USER = os.environ.get("PROFILE_USER", "arielDirema")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

ROLE = "Backend & Systems Engineer"
TAGLINE = "Building and sharing work in public"
SCHOOL = "Software Engineering student · École Polytechnique de Lomé"

# Sober GitHub-dark palette
BG0, BG1, BORDER = "#0d1117", "#161b22", "#30363d"
TEXT, MUTED, SUBTLE, LINK = "#e6edf3", "#8b949e", "#6e7681", "#58a6ff"
GREENS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
SANS = "'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "Consolas, 'SFMono-Regular', 'Liberation Mono', Menlo, monospace"
LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "Kotlin": "#A97BFF", "Java": "#b07219",
    "PHP": "#4F5D95", "Blade": "#f7523f", "HTML": "#e34c26", "CSS": "#663399", "Jupyter Notebook": "#DA5B0B",
    "Shell": "#89e051", "C": "#555555", "C++": "#f34b7d", "Dart": "#00B4AB", "Vue": "#41b883",
}


# ------------------------------------------------------------------ GitHub API
def request(url, data=None, raw=False):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-generator"}
    if TOKEN and "api.github.com" in url:
        headers["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, headers=headers,
                                 method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    return body if raw else json.loads(body)


def collect():
    user = request(f"https://api.github.com/users/{USER}")
    repos = [r for r in request(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner")
             if not r["fork"] and r["name"].lower() != USER.lower()]
    langs = {}
    for r in repos:
        for lang, size in request(r["languages_url"]).items():
            langs[lang] = langs.get(lang, 0) + size
    data = {"user": user, "repos": len(repos), "stars": sum(r["stargazers_count"] for r in repos),
            "followers": user["followers"], "langs": langs, "calendar": None, "contributions": None}
    if TOKEN:
        q = """query($login: String!) { user(login: $login) { contributionsCollection {
                 contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } } } } }"""
        try:
            c = request("https://api.github.com/graphql", {"query": q, "variables": {"login": USER}})
            cal = c["data"]["user"]["contributionsCollection"]["contributionCalendar"]
            data["contributions"] = cal["totalContributions"]
            data["calendar"] = [[(d["date"], d["contributionCount"]) for d in w["contributionDays"]] for w in cal["weeks"]]
        except Exception as e:
            print("GraphQL indisponible :", e, file=sys.stderr)
    return data


# ------------------------------------------------------------------ texte
def text_width(s, size, bold=False):
    """Approximate rendered width (sans-serif), enough to wrap a title."""
    return sum((0.36 if c in "il.,:'· " else 0.62 if c.isupper() else 0.54) for c in s) * size * (1.06 if bold else 1)


def wrap(s, size, max_w, bold=False):
    words, lines, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if text_width(t, size, bold) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


# ------------------------------------------------------------------ ASCII art
def ascii_avatar(url, cols, rows):
    """Avatar → rows of (char, colour). Dark pixels become spaces so the portrait floats on the background."""
    from PIL import Image, ImageEnhance, ImageOps
    img = Image.open(io.BytesIO(request(url, raw=True))).convert("RGB")
    side = min(img.size)
    img = img.crop(((img.width - side) // 2, (img.height - side) // 2,
                    (img.width + side) // 2, (img.height + side) // 2))
    img = img.resize((cols, rows), Image.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=1)              # étale l'histogramme d'une photo très sombre
    img = ImageEnhance.Color(img).enhance(1.5)              # couleurs plus franches (vert, orange)
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=1)
    ramp = " .'`,:;-~=+i!lI?7tfjxzvcunrJYUCLQ0OZmwqpdbkhao*#MW&8%B@"
    out = []
    for y in range(rows):
        row = []
        for x in range(cols):
            lum = (gray.getpixel((x, y)) / 255) ** 0.8
            if lum < 0.12:                                   # quasi-noir : espace (fond plus propre)
                row.append((" ", None))
                continue
            ch = ramp[min(len(ramp) - 1, int(lum * len(ramp)))]
            r, g, b = img.getpixel((x, y))
            k = min(3.2, (125 + 130 * lum) / max(1, max(r, g, b)))  # tons sombres lisibles, zones claires vives
            col = "#%02x%02x%02x" % tuple(min(255, int(c * k)) & 0xF0 for c in (r, g, b))
            row.append((ch, col))
        out.append(row)
    return out


def ascii_svg(art, x0, y0, size):
    cw, lh = size * 0.6, size * 1.0
    parts = []
    for y, row in enumerate(art):
        spans, cur_col, buf = [], None, ""
        for ch, col in row + [(None, "END")]:
            if col != cur_col and buf:
                spans.append((buf, cur_col))
                buf = ""
            cur_col = col
            if ch is not None:
                buf += ch
        line = "".join(f'<tspan fill="{c}">{escape(t)}</tspan>' if c else escape(t) for t, c in spans)
        parts.append(f'<text x="{x0}" y="{y0 + (y + 1) * lh:.1f}" xml:space="preserve">{line}</text>')
    return (f'<g font-family="{MONO}" font-size="{size}" font-weight="700" fill="{SUBTLE}">' + "".join(parts) + "</g>",
            cw * len(art[0]), lh * len(art))


# ------------------------------------------------------------------ en-tête
def header_svg(data):
    W, H = 880, 400
    split = 520
    user = data["user"]
    name = user.get("name") or USER
    name_lines = wrap(name, 34, split - 80, bold=True)
    y = 62
    body = [f'<text x="{split / 2}" y="{y}" class="eyebrow" text-anchor="middle">GITHUB PROFILE · {escape(USER.upper())}</text>']
    y += 54
    for i, line in enumerate(name_lines):
        body.append(f'<text x="{split / 2}" y="{y + i * 42}" class="name" text-anchor="middle">{escape(line)}</text>')
    y += (len(name_lines) - 1) * 42 + 28
    body.append(f'<line x1="40" y1="{y}" x2="{split - 40}" y2="{y}" stroke="{BORDER}"/>')
    y += 44
    body.append(f'<text x="{split / 2}" y="{y}" class="role" text-anchor="middle">{escape(ROLE)}</text>')
    y += 22
    body.append(f'<line x1="40" y1="{y}" x2="{split - 40}" y2="{y}" stroke="{BORDER}"/>')
    y += 34
    body.append(f'<text x="{split / 2}" y="{y}" class="muted" text-anchor="middle">{escape(SCHOOL)}</text>')
    y += 32
    tw = text_width(TAGLINE, 15, True)
    body.append(f'<circle cx="{split / 2 - tw / 2 - 10}" cy="{y - 5}" r="4" fill="{GREENS[4]}"/>'
                f'<text x="{split / 2 + 4}" y="{y}" class="strong" text-anchor="middle">{escape(TAGLINE)}</text>')
    y += 32
    body.append(f'<text x="{split / 2}" y="{y}" class="link" text-anchor="middle">github.com/{escape(USER)}</text>')

    # portrait ASCII
    cols, rows, size = 84, 48, 5
    try:
        art = ascii_avatar(user["avatar_url"] + "&s=200", cols, rows)
        g, aw, ah = ascii_svg(art, 0, 0, size)
        ax = split + (W - split - aw) / 2
        ay = (H - ah) / 2 - 4
        portrait = f'<g transform="translate({ax:.1f} {ay:.1f})">{g}</g>'
    except Exception as e:  # Pillow absent ou avatar injoignable : on garde la carte sans portrait
        print("ASCII indisponible :", e, file=sys.stderr)
        portrait = ""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(name)} — {escape(ROLE)}">
  <title>{escape(name)} — {escape(ROLE)}</title>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{BG1}"/><stop offset="1" stop-color="{BG0}"/>
    </linearGradient>
  </defs>
  <style>
    .eyebrow {{ font: 600 11px {SANS}; letter-spacing: 1.6px; fill: {MUTED}; }}
    .name {{ font: 800 34px {SANS}; fill: {TEXT}; }}
    .role {{ font: 700 26px {SANS}; fill: {TEXT}; }}
    .muted {{ font: 400 15px {SANS}; fill: {MUTED}; }}
    .strong {{ font: 700 15px {SANS}; fill: {TEXT}; }}
    .link {{ font: 600 15px {SANS}; fill: {LINK}; }}
  </style>
  <rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="10" fill="url(#bg)" stroke="{BORDER}"/>
  <line x1="{split}" y1="1" x2="{split}" y2="{H - 1}" stroke="{BORDER}"/>
  {"".join(body)}
  {portrait}
</svg>
"""


# ------------------------------------------------------------------ activité
def activity_svg(data):
    W = 880
    pad = 32
    parts = [f'<text x="{pad}" y="44" class="eyebrow">GITHUB ACTIVITY</text>']
    # chiffres clés
    kpis = [("Repositories", data["repos"]), ("Stars", data["stars"]), ("Followers", data["followers"])]
    if data["contributions"] is not None:
        kpis.append(("Contributions · 12 mo", data["contributions"]))
    tile_w = (W - 2 * pad - (len(kpis) - 1) * 12) / len(kpis)
    for i, (label, value) in enumerate(kpis):
        x = pad + i * (tile_w + 12)
        parts.append(f'<rect x="{x:.1f}" y="62" width="{tile_w:.1f}" height="74" rx="8" fill="{BG1}" stroke="{BORDER}"/>'
                     f'<text x="{x + 18:.1f}" y="104" class="kpi">{value}</text>'
                     f'<text x="{x + 18:.1f}" y="124" class="label">{escape(label)}</text>')
    y = 164
    # calendrier des contributions
    cal = data["calendar"]
    if cal:
        weeks = cal[-53:]
        cell, gap = 11, 3
        grid_w = len(weeks) * (cell + gap) - gap
        gx = pad + (W - 2 * pad - grid_w) / 2
        parts.append(f'<text x="{pad}" y="{y}" class="section">Contributions in the last year</text>')
        y += 16
        mx = max([c for w in weeks for _, c in w] + [1])
        last_month = None
        for wi, week in enumerate(weeks):
            first = dt.date.fromisoformat(week[0][0])
            if first.month != last_month and first.day <= 7:
                parts.append(f'<text x="{gx + wi * (cell + gap):.1f}" y="{y + 8}" class="tiny">{first.strftime("%b")}</text>')
                last_month = first.month
        y += 16
        for wi, week in enumerate(weeks):
            for date, count in week:
                d = dt.date.fromisoformat(date)
                lvl = 0 if count == 0 else min(4, 1 + int(3 * count / mx))
                parts.append(f'<rect x="{gx + wi * (cell + gap):.1f}" y="{y + d.isoweekday() % 7 * (cell + gap)}" '
                             f'width="{cell}" height="{cell}" rx="2" fill="{GREENS[lvl]}"><title>{count} on {date}</title></rect>')
        y += 7 * (cell + gap) + 10
        lx = gx + grid_w - 5 * (cell + gap) - 70
        parts.append(f'<text x="{lx - 6:.1f}" y="{y + 9}" class="tiny" text-anchor="end">Less</text>')
        for i, c in enumerate(GREENS):
            parts.append(f'<rect x="{lx + i * (cell + gap):.1f}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{c}"/>')
        parts.append(f'<text x="{lx + 5 * (cell + gap) + 4:.1f}" y="{y + 9}" class="tiny">More</text>')
        y += 34
    # langages
    langs = data["langs"]
    total = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1])[:6]
    rest = total - sum(v for _, v in top)
    if rest > 0:
        top.append(("Other", rest))
    parts.append(f'<text x="{pad}" y="{y}" class="section">Languages</text>')
    y += 14
    bw = W - 2 * pad
    parts.append(f'<clipPath id="bar"><rect x="{pad}" y="{y}" width="{bw}" height="8" rx="4"/></clipPath><g clip-path="url(#bar)">')
    x = pad
    for lang, size in top:
        w = bw * size / total
        parts.append(f'<rect x="{x:.1f}" y="{y}" width="{w + 0.6:.1f}" height="8" fill="{LANG_COLORS.get(lang, SUBTLE)}"/>')
        x += w
    parts.append("</g>")
    y += 32
    x = pad
    for lang, size in top:
        label = f"{lang} {100 * size / total:.1f}%"
        parts.append(f'<circle cx="{x + 5}" cy="{y - 4}" r="5" fill="{LANG_COLORS.get(lang, SUBTLE)}"/>'
                     f'<text x="{x + 15}" y="{y}" class="label"><tspan class="strongs">{escape(lang)}</tspan> '
                     f'{100 * size / total:.1f}%</text>')
        x += 26 + text_width(label, 13) + 14
        if x > W - pad - 120:
            x = pad
            y += 24
    H = y + 30
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="GitHub activity of {escape(USER)}">
  <title>GitHub activity of {escape(USER)}</title>
  <style>
    .eyebrow {{ font: 600 11px {SANS}; letter-spacing: 1.6px; fill: {MUTED}; }}
    .section {{ font: 600 14px {SANS}; fill: {TEXT}; }}
    .kpi {{ font: 700 28px {SANS}; fill: {TEXT}; }}
    .label {{ font: 400 13px {SANS}; fill: {MUTED}; }}
    .strongs {{ font-weight: 600; fill: {TEXT}; }}
    .tiny {{ font: 400 10px {SANS}; fill: {MUTED}; }}
  </style>
  <rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="10" fill="{BG0}" stroke="{BORDER}"/>
  {"".join(parts)}
</svg>
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    data = collect()
    for name, svg in (("header.svg", header_svg(data)), ("activity.svg", activity_svg(data))):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(svg)
        print(name, len(svg) // 1024, "Ko")
    print({k: data[k] for k in ("repos", "stars", "followers", "contributions")})


if __name__ == "__main__":
    main()
