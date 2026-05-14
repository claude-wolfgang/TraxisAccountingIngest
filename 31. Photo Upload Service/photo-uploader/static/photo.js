/**
 * Photo Upload Service — Frontend Logic
 *
 * Flow:
 *   1. Choose entity type
 *   2. Search for entity (or scan QR)
 *   2b. (Work orders only) Select operation
 *   3. Take photo
 *   4. Upload
 */

(function () {
    "use strict";

    // ── State ────────────────────────────────────────────────────────────

    let currentType = "";
    let selectedEntity = null;
    let selectedOp = null;       // {opNumber, description, workCenter}
    let capturedFile = null;
    let searchTimeout = null;

    const TYPE_LABELS = {
        workorder: "Work Order",
        tool: "Tool",
        equipment: "Equipment",
        part: "Part",
        fixture: "Fixture",
        cots: "COTS",
        ncr: "NCR",
        claude: "Claude",
    };

    // ── DOM refs ─────────────────────────────────────────────────────────

    const steps = {
        type: document.getElementById("step-type"),
        search: document.getElementById("step-search"),
        qr: document.getElementById("step-qr"),
        ops: document.getElementById("step-ops"),
        capture: document.getElementById("step-capture"),
        suggest: document.getElementById("step-suggest"),
        done: document.getElementById("step-done"),
    };

    const searchInput = document.getElementById("search-input");
    const searchSpinner = document.getElementById("search-spinner");
    const searchResults = document.getElementById("search-results");
    const searchTypeLabel = document.getElementById("search-type-label");

    const opsEntityId = document.querySelector("#ops-entity-info .entity-id");
    const opsEntityName = document.querySelector("#ops-entity-info .entity-name");
    const opsSpinner = document.getElementById("ops-spinner");
    const opsList = document.getElementById("ops-list");

    const entityInfoId = document.querySelector("#entity-info .entity-id");
    const entityInfoName = document.querySelector("#entity-info .entity-name");

    const photoCapture = document.getElementById("photo-capture");
    const photoPreview = document.getElementById("photo-preview");
    const previewContainer = document.getElementById("preview-container");
    const photoNote = document.getElementById("photo-note");
    const uploadBtn = document.getElementById("btn-upload");

    const qrCapture = document.getElementById("qr-capture");
    const qrStatus = document.getElementById("qr-status");

    // ── Navigation ───────────────────────────────────────────────────────

    function showStep(stepKey) {
        Object.values(steps).forEach((s) => s.classList.remove("active"));
        steps[stepKey].classList.add("active");
    }

    function reset() {
        currentType = "";
        selectedEntity = null;
        selectedOp = null;
        capturedFile = null;
        searchInput.value = "";
        searchResults.innerHTML = "";
        opsList.innerHTML = "";
        photoNote.value = "";
        previewContainer.classList.add("hidden");
        uploadBtn.classList.add("hidden");
        uploadBtn.disabled = true;
        uploadBtn.textContent = "Upload Photo";
        photoCapture.value = "";
        qrCapture.value = "";
        qrStatus.textContent = "";
        showStep("type");
    }

    // ── Step 1: Entity type selection ────────────────────────────────────

    document.querySelectorAll(".type-btn[data-type]").forEach((btn) => {
        btn.addEventListener("click", () => {
            const type = btn.dataset.type;
            if (type === "qr") {
                showStep("qr");
                return;
            }
            if (type === "suggest") {
                document.getElementById("suggestion-text").value = "";
                showStep("suggest");
                return;
            }
            currentType = type;
            if (type === "claude") {
                const ts = new Date().toISOString().slice(0, 16).replace("T", " ");
                selectedEntity = { id: ts, name: "Claude photo", proshop_url: "" };
                goToCapture(selectedEntity);
                return;
            }
            searchTypeLabel.textContent = TYPE_LABELS[type] || type;
            searchInput.value = "";
            searchResults.innerHTML = "";
            searchInput.inputMode = "text";
            searchInput.placeholder = (type === "workorder") ? "Type WO number or part number..." : "Search by name or ID...";
            showStep("search");
            searchInput.focus();
        });
    });

    // ── Step 2: Search ───────────────────────────────────────────────────

    document.getElementById("search-qr-capture").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        try {
            const data = await decodeQR(file);
            if (data && handleQRResult(data)) return;
            showToast("No QR code found", true);
        } catch (err) {
            showToast("QR scan failed", true);
        }
        e.target.value = "";
    });

    document.getElementById("btn-search").addEventListener("click", () => {
        searchInput.blur();
        const q = searchInput.value.trim();
        if (q.length >= 2) doSearch(q);
        setTimeout(() => {
            searchResults.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 300);
    });

    // Auto-format pure-digit WO searches as "XX-XXXX" — ProShop's WO
    // number format always has a dash after the 2-digit year, and typing
    // "260120" on a tablet should resolve to "26-0120". Skipped if the
    // user already typed a dash or any non-digit (e.g. a part number).
    function maybeAutoHyphen() {
        if (currentType !== "workorder") return;
        const raw = searchInput.value;
        if (raw.length < 3) return;
        if (!/^\d+$/.test(raw)) return;
        const next = raw.slice(0, 2) + "-" + raw.slice(2);
        searchInput.value = next;
        // Keep caret at end so the user can keep typing without
        // landing back at position 0 (some browsers reset on .value=).
        try { searchInput.setSelectionRange(next.length, next.length); } catch (_) {}
    }

    searchInput.addEventListener("input", () => {
        maybeAutoHyphen();
        clearTimeout(searchTimeout);
        const q = searchInput.value.trim();
        if (q.length < 2) {
            searchResults.innerHTML = "";
            return;
        }
        searchSpinner.classList.remove("hidden");
        searchTimeout = setTimeout(() => doSearch(q), 350);
    });

    async function doSearch(q) {
        try {
            const resp = await fetch(
                `/api/search?type=${encodeURIComponent(currentType)}&q=${encodeURIComponent(q)}`
            );
            const data = await resp.json();
            renderResults(data.results || []);
        } catch (err) {
            console.error("Search error:", err);
            searchResults.innerHTML =
                '<div class="help-text">Search failed. Check connection.</div>';
        } finally {
            searchSpinner.classList.add("hidden");
        }
    }

    function renderResults(results) {
        const q = searchInput.value.trim();
        if (results.length === 0) {
            searchResults.innerHTML = `
                <div class="help-text">No results found in ProShop.</div>
                ${q.length >= 2 ? `
                <div class="result-item manual-entry" data-id="${esc(q)}" data-name="" data-url="">
                    <span class="result-id">Use "${esc(q)}"</span>
                    <span class="result-name">Not found in ProShop — tap to use anyway</span>
                </div>` : ''}
            `;
            bindResultClicks();
            return;
        }
        searchResults.innerHTML = results
            .map(
                (r) => `
            <div class="result-item" data-id="${esc(r.id)}"
                 data-name="${esc(r.name)}" data-url="${esc(r.proshop_url || "")}">
                <span class="result-id">${esc(r.id)}</span>
                <span class="result-name">${esc(r.name)}</span>
                ${r.detail ? `<span class="result-detail">${esc(r.detail)}</span>` : ""}
            </div>
        `
            )
            .join("");

        bindResultClicks();
    }

    function bindResultClicks() {
        searchResults.querySelectorAll(".result-item").forEach((el) => {
            el.addEventListener("click", () => {
                const entity = {
                    id: el.dataset.id,
                    name: el.dataset.name,
                    proshop_url: el.dataset.url,
                };
                selectedEntity = entity;

                // Work orders and parts go to operation selection first
                if (currentType === "workorder" || currentType === "part") {
                    showOpsStep(entity);
                } else {
                    goToCapture(entity);
                }
            });
        });
    }

    // ── Step 2c: Operation selection (work orders only) ─────────────────

    async function showOpsStep(entity) {
        opsEntityId.textContent = entity.id;
        opsEntityName.textContent = entity.name || "";
        opsList.innerHTML = "";
        opsSpinner.classList.remove("hidden");
        showStep("ops");

        try {
            const param = currentType === "part"
                ? `part=${encodeURIComponent(entity.id)}`
                : `wo=${encodeURIComponent(entity.id)}`;
            const resp = await fetch(
                `/api/operations?${param}`
            );
            const data = await resp.json();
            renderOps(data.ops || []);
        } catch (err) {
            console.error("Ops fetch error:", err);
            opsList.innerHTML =
                '<div class="help-text">Failed to load operations.</div>';
        } finally {
            opsSpinner.classList.add("hidden");
        }
    }

    function renderOps(ops) {
        if (ops.length === 0) {
            opsList.innerHTML =
                '<div class="help-text">No operations found.</div>';
            return;
        }
        opsList.innerHTML = ops
            .map(
                (op) => `
            <div class="result-item op-item"
                 data-op="${esc(op.opNumber)}"
                 data-desc="${esc(op.description)}"
                 data-wc="${esc(op.workCenter)}">
                <span class="result-id">Op ${esc(op.opNumber)}</span>
                <span class="result-name">${esc(op.description) || "(no description)"}</span>
                ${op.workCenter ? `<span class="result-detail">${esc(op.workCenter)}</span>` : ""}
            </div>
        `
            )
            .join("");

        opsList.querySelectorAll(".op-item").forEach((el) => {
            el.addEventListener("click", () => {
                selectedOp = {
                    opNumber: el.dataset.op,
                    description: el.dataset.desc,
                    workCenter: el.dataset.wc,
                };
                goToCapture(selectedEntity);
            });
        });
    }

    // ── Proceed to photo capture ─────────────────────────────────────────

    // Map entity type → list of label_type strings the print bar should show
    const LABELS_FOR_TYPE = {
        workorder: ["material", "box"],
        tool: ["tool"],
        equipment: ["equipment"],
        cots: ["cots"],
    };

    function showPrintBarFor(type) {
        const bar = document.getElementById("print-label-bar");
        const labels = LABELS_FOR_TYPE[type] || [];
        if (!labels.length) {
            bar.classList.add("hidden");
            return;
        }
        bar.classList.remove("hidden");
        bar.querySelectorAll(".print-label-btn").forEach((btn) => {
            const show = labels.includes(btn.dataset.label);
            btn.classList.toggle("hidden", !show);
            btn.classList.remove("printed", "failed");
            btn.disabled = false;
            btn.textContent = btn.dataset.defaultLabel || btn.textContent;
            btn.dataset.defaultLabel = btn.dataset.defaultLabel || btn.textContent;
        });
    }

    function goToCapture(entity) {
        // Build display text
        let label = entity.id;
        if (selectedOp) {
            label += ` — Op ${selectedOp.opNumber}`;
            if (selectedOp.description) label += ` (${selectedOp.description})`;
        }
        entityInfoId.textContent = label;
        entityInfoName.textContent = entity.name || "";

        capturedFile = null;
        previewContainer.classList.add("hidden");
        uploadBtn.classList.add("hidden");
        uploadBtn.disabled = true;
        uploadBtn.textContent = "Upload Photo";
        photoCapture.value = "";
        photoNote.value = "";
        showPrintBarFor(currentType);
        showStep("capture");
    }

    // ── Print Label buttons ──────────────────────────────────────────────

    document.querySelectorAll(".print-label-btn").forEach((btn) => {
        btn.dataset.defaultLabel = btn.textContent;
        btn.addEventListener("click", () => printLabel(btn));
    });

    async function printLabel(btn) {
        if (!selectedEntity) return;
        const labelType = btn.dataset.label;

        let boxQty = "";
        if (labelType === "box") {
            boxQty = window.prompt("Enter Qty of Parts in Box");
            if (boxQty === null || boxQty.trim() === "") return;
            boxQty = boxQty.trim();
        }

        btn.disabled = true;
        btn.classList.remove("printed", "failed");
        btn.textContent = "Printing…";

        try {
            const resp = await fetch("/api/print-label", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    label_type: labelType,
                    entity_id: selectedEntity.id,
                    box_qty: boxQty,
                }),
            });
            const data = await resp.json();
            if (resp.ok && data.success) {
                btn.classList.add("printed");
                btn.textContent = "✓ Printed";
                showToast(`Printed ${data.label_name || labelType}`);
            } else {
                throw new Error(data.error || `HTTP ${resp.status}`);
            }
        } catch (err) {
            console.error("Print error:", err);
            btn.classList.add("failed");
            btn.textContent = "✗ Failed";
            showToast(err.message || "Print failed", true);
        } finally {
            setTimeout(() => {
                btn.disabled = false;
                btn.classList.remove("printed", "failed");
                btn.textContent = btn.dataset.defaultLabel;
            }, 3000);
        }
    }

    // ── Step 3: Photo capture ────────────────────────────────────────────

    photoCapture.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (!file) return;
        capturedFile = file;

        const reader = new FileReader();
        reader.onload = (ev) => {
            photoPreview.src = ev.target.result;
            previewContainer.classList.remove("hidden");
            uploadBtn.classList.remove("hidden");
            uploadBtn.disabled = false;
        };
        reader.readAsDataURL(file);
    });

    // ── Step 4: Upload ───────────────────────────────────────────────────

    uploadBtn.addEventListener("click", async () => {
        if (!capturedFile || !selectedEntity) return;

        uploadBtn.disabled = true;
        uploadBtn.textContent = "Uploading...";

        const formData = new FormData();
        formData.append("photo", capturedFile);
        formData.append("entity_type", currentType);
        formData.append("entity_id", selectedEntity.id);
        formData.append("entity_name", selectedEntity.name || "");
        formData.append("proshop_url", selectedEntity.proshop_url || "");
        formData.append("note", photoNote.value.trim());

        // Include operation info for work orders
        if (selectedOp) {
            formData.append("operation_number", selectedOp.opNumber);
            formData.append("operation_desc", selectedOp.description || "");
        }

        try {
            const resp = await fetch("/api/photos", {
                method: "POST",
                body: formData,
            });
            const data = await resp.json();

            if (resp.ok && data.success) {
                // Stay on the capture step with the same entity+op selected
                // so the operator can keep snapping photos of the same job.
                // The "Home" back button in the header is the escape hatch.
                capturedFile = null;
                photoCapture.value = "";
                photoNote.value = "";
                previewContainer.classList.add("hidden");
                photoPreview.src = "";
                uploadBtn.classList.add("hidden");
                uploadBtn.disabled = true;
                uploadBtn.textContent = "Upload Photo";
                const savedFor = currentType === "claude"
                    ? "Photo saved (Claude)"
                    : "Photo saved — tap Home when done";
                showToast(savedFor);
            } else {
                showToast(data.error || "Upload failed", true);
                uploadBtn.disabled = false;
                uploadBtn.textContent = "Upload Photo";
            }
        } catch (err) {
            console.error("Upload error:", err);
            showToast("Upload failed. Check connection.", true);
            uploadBtn.disabled = false;
            uploadBtn.textContent = "Upload Photo";
        }
    });

    // ── QR Scanning ──────────────────────────────────────────────────────

    async function decodeQR(file) {
        // Try native BarcodeDetector
        if (typeof BarcodeDetector !== "undefined") {
            try {
                const detector = new BarcodeDetector({ formats: ["qr_code"] });
                const bitmap = await createImageBitmap(file);
                const results = await detector.detect(bitmap);
                if (results.length > 0) return results[0].rawValue;
            } catch (e) {}
        }
        // Try jsQR
        if (typeof jsQR !== "undefined") {
            try {
                const bitmap = await createImageBitmap(file);
                var w = bitmap.width, h = bitmap.height;
                if (w > 1500 || h > 1500) {
                    var scale = 1500 / Math.max(w, h);
                    w = Math.round(w * scale);
                    h = Math.round(h * scale);
                }
                const canvas = document.createElement("canvas");
                canvas.width = w;
                canvas.height = h;
                const ctx = canvas.getContext("2d");
                ctx.drawImage(bitmap, 0, 0, w, h);
                const imgData = ctx.getImageData(0, 0, w, h);
                const code = jsQR(imgData.data, w, h);
                if (code && code.data) return code.data;
            } catch (e) {}
        }
        // Fallback: server-side decode
        try {
            const formData = new FormData();
            formData.append("photo", file);
            const resp = await fetch("/api/qr-decode", { method: "POST", body: formData });
            const data = await resp.json();
            if (data.found) return data.data;
        } catch (e) {}
        return null;
    }

    function handleQRResult(data) {
        const parsed = parseProShopUrl(data);
        if (parsed) {
            currentType = parsed.type;
            selectedEntity = { id: parsed.id, name: "", proshop_url: data };
            if (currentType === "workorder") {
                showOpsStep(selectedEntity);
            } else {
                goToCapture(selectedEntity);
            }
            showToast(`Found: ${TYPE_LABELS[parsed.type] || parsed.type} ${parsed.id}`);
            return true;
        }
        return false;
    }

    qrCapture.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        qrStatus.textContent = "Decoding QR code...";

        try {
            const data = await decodeQR(file);
            if (!data) {
                qrStatus.textContent = "No QR code found. Try again or use manual search.";
                return;
            }
            if (!handleQRResult(data)) {
                qrStatus.textContent = `QR says: "${data}" — not a recognized ProShop URL.`;
            }
        } catch (err) {
            console.error("QR decode error:", err);
            qrStatus.textContent = "Failed to decode image.";
        }
    });

    function parseProShopUrl(url) {
        const patterns = [
            { re: /proshop:\/\/wo\/([A-Za-z0-9_-]+)/, type: "workorder" },
            { re: /workorders?\/(?:\d{4}\/)?([A-Za-z0-9_-]+)/, type: "workorder" },
            { re: /tools?\/([A-Za-z0-9_-]+)/, type: "tool" },
            { re: /equipment\/[^\/]+\/([A-Za-z0-9_-]+)/, type: "equipment" },
            { re: /equipment\/([A-Za-z0-9_-]+)/, type: "equipment" },
            { re: /fixtures?\/([A-Za-z0-9_-]+)/, type: "fixture" },
            { re: /parts?\/[^\/]+\/([A-Za-z0-9_-]+)/, type: "part" },
            { re: /ots\/([^\/]+\/[A-Za-z0-9_-]+|[A-Za-z0-9_-]+)/, type: "cots" },
        ];
        for (const p of patterns) {
            const m = url.match(p.re);
            if (m) return { type: p.type, id: m[1] };
        }
        return null;
    }

    // ── Back buttons ─────────────────────────────────────────────────────

    document.querySelectorAll(".back-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            reset();
        });
    });

    // "Take Another Photo" button
    document.getElementById("btn-another").addEventListener("click", reset);

    // ── Toast ────────────────────────────────────────────────────────────

    function showToast(msg, isError) {
        const toast = document.getElementById("toast");
        toast.textContent = msg;
        toast.className = isError ? "toast error" : "toast";
        setTimeout(() => toast.classList.add("hidden"), 3000);
    }

    // ── Utility ──────────────────────────────────────────────────────────

    function esc(str) {
        const el = document.createElement("span");
        el.textContent = str || "";
        return el.innerHTML;
    }

    // ── Suggestions ─────────────────────────────────────────────────────

    document.getElementById("btn-submit-suggestion").addEventListener("click", async () => {
        const text = document.getElementById("suggestion-text").value.trim();
        if (!text) {
            showToast("Please type a suggestion", true);
            return;
        }
        try {
            const resp = await fetch("/api/suggest", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: text }),
            });
            if (resp.ok) {
                showToast("Suggestion saved — thank you!");
                showStep("type");
            } else {
                showToast("Failed to save suggestion", true);
            }
        } catch (err) {
            showToast("Failed to save suggestion", true);
        }
    });
})();
