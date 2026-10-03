// main.js — students will add JavaScript here as features are built

// Profile page: click a category row to lift and highlight it; click again to clear.
(function () {
    var rows = document.querySelectorAll(".profile-cat");
    if (!rows.length) return;

    function select(row) {
        var wasActive = row.classList.contains("is-active");
        rows.forEach(function (r) {
            r.classList.remove("is-active");
            r.setAttribute("aria-pressed", "false");
        });
        if (!wasActive) {
            row.classList.add("is-active");
            row.setAttribute("aria-pressed", "true");
        }
    }

    rows.forEach(function (row) {
        row.addEventListener("click", function () { select(row); });
        row.addEventListener("keydown", function (e) {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                select(row);
            }
        });
    });
})();
