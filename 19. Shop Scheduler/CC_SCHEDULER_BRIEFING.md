# Claude Code Briefing — Project Survey & Scheduler Contribution Analysis

## Context

Traxis Manufacturing is a 5-person precision CNC job shop running 8 mills and 2 lathes. We are building a **daily job readiness scheduler** — a morning briefing report that answers:

1. Which machines are opening in the next 10 days?
2. Which jobs are fully ready to run (material + tooling + program complete)?
3. What does Garrett need to program this week to hit upcoming machine openings?
4. What does Rene need to order today given lead times and projected run dates?

The goal is to surface this as a daily generated summary the owner can use to direct the team each morning.

---

## Data Sources Available

- **ProShop ERP** — GraphQL API at `https://traxismfg.adionsystems.com/api/graphql`, credentials in `.traxis.env`. Tracks: job queue, material type and order status, tooling requirements per job, planned hours, due dates, inspection status.
- **FOCAS Monitor** — C# service logging real Fanuc machine data to a local database. Provides actual machine runtime, idle time, and utilization metrics that can inform real projected machine opening times.
- **Fusion 360 / CAM sidecar JSONs** — Post processor outputs per-operation tool data as JSON sidecar files alongside NC programs.

---

## Task 1 — Project Inventory

Survey all project folders under:
`MACHINE COMM Traxis\Proshop Automation and Claude Projects`

For each project found, provide:
- **Project name / folder number**
- **What it does** (1-2 sentences)
- **Systems it touches** (ProShop, FOCAS, Fusion, Dropbox, other)
- **Data it reads and/or writes**
- **Current status** (working / partial / stalled / unknown)

---

## Task 2 — Scheduler Contribution Mapping

After the inventory, identify which existing tools could contribute to the job readiness scheduler and how:

- What data could it provide?
- Does it need modification or just integration?
- What's the connection point (API call, file read, database query)?

Flag any gaps — things the scheduler needs that no existing tool currently provides.

---

## Task 3 — ProShop Data Reality Check

Query ProShop for a sample of 10-15 active jobs and report:

- Which scheduling-relevant fields are **populated and usable** (due dates, planned hours, material order status, tooling status)
- Which fields exist but are **consistently empty**
- What's **missing entirely** that the scheduler would need

This will ground the scheduler design in what the data actually looks like, not what we assume.

---

## Output Format

Return results as structured markdown. Be direct about gaps and unknowns — we'd rather know what's missing than have it papered over.
