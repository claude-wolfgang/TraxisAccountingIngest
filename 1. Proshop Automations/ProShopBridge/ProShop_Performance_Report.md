# ProShop Performance Issue Report

**From:** Traxis Manufacturing
**To:** Adion Systems / ProShop Support
**Date:** April 11, 2026
**Re:** Significant page load and form submission delays on traxismfg.adionsystems.com

---

## Summary

We are experiencing significant performance degradation on our ProShop instance that is impacting daily operations. Page loads that previously completed in a few seconds are now routinely timing out, and form submissions for written descriptions are taking over two minutes to process. This affects both manual browser use and our Fusion 360 integration tooling.

## Network Verification

We have confirmed that the issue is not on our end. Direct network measurements to your server:

| Metric | Result |
|--------|--------|
| DNS resolution | 5 ms |
| TCP connect | 60 ms |
| TLS handshake | 183 ms |
| First byte (server response) | 287 ms |
| Fileserver static asset (ckeditor.js, 740 KB) | 573 ms |
| Google.com baseline (for comparison) | 150 ms |

Our network connectivity to your server is healthy. The delays are occurring during server-side processing, not data transfer.

## Observed Performance Issues

We have instrumented our integration tooling with detailed timing logs. The following measurements were recorded on April 11, 2026, across multiple sessions:

### Login Page

| Attempt | Time |
|---------|------|
| 1 | 8.3 s |
| 2 | 7.9 s |
| 3 | 6.8 s |
| 4 | 13.3 s |
| 5 | 9.7 s |
| 6 | 9.6 s |
| 7 | 14.7 s |
| 8 | 6.7 s |

**Average login time: 9.6 seconds.** This is the time from submitting credentials to receiving the authenticated response.

### Written Description Page Load

The written description page for part 10130, OP 80, consistently fails to fully load within 20 seconds. The HTML content and application UI (buttons, CKEditor) load within the first few seconds, but the page continues requesting resources from the fileserver that prevent the browser from reporting the page as complete.

| Attempt | Result |
|---------|--------|
| 1 | Timed out at 20 s (partial load) |
| 2 | Timed out at 20 s (partial load) |
| 3 | Timed out at 20 s (partial load) |
| 4 | Timed out at 20 s (partial load) |

Every single written description page load on this part timed out at 20 seconds.

### Written Description Save (Form POST)

Saving a written description with embedded screenshots (~400 KB payload) took over 120 seconds for the server to process and respond. The page URL updated to include `isSubmit=yes` and eventually returned to view mode, confirming the server did process the submission — it just took an extraordinary amount of time.

### Sequence Detail Page (for comparison)

The sequence detail page for the same part loads in 2.8 to 5.8 seconds, which is noticeably faster but still slower than expected for a table view.

## Impact

- **Manual use is tedious.** Navigating between pages, checking out records, and saving changes all involve multi-second waits that add up significantly over a workday.
- **Integration tooling is breaking.** Our Fusion 360 add-in automates written description updates. The server-side delays are causing browser timeouts that prevent automated saves from completing reliably.
- **This is a regression.** The same workflows were completing successfully in March 2026. No changes have been made on our end — same machines, same network, same browser versions.

## What We Are Asking

1. **Investigation into server-side performance** — particularly the written description page load and form POST processing times. A 400 KB form submission should not take 2+ minutes.
2. **Fileserver resource loading** — pages appear to hang on requests to the `/fileserver/images/` path during full page loads, even though the application content is ready. This may be a static asset caching or CDN configuration issue.
3. **Any known issues or recent changes** — if there have been updates to the ProShop platform, database, or hosting infrastructure that may explain the timing of this regression.

We are happy to provide additional diagnostic data, logs, or screenshots to assist with the investigation.

Thank you for your attention to this matter.

---

*Diagnostic data collected via automated instrumentation with timestamped logging on April 11, 2026.*
