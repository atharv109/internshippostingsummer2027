# intern-radar

Finds Summer 2027 software internships at startups that **aren't** on
[SimplifyJobs' list](https://github.com/SimplifyJobs/Summer2027-Internships), and drops
any posting that requires citizenship, ITAR/U.S. person status, a clearance, or no
sponsorship "now or in the future."

**Results:** [RESULTS.md](RESULTS.md) (open roles) and `results.csv` (everything, with the blocking phrase for excluded roles).

## How it works
1. Takes every active, hiring YC company plus anything in `extra_companies.txt`.
2. Finds which public job board each one uses (Ashby, Greenhouse or Lever) and caches it in `boards.json`.
3. Pulls their postings daily, keeps software intern roles, removes anything already on Simplify.
4. Sorts so the roles with likely the fewest applicants come first: company not on Simplify at all, newest posting, smallest team.

## Setup
1. Push this folder to a new GitHub repo.
2. Actions tab → **intern-radar** → **Run workflow** (tick *discover* the first time).
3. It then runs every morning and commits fresh results.

Add a company: put its job-board slug (the part after `jobs.ashbyhq.com/`, `boards.greenhouse.io/` or `jobs.lever.co/`) on a new line in `extra_companies.txt`.
