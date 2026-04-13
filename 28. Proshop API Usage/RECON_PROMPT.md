# ProShop API Usage — Recon Mission

## Instructions for Claude Code

**Read this before doing anything else. This is a reconnaissance mission only — no files are to be created, modified, or deleted.**

The shop has received a complaint from ProShop (our ERP host) that we are averaging **1,600 API calls per hour**. We need to understand where those calls are coming from before we build any monitoring or rate-limiting solution.

---

## Your Task

Investigate how automation scripts across the Traxis project ecosystem make calls to the ProShop GraphQL API. Do not write, modify, or delete any files. Report only.

---

## Where to Look

Primary search root:
```
D:\Dropbox\MACHINE COMM Traxis\Proshop Automation and Claude Projects\
```

Search every numbered project subfolder. Also check:
- Any `.py` files anywhere under the root
- Windows Task Scheduler (run `schtasks /query /fo LIST /v` and look for anything Traxis-related)
- Any `.bat` or `.ps1` files that might launch Python scripts on a schedule

---

## What to Look For

Search for files containing any of these strings:
- `api/graphql`
- `accesstoken`
- `client_credentials`
- `execute(`
- `requests.post`
- `httpx`
- `gql`

---

## Questions to Answer

1. **How many distinct scripts make ProShop API calls?**  
   List each one by filename and project folder number.

2. **Does any code share a common API client, or does each script have its own auth/HTTP logic?**  
   If shared, identify the shared module. If not, note each script's approach.

3. **What GraphQL queries does each script run?**  
   List query/mutation names or paste the query strings if short. Note if any use pagination or fetch large collections (e.g., all work orders).

4. **Are any scripts running on a loop, schedule, or polling interval?**  
   Look for `while True`, `time.sleep`, `schedule`, cron-style patterns, or Task Scheduler entries. If found, estimate calls per hour.

5. **Are any scripts triggered by external events** (file watcher, webhook, button press) **vs. running continuously?**

6. **What would it take to route all scripts through a single shared client?**  
   Estimate effort per script — is it a one-line import swap, or does each one have deeply embedded auth logic?

---

## Deliverable

Produce a markdown report with:
- A summary table: `Script | Folder | Query Types | Call Pattern | Estimated Calls/Hr`
- A section per script with findings
- A section at the end: "Most likely culprits for high call volume"
- A section: "Recommended path to shared client"

Save the report as `RECON_REPORT.md` in the project folder for API monitoring.

**Do not write any other files.**
