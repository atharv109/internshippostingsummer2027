"""Find Summer 2027 software internships at startups that aren't on SimplifyJobs' list.

Sources: YC companies (yc-oss) + extra_companies.txt, checked against the public
Ashby / Greenhouse / Lever job-board APIs. Stdlib only.
"""
import csv, html, json, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

SIMPLIFY = "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/README.md"
YC = "https://yc-oss.github.io/api/companies/all.json"
BOARDS_FILE, OUT_CSV, OUT_MD = "boards.json", "results.csv", "RESULTS.md"

INTERN = re.compile(r"\bintern(ship)?\b|\bco-?op\b", re.I)
SOFTWARE = re.compile(r"software|engineer|developer|backend|back-end|frontend|front-end|full.?stack|platform|infrastructure|\bml\b|machine learning|\bai\b|data|security|devops|\bsre\b|product engineer", re.I)
NOT_SOFTWARE = re.compile(r"mechanical|electrical|hardware|manufactur|civil|chemical|firmware|embedded|\brf\b|structures|propulsion|thermal|avionics|marketing|sales|finance|legal|recruit|design intern|operations intern|\bhr\b", re.I)
WRONG_TERM = re.compile(r"\b(fall|spring|winter)\b|\b2026\b", re.I)
# Postings that rule out F-1 students
BLOCKED = re.compile(
    r"\bITAR\b|export control|u\.?s\.? persons?\b|u\.?s\.? citizen|united states citizen|security clearance|"
    r"(sponsor\w*)[^.]{0,80}(now or in the future|future)|"
    r"(now or in the future)[^.]{0,80}sponsor|\bOPT\b[^.]{0,60}not eligible",
    re.I)


def get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "intern-radar/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


# ---------- board APIs: each returns a list of normalized postings ----------
def ashby(slug):
    d = get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")
    return [dict(title=j["title"], location=j.get("location", ""), url=j["jobUrl"],
                 posted=j.get("publishedAt", ""), body=j.get("descriptionPlain") or text(j.get("descriptionHtml")),
                 pay=(j.get("compensation") or {}).get("compensationTierSummary", ""))
            for j in d.get("jobs", [])]


def greenhouse(slug):
    d = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    return [dict(title=j["title"], location=(j.get("location") or {}).get("name", ""), url=j["absolute_url"],
                 posted=j.get("first_published") or j.get("updated_at", ""), body=text(j.get("content")), pay="")
            for j in d.get("jobs", [])]


def lever(slug):
    d = get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    out = []
    for j in d:
        ts = j.get("createdAt")
        posted = datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat() if ts else ""
        body = j.get("descriptionPlain", "") + " " + " ".join(text(l.get("content")) for l in j.get("lists", []))
        out.append(dict(title=j["text"], location=(j.get("categories") or {}).get("location", ""),
                        url=j["hostedUrl"], posted=posted, body=body, pay=""))
    return out


ATS = {"ashby": ashby, "greenhouse": greenhouse, "lever": lever}


# ---------- discovery: which board does each company use? ----------
def slug_guesses(c):
    name = re.sub(r"[^a-z0-9 ]", "", c["name"].lower())
    return list(dict.fromkeys(filter(None, [c.get("slug", ""), name.replace(" ", ""), name.replace(" ", "-")])))


def find_board(c):
    for ats, fn in ATS.items():
        for slug in slug_guesses(c):
            try:
                if fn(slug):  # non-empty board = match
                    return c["name"], {"ats": ats, "slug": slug, "team_size": c.get("team_size"), "batch": c.get("batch", "")}
            except Exception:
                pass
    return c["name"], None


def discover(boards):
    companies = [c for c in get(YC, 60) if c.get("status") == "Active" and c.get("isHiring", True)]
    for line in open("extra_companies.txt"):
        line = line.split("#")[0].strip()
        if line:
            companies.append({"name": line, "slug": line})
    todo = [c for c in companies if c["name"] not in boards]
    print(f"discovering boards for {len(todo)} companies", file=sys.stderr)
    with ThreadPoolExecutor(32) as ex:
        for name, b in ex.map(find_board, todo):
            boards[name] = b  # None = checked, no public board
    return boards


# ---------- Simplify list ----------
def simplify_index():
    md = urllib.request.urlopen(SIMPLIFY, timeout=60).read().decode()
    flat = set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d{6,}", md))
    companies = {norm(c) for c in re.findall(r'utm_medium=company">([^<]+)</a>', md)}
    return flat, companies


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def posting_ids(url):
    return re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d{6,}", url)


def keep(p):
    t = p["title"]
    return bool(INTERN.search(t) and SOFTWARE.search(t) and not NOT_SOFTWARE.search(t)
                and not (WRONG_TERM.search(t) and "summer" not in t.lower()))


def days_old(iso):
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days
    except Exception:
        return None


def scan_board(item):
    name, b = item
    try:
        return name, b, ATS[b["ats"]](b["slug"])
    except Exception:
        return name, b, []


def main(rediscover=False):
    try:
        boards = json.load(open(BOARDS_FILE))
    except FileNotFoundError:
        boards = {}
    if rediscover or not boards:
        boards = discover(boards)
        json.dump(boards, open(BOARDS_FILE, "w"), indent=1, sort_keys=True)

    simplify_ids, simplify_cos = simplify_index()
    rows = []
    with ThreadPoolExecutor(32) as ex:
        for name, b, posts in ex.map(scan_board, [(n, b) for n, b in boards.items() if b]):
            for p in filter(keep, posts):
                if any(i in simplify_ids for i in posting_ids(p["url"])):
                    continue
                blocked = BLOCKED.search(p["body"])
                rows.append(dict(company=name, title=p["title"], location=p["location"], days_old=days_old(p["posted"]),
                                 team_size=b.get("team_size") or "", yc_batch=b.get("batch", ""), pay=p["pay"],
                                 company_on_simplify="yes" if norm(name) in simplify_cos else "no",
                                 f1_blocker=blocked.group(0) if blocked else "", url=p["url"]))

    # fewest likely applicants first: not blocked, company absent from Simplify, newest, smallest team
    rows.sort(key=lambda r: (bool(r["f1_blocker"]), r["company_on_simplify"] == "yes",
                             r["days_old"] if r["days_old"] is not None else 999, int(r["team_size"] or 10**6)))
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["company"])
        w.writeheader(); w.writerows(rows)

    ok = [r for r in rows if not r["f1_blocker"]]
    with open(OUT_MD, "w") as f:
        f.write(f"# Startup software internships not on SimplifyJobs\n\nUpdated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. "
                f"{len(ok)} open to F-1 students, {len(rows) - len(ok)} excluded for citizenship/ITAR/sponsorship wording "
                f"(see results.csv). Sorted fewest likely applicants first.\n\n"
                "| Company | Role | Location | Age | Team | Pay | Link |\n|---|---|---|---|---|---|---|\n")
        for r in ok:
            age = f'{r["days_old"]}d' if r["days_old"] is not None else "?"
            f.write(f'| {r["company"]} | {r["title"]} | {r["location"]} | {age} | {r["team_size"]} | {r["pay"]} | [Apply]({r["url"]}) |\n')
    print(f"{len(ok)} open, {len(rows) - len(ok)} blocked, from {sum(1 for b in boards.values() if b)} boards", file=sys.stderr)


if __name__ == "__main__":
    main(rediscover="--discover" in sys.argv)
