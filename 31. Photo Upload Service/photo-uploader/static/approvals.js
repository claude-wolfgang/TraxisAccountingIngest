(function () {
    "use strict";

    function showToast(msg, isError) {
        const toast = document.getElementById("toast");
        if (!toast) return;
        toast.textContent = msg;
        toast.className = isError ? "toast error" : "toast";
        setTimeout(() => toast.classList.add("hidden"), 2500);
    }

    async function postAction(orderId, action, body) {
        const resp = await fetch(`/api/${action}/${orderId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body || {}),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
        return data;
    }

    function fadeRow(row) {
        row.style.transition = "opacity 0.4s";
        row.style.opacity = "0.3";
        setTimeout(() => row.remove(), 600);
    }

    document.querySelectorAll(".btn-approve[data-id]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const id = btn.dataset.id;
            btn.disabled = true;
            btn.textContent = "...";
            try {
                await postAction(id, "approve", { approver: "wolfgang" });
                showToast(`Order #${id} approved`);
                fadeRow(document.querySelector(`tr[data-order-id="${id}"]`));
            } catch (err) {
                showToast(err.message, true);
                btn.disabled = false;
                btn.textContent = "Approve";
            }
        });
    });

    document.querySelectorAll(".btn-reject[data-id]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const id = btn.dataset.id;
            const reason = window.prompt("Reason for rejection (optional)") || "";
            btn.disabled = true;
            btn.textContent = "...";
            try {
                await postAction(id, "reject", { approver: "wolfgang", reason });
                showToast(`Order #${id} rejected`);
                fadeRow(document.querySelector(`tr[data-order-id="${id}"]`));
            } catch (err) {
                showToast(err.message, true);
                btn.disabled = false;
                btn.textContent = "Reject";
            }
        });
    });

    const approveAllBtn = document.getElementById("btn-approve-all");
    if (approveAllBtn) {
        approveAllBtn.addEventListener("click", async () => {
            const rows = document.querySelectorAll(".approval-row");
            if (!rows.length) return;
            if (!window.confirm(`Approve all ${rows.length} pending orders?`)) return;
            approveAllBtn.disabled = true;
            approveAllBtn.textContent = "Approving...";
            let ok = 0, fail = 0;
            for (const row of rows) {
                const id = row.dataset.orderId;
                try {
                    await postAction(id, "approve", { approver: "wolfgang" });
                    fadeRow(row);
                    ok++;
                } catch (err) {
                    fail++;
                }
            }
            showToast(`${ok} approved${fail ? `, ${fail} failed` : ""}`, fail > 0);
            setTimeout(() => location.reload(), 800);
        });
    }
})();
